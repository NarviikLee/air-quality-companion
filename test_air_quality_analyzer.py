import unittest
from air_quality_analyzer import AirQualityAnalyzer, AirQualityState, map_robot_state
from sensor_status import validate_sensor_value

GOOD = {'PM1.0': 8, 'PM2.5': 12, 'PM10': 18, 'Temperature': 24, 'Humidity': 45}


class AnalyzerTests(unittest.TestCase):
    def prepared(self, values=GOOD):
        a = AirQualityAnalyzer()
        for t in range(41):
            a.accept_sample(values, t)
        return a

    def test_real_time_warmup_and_confirmation(self):
        a = AirQualityAnalyzer()
        for t in range(30):
            a.accept_sample(GOOD, t)
        self.assertIsNone(a.candidate_state)
        a.accept_sample(GOOD, 30)
        self.assertEqual(a.candidate_started_at, 30)
        for t in range(31, 40):
            a.accept_sample(GOOD, t)
        self.assertIsNone(a.confirmed_state)
        a.accept_sample(GOOD, 40)
        self.assertEqual(a.confirmed_state, AirQualityState.COMFORTABLE)
        self.assertTrue(all(s.timestamp >= 10 for s in a.samples))

    def test_sparse_window_not_ready(self):
        a = AirQualityAnalyzer()
        for t in range(0, 61, 2):
            a.accept_sample(GOOD, t)
        self.assertFalse(a.ready)
        self.assertIsNone(a.confirmed_state)

    def test_mapping_and_reasons(self):
        for name in ('Temperature', 'Humidity'):
            self.assertEqual(map_robot_state(name, 80), 1)
        for name in ('PM1.0', 'PM2.5', 'PM10'):
            self.assertEqual(map_robot_state(name, 200), 2)
        a = self.prepared(dict(GOOD, Humidity=80, VOC=None))
        self.assertEqual(a.confirmed_state, 1)
        self.assertEqual(a.reasons, ['humidity_high'])

    def test_invalid_before_average(self):
        for name, value in [('PM1.0', -1), ('Humidity', 101), ('Temperature', None),
                            ('Temperature', float('nan')), ('PM10', 'bad')]:
            a = AirQualityAnalyzer()
            self.assertFalse(a.accept_sample(dict(GOOD, **{name: value}), 0))
            self.assertFalse(a.samples)
        self.assertEqual(validate_sensor_value('Temperature', -5), -5)

    def test_failure_retains_confirmed_but_breaks_candidate(self):
        a = self.prepared()
        a.accept_sample(dict(GOOD, **{'PM2.5': 10000}), 41)
        self.assertEqual(a.candidate_state, 2)
        a.record_failure(42)
        self.assertEqual(a.confirmed_state, 0)
        self.assertIsNone(a.candidate_state)
        self.assertTrue(a.samples)
        a.record_failure(43)
        a.record_failure(44)
        self.assertTrue(a.sensor_check)
        self.assertFalse(a.samples)

    def test_stale_without_sample_and_gap_on_arrival(self):
        for tick in (True, False):
            a = self.prepared()
            if tick:
                a.check_stale(45)
                self.assertTrue(a.sensor_check)
            a.accept_sample(GOOD, 45)
            self.assertEqual(a.first_at, 45)
            self.assertEqual(len(a.samples), 1)
            self.assertIsNone(a.confirmed_state)

    def test_no_timer_confirmation(self):
        a = AirQualityAnalyzer()
        for t in range(31):
            a.accept_sample(GOOD, t)
        a.check_stale(34)
        self.assertIsNone(a.confirmed_state)
        a.check_stale(40)
        self.assertTrue(a.sensor_check)

    def test_candidate_changes_and_returns_to_confirmed(self):
        a = self.prepared()
        # Use a stable full window to isolate candidate transitions.
        from unittest.mock import patch
        with patch('air_quality_analyzer.map_robot_state', return_value=AirQualityState.BAD):
            a.accept_sample(GOOD, 41)
        with patch('air_quality_analyzer.map_robot_state', return_value=AirQualityState.NORMAL):
            a.accept_sample(GOOD, 42)
        self.assertEqual(a.candidate_started_at, 42)
        a.accept_sample(GOOD, 43)
        self.assertIsNone(a.candidate_state)


if __name__ == '__main__':
    unittest.main()
