import inspect
import unittest
from unittest.mock import Mock
import sensor_protocol_template as template
import sensor_connection_example as settings


class PublicTemplateTests(unittest.TestCase):
    def test_no_real_settings_or_io(self):
        for key in ('SLAVE_ID', 'START_ADDRESS', 'QUANTITY'):
            self.assertIsNone(getattr(template, key))
        self.assertIsNone(settings.SERIAL_BAUDRATE)
        port = Mock()
        with self.assertRaises(template.ProtocolError):
            template.read_sensor_data(port)
        self.assertEqual(port.mock_calls, [])

    def test_parameter_names_match_local_interface(self):
        import sensor_protocol as local
        for name in ('modbus_crc', 'convert_modbus_address', 'create_read_request',
                     'parse_registers', 'receive_frame', 'read_sensor_data'):
            self.assertEqual(list(inspect.signature(getattr(local, name)).parameters),
                             list(inspect.signature(getattr(template, name)).parameters))
