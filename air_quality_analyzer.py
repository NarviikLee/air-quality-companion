"""V1 display policy. No Qt, I/O, timers or device control."""
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
import time
import sensor_data as config
from sensor_status import assess_sensor, validate_sensor_value, TEMPERATURE_COMFORT

NAMES = ('PM1.0', 'PM2.5', 'PM10', 'Temperature', 'Humidity')


class AirQualityState(IntEnum):
    COMFORTABLE = 0
    NORMAL = 1
    BAD = 2


@dataclass(frozen=True)
class Measurement:
    timestamp: float
    values: tuple


def map_robot_state(name, value):
    level = assess_sensor(name, value).level
    if level == 'CARD_UNKNOWN':
        raise ValueError('Invalid analysis value')
    if level == 'CARD_GOOD':
        return AirQualityState.COMFORTABLE
    if name in ('Temperature', 'Humidity') or level == 'CARD_NORMAL':
        return AirQualityState.NORMAL
    return AirQualityState.BAD


class AirQualityAnalyzer:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.reset()

    def reset(self):
        self.samples = deque()
        self.first_at = self.last_at = None
        self.failures = 0
        self.sensor_check = True
        self.delayed = False
        self.ready = False
        self.averages = {}
        self.confirmed_state = None
        self.reasons = []
        self.clear_candidate()

    def clear_candidate(self):
        self.candidate_state = self.candidate_started_at = None
        self.candidate_reasons = []

    def _prune(self, now):
        while self.samples and self.samples[0].timestamp < now - config.MOVING_AVERAGE_WINDOW_SEC:
            self.samples.popleft()

    def check_stale(self, now=None):
        now = self.clock() if now is None else now
        if self.last_at is not None and now - self.last_at >= config.SENSOR_STALE_TIMEOUT_SEC:
            self.reset()
            return True
        self._prune(now)
        if self.ready and len(self.samples) < config.MIN_SAMPLES_IN_WINDOW:
            self.ready = False
            self.clear_candidate()
        return False

    def record_failure(self, now=None, no_port=False):
        now = self.clock() if now is None else now
        self.clear_candidate()
        self.delayed = True
        self.failures += 1
        if no_port or self.failures >= config.MAX_CONSECUTIVE_FAILURES:
            self.reset()
        else:
            self.check_stale(now)

    def accept_sample(self, values, timestamp=None):
        now = self.clock() if timestamp is None else timestamp
        if self.last_at is not None and now <= self.last_at:
            return False  # Duplicate/out-of-order samples cannot advance confirmation.
        self.check_stale(now)  # Check the gap BEFORE updating last_at.
        clean = tuple(validate_sensor_value(name, values.get(name)) for name in NAMES)
        if any(value is None for value in clean):
            self.record_failure(now)
            return False
        self.sensor_check = False
        self.delayed = False
        self.failures = 0
        if self.first_at is None:
            self.first_at = now
        self.last_at = now
        self.samples.append(Measurement(now, clean))
        self._prune(now)
        self.ready = (now - self.first_at >= config.MOVING_AVERAGE_WINDOW_SEC
                      and len(self.samples) >= config.MIN_SAMPLES_IN_WINDOW)
        if not self.ready:
            self.clear_candidate()
            return True
        self.averages = {name: sum(s.values[i] for s in self.samples) / len(self.samples)
                         for i, name in enumerate(NAMES)}
        states = {name: map_robot_state(name, value) for name, value in self.averages.items()}
        state = max(states.values())
        reasons = []
        for name in NAMES:
            if states[name] != state or state == AirQualityState.COMFORTABLE:
                continue
            value = self.averages[name]
            if name == 'Temperature':
                reason = 'temperature_low' if value < TEMPERATURE_COMFORT[0] else 'temperature_high'
            elif name == 'Humidity':
                reason = 'humidity_low' if value < 30 else 'humidity_high'
            else:
                reason = {'PM1.0': 'pm1', 'PM2.5': 'pm25', 'PM10': 'pm10'}[name] + ('_bad' if state == 2 else '_normal')
            reasons.append(reason)
        if state == self.confirmed_state:
            self.reasons = reasons
            self.clear_candidate()
        elif state != self.candidate_state:
            self.candidate_state = state
            self.candidate_started_at = now
            self.candidate_reasons = reasons
        else:
            self.candidate_reasons = reasons
            if now - self.candidate_started_at >= config.STATE_CONFIRM_DURATION_SEC:
                self.confirmed_state, self.reasons = state, reasons
                self.clear_candidate()
        return True
