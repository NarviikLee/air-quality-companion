"""Bounded logging for consecutive identical errors; never throttles work."""
import time


class RepeatedErrorLog:
    def __init__(self, logger, interval=60, clock=time.monotonic):
        if interval <= 0:
            raise ValueError('Log interval must be positive')
        self.logger, self.interval, self.clock = logger, interval, clock
        self.message = None
        self.total = 0
        self.suppressed = 0
        self.last_logged = 0

    def failure(self, error):
        message = '{}: {}'.format(type(error).__name__, error)
        now = self.clock()
        if message != self.message:
            self.flush('error changed')
            self.message, self.total, self.suppressed = message, 1, 0
            self.last_logged = now
            self.logger.warning('Sensor read failed: %s', message)
            return
        self.total += 1
        self.suppressed += 1
        if now - self.last_logged >= self.interval:
            self.flush('still failing')
            self.last_logged = now

    def flush(self, reason):
        if self.suppressed:
            self.logger.warning('Sensor error summary (%s): %s; repeated=%d, total=%d',
                                reason, self.message, self.suppressed, self.total)
            self.suppressed = 0

    def recovered(self):
        if self.message is not None:
            self.logger.info('Sensor data recovered after %d failures (unlogged repeats=%d); last error: %s',
                             self.total, self.suppressed, self.message)
            self.message = None
            self.total = self.suppressed = 0
