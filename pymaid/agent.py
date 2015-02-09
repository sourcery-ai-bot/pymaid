from pymaid.controller import Controller
from pymaid.parser import DEFAULT_PARSER


class ServiceAgent(object):

    __slots__ = ['stub', 'conn', 'controller', 'profiling', 'methods']

    def __init__(self, stub, conn=None, profiling=False):
        self.stub, self.conn, self.controller = stub, conn, Controller()
        self.profiling, self.methods = profiling, {}

    def close(self):
        self.stub, self.conn, self.controller = None, None, None
        self.methods.clear()

    def get_method(self, name):
        if name in self.methods:
            return self.methods[name]

        method_descriptor = self.stub.DESCRIPTOR.FindMethodByName(name)
        method, request_class = None, None
        if method_descriptor:
            request_class = self.stub.GetRequestClass(method_descriptor)
            method = getattr(self.stub, name)
            if self.profiling:
                from pymaid.utils.profiler import profiling
                method = profiling(name)(method)
            self.methods[name] = method, request_class
        return method, request_class

    def print_summary(slef):
        from pymaid.utils.profiler import default
        default.print_summary()

    def __dir__(self):
        return dir(self.stub)

    def __getattr__(self, name):
        method, request_class = self.get_method(name)
        if not method:
            return object.__getattr__(self, name)

        def rpc(request=None, controller=None, callback=None, conn=None,
                broadcast=False, group=None, parser_type=DEFAULT_PARSER,
                **kwargs):
            if not controller:
                controller = self.controller

            controller.set_broadcast(broadcast)
            controller.set_group(group)
            controller.set_parser_type(parser_type)
            if not (broadcast or group):
                assert conn or self.conn
                controller.set_conn(conn or self.conn)
            else:
                controller.is_notification = True

            if not request:
                assert request_class
                request = request_class(**kwargs)

            return method(controller, request, callback)
        return rpc
