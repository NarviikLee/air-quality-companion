"""통신 및 데모 설정: 상수를 수정하고 프로그램을 다시 실행하세요."""
from dataclasses import dataclass
from configparser import ConfigParser, Error as ConfigError
from pathlib import Path
import random
from sensor_status import CARD_COLORS, assess_sensor

SOURCE_MODE = 'serial'  # 'serial': 실제 포트 검색, 'demo': 기존 더미 화면
try:
    from sensor_connection_local import (OS_MODE, SERIAL_BAUDRATE, SERIAL_BYTESIZE,
        SERIAL_PARITY, SERIAL_STOPBITS, SERIAL_TIMEOUT_SECONDS,
        SERIAL_WRITE_TIMEOUT_SECONDS, PREFERRED_PORT, PORT_FAILURE_LIMIT)
except ModuleNotFoundError as error:
    if error.name != 'sensor_connection_local':
        raise
    from sensor_connection_example import (OS_MODE, SERIAL_BAUDRATE, SERIAL_BYTESIZE,
        SERIAL_PARITY, SERIAL_STOPBITS, SERIAL_TIMEOUT_SECONDS,
        SERIAL_WRITE_TIMEOUT_SECONDS, PREFERRED_PORT, PORT_FAILURE_LIMIT)


def create_sensor_source():
    if SOURCE_MODE == 'demo':
        return DummySensorSource()
    if SOURCE_MODE == 'serial':
        from serial_source import SerialSensorSource
        return SerialSensorSource()
    raise ValueError('SOURCE_MODE must be serial or demo')

AUTO_UPDATE = True  # False이면 초기값 고정. 시계는 계속 갱신됩니다.
SAMPLE_INTERVAL_SEC = 1
MOVING_AVERAGE_WINDOW_SEC = 30
MIN_SAMPLES_IN_WINDOW = 24
STATE_CONFIRM_DURATION_SEC = 10
MAX_CONSECUTIVE_FAILURES = 3
SENSOR_STALE_TIMEOUT_SEC = 5


def _sensor_detail_timeout_sec(path=None):
    """Load the UI timeout without making a missing config fatal at startup."""
    parser = ConfigParser()
    path = Path(path) if path is not None else Path(__file__).resolve().with_name('app_config.ini')
    try:
        parser.read(str(path), encoding='utf-8')
    except (ConfigError, OSError, UnicodeError):
        return 5.0
    if not parser.has_option('ui', 'sensor_detail_timeout_sec'):
        return 5.0
    try:
        value = parser.getfloat('ui', 'sensor_detail_timeout_sec')
    except (ConfigError, ValueError):
        return 5.0
    return value if value > 0 else 5.0


SENSOR_DETAIL_TIMEOUT_SEC = _sensor_detail_timeout_sec()
ENABLE_MOVING_DISPLAY = False
UPDATE_INTERVAL_MS = round(SAMPLE_INTERVAL_SEC * 1000)
MAIN_VALUE = 24.0  # 센서와 독립적인 임시 점수. 실제 AQI가 아닙니다.
MAIN_STEP = 2.0
MAIN_MAX = 100.0
DEMO_CONNECTION = 'ok'  # 'ok', 'waiting' (수신 실패), 'no_port' (포트 없음)
RETRY_INTERVAL_SECONDS = 3
DEMO_RECOVER_AFTER = 0  # 0: 계속 실패, 2: 두 번 재시도 후 정상 복구


class PortUnavailableError(Exception):
    """설정된 시리얼 포트를 사용할 수 없음."""


class DataUnavailableError(Exception):
    """포트는 있지만 유효한 측정 데이터를 받지 못함."""


@dataclass(frozen=True)
class SensorSpec:
    name: str
    unit: str
    initial: float
    minimum: float
    maximum: float
    step: float
    decimals: int = 0


# 이름, 단위, 초기값, 최솟값, 링 최댓값, 1초 변동 폭, 소수 자릿수
# 이름은 중복 없이 최대 8개. 목록을 바꾸면 카드도 자동으로 바뀝니다.
SENSORS = [
    SensorSpec('PM1.0', 'µg/m³', 8, 0, 100, 1, 1),
    SensorSpec('PM2.5', 'µg/m³', 12, 0, 100, 1, 1),
    SensorSpec('PM10', 'µg/m³', 18, 0, 150, 2, 1),
    SensorSpec('Bio', 'a.u.', 16, 0, 100, 2),
    SensorSpec('Temperature', '°C', 24.5, -10, 50, 0.2, 1),
    SensorSpec('Humidity', '%', 46, 0, 100, 1),
    SensorSpec('VOC', 'a.u.', 22, 0, 100, 2),
    SensorSpec('NOx', 'a.u.', 14, 0, 100, 1),
]

# UI 확인 전용 임시 기준이며 건강/안전 기준이 아닙니다.
DEMO_THRESHOLDS = {'MAIN': (30, 55, 80)}
STATUS_COLORS = {'GOOD': '#22A878', 'NORMAL': '#C9A316',
                 'BAD': '#EE8737', 'VERY BAD': '#DE5259'}
STATUS_COLORS.update(CARD_COLORS)
STATUS_MESSAGES = {'GOOD': '현재 공기 상태가 좋습니다',
                   'NORMAL': '현재 공기 상태는 보통입니다',
                   'BAD': '현재 공기 상태가 나쁩니다',
                   'VERY BAD': '현재 공기 상태가 매우 나쁩니다'}


def get_status(sensor_name, value):
    """Keep the central demo score unchanged; use sourced policy for cards."""
    if sensor_name != 'MAIN':
        return assess_sensor(sensor_name, value).level
    limits = DEMO_THRESHOLDS['MAIN']
    for status, boundary in zip(('GOOD', 'NORMAL', 'BAD'), limits):
        if value <= boundary:
            return status
    return 'VERY BAD'


class DummySensorSource:
    """향후 실제 센서도 이름 -> 값 사전을 반환하도록 교체할 수 있습니다."""
    def __init__(self):
        self.values = {spec.name: spec.initial for spec in SENSORS}
        self.main_value = MAIN_VALUE
        self.failed_reads = 0

    def read(self):
        if DEMO_CONNECTION not in ('ok', 'waiting', 'no_port'):
            raise ValueError('DEMO_CONNECTION must be ok, waiting or no_port')
        if DEMO_CONNECTION != 'ok' and (
                DEMO_RECOVER_AFTER <= 0 or self.failed_reads < DEMO_RECOVER_AFTER):
            self.failed_reads += 1
            if DEMO_CONNECTION == 'no_port':
                raise PortUnavailableError()
            raise DataUnavailableError()
        if AUTO_UPDATE:
            for spec in SENSORS:
                self.values[spec.name] = max(spec.minimum, min(spec.maximum,
                    self.values[spec.name] + random.uniform(-spec.step, spec.step)))
            self.main_value = max(0, min(MAIN_MAX,
                self.main_value + random.uniform(-MAIN_STEP, MAIN_STEP)))
        return dict(self.values), self.main_value
