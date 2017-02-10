import logging
import logging.config
from logging import LogRecord

from time import time
from functools import wraps
from types import MethodType
from sys import _getframe as getframe

from google.protobuf.service import Service

from pymaid.error import Warning

__all__ = [
    'create_project_logger', 'logger_wrapper', 'trace_service', 'trace_method',
    'trace_stub'
]

levelnames = logging._levelNames

root_logger = logging.getLogger('root')
root_logger.wrappers = []
pymaid_logger = logging.getLogger('pymaid')
pymaid_logger.wrappers = []
project_logger = None


def create_project_logger(name):
    global project_logger
    assert not project_logger
    project_logger = logging.getLogger(name)
    for cls in root_logger.wrappers:
        cls.logger = project_logger.getChild(cls.__name__)
    return project_logger


def pymaid_logger_wrapper(name=''):

    def _(cls):
        cls.logger = pymaid_logger.getChild(name)
        pymaid_logger.wrappers.append(cls)
        return cls

    if isinstance(name, type):
        cls, name = name, name.__name__
        return _(cls)
    else:
        return _


def logger_wrapper(name=''):

    def _(cls):
        cls.logger = get_logger(name)
        if cls.logger.parent is root_logger:
            root_logger.wrappers.append(cls)
        return cls

    if isinstance(name, type):
        cls, name = name, name.__name__
        return _(cls)
    else:
        return _


def get_logger(name):
    if project_logger:
        logger = project_logger.getChild(name)
    else:
        logger = root_logger.getChild(name)
    return logger


def update_record(record, level, msg, *args):
    record.levelno = level
    record.levelname = levelnames[level]
    record.msg = msg
    record.args = args
    ct = time()
    record.created = ct
    record.msecs = (ct - int(ct)) * 1000


def trace_service(level=logging.INFO, debug_info_func=None):
    def wrapper(cls):
        assert level in levelnames, level
        for method in cls.DESCRIPTOR.methods:
            name = method.name
            setattr(cls, name,
                    trace_method(level, debug_info_func)(getattr(cls, name)))
        return cls
    if isinstance(level, str):
        level = levelnames[level]
        return wrapper
    elif isinstance(level, int):
        return wrapper
    else:
        assert issubclass(level, Service), level
        cls, level, debug_info_func = level, 'INFO', None
        return wrapper(cls)


def trace_method(level=logging.INFO, debug_info_func=None):
    def wrapper(func):
        assert level in levelnames, level
        co = func.func_code
        full_name = co.co_name
        if isinstance(func, MethodType):
            full_name = '%s.%s' % (func.im_class.DESCRIPTOR.name, full_name)

        # name, level, fn, lno, msg, args, exc_info, func
        record = logging.LogRecord(
            '', level, co.co_filename, co.co_firstlineno, '', (), None,
            full_name
        )

        @wraps(func)
        def _(self, controller, request, done):
            assert isinstance(self, Service)

            if debug_info_func:
                debug_info = debug_info_func(controller)
            else:
                debug_info = '[conn|%d]' % controller.conn.connid
            logger = self.logger
            record.name = logger.name
            req = repr(str(request))
            update_record(
                record, level, '%s [Enter|%s] [req|%s]', debug_info, full_name,
                req
            )
            logger.handle(record)

            def done_wrapper(resp=None, **kwargs):
                update_record(
                    record, level, '%s [Leave|%s] [resp|%s]', debug_info,
                    full_name, kwargs or repr(str(resp))
                )
                logger.handle(record)
                done(resp, **kwargs)
            try:
                return func(self, controller, request, done_wrapper)
            except BaseException as ex:
                if isinstance(ex, Warning):
                    update_record(
                        record, logging.WARN,
                        '%s [Leave|%s][req|%s] [warning|%s]',
                        debug_info, full_name, req, ex
                    )
                else:
                    update_record(
                        record, logging.ERROR,
                        '%s [Leave|%s][req|%s] [exception|%s]',
                        debug_info, full_name, req, ex
                    )
                logger.handle(record)
                raise
        return _
    if isinstance(level, str):
        level = levelnames[level]
        return wrapper
    elif isinstance(level, int):
        return wrapper
    else:
        assert callable(level), level
        func, level, debug_info_func = level, logging.INFO, None
        return wrapper(func)


def trace_stub(level=logging.DEBUG, stub=None, stub_name='', request_name=''):
    def wrapper(rpc):
        from pymaid.conf import settings
        if not settings.DEBUG:
            return rpc
        assert level in levelnames, level

        @wraps(rpc)
        def _(request=None, *args, **kwargs):
            frame = getframe(1)
            stub.logger.handle(LogRecord(
                stub.logger.name, level, frame.f_code.co_filename,
                frame.f_lineno, '[stub|%s][request|%s][kwargs|%s]',
                (stub_name, request, kwargs), None, stub_name
            ))
            return rpc(request, *args, **kwargs)
        return _
    if isinstance(level, str):
        level = levelnames[level]
        return wrapper
    elif isinstance(level, int):
        return wrapper
    else:
        assert callable(level), level
        rpc, level = level, logging.DEBUG
        return wrapper(rpc)
