"""Filter OS-enumerated ports; never guess that a device exists."""
import re
import sys


def resolve_os_mode(mode, platform=None):
    mode = mode.strip().lower()
    if mode == 'auto':
        platform = sys.platform if platform is None else platform
        if platform == 'win32':
            return 'windows'
        if platform.startswith('linux'):
            return 'linux'
        raise ValueError(f'Unsupported serial platform: {platform}')
    if mode not in ('windows', 'linux'):
        raise ValueError('OS_MODE must be auto, windows or linux')
    return mode


def discover_ports(enumerator, mode):
    mode = resolve_os_mode(mode)
    # Preserve the exact device path supplied by pySerial when opening it.
    pattern = r'COM[1-9][0-9]*' if mode == 'windows' else r'/dev/tty[^/]+'
    names = {item.device for item in enumerator()
             if re.fullmatch(pattern, item.device, flags=re.IGNORECASE if mode == 'windows' else 0)}
    return sorted(names, key=lambda name: [int(part) if part.isdigit() else part
                                          for part in re.split(r'(\d+)', name)])
