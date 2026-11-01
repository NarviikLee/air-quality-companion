"""Run real termination signals in an isolated Qt process."""
import os
import subprocess
import sys
import unittest
from pathlib import Path


class ShutdownSignalTests(unittest.TestCase):
    def test_signals_close_busy_worker_cleanly(self):
        for name in ('SIGTERM', 'SIGINT'):
            with self.subTest(signal=name):
                code = r'''
import os, signal, threading
from qt_compat import QApplication, QTimer, run_app
from dashboard import MainWindow
from main import ShutdownSignals
from sensor_data import DataUnavailableError

app = QApplication([])
started = threading.Event()
sources = []
class Source:
    def __init__(self):
        self.closed = False
        self.owner = threading.get_ident()
        sources.append(self)
    def configure_worker(self, cancel_event, checking):
        self.cancel = cancel_event
    def read(self):
        started.set()
        self.cancel.wait(5)
        raise DataUnavailableError('cancelled')
    def close(self):
        assert threading.get_ident() == self.owner
        self.closed = True

window = MainWindow(Source)
bridge = ShutdownSignals(window)
window.show()
def send_signal():
    if not started.is_set():
        QTimer.singleShot(20, send_signal)
        return
    signum = getattr(signal, 'SIGNAL_NAME')
    if os.name == 'posix':
        os.kill(os.getpid(), signum)
    else:
        signal.raise_signal(signum)
    # Repeated requests must not restart or bypass cleanup.
    bridge.receive(signum, None)
QTimer.singleShot(20, send_signal)
QTimer.singleShot(8000, lambda: os._exit(9))
result = run_app(app)
bridge.restore()
assert result == 0
assert bridge.requested
assert sources and sources[0].closed
assert not window.sensor_thread.isRunning()
assert not window.isVisible()
print('PASS: signal -> closeEvent -> worker cleanup -> exit 0')
'''.replace('SIGNAL_NAME', name)
                environment = dict(os.environ, QT_QPA_PLATFORM='offscreen')
                result = subprocess.run([sys.executable, '-c', code],
                    cwd=str(Path(__file__).resolve().parents[1]), env=environment,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12)
                self.assertEqual(result.returncode, 0, repr(result.stdout + result.stderr))
                self.assertIn(b'PASS:', result.stdout)


if __name__ == '__main__':
    unittest.main()
