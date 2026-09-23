import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import unittest
from unittest.mock import Mock, patch
from qt_compat import QApplication, QWidget, QTest
from service_watchdog import ServiceWatchdog, notify_systemd

APP = QApplication.instance() or QApplication([])


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.window = QWidget()
        self.window._closing = False
        self.window.shutdown_deadline = None
        self.window.operation_deadline = None
        self.environment = {'WATCHDOG_USEC': '30000000', 'NOTIFY_SOCKET': '/run/test-notify'}
        self.sender = Mock()
        self.clock = Mock(return_value=100)
        self.watchdog = ServiceWatchdog(self.window, self.environment, self.sender, self.clock)
        self.addCleanup(self.watchdog.stop)

    def test_waiting_and_repeated_timeouts_keep_heartbeat(self):
        # Completed timeout/no-port reads clear operation_deadline in MainWindow.
        for now in (100, 1000, 10000):
            self.clock.return_value = now
            self.watchdog.tick()
        self.assertEqual(self.sender.call_count, 4)

    def test_stalled_worker_withholds_then_recovery_resumes(self):
        self.window.operation_deadline = 100
        self.clock.return_value = 110
        self.watchdog.tick()
        before = self.sender.call_count
        self.clock.return_value = 111
        self.watchdog.tick()
        self.watchdog.tick()
        self.assertEqual(self.sender.call_count, before)
        self.window.operation_deadline = None
        self.watchdog.tick()
        self.assertEqual(self.sender.call_count, before + 1)

    def test_shutdown_gets_grace_but_not_infinite_heartbeat(self):
        self.window._closing = True
        self.window.shutdown_deadline = 103
        self.watchdog.tick()
        before = self.sender.call_count
        self.clock.return_value = 114
        self.watchdog.tick()
        self.assertEqual(self.sender.call_count, before)

    def test_manual_run_and_foreign_pid_disabled(self):
        for env in ({}, dict(self.environment, WATCHDOG_PID=str(os.getpid() + 1))):
            sender = Mock()
            watchdog = ServiceWatchdog(self.window, env, sender)
            self.assertFalse(watchdog.timer.isActive())
            watchdog.tick()
            sender.assert_not_called()

    def test_gui_event_loop_drives_heartbeat(self):
        self.watchdog.timer.setInterval(10)
        before = self.sender.call_count
        QTest.qWait(60)
        self.assertGreater(self.sender.call_count, before)

    def test_send_failure_can_recover(self):
        self.sender.side_effect = OSError('temporary failure')
        self.watchdog.tick()
        self.assertTrue(self.watchdog.send_failed)
        self.sender.side_effect = None
        self.watchdog.tick()
        self.assertFalse(self.watchdog.send_failed)

    def test_abstract_socket_message_and_nonblocking(self):
        with patch('service_watchdog.socket.AF_UNIX', 1, create=True), patch('service_watchdog.socket.socket') as factory:
            channel = factory.return_value.__enter__.return_value
            notify_systemd('@watchdog-test', 'WATCHDOG=1')
            channel.setblocking.assert_called_once_with(False)
            channel.sendto.assert_called_once_with(b'WATCHDOG=1', '\0watchdog-test')

    def test_real_window_no_port_is_healthy(self):
        from dashboard import MainWindow
        from sensor_data import PortUnavailableError
        class NoPortSource:
            def read(self):
                raise PortUnavailableError('No serial ports found')
        window = MainWindow(NoPortSource)
        sender = Mock()
        watchdog = ServiceWatchdog(window, self.environment, sender)
        watchdog.timer.setInterval(10)
        try:
            QTest.qWait(200)
            self.assertIsNone(window.operation_deadline)
            self.assertIsNotNone(window.retry_deadline)
            self.assertGreater(sender.call_count, 1)
            self.assertFalse(watchdog.withheld)
        finally:
            watchdog.stop()
            window.close()
            for _ in range(100):
                QTest.qWait(20)
                if not window.sensor_thread.isRunning():
                    break
            self.assertFalse(window.sensor_thread.isRunning())
            window.sensor_thread.wait()
            APP.processEvents()


if __name__ == '__main__':
    unittest.main()
