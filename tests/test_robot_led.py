import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from qt_compat import QApplication, QTest, Qt
from air_quality_analyzer import AirQualityAnalyzer
from robot_led import RobotLedController, RobotDisplayState as R
from tests.test_air_quality_analyzer import GOOD
from tests.test_sensor_worker import wait_until
from sensor_worker import SensorSnapshot
import sensor_data as config
from dashboard import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class RobotTests(unittest.TestCase):
    def test_long_disconnect_returns_detail_home_but_short_recovery_keeps_page(self):
        class Source:
            def read(self):
                return {s.name: s.initial for s in config.SENSORS}, None
        w = MainWindow(Source)
        try:
            wait_until(lambda: not w._busy)
            w.data_timer.stop()
            now = w.last_received_at
            w.show_sensor_detail()
            w.on_failed('no_port', 'USB unplugged')
            with patch('dashboard.time.monotonic', return_value=now + 29.9):
                w.check_worker_health()
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            values = {s.name: s.initial for s in config.SENSORS}
            w.on_received(SensorSnapshot(values, now + 29.9), None)
            with patch('dashboard.time.monotonic', return_value=now + 30):
                w.check_worker_health()
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            w.on_failed('no_port', 'USB unplugged again')
            with patch('dashboard.time.monotonic', return_value=now + 60):
                w.check_worker_health()
            self.assertIs(w.pages.currentWidget(), w.robot_home_page)
            self.assertEqual(w.robot_home_page.display_state, R.SENSOR_CHECK)
            self.assertFalse(w.detail_return_timer.isActive())
            w.on_received(SensorSnapshot(values, now + 61), None)
            self.assertIs(w.pages.currentWidget(), w.robot_home_page)
        finally:
            w.close()
            wait_until(lambda: not w.sensor_thread.isRunning())
            w.sensor_thread.wait()
            APP.processEvents()

    def test_disconnect_face_hold_expires_and_reconnect_uses_fresh_window(self):
        class Source:
            def read(self):
                return {s.name: s.initial for s in config.SENSORS}, None
        w = MainWindow(Source)
        try:
            wait_until(lambda: not w._busy)
            w.data_timer.stop()
            now = time.monotonic()
            w.analyzer.reset()
            for t in range(41):
                w.analyzer.accept_sample(GOOD, now - 40 + t)
            w.last_received_at = now
            w.refresh_robot()
            w.on_failed('no_port', 'USB unplugged')
            self.assertEqual(w.robot_home_page.display_state, R.COMFORTABLE)
            self.assertTrue(all(state.text() == '수신 지연' for _, state in w.gauges.values()))
            with patch('dashboard.time.monotonic', return_value=now + 31):
                w.refresh_robot()
                self.assertEqual(w.robot_home_page.display_state, R.SENSOR_CHECK)
            values = {s.name: s.initial for s in config.SENSORS}
            w.on_received(SensorSnapshot(values, now + 32), None)
            self.assertTrue(w.analyzer.reconnect_mode)
            self.assertIsNone(w.analyzer.confirmed_state)
            self.assertEqual(len(w.analyzer.samples), 1)
            self.assertEqual(w.robot_home_page.display_state, R.MONITORING)
            w.on_failed('no_port', 'USB unplugged again')
            w.on_received(SensorSnapshot(values, now + 33), None)
            self.assertEqual(len(w.analyzer.samples), 1)
        finally:
            w.close()
            wait_until(lambda: not w.sensor_thread.isRunning())
            w.sensor_thread.wait()
            APP.processEvents()

    def test_press_navigation_release_and_animation_lifecycle(self):
        class Source:
            def read(self):
                return {s.name: s.initial for s in config.SENSORS}, None
        w = MainWindow(Source)
        w.show()
        try:
            wait_until(lambda: not w._busy)
            w.data_timer.stop()
            face = w.robot_home_page.face
            self.assertTrue(face.animation_timer.isActive())
            for target in (face, w.robot_home_page.title, w.robot_home_page):
                QTest.mousePress(target, Qt.LeftButton)
                self.assertIs(w.pages.currentWidget(), w.dashboard_page)
                self.assertFalse(face.animation_timer.isActive())
                QTest.mouseRelease(w.dashboard_page, Qt.LeftButton)
                self.assertIs(w.pages.currentWidget(), w.dashboard_page)
                QTest.mousePress(w.gauges['PM1.0'][0].number, Qt.LeftButton)
                self.assertIs(w.pages.currentWidget(), w.robot_home_page)
                QTest.mouseRelease(face, Qt.LeftButton)
                self.assertIs(w.pages.currentWidget(), w.robot_home_page)
                self.assertTrue(face.animation_timer.isActive())
                self.assertFalse(w.detail_return_timer.isActive())
            started = face.animation_started_at
            w.refresh_robot()
            self.assertEqual(face.animation_started_at, started)
        finally:
            w.close()
            wait_until(lambda: not w.sensor_thread.isRunning())
            w.sensor_thread.wait()
            APP.processEvents()
        self.assertFalse(face.animation_timer.isActive())

    def test_detail_timeout_config_falls_back_safely(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'app_config.ini'
            self.assertEqual(config._sensor_detail_timeout_sec(path), 5.0)
            path.write_text('[ui]\nsensor_detail_timeout_sec = 8\n', encoding='utf-8')
            self.assertEqual(config._sensor_detail_timeout_sec(path), 8.0)
            path.write_text('[ui\nsensor_detail_timeout_sec = 8\n', encoding='utf-8')
            self.assertEqual(config._sensor_detail_timeout_sec(path), 5.0)
            path.write_text('[ui]\nsensor_detail_timeout_sec = invalid\n', encoding='utf-8')
            self.assertEqual(config._sensor_detail_timeout_sec(path), 5.0)
            path.write_text('[ui]\nsensor_detail_timeout_sec = 0\n', encoding='utf-8')
            self.assertEqual(config._sensor_detail_timeout_sec(path), 5.0)
            path.write_text('[ui]\nsensor_detail_timeout_sec = inf\n', encoding='utf-8')
            self.assertEqual(config._sensor_detail_timeout_sec(path), 5.0)
            path.write_text('[ui]\nsensor_detail_timeout_sec = 2147484\n', encoding='utf-8')
            self.assertEqual(config._sensor_detail_timeout_sec(path), 5.0)

    def test_demo_states_cycle_through_every_expression(self):
        class Source:
            def read(self):
                return {s.name: s.initial for s in config.SENSORS}, None
        w = MainWindow(Source, demo_states=True)
        try:
            wait_until(lambda: not w._busy)
            w.data_timer.stop()
            w.demo_state_timer.stop()
            seen = []
            for _ in range(len(R)):
                seen.append(w.robot_home_page.display_state)
                w.show_next_demo_state()
            self.assertEqual(seen, [R.SENSOR_CHECK, R.MONITORING, R.NORMAL, R.BAD,
                                    R.COMFORTABLE, R.MOVING, R.PURIFYING])
            self.assertEqual(w.robot_home_page.display_state, R.SENSOR_CHECK)
        finally:
            w.close()
            wait_until(lambda: not w.sensor_thread.isRunning())
            w.sensor_thread.wait()
            APP.processEvents()

    def test_purifying_is_display_only_and_sensor_check_has_priority(self):
        analyzer, controller = AirQualityAnalyzer(), RobotLedController()
        controller.set_purifying(True)
        self.assertEqual(controller.resolve(analyzer)[0], R.SENSOR_CHECK)
        analyzer.accept_sample(GOOD, 0)
        self.assertEqual(controller.resolve(analyzer)[0], R.PURIFYING)
        controller.set_purifying(False)
        self.assertEqual(controller.resolve(analyzer)[0], R.MONITORING)

    def test_partial_channel_failure_does_not_change_robot_face(self):
        analyzer, controller = AirQualityAnalyzer(), RobotLedController()
        for timestamp in range(41):
            analyzer.accept_sample(GOOD, timestamp)
        expected = controller.resolve(analyzer)[:2]
        for timestamp in range(41, 46):
            analyzer.accept_sample(dict(GOOD, Humidity=None), timestamp)
        self.assertEqual(controller.resolve(analyzer)[:2], expected)
        self.assertEqual(analyzer.channel_display_status('Humidity'), 'checking')

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
            a.accept_sample(dict(GOOD, **{'PM2.5': 1000}), 41)
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
            QTest.mouseClick(w.robot_home_page.title, Qt.LeftButton)
            w.show_sensor_detail()
            self.assertIs(w.pages.currentWidget(), w.robot_home_page)
            self.assertFalse(w.robot_home_page.face.isEnabled())
            w.analyzer.accept_sample(GOOD, time.monotonic())
            w.refresh_robot()
            self.assertTrue(w.robot_home_page.face.isEnabled())
            QTest.mouseClick(w.robot_home_page.title, Qt.LeftButton)
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            self.assertTrue(w.detail_return_timer.isActive())
            self.assertEqual(w.detail_return_timer.interval(), config.SENSOR_DETAIL_TIMEOUT_SEC * 1000)
            self.assertTrue(w.home_button.isHidden())
            values = {s.name: s.initial for s in config.SENSORS}
            w.analyzer.reset()
            start = time.monotonic() - 40
            for t in range(41):
                w.analyzer.accept_sample(GOOD, start + t)
            snapshot = SensorSnapshot(dict(values, VOC=None), time.monotonic())
            w.on_received(snapshot, None)
            self.assertIsNone(w.gauges['VOC'][0].value)
            self.assertTrue(all(not gauge.toolTip() and not state.toolTip()
                                for gauge, state in w.gauges.values()))
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            self.assertEqual(w.analyzer.confirmed_state, 0)
            w.on_failed('waiting', 'timeout')
            self.assertEqual(w.analyzer.confirmed_state, 0)
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            self.assertTrue(all(state.text() == '수신 지연'
                                for _, state in w.gauges.values()))
            w.refresh_reception_status(time.monotonic())
            self.assertIn('수신 지연', w.connection_label.text())
            w.on_failed('waiting', 'timeout')
            w.on_failed('waiting', 'timeout')
            self.assertEqual(w.robot_home_page.display_state, R.COMFORTABLE)
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            QTest.mouseClick(w.gauges['PM1.0'][0], Qt.LeftButton)
            self.assertIs(w.pages.currentWidget(), w.robot_home_page)
            self.assertFalse(w.detail_return_timer.isActive())
            self.assertTrue(w.robot_home_page.face.isEnabled())
            QTest.mouseClick(w.robot_home_page.face, Qt.LeftButton)
            self.assertIs(w.pages.currentWidget(), w.robot_home_page)
        finally:
            w.close()
            wait_until(lambda: not w.sensor_thread.isRunning())
            w.sensor_thread.wait()
            APP.processEvents()

    def test_sensor_detail_returns_after_timeout(self):
        class Source:
            def read(self):
                return {s.name: s.initial for s in config.SENSORS}, None
        w = MainWindow(Source)
        try:
            wait_until(lambda: not w._busy)
            w.data_timer.stop()
            w.show_sensor_detail()
            self.assertIs(w.pages.currentWidget(), w.dashboard_page)
            w.detail_return_timer.start(20)
            QTest.qWait(50)
            self.assertIs(w.pages.currentWidget(), w.robot_home_page)
            self.assertFalse(w.detail_return_timer.isActive())
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
            self.assertTrue(all(state.text() == '수신 지연'
                                for _, state in w.gauges.values()))
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
