"""Single-owner acquisition worker. Sources must use bounded read/write timeouts."""
import logging
import math
import time
from sensor_status import validate_sensor_value
from threading import Event

from qt_compat import QObject, QThread, Signal, Slot
from sensor_data import create_sensor_source, PortUnavailableError, SENSORS
from repeated_error_log import RepeatedErrorLog

logger = logging.getLogger(__name__)


class SensorSnapshot(dict):
    """Existing dict signal contract plus a monotonic acquisition timestamp."""
    def __init__(self, values, timestamp):
        super().__init__(values)
        self.timestamp = timestamp


class SensorWorker(QObject):
    received = Signal(object, object)
    failed = Signal(str, str)
    checking = Signal()

    def __init__(self, source_factory=create_sensor_source):
        super().__init__()
        self.source_factory = source_factory
        self.source = None
        self.cancel_event = Event()
        self.error_log = RepeatedErrorLog(logger)

    @Slot()
    def read(self):
        if QThread.currentThread().isInterruptionRequested():
            return
        try:
            # Construct, access and close the source only in this thread.
            if self.source is None:
                self.source = self.source_factory()
                configure = getattr(self.source, 'configure_worker', None)
                if configure is not None:
                    configure(self.cancel_event, self.checking.emit)
            values, main_value = self.source.read()
            timestamp = time.monotonic()
            snapshot = SensorSnapshot({spec.name: validate_sensor_value(spec.name, values[spec.name])
                                       for spec in SENSORS}, timestamp)
            main_value = float(main_value) if main_value is not None else None
            if main_value is not None and not math.isfinite(main_value):
                raise ValueError('Non-finite sensor value')
        except Exception as error:
            if not QThread.currentThread().isInterruptionRequested():
                self.error_log.failure(error)
                self.failed.emit('no_port' if isinstance(error, PortUnavailableError)
                                 else 'waiting', f'{type(error).__name__}: {error}')
        else:
            if not QThread.currentThread().isInterruptionRequested():
                self.error_log.recovered()
                self.received.emit(snapshot, main_value)

    @Slot()
    def stop(self):
        try:
            self.error_log.flush('worker stopping')
            if self.source is not None:
                close = getattr(self.source, 'close', None)
                if close is not None:
                    close()
        except Exception:
            logger.exception('Sensor source close failed')
        finally:
            self.source = None
            QThread.currentThread().quit()
