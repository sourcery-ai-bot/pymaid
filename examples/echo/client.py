from __future__ import print_function
import re
from argparse import ArgumentParser

from gevent.pool import Pool

from pymaid.channel import ClientChannel
from pymaid.pb import PBHandler, ServiceStub
from pymaid.utils import greenlet_pool

from echo_pb2 import EchoService_Stub


message = 'a' * 8000


def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        '-c', dest='concurrency', type=int, default=100, help='concurrency'
    )
    parser.add_argument(
        '-r', dest='request', type=int, default=100, help='request per client'
    )
    parser.add_argument(
        '--address', type=str, default='/tmp/pymaid_echo.sock',
        help='connect address'
    )

    args = parser.parse_args()
    if re.search(r':\d+$', args.address):
        address, port = args.address.split(':')
        args.address = (address, int(port))
    print(args)
    return args


def wrapper(pid, address, count, message=message):
    conn = channel.connect(address)
    for x in range(count):
        response = service.echo(request, conn=conn)
        assert response.message == message, len(response.message)
    conn.close()


channel = ClientChannel(PBHandler())
service = ServiceStub(EchoService_Stub(None))
method = service.stub.DESCRIPTOR.FindMethodByName('echo')
request_class = service.stub.GetRequestClass(method)
request = request_class(message=message)


def main(args):
    pool = Pool()
    # pool.spawn(wrapper, 111111, 10000)
    for x in range(args.concurrency):
        pool.spawn(wrapper, x, args.address, args.request)

    try:
        pool.join()
    except:
        import traceback
        traceback.print_exc()
        print(pool.size, len(pool.greenlets))
        print(len(channel.connections))
        print(greenlet_pool.size, len(greenlet_pool.greenlets))


if __name__ == "__main__":
    args = parse_args()
    main(args)
