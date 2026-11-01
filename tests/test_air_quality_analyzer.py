import unittest
from air_quality_analyzer import AirQualityAnalyzer, AirQualityState, NAMES, map_robot_state
from sensor_status import validate_sensor_value

GOOD = {'PM1.0': 8, 'PM2.5': 12, 'PM10': 18, 'Temperature': 24, 'Humidity': 45}


class AnalyzerTests(unittest.TestCase):
    def test_reconnect_confirms_with_fresh_samples_in_fifteen_seconds(self):
        a = self.prepared(dict(GOOD, Humidity=80))
        a.begin_reconnect(a.confirmed_state, a.reasons)
        self.assertFalse(a.samples)
        for t in range(100, 115):
            a.accept_sample(GOOD, t)
            a.check_stale(t + .25)
        self.assertEqual(a.confirmed_state, AirQualityState.NORMAL)
        a.accept_sample(GOOD, 115)
        self.assertEqual(a.confirmed_state, AirQualityState.COMFORTABLE)
        self.assertFalse(a.reconnect_mode)
        a.accept_sample(GOOD, 116)
        self.assertFalse(a.ready)
        self.assertEqual(a.confirmed_state, AirQualityState.COMFORTABLE)

    def test_missing_channel_cannot_complete_reconnect_recovery(self):
        a = self.prepared(dict(GOOD, Humidity=80))
        a.begin_reconnect(a.confirmed_state)
        for t in range(100, 121):
            a.accept_sample(dict(GOOD, Humidity=None), t)
        self.assertEqual(a.confirmed_state, AirQualityState.NORMAL)
        self.assertTrue(a.reconnect_mode)

    def test_long_disconnect_recovery_without_retained_face(self):
        a = AirQualityAnalyzer()
        a.begin_reconnect()
        for t in range(16):
            a.accept_sample(GOOD, t)
        self.assertEqual(a.confirmed_state, AirQualityState.COMFORTABLE)
        self.assertFalse(a.reconnect_mode)

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

    def test_timer_jitter_does_not_prevent_analyzer_from_becoming_ready(self):
        a = AirQualityAnalyzer()
        for index in range(42):
            a.accept_sample(GOOD, index * 1.01)
        self.assertTrue(a.ready)
        self.assertEqual(a.confirmed_state, AirQualityState.COMFORTABLE)

    def test_mapping_and_reasons(self):
        for name in ('Temperature', 'Humidity'):
            self.assertEqual(map_robot_state(name, 80), 1)
        for name in ('PM1.0', 'PM2.5', 'PM10'):
            self.assertEqual(map_robot_state(name, 200), 2)
        a = self.prepared(dict(GOOD, Humidity=80, VOC=None))
        self.assertEqual(a.confirmed_state, 1)
        self.assertEqual(a.reasons, ['humidity_high'])

    def test_warm_humidity_changes_robot_from_comfortable_to_normal(self):
        a = self.prepared(dict(GOOD, Temperature=25, Humidity=50))
        self.assertEqual(a.confirmed_state, AirQualityState.NORMAL)
        self.assertEqual(a.reasons, ['humidity_high'])

    def test_same_humidity_is_comfortable_at_milder_temperature(self):
        a = self.prepared(dict(GOOD, Temperature=22, Humidity=50))
        self.assertEqual(a.confirmed_state, AirQualityState.COMFORTABLE)
        self.assertEqual(a.reasons, [])

    def test_high_temperature_does_not_blame_normal_humidity(self):
        a = self.prepared(dict(GOOD, Temperature=28, Humidity=40))
        self.assertEqual(a.confirmed_state, AirQualityState.NORMAL)
        self.assertEqual(a.reasons, ['temperature_high'])

    def test_invalid_before_average(self):
        for name, value in [('PM1.0', -1), ('Humidity', 101), ('Temperature', None),
                            ('Temperature', float('nan')), ('Temperature', 100.1),
                            ('PM2.5', 5000.1), ('PM10', 'bad')]:
            a = AirQualityAnalyzer()
            self.assertTrue(a.accept_sample(dict(GOOD, **{name: value}), 0))
            self.assertEqual(len(a.samples), 1)
            self.assertIsNone(a.samples[0].values[NAMES.index(name)])
            self.assertFalse(a.ready)
        self.assertEqual(validate_sensor_value('Temperature', -5), -5)

    def test_failure_retains_confirmed_but_breaks_candidate(self):
        a = self.prepared()
        a.accept_sample(dict(GOOD, **{'PM2.5': 1000}), 41)
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
        with patch.object(a, '_rapid_worsening', return_value=(None, [])):
            with patch('air_quality_analyzer.map_robot_state', return_value=AirQualityState.BAD):
                a.accept_sample(GOOD, 41)
            with patch('air_quality_analyzer.map_robot_state', return_value=AirQualityState.NORMAL):
                a.accept_sample(GOOD, 42)
            self.assertEqual(a.candidate_started_at, 42)
            a.accept_sample(GOOD, 43)
        self.assertIsNone(a.candidate_state)

    def test_sustained_pm_rise_changes_state_without_waiting_for_average(self):
        a = self.prepared()
        bad = dict(GOOD, **{'PM2.5': 100})
        a.accept_sample(bad, 41)
        a.accept_sample(bad, 42)
        a.accept_sample(bad, 43)
        self.assertEqual(a.confirmed_state, AirQualityState.COMFORTABLE)
        a.accept_sample(bad, 44)
        self.assertEqual(a.confirmed_state, AirQualityState.BAD)
        self.assertEqual(a.reasons, ['pm25_bad'])

    def test_single_pm_spike_does_not_change_confirmed_state(self):
        a = self.prepared()
        bad = dict(GOOD, **{'PM2.5': 100})
        for timestamp, values in [(41, bad), (42, GOOD), (43, GOOD),
                                  (44, GOOD), (45, GOOD)]:
            a.accept_sample(values, timestamp)
        self.assertEqual(a.confirmed_state, AirQualityState.COMFORTABLE)

    def test_four_of_five_pm_readings_tolerate_one_normal_reading(self):
        a = self.prepared()
        bad = dict(GOOD, **{'PM10': 200})
        for timestamp, values in [(41, bad), (42, bad), (43, GOOD),
                                  (44, bad), (45, bad)]:
            a.accept_sample(values, timestamp)
        self.assertEqual(a.confirmed_state, AirQualityState.BAD)
        self.assertEqual(a.reasons, ['pm10_bad'])

    def test_three_of_five_pm_readings_are_not_enough(self):
        a = self.prepared()
        bad = dict(GOOD, **{'PM2.5': 100})
        for timestamp, values in [(41, bad), (42, GOOD), (43, bad),
                                  (44, GOOD), (45, bad)]:
            a.accept_sample(values, timestamp)
        self.assertEqual(a.confirmed_state, AirQualityState.COMFORTABLE)

    def test_sustained_normal_pm_level_fast_tracks_one_step_worse(self):
        a = self.prepared()
        normal = dict(GOOD, **{'PM2.5': 20})
        for timestamp in (41, 42, 43, 44):
            a.accept_sample(normal, timestamp)
        self.assertEqual(a.confirmed_state, AirQualityState.NORMAL)
        self.assertEqual(a.reasons, ['pm25_normal'])

    def test_failure_clears_rapid_rise_history(self):
        a = self.prepared()
        bad = dict(GOOD, **{'PM1.0': 100})
        for timestamp in (41, 42, 43):
            a.accept_sample(bad, timestamp)
        a.record_failure(44)
        a.accept_sample(bad, 45)
        self.assertEqual(a.confirmed_state, AirQualityState.COMFORTABLE)

    def test_one_invalid_channel_does_not_discard_other_measurements(self):
        a = self.prepared()
        partial = dict(GOOD, Humidity=None)
        self.assertTrue(a.accept_sample(partial, 41))
        self.assertEqual(a.failures, 0)
        self.assertFalse(a.delayed)
        self.assertIsNone(a.samples[-1].values[NAMES.index('Humidity')])
        self.assertEqual(a.samples[-1].values[NAMES.index('PM2.5')], GOOD['PM2.5'])

    def test_all_invalid_analysis_channels_are_a_frame_failure(self):
        a = self.prepared()
        invalid = {name: None for name in NAMES}
        self.assertFalse(a.accept_sample(invalid, 41))
        self.assertEqual(a.failures, 1)
        self.assertTrue(a.delayed)

    def test_missing_channel_cannot_make_confirmed_state_improve(self):
        bad = dict(GOOD, Humidity=80)
        a = self.prepared(bad)
        for timestamp in range(41, 76):
            a.accept_sample(dict(GOOD, Humidity=None), timestamp)
        self.assertFalse(a.ready)
        self.assertEqual(a.confirmed_state, AirQualityState.NORMAL)

    def test_valid_channels_keep_averaging_while_one_channel_is_missing(self):
        a = self.prepared()
        partial = dict(GOOD, Humidity=None, **{'PM2.5': 100})
        for timestamp in range(41, 76):
            a.accept_sample(partial, timestamp)
        self.assertFalse(a.ready)
        self.assertIn('PM2.5', a.averages)
        self.assertNotIn('Humidity', a.averages)
        self.assertGreater(a.averages['PM2.5'], 90)
        self.assertEqual(a.confirmed_state, AirQualityState.BAD)

    def test_invalid_pm_does_not_clear_another_pm_rapid_history(self):
        a = self.prepared()
        for timestamp in (41, 42, 43, 44):
            a.accept_sample(dict(GOOD, **{'PM1.0': None, 'PM2.5': 100}), timestamp)
        self.assertEqual(a.confirmed_state, AirQualityState.BAD)
        self.assertEqual(a.reasons, ['pm25_bad'])

    def test_short_channel_gap_keeps_existing_window(self):
        a = self.prepared()
        a.accept_sample(dict(GOOD, Humidity=None), 41)
        self.assertEqual(a.channel_display_status('Humidity'), 'invalid')
        a.accept_sample(GOOD, 42)
        self.assertIsNone(a.channel_display_status('Humidity'))
        self.assertTrue(a.ready)

    def test_stale_channel_alone_restarts_its_warmup(self):
        a = self.prepared()
        for timestamp in range(41, 46):
            a.accept_sample(dict(GOOD, Humidity=None), timestamp)
        self.assertEqual(a.channel_display_status('Humidity'), 'checking')
        self.assertNotIn('Humidity', a.ready_channels)
        self.assertIn('PM2.5', a.ready_channels)
        a.accept_sample(GOOD, 46)
        self.assertEqual(a.channel_display_status('Humidity'), 'recovering')
        for timestamp in range(47, 76):
            a.accept_sample(GOOD, timestamp)
        self.assertEqual(a.channel_display_status('Humidity'), 'recovering')
        a.accept_sample(GOOD, 76)
        self.assertIsNone(a.channel_display_status('Humidity'))
        self.assertTrue(a.ready)


if __name__ == '__main__':
    unittest.main()
