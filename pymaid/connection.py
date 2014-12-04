__all__ = ['Connection']

import sys
import errno
import struct

from gevent import getcurrent
from gevent.hub import get_hub
from gevent.greenlet import Greenlet
from gevent.queue import Queue, Empty
from gevent import socket

from pymaid.controller import Controller
from pymaid.agent import ServiceAgent
from pymaid.apps.monitor import MonitorService_Stub
from pymaid.utils import logger_wrapper
from pymaid.error import HeartbeatTimeout


@logger_wrapper
class Connection(object):

    HEADER = '!I'
    HEADER_LENGTH = struct.calcsize(HEADER)
    MAX_PACKET_LENGTH = 8 * 1024

    LINGER_PACK = struct.pack('ii', 1, 0)
    CONN_ID = 1000000
    MAX_SEND = 10
    MAX_RECV = 10

    def __init__(self, sock, server_side):
        self.setsockopt(sock)
        self._socket = sock
        self.peername = sock.getpeername()
        self.sockname = sock.getsockname()
        self.server_side = server_side
        self.hub = get_hub()

        self.is_closed = False
        self._close_cb = None
        self._heartbeat_timer = None

        self.conn_id = self.__class__.CONN_ID
        self.__class__.CONN_ID += 1
        if self.__class__.CONN_ID >= 10000000:
            self.__class__.CONN_ID = 1000000

        self._send_queue = Queue()
        self._recv_queue = Queue()
        self.controller = Controller()
        self.controller.conn = self

        self._read_event = self.hub.loop.io(sock.fileno(), 1)
        self._read_event.start(self._recv_loop)

        self._write_event = self.hub.loop.io(sock.fileno(), 2)
        self._write_event.start(self._send_loop)

    def setsockopt(self, sock):
        sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, self.LINGER_PACK)

    def setup_server_heartbeat(self, interval, max_timeout_count):
        assert interval > 0
        assert max_timeout_count >= 1

        self._heartbeat_interval = interval
        self._heartbeat_timeout_counter = 0
        self._max_heartbeat_timeout_count = max_timeout_count

        self._heartbeat_timeout_cb = self._heartbeat_timeout
        self._start_heartbeat_timer()

    def setup_client_heartbeat(self, channel):
        self._monitor_agent = ServiceAgent(MonitorService_Stub(channel), self)
        resp = self._monitor_agent.get_heartbeat_info()

        if not resp.need_heartbeat:
            return
        self._heartbeat_interval = resp.heartbeat_interval

        self._heartbeat_timeout_cb = self._send_heartbeat
        self._start_heartbeat_timer()

    def clear_heartbeat_counter(self):
        self._heartbeat_timeout_counter = 0
        self._start_heartbeat_timer()

    def _start_heartbeat_timer(self):
        if self._heartbeat_timer is not None:
            self._heartbeat_timer.stop()
        self._heartbeat_timer = self.hub.loop.timer(self._heartbeat_interval)
        self._heartbeat_timer.start(self._heartbeat_timeout_cb)

    def _heartbeat_timeout(self):
        self._heartbeat_timeout_counter += 1
        if self._heartbeat_timeout_counter >= self._max_heartbeat_timeout_count:
            self.close(HeartbeatTimeout(host=self.sockname, peer=self.peername))
        else:
            self._start_heartbeat_timer()

    def _send_heartbeat(self):
        # TODO: add send heartbeat
        self._monitor_agent.notify_heartbeat()
        self._start_heartbeat_timer()

    def send(self, packet_buff):
        assert packet_buff
        self._send_queue.put(packet_buff.meta_data.SerializeToString())

    def recv(self, timeout=None):
        packet_buffer = self._recv_queue.get(timeout=timeout)
        if not packet_buffer:
            return
        controller = self.controller
        controller.Reset()
        controller.meta_data.ParseFromString(packet_buffer)
        return controller

    def close(self, reason=None, reset=False):
        if self.is_closed:
            return
        self.is_closed = True

        self.controller.conn = None
        self.controller = None
        if isinstance(reason, Greenlet):
            reason = reason.exception
        #print 'connection close', reason

        self.logger.error(
            '[host|%s][peer|%s] closed with reason: %s',
            self.sockname, self.peername, reason
        )

        if self._heartbeat_timer is not None:
            self._heartbeat_timer.stop()

        if not reset:
            self._send_queue.queue.clear()
            self._send_queue.put('')
            self._send_loop()
        self._read_event.stop()
        self._write_event.stop()
        self._socket.close()

        if self._close_cb:
            self._close_cb(self, reason)

    def set_close_cb(self, close_cb):
        assert self._close_cb is None
        assert callable(close_cb)
        self._close_cb = close_cb

    def _send_loop(self):
        get_packet, sendall = self._send_queue.get_nowait, self._socket.sendall
        pack = struct.pack
        if getcurrent() == self.hub:
            self._socket.setblocking(0)
        try:
            for _ in xrange(self.MAX_SEND):
                packet_buffer = get_packet()
                if packet_buffer is None:
                    break

                header_buffer = pack(self.HEADER, len(packet_buffer))
                # see pydoc of socket.sendall
                sendall(header_buffer+packet_buffer)
        except Empty:
            pass
        except socket.error as ex:
            self.close(ex)
        if getcurrent() == self.hub:
            self._socket.setblocking(1)

    def _recv_n(self, nbytes):
        recv, buffers, length = self._socket.recv, [], 0
        if getcurrent() == self.hub:
            self._socket.setblocking(0)
        try:
            while length < nbytes:
                t = recv(nbytes - length)
                if not t:
                    ret = None
                    break
                buffers.append(t)
                length += len(t)
        except socket.error as ex:
            if ex.args[0] == socket.EWOULDBLOCK:
                ret = 0
            else:
                ret = ex
        else:
            ret = ''.join(buffers)
        if getcurrent() == self.hub:
            self._socket.setblocking(1)
        return ret

    def _recv_loop(self):
        recv_n, unpack = self._recv_n, struct.unpack
        recv_packet = self._recv_queue.put
        HEADER, HEADER_LENGTH = self.HEADER, self.HEADER_LENGTH
        MAX_PACKET_LENGTH = self.MAX_PACKET_LENGTH
        for _ in xrange(self.MAX_RECV):
            header = recv_n(HEADER_LENGTH)
            if header == 0:
                break
            if header is None or header == '':
                self.close('has received EOF', reset=True)
                break
            if not isinstance(header, str):
                self.close(header)
                break

            packet_length = unpack(HEADER, header)[0]
            if packet_length >= MAX_PACKET_LENGTH:
                self.close('recv invalid payload [length|%d]' % packet_length)

            packet_buffer = recv_n(packet_length)
            recv_packet(packet_buffer)
