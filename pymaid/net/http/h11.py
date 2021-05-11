from io import BytesIO
from typing import List, Tuple

import httptools

from multidict import CIMultiDict
from pymaid.conf import settings
from pymaid.net.utils.uri import parse_uri


CRITICAL_ERROR_TEXT = '''HTTP/1.0 500 INTERNAL SERVER ERROR
Server: pymaid
X-Powered-By: pymaid
X-HTTP-Backend: httptools
Content-Type: text/html; charset=utf-8
Content-Length: 127

<!DOCTYPE HTML PUBLIC '-//W3C//DTD HTML 3.2 Final//EN'>
<title>Internal Server Error</title>
<h1>Internal Server Error</h1>
'''.replace('\n', '\r\n')

HTTP_SWITCHING_PROTOCOLS = '''HTTP/1.1 101 SWITCHING PROTOCOLS
Connection: Upgrade
Upgrade: h2c
Server: pymaid
X-Powered-By: pymaid
X-HTTP-Backend: httptools
Content-Length: 0

'''.replace('\n', '\r\n')

HTTP_TOO_BIG = '''HTTP/1.1 413 PAYLOAD TOO LARGE
Server: pymaid
X-Powered-By: pymaid
X-HTTP-Backend: httptools
Content-Length: 0

'''.replace('\n', '\r\n')

HTTP_INVALID_COMPRESSION = '''HTTP/1.1 400 BAD REQUEST
Server: pymaid
X-Powered-By: pymaid
X-HTTP-Backend: httptools
Content-Length: 25

Invalid compressed data
'''.replace('\n', '\r\n')


class Http:

    HEADER_SINGLETON = frozenset(
        [
            'Authorization',
            'Content-Type',
            'Content-Disposition',
            'Content-Length',
            'From',
            'Host',
            'If-Modified_Since',
            'If-Unmodified_Since',
            'Location'
            'Max-Forwards',
            'Proxy-Authorization',
            'Referer',
            'User-Agent',
        ]
    )

    HEADER_MUST_HAVE_VALUE = frozenset(['Location'])

    HEADER_MULTIPLE_VALUE_SPECIAL_CASE = frozenset(
        ['Proxy-Authenticate', 'Set-Cookie', 'WWW-Authenticate']
    )

    def __init__(self):
        self.headers = CIMultiDict()
        self.body = BytesIO()

    def append_header(self, name, value):
        '''Add header.

        When handling multiple values for one header, follow the rule metioned
        in `Mozilla implementation`_.

        .. _Mozilla implementation: https://github.com/bnoordhuis/mozilla-\
            central/blob/master/netwerk/protocol/http/nsHttpHeaderArray.h#L185
        '''
        assert name and value, f'empty header: name={name} or value={value}'
        self.headers.extend([(name, value)])

    # def validate_headers(self):
    #     # called when all headers received
    #     pass

    def extend_body(self, body: bytes):
        self.body.write(body)
        if self.body.tell() >= settings.pymaid.MAX_BODY_SIZE:
            raise


class HttpRequest(Http):

    def __init__(self):
        super().__init__()
        self.uri = ''
        self.method = ''
        self.http_version = ''
        self.should_upgrade = False
        self.should_keep_alive = False


class HttpResponse(Http):

    def __init__(self):
        super().__init__()
        self.status = ''
        self.status_code = 0


class Parser:

    '''
    httptools callbacks
    - on_message_begin()
    - on_url(url: bytes)
    - on_header(name: bytes, value: bytes)
    - on_headers_complete()
    - on_body(body: bytes)
    - on_message_complete()
    - on_chunk_header()
    - on_chunk_complete()
    - on_status(status: bytes)

    def get_http_version(self) -> str:
        """Return an HTTP protocol version."""

    def should_keep_alive(self) -> bool:
        """Return ``True`` if keep-alive mode is preferred."""

    def should_upgrade(self) -> bool:
        """Return ``True`` if the parsed request is a valid Upgrade request.
        The method exposes a flag set just before on_headers_complete.
        Calling this method earlier will only yield `False`.
        """

    def get_method(self) -> bytes:
        """Return HTTP request method (GET, HEAD, etc)"""

    def get_status_code(self) -> int:
        """Return the status code of the HTTP response"""

    '''

    def __init__(self):
        self.instance = None
        self.queue = []
        self.parser = self.ParserClass(self)

    def handle_parser_exception(self, exc):
        '''Default exception handler.

        Raise exc again.
        '''
        raise exc

    def on_message_begin(self):
        '''Called when a message begins. '''
        assert not self.instance
        self.instance = self.ProtocolClass()

    def on_header(self, name: bytes, value: bytes):
        '''Called when a header has been received.

        :param bytes name: The name of the header.
        :param bytes value: The value of the header.
        '''
        self.instance.append_header(name.decode(), value.decode())

    def on_headers_complete(self):
        '''Called when the headers have been completely sent.'''
        # self.instance.validate_headers()
        self.instance.http_version = self.parser.get_http_version()

    def on_body(self, body: bytes):
        '''Called when part of the body has been received.

        :param bytes body: The body bytes.
        '''
        self.instance.extend_body(body)

    def on_message_complete(self):
        '''Put the complete request/response instance into queue.

        Reset instance for the next parse round.
        '''
        self.queue.append(self.instance)
        self.instance = None


class RequestParser(Parser):

    ParserClass = httptools.HttpRequestParser
    ProtocolClass = HttpRequest

    def feed_data(self, data: bytes) -> Tuple[int, List[HttpRequest]]:
        data = memoryview(data)
        # httptools will consume all data
        used = len(data)
        try:
            self.parser.feed_data(data)
        except httptools.HttpParserUpgrade as exc:
            # do nothing about HttpParserUpgrade
            # just return a complete instance for upper level to handle

            # the first args is the offset of used data
            used = exc.args[0]
        except httptools.HttpParserError as exc:
            raise exc
        data = self.queue[:]
        del self.queue[:]
        return used, data

    def on_url(self, url: bytes):
        self.instance.uri = parse_uri(url.decode('utf-8'))

    def on_headers_complete(self):
        super().on_headers_complete()
        instance = self.instance
        parser = self.parser

        instance.method = parser.get_method().decode('utf-8')
        instance.should_upgrade = parser.should_upgrade()
        instance.keep_alive = parser.should_keep_alive()


class ResponseParser(Parser):

    ParserClass = httptools.HttpResponseParser
    ProtocolClass = HttpResponse

    def feed_data(self, data: bytes) -> Tuple[int, List[HttpResponse]]:
        data = memoryview(data)
        # httptools will consume all data
        used = len(data)
        try:
            self.parser.feed_data(data)
        except httptools.HttpParserError as exc:
            raise exc
        data = self.queue[:]
        del self.queue[:]
        return used, data

    def on_status(self, status: bytes):
        self.instance.status = status.decode('utf-8')
        self.instance.status_code = self.parser.get_status_code()
