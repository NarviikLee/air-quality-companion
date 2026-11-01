"""systemd watchdog driven only by the GUI event loop (Python 3.7 / Qt 5)."""
import logging
import os
import socket
import time

from qt_compat import QTimer

LOG = logging.getLogger(__name__)
RECOVERY_GRACE_SECONDS = 10


def notify_systemd(address, message):
    if address.startswith('@'):
        address = '\0' + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
        channel.setblocking(False)
        channel.sendto(message.encode('utf-8'), address)


class ServiceWatchdog:
    def __init__(self, window, environment=None, sender=notify_systemd, clock=time.monotonic):
        self.window, self.sender, self.clock = window, sender, clock
        self.address = None
        self.withheld = False
        self.send_failed = False
        self.timer = QTimer(window)
        self.timer.timeout.connect(self.tick)
        environment = os.environ if environment is None else environment
        try:
            usec = int(environment.get('WATCHDOG_USEC', '0'))
            pid = int(environment.get('WATCHDOG_PID', str(os.getpid())))
        except ValueError:
            LOG.error('Invalid systemd watchdog environment')
            return
        address = environment.get('NOTIFY_SOCKET', '')
        if usec <= 0 or pid != os.getpid() or not address:
            return  # Normal desktop/manual execution needs no systemd dependency.
        if not address.startswith(('/', '@')):
            LOG.error('Invalid systemd notification socket')
            return
        self.address = address
        # Ping well within systemd's deadline, even with moderate UI scheduling jitter.
        self.timer.start(max(1, min(5000, usec // 3000)))
        LOG.info('Service watchdog enabled (timeout %.1fs)', usec / 1000000)
        self.tick()

    def tick(self):
        if self.address is None:
            return
        now = self.clock()
        window = self.window
        deadline = window.shutdown_deadline if window._closing else window.operation_deadline
        stalled = deadline is not None and now > deadline + RECOVERY_GRACE_SECONDS
        if stalled:
            if not self.withheld:
                LOG.error('Worker cleanup stalled; withholding watchdog heartbeat for service recovery')
                self.withheld = True
            return
        if self.withheld:
            LOG.info('Worker recovered; resuming watchdog heartbeat')
            self.withheld = False
        try:
            self.sender(self.address, 'WATCHDOG=1')
            self.send_failed = False
        except OSError as error:
            if not self.send_failed:
                LOG.error('Cannot send systemd watchdog heartbeat: %s', error)
            self.send_failed = True

    def stop(self):
        self.timer.stop()
