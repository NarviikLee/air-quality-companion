"""Per-card display policy. Sources and limitations: SENSOR_CRITERIA.md."""
from dataclasses import dataclass
import math

CARD_COLORS = {
    'CARD_GOOD': '#16835B',
    'CARD_NORMAL': '#B58A00',
    'CARD_WARNING': '#C86516',
    'CARD_BAD': '#D63B3B',
    'CARD_SEVERE': '#D63B3B',
    'CARD_UNKNOWN': '#73817C',
}
# PM1.0 is a user-selected product reference, not an AirKorea standard.
PM_LIMITS = {'PM1.0': (10, 25, 50), 'PM2.5': (15, 35, 75), 'PM10': (30, 80, 150)}
# Product comfort preference, not a regulatory or health threshold.
TEMPERATURE_COMFORT = (20, 26)


@dataclass(frozen=True)
class Assessment:
    level: str
    message: str
    detail: str


def validate_sensor_value(name, value):
    """Return a finite measurement or None; display limits are not sensor limits."""
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value) or (name != 'Temperature' and value < 0) or (name == 'Humidity' and value > 100):
        return None
    return value


def assess_sensor(name, value):
    value = validate_sensor_value(name, value)
    if value is None:
        return Assessment('CARD_UNKNOWN', '값 확인', '유효한 측정 범위를 확인하세요.')
    if name in PM_LIMITS:
        detail = '에어코리아 일평균 농도 구간을 현재 수신값에 적용한 참고 표시입니다. 공식 AQI가 아닙니다.'
        if name == 'PM1.0':
            detail = '사용자가 정한 PM1.0 참고 구간(10/25/50)입니다. 공식 대기질 기준이 아닙니다.'
        for boundary, level, message in zip(
                PM_LIMITS[name], ('CARD_GOOD', 'CARD_NORMAL', 'CARD_WARNING'), ('좋음', '보통', '나쁨')):
            if value <= boundary:
                return Assessment(level, message, detail)
        return Assessment('CARD_SEVERE', '매우 나쁨', detail)
    if name == 'Humidity':
        detail = 'EPA 권장 습도 30~50%, 60% 미만 유지 참고. 색상은 제품 표시 정책입니다.'
        if value < 30:
            return Assessment('CARD_WARNING', '건조', detail)
        if value <= 50:
            return Assessment('CARD_GOOD', '적정', detail)
        if value < 60:
            return Assessment('CARD_WARNING', '다소 습함', detail)
        return Assessment('CARD_BAD', '습함', detail)
    if name == 'Temperature':
        detail = '제품의 실내 온도 참고 범위 20~26°C. 개인·계절에 따라 쾌적 범위는 다릅니다.'
        if value < TEMPERATURE_COMFORT[0]:
            return Assessment('CARD_WARNING', '낮음', detail)
        if value > TEMPERATURE_COMFORT[1]:
            return Assessment('CARD_WARNING', '높음', detail)
        return Assessment('CARD_GOOD', '적정', detail)
    detail = '센서 모델·출력 단위·제조사 판정 기준 확인 전에는 등급을 부여하지 않습니다.'
    return Assessment('CARD_UNKNOWN', '기준 미정', detail)
