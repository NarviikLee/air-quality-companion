"""Public template for the private sensor communication module.

Copy this file to ``sensor_protocol.py`` and implement each function using the
sensor manufacturer's protocol document.  The application imports
``read_sensor_data`` from that private module.

This template intentionally contains no device address, request frame, CRC
parameters, register mapping, scaling rule, or sample packet.
"""

from typing import BinaryIO, Dict, List


class SensorProtocolNotConfiguredError(RuntimeError):
    """Raised when the private sensor protocol has not been implemented."""


def modbus_crc(data: bytes) -> int:
    """Return the checksum required by the target sensor protocol.

    Implement this from the device specification.  Checksum width, initial
    value, polynomial, byte order, and covered byte range are device-specific.
    """
    del data
    raise SensorProtocolNotConfiguredError(
        "Implement modbus_crc() from the private sensor specification."
    )


def convert_modbus_address(start_address: int) -> int:
    """Convert an application address to the address sent to the device.

    Address conversion rules are device-specific and must come from the
    authorized protocol document.
    """
    del start_address
    raise SensorProtocolNotConfiguredError(
        "Implement convert_modbus_address() from the private sensor specification."
    )


def create_read_request(
    start_address: int = None,
    quantity: int = None,
    slave_id: int = None,
) -> bytes:
    """Build a request frame for a sensor data read.

    Validate the requested range and assemble the frame expected by the
    device.  Do not place real register addresses or packet examples in this
    public template.
    """
    del start_address, quantity
    raise SensorProtocolNotConfiguredError(
        "Implement create_read_request() from the private sensor specification."
    )


def validate_response(response: bytes) -> None:
    """Validate a raw response before any values are decoded.

    A private implementation should check the response length, device
    identity, operation result, checksum, and any device-defined error frame.
    Raise a descriptive exception when validation fails.
    """
    del response
    raise SensorProtocolNotConfiguredError(
        "Implement validate_response() from the private sensor specification."
    )


def parse_registers(response: bytes, quantity: int) -> List[int]:
    """Decode validated response bytes into raw register values.

    Apply only the byte order and word layout defined by the manufacturer.
    Scaling and physical-unit conversion should be handled separately so each
    step can be tested independently.
    """
    del response, quantity
    raise SensorProtocolNotConfiguredError(
        "Implement parse_registers() from the private sensor specification."
    )


def decode_sensor_values(registers: List[int]) -> Dict[str, float]:
    """Map raw registers to the names and units expected by the GUI.

    Confirm each field's address, signedness, register count, scale, unit, and
    invalid-value definition before implementing this function.
    """
    del registers
    raise SensorProtocolNotConfiguredError(
        "Implement decode_sensor_values() from the private sensor specification."
    )


def read_sensor_data(serial_port: BinaryIO) -> Dict[str, float]:
    """Request, validate, decode, and return one sensor snapshot.

    This is the public interface used by ``bioaerosol_QT_control.py``.  The
    returned mapping must contain every field consumed by the GUI.  Keep serial
    timeout and retry policy consistent with the application.
    """
    del serial_port
    raise SensorProtocolNotConfiguredError(
        "Sensor protocol is not included. Copy sensor_protocol_template.py to "
        "sensor_protocol.py and implement it from the authorized specification."
    )
