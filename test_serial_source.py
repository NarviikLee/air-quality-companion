import unittest
from types import SimpleNamespace
from unittest.mock import patch
import serial
import sensor_data as config
from serial_source import SerialSensorSource

RAW = dict(pm1=8, pm25=12, pm10=18, bioaerosol=16,
           temperature=24.5, humidity=46, voc=22, nox=14)


class Port:
    def __init__(self, name):
        self.port, self.closed = name, False

    def close(self):
        self.closed = True


class SerialSourceTests(unittest.TestCase):
    def setUp(self):
        mode_patch = patch.object(config, 'OS_MODE', 'windows')
        mode_patch.start()
        self.addCleanup(mode_patch.stop)
        self.names = []
        self.opened = []
        self.bad = set()
        self.busy = set()
        self.settings = []
        def open_port(**kwargs):
            self.settings.append(kwargs)
            if kwargs['port'] in self.busy:
                raise serial.SerialException('Access denied')
            port = Port(kwargs['port'])
            self.opened.append(port)
            return port
        def read(port):
            if port.port not in self.names:
                raise serial.SerialException('Device disconnected')
            if port.port in self.bad:
                raise ValueError('CRC mismatch')
            return RAW.copy()
        self.source = SerialSensorSource(
            lambda: [SimpleNamespace(device=n) for n in self.names], open_port, read)
        self.addCleanup(self.source.close)

    def test_no_port_then_plug_in(self):
        with self.assertRaises(config.PortUnavailableError):
            self.source.read()
        self.names = ['COM2']
        data, main = self.source.read()
        self.assertEqual(data['Temperature'], 24.5)
        self.assertIsNone(main)
        self.assertGreater(self.settings[0]['timeout'], 0)
        self.assertGreater(self.settings[0]['write_timeout'], 0)
        self.source.read()
        self.assertEqual(len(self.opened), 1)

    def test_port_list_logged_only_when_changed(self):
        with patch('serial_source.LOG') as log:
            self.source.discover()
            self.source.discover()
            self.assertEqual(log.info.call_count, 1)
            self.names = ['COM2']
            self.source.discover()
            self.source.discover()
            self.assertEqual(log.info.call_count, 2)
            self.names = []
            self.source.discover()
            self.assertEqual(log.info.call_count, 3)

    def test_failed_probes_keep_running_without_info_spam(self):
        self.names = ['COM2']
        self.bad = {'COM2'}
        with patch('serial_source.LOG') as log:
            for _ in range(20):
                with self.assertRaises(config.DataUnavailableError):
                    self.source.read()
            self.assertEqual(len(self.opened), 20)
            self.assertEqual(log.info.call_count, 1)
            self.assertEqual(log.debug.call_count, 20)

    def test_three_ports_bad_busy_good(self):
        self.names = ['COM1', 'COM2', 'COM3']
        self.bad = {'COM1'}
        self.busy = {'COM2'}
        for _ in range(2):
            with self.assertRaises(config.DataUnavailableError):
                self.source.read()
        self.source.read()
        self.assertEqual(self.source.connection.port, 'COM3')
        self.assertTrue(self.opened[0].closed)

    def test_all_invalid_candidates_cycle(self):
        self.names = ['COM1', 'COM2', 'COM3']
        self.bad = set(self.names)
        for _ in range(4):
            with self.assertRaises(config.DataUnavailableError):
                self.source.read()
        self.assertEqual([p.port for p in self.opened], ['COM1', 'COM2', 'COM3', 'COM1'])
        self.assertTrue(all(p.closed for p in self.opened))

    def test_unplug_and_replug_with_new_name(self):
        self.names = ['COM1']
        self.source.read()
        self.names = []
        with self.assertRaises(config.PortUnavailableError):
            self.source.read()
        self.assertTrue(self.opened[0].closed)
        self.names = ['COM4']
        self.source.read()
        self.assertEqual(self.source.connection.port, 'COM4')

    def test_persistent_crc_failure_moves_to_next_port(self):
        self.names = ['COM1', 'COM2']
        self.source.read()
        self.bad = {'COM1'}
        for _ in range(config.PORT_FAILURE_LIMIT):
            with self.assertRaises(config.DataUnavailableError):
                self.source.read()
        self.assertTrue(self.opened[0].closed)
        self.source.read()
        self.assertEqual(self.source.connection.port, 'COM2')

    def test_intermittent_failure_keeps_connection(self):
        self.names = ['COM1']
        self.source.read()
        self.bad = {'COM1'}
        with self.assertRaises(config.DataUnavailableError):
            self.source.read()
        self.bad.clear()
        self.source.read()
        self.assertEqual(len(self.opened), 1)
        self.assertEqual(self.source.failures, 0)

    def test_last_success_preferred_on_new_scan(self):
        self.names = ['COM2']
        self.source.read()
        self.source.close()
        self.names = ['COM1', 'COM2']
        self.source.read()
        self.assertEqual(self.source.connection.port, 'COM2')

    def test_connected_reads_do_not_enumerate_ports(self):
        self.names = ['COM1']
        self.source.read()
        self.source.ports = lambda: (_ for _ in ()).throw(AssertionError('Unexpected scan'))
        self.source.read()

    def test_invalid_field_in_valid_response_keeps_port(self):
        self.names = ['COM1']
        self.source.reader = lambda port: dict(RAW, voc=None)
        values, _ = self.source.read()
        self.assertIsNone(values['VOC'])
        self.assertEqual(values['PM2.5'], 12)
        self.assertFalse(self.source.connection.closed)

    def test_protocol_exceptions_are_whole_response_failures(self):
        from sensor_protocol import CRCError, FrameError
        self.names = ['COM1']
        for error in (CRCError, FrameError):
            self.source.reader = lambda port: (_ for _ in ()).throw(error('invalid frame'))
            with self.assertRaises(config.DataUnavailableError):
                self.source.read()
            self.assertIsNone(self.source.connection)
    def test_checking_notification_only_after_discovery(self):
        from threading import Event
        notifications = []
        self.source.configure_worker(Event(), lambda: notifications.append(True))
        with self.assertRaises(config.PortUnavailableError):
            self.source.read()
        self.assertEqual(notifications, [])
        self.names = ['COM1']
        self.source.read()
        self.assertEqual(notifications, [True])

    def test_linux_usb_reconnect_and_candidate_validation(self):
        self.source.os_mode = 'linux'
        self.names = ['COM1', '/dev/ttyUSB0', '/dev/ttyUSB1']
        self.bad = {'/dev/ttyUSB0'}
        with self.assertRaises(config.DataUnavailableError):
            self.source.read()
        self.source.read()
        self.assertEqual(self.source.connection.port, '/dev/ttyUSB1')
        self.names = []
        with self.assertRaises(config.PortUnavailableError):
            self.source.read()
        self.names = ['/dev/ttyACM0']
        self.source.read()
        self.assertEqual(self.source.connection.port, '/dev/ttyACM0')


if __name__ == '__main__':
    unittest.main()
