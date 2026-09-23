"""Real multi-process lock tests; no sensor or running desktop required."""
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from single_instance import SingleInstance

ROOT = Path(__file__).resolve().parents[1]
CONTENDER = '''
import sys
from single_instance import SingleInstance
sys.stdin.readline()
guard = SingleInstance(sys.argv[1])
owned = guard.acquire()
print('OWNER' if owned else 'DUPLICATE', flush=True)
if owned:
    sys.stdin.readline()
'''


class InstanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(ROOT), prefix='lock-test-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.path = self.home / 'instance.lock'

    def test_same_process_second_descriptor_denied(self):
        first, second = SingleInstance(self.path), SingleInstance(self.path)
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
        finally:
            first.release()
            second.release()

    def test_existing_file_is_not_a_stale_lock(self):
        self.path.write_text('left from an old process')
        guard = SingleInstance(self.path)
        try:
            self.assertTrue(guard.acquire())
            self.assertFalse(os.get_inheritable(guard.fd))
        finally:
            guard.release()
        self.assertTrue(self.path.exists())
        self.assertEqual(self.path.read_text(), 'left from an old process')

    def test_lock_path_error_fails_instead_of_running_unlocked(self):
        self.path.mkdir()
        with self.assertRaises(OSError):
            SingleInstance(self.path).acquire()

    def test_simultaneous_processes_exactly_one_owner_and_crash_release(self):
        processes = [subprocess.Popen([sys.executable, '-u', '-c', CONTENDER, str(self.path)],
                     cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, universal_newlines=True) for _ in range(12)]
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=12)
        try:
            reads = [pool.submit(p.stdout.readline) for p in processes]
            for p in processes:
                p.stdin.write('go\n')
                p.stdin.flush()
            results = [f.result(timeout=15).strip() for f in reads]
            self.assertEqual(results.count('OWNER'), 1, results)
            self.assertEqual(results.count('DUPLICATE'), 11, results)
            owner = processes[results.index('OWNER')]
            owner.kill()
            owner.wait(timeout=5)
            replacement = SingleInstance(self.path)
            try:
                # Windows may finish process teardown before releasing byte locks.
                deadline = time.monotonic() + 3
                acquired = replacement.acquire()
                while not acquired and time.monotonic() < deadline:
                    time.sleep(.02)
                    acquired = replacement.acquire()
                self.assertTrue(acquired)
            finally:
                replacement.release()
        finally:
            for p in processes:
                if p.poll() is None:
                    p.kill()
                p.communicate(timeout=5)
            pool.shutdown(wait=True)

    def test_clean_process_exit_releases(self):
        result = subprocess.run([sys.executable, '-c',
            'from single_instance import SingleInstance; import sys; '
            'guard=SingleInstance(sys.argv[1]); assert guard.acquire()', str(self.path)],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        guard = SingleInstance(self.path)
        try:
            self.assertTrue(guard.acquire())
        finally:
            guard.release()

    def test_app_duplicate_exits_before_gui_and_serial_for_all_modes(self):
        guard = SingleInstance(self.home / '.air-quality-display' / 'instance.lock')
        self.assertTrue(guard.acquire())
        # Isolate the per-user lock without writing to the real user's home.
        environment = dict(os.environ, USERPROFILE=str(self.home), HOME=str(self.home),
                           QT_QPA_PLATFORM='intentionally-invalid-platform')
        try:
            for args in ([], ['--demo'], ['--fullscreen'], ['--demo', '--windowed']):
                result = subprocess.run([sys.executable, str(ROOT / 'main.py')] + args,
                    cwd=str(self.home), env=environment, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(b'already running', result.stderr)
                self.assertNotIn(b'Serial port', result.stderr)
                self.assertNotIn(b'Python 3.', result.stderr)
        finally:
            guard.release()

    def test_old_file_time_does_not_expire_live_lock(self):
        os.utime(self.home, (1, 1))
        owner = SingleInstance(self.path)
        try:
            self.assertTrue(owner.acquire())
            os.utime(self.path, (1, 1))
            other = SingleInstance(self.path)
            try:
                self.assertFalse(other.acquire())
            finally:
                other.release()
        finally:
            owner.release()

    def test_app_lock_failure_refuses_start(self):
        (self.home / '.air-quality-display').write_text('not a directory')
        environment = dict(os.environ, USERPROFILE=str(self.home), HOME=str(self.home),
                           QT_QPA_PLATFORM='intentionally-invalid-platform')
        result = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--demo'],
            cwd=str(ROOT), env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(b'refusing to start', result.stderr)

    def test_live_demo_blocks_real_mode_and_releases_after_kill(self):
        environment = dict(os.environ, USERPROFILE=str(self.home), HOME=str(self.home),
                           QT_QPA_PLATFORM='offscreen', PYTHONUNBUFFERED='1')
        for key in ('WATCHDOG_USEC', 'WATCHDOG_PID', 'NOTIFY_SOCKET'):
            environment.pop(key, None)
        log_path = self.home / 'app.log'
        with log_path.open('wb') as output:
            owner = subprocess.Popen([sys.executable, str(ROOT / 'main.py'), '--demo', '--windowed'],
                cwd=str(self.home), env=environment, stdout=output, stderr=output)
            try:
                deadline = time.monotonic() + 10
                while b'Python ' not in log_path.read_bytes():
                    self.assertIsNone(owner.poll(), log_path.read_bytes())
                    self.assertLess(time.monotonic(), deadline, log_path.read_bytes())
                    time.sleep(.05)
                duplicate = subprocess.run([sys.executable, str(ROOT / 'main.py')],
                    cwd=str(ROOT), env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
                self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
                self.assertIn(b'already running', duplicate.stderr)
                self.assertIsNone(owner.poll(), log_path.read_bytes())
            finally:
                if owner.poll() is None:
                    owner.kill()
                owner.wait(timeout=5)
        guard = SingleInstance(self.home / '.air-quality-display' / 'instance.lock')
        try:
            deadline = time.monotonic() + 3
            acquired = guard.acquire()
            while not acquired and time.monotonic() < deadline:
                time.sleep(.02)
                acquired = guard.acquire()
            self.assertTrue(acquired)
        finally:
            guard.release()


if __name__ == '__main__':
    unittest.main()
