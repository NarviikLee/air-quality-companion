"""Port discovery and reconnect, called only by SensorWorker.

One candidate per read call; the UI schedules the next attempt.
"""
import logging
from sensor_status import validate_sensor_value
import serial
from serial.tools.list_ports import comports
import sensor_data as config
from sensor_protocol import read_sensor_data
from port_discovery import discover_ports, resolve_os_mode

LOG = logging.getLogger(__name__)
KEYS = {'PM1.0': 'pm1', 'PM2.5': 'pm25', 'PM10': 'pm10',
        'Bio': 'bioaerosol', 'Temperature': 'temperature',
        'Humidity': 'humidity', 'VOC': 'voc', 'NOx': 'nox'}


class SerialSensorSource:
    def __init__(self, ports=comports, opener=serial.Serial, reader=read_sensor_data):
        if (config.SERIAL_TIMEOUT_SECONDS <= 0 or config.SERIAL_WRITE_TIMEOUT_SECONDS <= 0
                or config.PORT_FAILURE_LIMIT < 1):
            raise ValueError('Timeouts must be positive and failure limit at least one')
        self.ports, self.opener, self.reader = ports, opener, reader
        self.os_mode = resolve_os_mode(config.OS_MODE)
        LOG.info('Serial port discovery mode: %s', self.os_mode)
        self.connection = None
        self.last_success = config.PREFERRED_PORT
        self.attempted = set()
        self.failures = 0
        self.cancel_event = None
        self.on_checking = lambda: None
        self._last_available = None

    def discover(self):
        available = discover_ports(self.ports, self.os_mode)
        current = tuple(available)
        if current != self._last_available:
            LOG.info('Serial port candidates: %s', ', '.join(available) or '(none)')
            self._last_available = current
        return available

    def configure_worker(self, cancel_event, on_checking):
        self.cancel_event = cancel_event
        self.on_checking = on_checking

    def close(self):
        connection, self.connection = self.connection, None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                LOG.exception('Failed to close serial port')

    def read(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise config.DataUnavailableError('Acquisition cancelled')
        probing = self.connection is None
        if probing:
            available = self.discover()
            if not available:
                self.attempted.clear()
                raise config.PortUnavailableError('No serial ports found')
            self.attempted.intersection_update(available)
            self.on_checking()
            candidates = [p for p in available if p not in self.attempted]
            if not candidates:
                self.attempted.clear()
                candidates = available
            candidates.sort(key=lambda p: p != self.last_success)
            name = candidates[0]
            self.attempted.add(name)
            LOG.debug('Checking serial port %s', name)
            try:
                self.connection = self.opener(port=name,
                    baudrate=config.SERIAL_BAUDRATE, bytesize=config.SERIAL_BYTESIZE,
                    parity=config.SERIAL_PARITY, stopbits=config.SERIAL_STOPBITS,
                    timeout=config.SERIAL_TIMEOUT_SECONDS,
                    write_timeout=config.SERIAL_WRITE_TIMEOUT_SECONDS)
                self.failures = 0
            except (OSError, ValueError) as error:
                raise config.DataUnavailableError(f'{name}: open failed: {error}') from error
        name = self.connection.port
        try:
            if self.reader is read_sensor_data:
                raw = self.reader(self.connection, cancel_event=self.cancel_event)
            else:
                raw = self.reader(self.connection)
            # reader must return only after whole-frame validation succeeds.
            values = {s.name: validate_sensor_value(s.name, raw[KEYS[s.name]])
                      for s in config.SENSORS}
        except Exception as error:
            self.failures += 1
            if probing or isinstance(error, OSError) or self.failures >= config.PORT_FAILURE_LIMIT:
                self.close()
                if not probing:
                    self.attempted = {name}
            # Re-enumerate after a failure to distinguish unplug from bad data.
            if not self.discover():
                self.close()
                raise config.PortUnavailableError('All serial ports disconnected') from error
            raise config.DataUnavailableError(f'{name}: {type(error).__name__}: {error}') from error
        self.failures = 0
        if probing:
            LOG.info('Sensor verified on %s', name)
        self.last_success = name
        self.attempted.clear()
        # Representative sensor is undecided: never fabricate an AQI for live data.
        return values, None
