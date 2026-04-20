"""
Reads /boot/lockin.conf (or a local fallback) to get server_url and api_key.

The /boot partition is FAT32 and visible on any OS without SSH — the user
just drops the file there after downloading it from the dashboard Settings page.
"""

import configparser
import sys
from pathlib import Path

_SEARCH_PATHS = [
    Path('/boot/lockin.conf'),
    Path('/boot/firmware/lockin.conf'),   # Ubuntu 22.04 on Pi
    Path(__file__).parent / 'lockin.conf',  # local dev fallback
]


def load() -> dict:
    cfg = configparser.ConfigParser()

    found = None
    for p in _SEARCH_PATHS:
        if p.exists():
            cfg.read(p)
            found = p
            break

    if found is None:
        print(
            '[LockIn] ERROR: lockin.conf not found.\n'
            '  Download it from the dashboard Settings page and copy to /boot/lockin.conf',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        return {
            'server_url': cfg.get('lockin', 'server_url').rstrip('/'),
            'api_key':    cfg.get('lockin', 'api_key').strip(),
        }
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        print(f'[LockIn] ERROR: malformed lockin.conf — {e}', file=sys.stderr)
        sys.exit(1)
