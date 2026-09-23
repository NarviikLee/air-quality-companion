import unittest
from types import SimpleNamespace
from port_discovery import discover_ports, resolve_os_mode


class DiscoveryTests(unittest.TestCase):
    def test_auto(self):
        self.assertEqual(resolve_os_mode('auto', 'win32'), 'windows')
        self.assertEqual(resolve_os_mode('auto', 'linux'), 'linux')
        with self.assertRaises(ValueError):
            resolve_os_mode('typo')
        with self.assertRaises(ValueError):
            resolve_os_mode('auto', 'darwin')

    def test_os_filter_and_numeric_order(self):
        names = ['COM10', 'COM2', '/dev/ttyUSB10', '/dev/ttyUSB2',
                 '/dev/ttyUSB0', '/dev/ttyACM0', '/dev/ttyAMA0',
                 '/dev/ttyS0', '/tmp/file', 'COM2']
        ports = lambda: [SimpleNamespace(device=name) for name in names]
        self.assertEqual(discover_ports(ports, 'windows'), ['COM2', 'COM10'])
        self.assertEqual(discover_ports(ports, 'linux'), [
            '/dev/ttyACM0', '/dev/ttyAMA0', '/dev/ttyS0',
            '/dev/ttyUSB0', '/dev/ttyUSB2', '/dev/ttyUSB10'])

    def test_empty(self):
        self.assertEqual(discover_ports(lambda: [], 'linux'), [])


if __name__ == '__main__':
    unittest.main()
