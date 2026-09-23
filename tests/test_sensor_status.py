import unittest
from unittest.mock import patch
from sensor_status import assess_sensor
from sensor_data import DummySensorSource, DEMO_THERMAL_HOLD_SAMPLES, get_status


class SensorStatusTests(unittest.TestCase):
    def test_pm_boundaries_and_fractional_values(self):
        for name, limits in [('PM1.0', (10, 25, 50)), ('PM2.5', (15, 35, 75)), ('PM10', (30, 80, 150))]:
            for boundary, at, above in zip(limits,
                    ('좋음', '보통', '나쁨'), ('보통', '나쁨', '매우 나쁨')):
                with self.subTest(name=name, boundary=boundary):
                    self.assertEqual(assess_sensor(name, boundary).message, at)
                    self.assertEqual(assess_sensor(name, boundary + 0.1).message, above)
            self.assertEqual(assess_sensor(name, 1000).level, 'CARD_SEVERE')
            self.assertEqual(assess_sensor(name, limits[1] + 0.1).level, 'CARD_WARNING')

    def test_humidity_edges(self):
        for value, message in [(0, '건조'), (29.9, '건조'), (30, '적정'),
                               (50, '적정'), (50.1, '다소 습함'), (59.9, '다소 습함'),
                               (60, '습함'), (100, '습함')]:
            self.assertEqual(assess_sensor('Humidity', value).message, message)

    def test_humidity_label_uses_temperature_context(self):
        cases = [
            (18, 45, '적정·서늘함', 'CARD_GOOD'),
            (22, 45, '쾌적', 'CARD_GOOD'),
            (25, 45, '쾌적', 'CARD_GOOD'),
            (25, 50, '다소 후텁지근', 'CARD_WARNING'),
            (28, 40, '온도 높음', 'CARD_WARNING'),
            (28, 50, '후텁지근', 'CARD_WARNING'),
            (22, 60, '습함', 'CARD_BAD'),
        ]
        for temperature, humidity, message, level in cases:
            with self.subTest(temperature=temperature, humidity=humidity):
                result = assess_sensor('Humidity', humidity, temperature=temperature)
                self.assertEqual(result.message, message)
                self.assertEqual(result.level, level)

    def test_temperature_is_comfort_not_pollution(self):
        for value, message in [(-5, '낮음'), (19.9, '낮음'), (20, '적정'),
                               (26, '적정'), (26.1, '높음')]:
            self.assertEqual(assess_sensor('Temperature', value).message, message)

    def test_unverified_units_never_get_good_or_danger(self):
        for name in ('VOC', 'NOx', 'Bio'):
            for value in (0, 100, 500, 65535):
                self.assertEqual(assess_sensor(name, value).level, 'CARD_UNKNOWN')

    def test_invalid_measurements(self):
        for name, value in [('PM2.5', -1), ('Humidity', 101),
                            ('Temperature', float('nan')), ('VOC', float('inf'))]:
            self.assertEqual(assess_sensor(name, value).message, '값 확인')

    def test_central_demo_policy_unchanged(self):
        for value, expected in [(30, 'GOOD'), (55, 'NORMAL'), (80, 'BAD'), (81, 'VERY BAD')]:
            self.assertEqual(get_status('MAIN', value), expected)

    def test_demo_holds_a_random_thermal_profile(self):
        source = DummySensorSource()
        with patch('sensor_data.random.choice', return_value=(25.0, 50.0)), \
                patch('sensor_data.random.uniform', return_value=0):
            values, _ = source.read()
        self.assertEqual(values['Temperature'], 25.0)
        self.assertEqual(values['Humidity'], 50.0)
        self.assertEqual(source.thermal_reads_remaining, DEMO_THERMAL_HOLD_SAMPLES - 1)
        self.assertEqual(
            assess_sensor('Humidity', values['Humidity'], values['Temperature']).message,
            '다소 후텁지근')


if __name__ == '__main__':
    unittest.main()
