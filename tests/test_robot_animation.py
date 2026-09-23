import unittest

from robot_animation import RobotAnimationController


class RobotAnimationTests(unittest.TestCase):
    def frame(self, expression, elapsed):
        return RobotAnimationController(expression).frame_at(elapsed)

    def test_monitoring_and_comfortable_move_on_different_axes(self):
        monitoring = self.frame('monitoring', 0.8)
        comfortable = self.frame('comfortable', 0.9)
        self.assertNotEqual(monitoring.eye_offset_x, 0)
        self.assertEqual(monitoring.eye_offset_y, 0)
        self.assertEqual(comfortable.eye_offset_x, 0)
        self.assertNotEqual(comfortable.eye_offset_y, 0)

    def test_normal_blinks_but_reopens(self):
        self.assertLess(self.frame('normal', 0.14).eye_openness, 0.2)
        self.assertEqual(self.frame('normal', 0.5).eye_openness, 1.0)

    def test_detected_symbol_toggles(self):
        self.assertTrue(self.frame('detected', 0.2).show_exclamation)
        self.assertFalse(self.frame('detected', 1.2).show_exclamation)

    def test_moving_and_purifying_alternate_sides(self):
        self.assertEqual(self.frame('moving', 0.2).direction, -1)
        self.assertEqual(self.frame('moving', 1.2).direction, 1)
        self.assertEqual(self.frame('purifying', 0.2).air_wave_side, -1)
        self.assertEqual(self.frame('purifying', 1.0).air_wave_side, 1)

    def test_waiting_and_purifying_advance_mouth_wave(self):
        self.assertNotEqual(self.frame('waiting', 0.1).mouth_phase,
                            self.frame('waiting', 0.2).mouth_phase)
        self.assertNotEqual(self.frame('purifying', 0.1).mouth_phase,
                            self.frame('purifying', 0.2).mouth_phase)


if __name__ == '__main__':
    unittest.main()
