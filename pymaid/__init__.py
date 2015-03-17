from __future__ import absolute_import
__all__ = [
    'ServiceAgent', 'Channel', 'Controller', 'Connection',
    'Error', 'Warning', 'parser', 'logger', 'pool', 'serve_forever'
]


import sys
import six

__version__ = '0.2.9'
VERSION = tuple(map(int, __version__.split('.')))


platform = sys.platform
if 'linux' in platform or 'darwin' in platform:
    import os
    if 'GEVENT_RESOLVER' not in os.environ:
        os.environ['GEVENT_RESOLVER'] = 'ares'
        import gevent
        six.moves.reload_module(gevent)
    else:
        gevent_resolver = os.environ['GEVENT_RESOLVER']
        if 'ares' not in gevent_resolver:
            sys.stdout.write(
                'ares-resolver is better, just `export GEVENT_RESOLVER=ares`\n'
            )
    if os.environ.get('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION') != 'cpp':
        sys.stdout.write(
            'C++ implementation protocol buffer has overall performance, see'
            '`https://github.com/google/protobuf/blob/master/python/README.txt#L84-L105`\n'
        )
    if os.environ.get('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION_VERSION') != '2':
        sys.stdout.write(
            'pb>=2.6 new C++ implementation also require to '
            '`export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION_VERSION=2`\n'
        )


from pymaid.agent import ServiceAgent
from pymaid.channel import Channel
from pymaid.controller import Controller
from pymaid.connection import Connection
from pymaid import parser
from pymaid.error import Error, Warning
from pymaid.utils import logger, pool


from gevent import wait
def serve_forever():
    wait()
