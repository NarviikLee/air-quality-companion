import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import time
import unittest
from unittest.mock import patch
from qt_compat import QApplication, QTest, Qt
from air_quality_analyzer import AirQualityAnalyzer
from robot_led import RobotLedController, RobotDisplayState as R
from test_air_quality_analyzer import GOOD
from test_sensor_worker import wait_until
from sensor_worker import SensorSnapshot
import sensor_data as config
from dashboard import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class RobotTests(unittest.TestCase):
    def test_purifying_is_display_only_and_sensor_check_has_priority(self):
        analyzer, controller = AirQualityAnalyzer(), RobotLedController()
        controller.set_purifying(True)
        self.assertEqual(controller.resolve(analyzer)[0], R.SENSOR_CHECK)
        analyzer.accept_sample(GOOD, 0)
        self.assertEqual(controller.resolve(analyzer)[0], R.PURIFYING)
        controller.set_purifying(False)
        self.assertEqual(controller.resolve(analyzer)[0], R.MONITORING)

    def test_moving_priority_and_candidate_face(self):
        a, c = AirQualityAnalyzer(), RobotLedController()
        c.set_moving(True)
        with patch.object(config, 'ENABLE_MOVING_DISPLAY', True):
            self.assertEqual(c.resolve(a)[0], R.SENSOR_CHECK)
            a.accept_sample(GOOD, 0)
            self.assertEqual(c.resolve(a)[0], R.MOVING)
            c.set_moving(False)
            self.assertEqual(c.resolve(a)[0], R.MONITORING)
            for t in range(1, 41):
                a.accept_sample(GOOD, t)
            c.set_moving(True)
            self.assertEqual(c.resolve(a)[0], R.MOVING)
            a.accept_sample(dict(GOOD, **{'PM2.5': 10000}), 41)
            c.set_moving(False)
            state, _, detail = c.resolve(a)
            self.assertEqual(state, R.COMFORTABLE)
            self.assertIn('변화', detail)
            a.check_stale(46)
            self.assertEqual(c.resolve(a)[0], R.SENSOR_CHECK)
        a.accept_sample(GOOD, 47)
        c.set_moving(True)
        self.assertEqual(c.resolve(a)[0], R.MONITORING)

    def test_navigation_invalid_field_and_failures(self):
        class Source:
            def read(self):
                return {s.name: s.initial for s in config.SENSORS}, None
        w = MainWindow(Source)
        w.show()
        try:
            wait_until(lambda: not w._busy)
            w.data_timer.stop()
            self.assertIs(w.pages.currentWidget(), w.robot_home_page)
            w.analyzer.reset()
            w.refresh_robot()
            QTest.mouseClick(w.robot_home_page.face, Qt.LeftButton)
            w.show_sensor_detail()
            self.assertIs(w.pages.currentWidget(), w.robot_home_page)
            self.assertFalse(w.robot_home_page.face.isEnabled())
            w.analyzer.accept_sample(GOOD, time.monotonic())
            w.refresh_robot()
            self.assertTrue(w.robot_home_page.face.isEnabled())
            QTest.mouseClick(w.robot_home_page.face, Qt.LeftButton)
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            values = {s.name: s.initial for s in config.SENSORS}
            w.analyzer.reset()
            start = time.monotonic() - 40
            for t in range(41):
                w.analyzer.accept_sample(GOOD, start + t)
            snapshot = SensorSnapshot(dict(values, VOC=None), time.monotonic())
            w.on_received(snapshot, None)
            self.assertIsNone(w.gauges['VOC'][0].value)
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            self.assertEqual(w.analyzer.confirmed_state, 0)
            w.on_failed('waiting', 'timeout')
            self.assertEqual(w.analyzer.confirmed_state, 0)
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            w.refresh_reception_status(time.monotonic())
            self.assertIn('수신 지연', w.connection_label.text())
            w.on_failed('waiting', 'timeout')
            w.on_failed('waiting', 'timeout')
            self.assertEqual(w.robot_home_page.display_state, R.SENSOR_CHECK)
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            QTest.mouseClick(w.home_button, Qt.LeftButton)
            self.assertIs(w.pages.currentWidget(), w.robot_home_page)
            self.assertFalse(w.robot_home_page.face.isEnabled())
            QTest.mouseClick(w.robot_home_page.face, Qt.LeftButton)
            self.assertIs(w.pages.currentWidget(), w.robot_home_page)
        finally:
            w.close()
            wait_until(lambda: not w.sensor_thread.isRunning())
            w.sensor_thread.wait()
            APP.processEvents()

    def test_start_based_schedule_skips_elapsed_slots(self):
        class Timer:
            def start(self, value):
                self.delay = value
        class Window:
            request_started_at = 100
            data_timer = Timer()
        w = Window()
        with patch('dashboard.time.monotonic', return_value=100.2):
            MainWindow.schedule_normal_read(w)
        self.assertAlmostEqual(w.data_timer.delay, 800, delta=1)
        with patch('dashboard.time.monotonic', return_value=102.2):
            MainWindow.schedule_normal_read(w)
        self.assertAlmostEqual(w.data_timer.delay, 800, delta=1)

    def test_health_timer_stales_without_changing_detail_page(self):
        class Source:
            def read(self):
                return {s.name: s.initial for s in config.SENSORS}, None
        w = MainWindow(Source)
        try:
            wait_until(lambda: not w._busy)
            w.data_timer.stop()
            w.show_sensor_detail()
            w.analyzer.last_at = time.monotonic() - 5
            QTest.qWait(300)
            self.assertTrue(w.analyzer.sensor_check)
            self.assertIsNone(w.operation_deadline)
            self.assertFalse(w._recovering)
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            w.on_received(SensorSnapshot({s.name: s.initial for s in config.SENSORS}, time.monotonic()), None)
            self.assertEqual(len(w.analyzer.samples), 1)
            self.assertIsNone(w.analyzer.confirmed_state)
        finally:
            w.close()
            wait_until(lambda: not w.sensor_thread.isRunning())
            w.sensor_thread.wait()
            APP.processEvents()
if __name__ == '__main__':
    unittest.main()
