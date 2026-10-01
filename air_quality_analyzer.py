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


def map_robot_state(name, value, temperature=None):
    """Map one validated display assessment to the robot's three states.

    Args:
        name: Sensor name from ``NAMES``.
        value: Numeric sensor measurement to assess.
        temperature: Optional temperature context used when assessing humidity.

    Returns:
        The corresponding ``AirQualityState`` value.

    Raises:
        ValueError: If the sensor name or measurement cannot be assessed.
    """
    level = assess_sensor(name, value, temperature=temperature).level
    if level == 'CARD_UNKNOWN':
        raise ValueError('Invalid analysis value')
    if level == 'CARD_GOOD':
        return AirQualityState.COMFORTABLE
    if name in ('Temperature', 'Humidity') or level == 'CARD_NORMAL':
        return AirQualityState.NORMAL
    return AirQualityState.BAD


class AirQualityAnalyzer:
    """Aggregate sensor samples and confirm a stable air-quality state.

    Args:
        clock: Callable returning monotonic time in seconds. Supplying a clock
            is useful for deterministic tests; the default is ``time.monotonic``.
    """

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.reset()

    def reset(self):
        """Discard all samples and return to the initial sensor-check state.

        Returns:
            None. All accumulated samples, averages, candidates, confirmed
            state, and failure counters are cleared as a side effect.
        """
        self.samples = deque()
        self.rapid_samples = {name: deque(maxlen=config.FAST_RISE_WINDOW_SAMPLES)
                              for name in NAMES[:3]}
        self.first_valid_at = {name: None for name in NAMES}
        self.last_valid_at = {name: None for name in NAMES}
        self.invalid_since = {name: None for name in NAMES}
        self.recovering_channels = set()
        self.ready_channels = set()
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

    def _rapid_worsening(self, now):
        """Return a sustained, worse PM state without waiting for the long average."""
        if self.confirmed_state is None:
            return None, []
        for target in (AirQualityState.BAD, AirQualityState.NORMAL):
            if target <= self.confirmed_state:
                continue
            reasons = []
            for name, samples in self.rapid_samples.items():
                timestamps = [timestamp for timestamp, value in samples
                              if map_robot_state(name, value) >= target]
                if (len(timestamps) >= config.FAST_RISE_REQUIRED_SAMPLES
                        and now - timestamps[0] >= config.FAST_RISE_CONFIRM_DURATION_SEC):
                    reason = {'PM1.0': 'pm1', 'PM2.5': 'pm25', 'PM10': 'pm10'}[name]
                    reasons.append(reason + ('_bad' if target == AirQualityState.BAD else '_normal'))
            if reasons:
                return target, reasons
        return None, []

    def _prune(self, now):
        while self.samples and self.samples[0].timestamp < now - config.MOVING_AVERAGE_WINDOW_SEC:
            self.samples.popleft()
        for index, name in enumerate(NAMES):
            if not any(sample.values[index] is not None for sample in self.samples):
                self.first_valid_at[name] = None

    def channel_display_status(self, name):
        """Return the acquisition status shown on one sensor detail card.

        Args:
            name: Sensor name to inspect.

        Returns:
            ``'checking'`` when no recent valid value is available,
            ``'invalid'`` for a short invalid-value gap, ``'recovering'`` while
            rebuilding that channel's averaging window, or ``None`` when the
            channel has no special display status. Unknown names also return
            ``None``.
        """
        if name not in self.first_valid_at:
            return None
        if self.invalid_since[name] is not None:
            last_valid = self.last_valid_at[name]
            if last_valid is None or self.last_at - last_valid >= config.CHANNEL_STALE_TIMEOUT_SEC:
                return 'checking'
            return 'invalid'
        if name in self.recovering_channels and name not in self.ready_channels:
            return 'recovering'
        return None

    def check_stale(self, now=None):
        """Expire stale data and update readiness for the current window.

        Args:
            now: Current monotonic time in seconds. When omitted, ``clock``
                supplied to the analyzer is used.

        Returns:
            ``True`` if the most recent sample was stale and the analyzer was
            fully reset; otherwise ``False``.
        """
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
        """Record one failed acquisition attempt.

        Args:
            now: Failure time in monotonic seconds. When omitted, ``clock``
                supplied to the analyzer is used.
            no_port: Whether the failure means that no sensor port is present.
                This causes an immediate full reset when true.

        Returns:
            None. Transient failures preserve the confirmed state but clear
            pending and rapid-rise candidates. A missing port or too many
            consecutive failures resets the analyzer completely.
        """
        now = self.clock() if now is None else now
        self.clear_candidate()
        for samples in self.rapid_samples.values():
            samples.clear()
        self.delayed = True
        self.failures += 1
        if no_port or self.failures >= config.MAX_CONSECUTIVE_FAILURES:
            self.reset()
        else:
            self.check_stale(now)

    def accept_sample(self, values, timestamp=None):
        """Validate and record one frame of sensor measurements.

        Args:
            values: Mapping whose keys are sensor names from ``NAMES`` and
                whose values are raw measurements. Missing, non-numeric, and
                out-of-range channel values are treated as invalid.
            timestamp: Sample time in monotonic seconds. When omitted, ``clock``
                supplied to the analyzer is used.

        Returns:
            ``True`` when at least one analysis value was accepted. ``False``
            when the sample was duplicate or out of order, or when every
            analysis value was invalid.

        Valid channels continue averaging when another channel is invalid.
        Accepted samples may update readiness, moving averages, candidates,
        the confirmed state, and the reasons associated with that state.
        """
        now = self.clock() if timestamp is None else timestamp
        if self.last_at is not None and now <= self.last_at:
            return False  # Duplicate/out-of-order samples cannot advance confirmation.
        self.check_stale(now)  # Check the gap BEFORE updating last_at.
        clean = tuple(validate_sensor_value(name, values.get(name)) for name in NAMES)
        if all(value is None for value in clean):
            self.record_failure(now)
            return False
        self.sensor_check = False
        self.delayed = False
        self.failures = 0
        if self.first_at is None:
            self.first_at = now
        self.last_at = now
        for index, name in enumerate(NAMES):
            value = clean[index]
            if value is None:
                if self.invalid_since[name] is None:
                    self.invalid_since[name] = now
                last_valid = self.last_valid_at[name]
                if (last_valid is None
                        or now - last_valid >= config.CHANNEL_STALE_TIMEOUT_SEC):
                    self.first_valid_at[name] = None
                    self.ready_channels.discard(name)
                    self.recovering_channels.add(name)
                if name in self.rapid_samples:
                    self.rapid_samples[name].clear()
                continue
            if (self.invalid_since[name] is not None
                    and self.last_valid_at[name] is not None
                    and now - self.last_valid_at[name] >= config.CHANNEL_STALE_TIMEOUT_SEC):
                self.first_valid_at[name] = now
                self.ready_channels.discard(name)
                self.recovering_channels.add(name)
            elif self.first_valid_at[name] is None:
                self.first_valid_at[name] = now
            self.invalid_since[name] = None
            self.last_valid_at[name] = now
            if name in self.rapid_samples:
                self.rapid_samples[name].append((now, value))
        measurement = Measurement(now, clean)
        self.samples.append(measurement)
        self._prune(now)
        ready_values = {}
        for index, name in enumerate(NAMES):
            valid = [(sample.timestamp, sample.values[index]) for sample in self.samples
                     if (sample.values[index] is not None
                         and self.first_valid_at[name] is not None
                         and sample.timestamp >= self.first_valid_at[name])]
            if (self.first_valid_at[name] is not None
                    and len(valid) >= config.MIN_SAMPLES_IN_WINDOW
                    and now - self.first_valid_at[name] >= config.MOVING_AVERAGE_WINDOW_SEC):
                ready_values[name] = [value for _, value in valid]
        self.ready_channels = set(ready_values)
        self.recovering_channels.difference_update(self.ready_channels)
        self.ready = len(ready_values) == len(NAMES)
        rapid_state, rapid_reasons = self._rapid_worsening(now)
        if rapid_state is not None:
            self.confirmed_state = rapid_state
            self.reasons = rapid_reasons
            self.clear_candidate()
            return True
        if not ready_values:
            self.clear_candidate()
            return True
        self.averages = {name: sum(values) / len(values)
                         for name, values in ready_values.items()}
        temperature = self.averages.get('Temperature')
        states = {name: map_robot_state(name, value, temperature=temperature)
                  for name, value in self.averages.items()}
        state = max(states.values())
        reasons = []
        for name in NAMES:
            if states.get(name) != state or state == AirQualityState.COMFORTABLE:
                continue
            value = self.averages[name]
            if name == 'Temperature':
                reason = 'temperature_low' if value < TEMPERATURE_COMFORT[0] else 'temperature_high'
            elif name == 'Humidity':
                if value < 30:
                    reason = 'humidity_low'
                elif value > 50 or (temperature > 24 and value > 45):
                    reason = 'humidity_high'
                else:
                    continue  # The temperature card already explains this thermal state.
            else:
                reason = {'PM1.0': 'pm1', 'PM2.5': 'pm25', 'PM10': 'pm10'}[name] + ('_bad' if state == 2 else '_normal')
            reasons.append(reason)
        if self.confirmed_state is None and not self.ready:
            self.clear_candidate()
        elif self.confirmed_state is not None and state < self.confirmed_state and not self.ready:
            # Missing channels cannot prove that the overall environment improved.
            self.clear_candidate()
        elif state == self.confirmed_state:
            if self.ready:
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
