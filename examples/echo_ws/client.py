import pymaid
import pymaid.net.ws

from examples.template import get_client_parser, parse_args


class EchoStream(pymaid.net.ws.WebSocket):

    KEEP_OPEN_ON_EOF = False

    # the same as the init function below
    def init(self):
        self.data_size = 0

    def data_received(self, data):
        self.data_size += len(data)


async def wrapper(address, count, msize):
    stream = await pymaid.net.dial_stream(address, transport_class=EchoStream)

    msg = b'a' * msize
    for _ in range(count):
        await stream.write(msg)
    stream.shutdown()
    await stream.wait_closed()
    assert stream.data_size == msize * count, (stream.data_size, msize * count)


async def main():
    args = parse_args(get_client_parser())
    tasks = [
        pymaid.create_task(wrapper(args.address, args.request, args.msize))
        for _ in range(args.concurrency)
    ]

    # await pymaid.wait(tasks, timeout=args.timeout)
    await pymaid.gather(*tasks)


if __name__ == "__main__":
    pymaid.run(main())
