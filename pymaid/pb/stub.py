from gevent.event import AsyncResult

from pymaid.pb.pymaid_pb2 import Void, Controller


class ServiceStub(object):

    def __init__(self, stub, conn=None, connection_pool=None, timeout=30.0):
        self.stub, self.meta = stub, Controller()
        self.conn, self.connection_pool = conn, connection_pool
        self.timeout = timeout
        self._bind_stub()

    def _bind_stub(self):
        stub, rpc_stub = self.stub, self._build_rpc_stub
        for method in stub.DESCRIPTOR.methods:
            setattr(self, method.name, rpc_stub(
                method.full_name,
                stub.GetRequestClass(method),
                stub.GetResponseClass(method)
            ))

    def _build_rpc_stub(self, service_method, request_class, response_class):
        if not issubclass(response_class, Void):
            packet_type, require_response = Controller.REQUEST, True
        else:
            packet_type, require_response = Controller.NOTIFICATION, False
        StubManager.request_class[service_method] = response_class
        StubManager.response_class[service_method] = response_class

        def rpc(request=None, conn=None, connections=None, timeout=None,
                **kwargs):
            request = request or request_class(**kwargs)

            meta = self.meta
            meta.Clear()
            meta.service_method = service_method
            meta.packet_type = packet_type
            if connections:
                for conn in connections:
                    conn.send(conn.pack_meta(meta, request))
            else:
                conn = conn or self.conn or \
                    self.connection_pool.get_connection()
                assert conn, conn
                if require_response:
                    meta.transmission_id = conn.transmission_id
                conn.transmission_id += 1
                conn.send(conn.pack_meta(meta, request))

                if hasattr(conn, 'release'):
                    conn.release()
                if not require_response:
                    return

                async_result = AsyncResult()
                conn.transmissions[meta.transmission_id] = async_result
                return async_result.get(timeout=timeout or self.timeout)
        return rpc

    def close(self):
        self.stub = self.meta = None
        self.conn = self.connection_pool = None


class StubManager(object):

    request_class = {}
    response_class = {}

    def __init__(self, conn=None, connection_pool=None):
        self.conn = conn
        self.connection_pool = connection_pool
        self._stubs = {}

    def add_stub(self, name, stub):
        assert name not in self._stubs, (name, self._stubs.keys())
        self._stubs[name] = stub
        stub.conn = stub.conn or self.conn
        stub.connection_pool = stub.connection_pool or self.connection_pool
        stub.name = name
        setattr(self, name, stub)

    def remove_stub(self, name):
        assert name in self._stubs, (name, self._stubs.keys())
        stub = self._stubs.pop(name, None)
        delattr(self, name)
        stub.close()
