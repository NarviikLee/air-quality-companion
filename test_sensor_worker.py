"""Thread integration checks without hardware."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import threading
import time
import unittest
from qt_compat import QTimer
from qt_compat import QTest
from qt_compat import QApplication
import dashboard
from sensor_data import SENSORS

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


def wait_until(predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(20)
    assert predicate(), 'Timed out'


class SlowSource:
    def __init__(self):
        self.threads = [threading.get_ident()]
        self.calls = 0
        self.closed = False

    def read(self):
        self.calls += 1
        self.threads.append(threading.get_ident())
        time.sleep(.3)
        return {s.name: s.initial for s in SENSORS}, 24

    def close(self):
        self.threads.append(threading.get_ident())
        self.closed = True


class WorkerTests(unittest.TestCase):
    def create(self, factory):
        window = dashboard.MainWindow(factory)
        window.show()
        self.addCleanup(lambda: self.shutdown(window))
        return window

    def shutdown(self, window):
        window.close()
        wait_until(lambda: not window.sensor_thread.isRunning())
        window.sensor_thread.wait()
        APP.processEvents()

    def test_responsive_no_overlap_and_same_thread_cleanup(self):
        sources = []
        def factory():
            source = SlowSource()
            sources.append(source)
            return source
        window = self.create(factory)
        pulses = []
        timer = QTimer()
        timer.timeout.connect(lambda: pulses.append(1))
        timer.start(20)
        for _ in range(10):
            window.update_sensors()
        QTest.qWait(160)
        self.assertGreater(len(pulses), 2)
        self.assertTrue(window._busy)
        self.assertEqual(sources[0].calls, 1)
        # Closing during a read must not block the GUI or destroy a live thread.
        window.close()
        self.assertTrue(window._closing)
        wait_until(lambda: not window.sensor_thread.isRunning())
        timer.stop()
        self.assertTrue(sources[0].closed)
        self.assertEqual(len(set(sources[0].threads)), 1)
        self.assertNotEqual(sources[0].threads[0], threading.get_ident())

    def test_crc_failure_retries_and_recovers(self):
        class Source(SlowSource):
            def read(self):
                self.calls += 1
                if self.calls == 1:
                    raise ValueError('CRC mismatch')
                return {s.name: s.initial for s in SENSORS}, 24
        window = self.create(Source)
        wait_until(lambda: bool(window.last_error))
        self.assertIn('CRC', window.last_error)
        self.assertTrue(window.data_timer.isActive())
        self.assertIs(window.pages.currentWidget(), window.robot_home_page)
        wait_until(lambda: not window.analyzer.sensor_check, 4)
        self.assertEqual(window.last_error, '')

    def test_incomplete_snapshot_is_waiting(self):
        class Source(SlowSource):
            def read(self):
                return {}, 24
        window = self.create(Source)
        wait_until(lambda: bool(window.last_error))
        self.assertIn('KeyError', window.last_error)
        self.assertTrue(window.data_timer.isActive())

    def test_serial_snapshot_displays_without_fake_main_score(self):
        from types import SimpleNamespace
        from serial_source import SerialSensorSource
        from test_serial_source import RAW, Port
        device = 'COM1' if os.name == 'nt' else '/dev/ttyUSB0'
        window = self.create(lambda: SerialSensorSource(
            ports=lambda: [SimpleNamespace(device=device)],
            opener=lambda **kwargs: Port(kwargs['port']),
            reader=lambda port, cancel_event=None: RAW.copy()))
        wait_until(lambda: not window.analyzer.sensor_check)
        self.assertEqual(window.main_gauge.status, 'MAIN')
        self.assertEqual(window.gauges['Temperature'][0].value, 24.5)

    def test_unexpected_thread_exit_closes_source_and_restarts(self):
        sources = []
        def factory():
            source = SlowSource()
            sources.append(source)
            return source
        window = self.create(factory)
        wait_until(lambda: not window._busy)
        window.data_timer.stop()
        window.sensor_thread.quit()
        wait_until(lambda: window._recovering)
        self.assertTrue(sources[0].closed)
        self.assertIs(window.pages.currentWidget(), window.robot_home_page)
        wait_until(lambda: len(sources) == 2 and not window._busy, 5)
        self.assertIs(window.pages.currentWidget(), window.robot_home_page)

    def test_cooperative_cancellation_on_close(self):
        class Source(SlowSource):
            def configure_worker(self, event, checking):
                self.event = event
            def read(self):
                self.event.wait(10)
                return {s.name: s.initial for s in SENSORS}, 24
        window = self.create(Source)
        QTest.qWait(100)
        start = time.monotonic()
        window.close()
        wait_until(lambda: not window.sensor_thread.isRunning(), 2)
        self.assertLess(time.monotonic() - start, 2)

    def test_no_port_retry_does_not_show_waiting_before_discovery(self):
        from sensor_data import PortUnavailableError
        class Source(SlowSource):
            def read(self):
                time.sleep(.1)
                raise PortUnavailableError('No ports')
        window = self.create(Source)
        wait_until(lambda: not window._busy)
        title = window.connection_title.text()
        window.update_sensors()
        self.assertEqual(window.connection_title.text(), title)
        wait_until(lambda: not window._busy)
        self.assertEqual(window.connection_title.text(), title)

    def test_deadline_cancels_stalled_read_then_recovers(self):
        sources = []
        class Source(SlowSource):
            def configure_worker(self, event, checking):
                self.event = event
            def read(self):
                if self is sources[0]:
                    self.event.wait(10)
                return {s.name: s.initial for s in SENSORS}, 24
        def factory():
            source = Source()
            sources.append(source)
            return source
        window = self.create(factory)
        wait_until(lambda: bool(sources))
        window.operation_deadline = time.monotonic() - 1
        window.check_worker_health()
        self.assertTrue(window._recovering)
        wait_until(lambda: len(sources) == 2 and not window._busy, 5)
        self.assertTrue(sources[0].closed)
        self.assertIs(window.pages.currentWidget(), window.robot_home_page)


if __name__ == '__main__':
    unittest.main()
