from gevent.pool import Pool

from pymaid.channel import Channel
from pymaid.connection import Connection
from pymaid.agent import ServiceAgent
from pymaid.utils import greenlet_pool

from echo_pb2 import EchoService_Stub

Connection.MAX_PACKET_LENGTH = 10000000


import string
message = string.letters + string.digits
message *= 23
message = 'a' * 1000000
def wrapper(pid, n, message=message):
    conn = channel.connect("127.0.0.1", 8888, ignore_heartbeat=True)
    method, request_class = service.get_method('echo')
    m = message + str(n)
    request = request_class(message=m)
    for x in xrange(n):
        response = service.echo(request, conn=conn)
        assert response.message == m, response.message
    conn.close()


channel = Channel()
service = ServiceAgent(EchoService_Stub(channel))
def main():
    import gc
    from collections import Counter
    gc.set_debug(gc.DEBUG_LEAK&gc.DEBUG_UNCOLLECTABLE)
    gc.enable()

    pool = Pool()
    #pool.spawn(wrapper, 111111, 10000)
    for x in xrange(1000):
        pool.spawn(wrapper, x, 1000)

    try:
        pool.join()
    except:
        print len(channel._outcome_connections)
        print len(channel._income_connections)
        print pool.size, len(pool.greenlets)
        print greenlet_pool.size, len(greenlet_pool.greenlets)

    else:
        assert len(channel._outcome_connections) == 0, channel._outcome_connections
        assert len(channel._income_connections) == 0, channel._income_connections
    objects = gc.get_objects()
    print Counter(map(type, objects))
    print
    service.print_summary()

if __name__ == "__main__":
    main()
