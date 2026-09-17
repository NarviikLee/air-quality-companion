"""Per-user OS lock shared by all copies/modes of the display application.

Never unlink the file: removing a locked inode can allow a second owner on Linux.
The kernel releases the lock when the descriptor/process closes, including crashes.
"""
import errno
import os
from pathlib import Path


def default_lock_path():
    return Path.home() / '.air-quality-display' / 'instance.lock'


class SingleInstance:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_lock_path()
        self.fd = None

    def acquire(self):
        if self.fd is not None:
            raise RuntimeError('This lock object already owns the lock')
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.set_inheritable(fd, False)
            if os.name == 'nt':
                import msvcrt
                # Locking beyond EOF is supported: no pre-lock writes or truncation.
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(fd)
            if error.errno in (errno.EACCES, errno.EAGAIN):
                return False
            raise
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        return True

    def release(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            try:
                if os.name == 'nt':
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
