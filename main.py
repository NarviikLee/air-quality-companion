"""Run fullscreen by default; use --windowed for a desktop window."""
import sys
import logging
import signal
from qt_compat import QApplication, run_app, BINDING, QtCore
from service_watchdog import ServiceWatchdog
from single_instance import SingleInstance

FULLSCREEN = True


class ShutdownSignals:
    """Defer OS termination requests to Qt's normal window-close path."""

    def __init__(self, window):
        self.window = window
        self.pending = None
        self.requested = False
        self.previous = {}
        self.timer = QtCore.QTimer(window)
        self.timer.timeout.connect(self.poll)
        for signum in (signal.SIGTERM, signal.SIGINT):
            self.previous[signum] = signal.signal(signum, self.receive)
        # Regular Python callbacks let CPython dispatch signals while Qt is idle.
        self.timer.start(100)

    def receive(self, signum, frame):
        # Do not call Qt or logging from the signal handler itself.
        self.pending = signum

    def poll(self):
        if self.pending is not None and not self.requested:
            self.requested = True
            logging.info('Shutdown requested by signal %s; cleaning up sensor worker', self.pending)
            self.window.close()

    def restore(self):
        self.timer.stop()
        for signum, previous in self.previous.items():
            signal.signal(signum, previous)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    # Keep the descriptor alive until process exit, including startup failure.
    instance_lock = SingleInstance()
    try:
        acquired = instance_lock.acquire()
    except OSError:
        logging.exception('Cannot acquire application lock; refusing to start')
        sys.exit(1)
    if not acquired:
        logging.warning('Air Quality Display is already running; duplicate launch ignored.')
        sys.exit(0)  # A service start while a manual instance owns the lock must not loop.
    demo_states = '--demo-states' in sys.argv
    if '--demo' in sys.argv or demo_states:
        import sensor_data
        sensor_data.SOURCE_MODE = 'demo'
    from dashboard import MainWindow
    logging.info('Python %s / %s / Qt %s', sys.version.split()[0], BINDING, QtCore.qVersion())
    app = QApplication(sys.argv)
    window = MainWindow(demo_states=demo_states)
    shutdown_signals = ShutdownSignals(window)
    service_watchdog = ServiceWatchdog(window)
    if '--windowed' not in sys.argv and (FULLSCREEN or '--fullscreen' in sys.argv):
        window.showFullScreen()
    else:
        window.show()
    try:
        exit_code = run_app(app)
    finally:
        service_watchdog.stop()
        shutdown_signals.restore()
    logging.info('Application stopped (exit code %s)', exit_code)
    instance_lock.release()
    sys.exit(exit_code)
