"""Public interface template, NOT a working device protocol.
Copy to sensor_protocol.py only if the private implementation is absent.
No device IDs, addresses, packet formats or register conversion maps are provided.
"""
SLAVE_ID = None
START_ADDRESS = None
QUANTITY = None
FUNCTION_CODE = None
EXCEPTION_FUNCTION_CODE = None

class ProtocolError(ValueError):
    pass
class ReceiveTimeoutError(ProtocolError):
    pass
class CRCError(ProtocolError):
    pass
class FrameError(ProtocolError):
    pass
class SensorExceptionError(ProtocolError):
    def __init__(self, code):
        self.code = code
        super().__init__('Sensor exception: {}'.format(code))
class AcquisitionCancelled(ProtocolError):
    pass

def validate_protocol_config():
    raise ProtocolError('Private sensor protocol is not configured; use --demo.')

def modbus_crc(data: bytes):
    return validate_protocol_config()

def convert_modbus_address(start_address):
    return validate_protocol_config()

def create_read_request(start_address=START_ADDRESS, quantity=QUANTITY, slave_id=SLAVE_ID):
    return validate_protocol_config()

def parse_registers(response, quantity):
    return validate_protocol_config()

def receive_frame(ser, cancel_event=None):
    return validate_protocol_config()

def read_sensor_data(ser, cancel_event=None):
    """Expected keys: pm1, pm25, pm10, bioaerosol, voc, nox, temperature, humidity.
    Restore an authorized implementation that validates the entire response,
    honors cancellation and returns these keys. This template does no I/O.
    """
    if cancel_event is not None and cancel_event.is_set():
        raise AcquisitionCancelled('Acquisition cancelled')
    return validate_protocol_config()
