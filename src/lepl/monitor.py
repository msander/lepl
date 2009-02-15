
from lepl.support import LogMixin


class MonitorInterface(LogMixin):
    
    def __init__(self):
        super(MonitorInterface, self).__init__()
    
    def next_iteration(self, value, exception, stack):
        pass
    
    def before_next(self, generator):
        pass
    
    def after_next(self, value):
        pass
    
    def before_throw(self, generator, value):
        pass
    
    def after_throw(self, value):
        pass
    
    def before_send(self, generator, value):
        pass
    
    def after_send(self, value):
        pass
    
    def exception(self, value):
        pass
    
    def raise_(self, value):
        pass
    
    def yield_(self, value):
        pass
    
    def push(self, value):
        pass
    
    def pop(self, value):
        pass
    

class MultipleMonitors(MonitorInterface):
    
    def __init__(self):
        super(MonitorInterface, self).__init__(monitors=None)
        self._monitors = [] if monitors is None else monitors
        
    def append(self, monitor):
        self._monitors.append(monitor)
        
    def __len__(self):
        return len(self._monitors)
    
    def next_iteration(self, value, exception, stack):
        for monitor in self._monitors:
            monitor.next_iteration(value, exception, stack)
    
    def before_next(self, generator):
        for monitor in self._monitors:
            monitor.before_next(generator)
    
    def after_next(self, value):
        for monitor in self._monitors:
            monitor.after_next(value)
    
    def before_throw(self, generator, value):
        for monitor in self._monitors:
            monitor.before_throw(generator, value)
    
    def after_throw(self, value):
        for monitor in self._monitors:
            monitor.after_throw(value)
    
    def before_send(self, generator, value):
        for monitor in self._monitors:
            monitor.before_send(generator, value)
    
    def after_send(self, value):
        for monitor in self._monitors:
            monitor.after_send(value)
    
    def exception(self, value):
        for monitor in self._monitors:
            monitor.exception(value)
    
    def raise_(self, value):
        for monitor in self._monitors:
            monitor.raise_(value)
    
    def yield_(self, value):
        for monitor in self._monitors:
            monitor.yield_(value)
    
    def push(self, value):
        for monitor in self._monitors:
            monitor.push(value)
    
    def pop(self, value):
        for monitor in self._monitors:
            monitor.pop(value)