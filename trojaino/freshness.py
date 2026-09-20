"""Tell the operator when their protection is old, without ever phoning home.

Three layers, none of which open a network connection:

1. Age. The build carries its own release date, so any copy can say how old it
   is with no connection, no catalog and no server. This is the only layer that
   always works, and it is the one that matters for a prepared plugin, which has
   no update mechanism of its own.
2. Advertised version. Claude Code already fetches and refreshes marketplace
   catalogs on the user's behalf. Reading what it has already written to disk
   turns "94 days old" into "0.3.0 is available". Those files are internal to
   Claude Code with no documented format, so every failure here is silent and
   falls back to layer 1.
3. Checking whether a newer release exists really does need the network, so it
   lives in `tjscan check-updates` and runs only when a person types it.

Nothing in this module may raise into a hook. A stale-reminder bug must never
stop a scan or a denial from working.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re

from trojaino._release import RELEASE_DATE

REMIND_AFTER_DAYS = 30
RELEASE_TAG = re.compile(r'v(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)')
_MAX_READ_BYTES = 1_000_000


def age_in_days(today: date | None = None) -> int | None:
    try:
        built = date.fromisoformat(RELEASE_DATE)
    except (TypeError, ValueError):
        return None
    current = today if today is not None else datetime.now(timezone.utc).date()
    return max((current - built).days, 0)


def _config_directory() -> Path:
    configured = os.environ.get('CLAUDE_CONFIG_DIR')
    return Path(configured) if configured else Path.home() / '.claude'


def _load(path: Path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > _MAX_READ_BYTES:
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def advertised_version(config_dir: Path | None = None, plugin: str = 'trojaino') -> str | None:
    """Newest version any locally cached catalog advertises. Never fetches."""
    try:
        base = config_dir if config_dir is not None else _config_directory()
        known = _load(base / 'plugins/known_marketplaces.json')
        if not isinstance(known, dict):
            return None
        found: list[str] = []
        for record in known.values():
            if not isinstance(record, dict):
                continue
            location = record.get('installLocation')
            if not isinstance(location, str) or not location:
                continue
            catalog = _load(Path(location) / '.claude-plugin/marketplace.json')
            if not isinstance(catalog, dict):
                continue
            for entry in catalog.get('plugins', []):
                if not isinstance(entry, dict) or entry.get('name') != plugin:
                    continue
                source = entry.get('source')
                ref = source.get('ref') if isinstance(source, dict) else None
                matched = RELEASE_TAG.fullmatch(ref) if isinstance(ref, str) else None
                if matched:
                    found.append(matched.group(1))
        return max(found, key=_version_key) if found else None
    except Exception:
        # Internal Claude Code files with no format guarantee: degrade silently.
        return None


def _version_key(version: str) -> tuple:
    head = version.split('-', 1)[0]
    return tuple(int(part) if part.isdigit() else 0 for part in head.split('.'))


def is_newer(candidate: str, current: str) -> bool:
    return _version_key(candidate) > _version_key(current)


def reminder(current_version: str, *, today: date | None = None,
             config_dir: Path | None = None) -> str | None:
    """One line for the operator, or None when there is nothing worth saying."""
    days = age_in_days(today)
    if days is None or days < REMIND_AFTER_DAYS:
        return None
    available = advertised_version(config_dir)
    if available and is_newer(available, current_version):
        return (f'Trojaino update available: this copy is {current_version}, built {days} days ago, '
                f'and a catalog on this machine advertises {available}. '
                'Tell the operator; do not update anything yourself.')
    return (f'Trojaino freshness: this copy is {current_version}, built {days} days ago, and its '
            'rule pack has not changed since. Suggest the operator run `tjscan check-updates` '
            '(which uses the network) to see whether a newer release exists.')


def _stamp_path() -> Path:
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
        return base / 'trojaino-pilot' / 'last-freshness-reminder'
    return Path.home() / '.local/state/trojaino-pilot' / 'last-freshness-reminder'


def due(today: date | None = None, stamp: Path | None = None) -> bool:
    """True at most once per REMIND_AFTER_DAYS. Any failure means stay quiet."""
    try:
        current = today if today is not None else datetime.now(timezone.utc).date()
        target = stamp if stamp is not None else _stamp_path()
        if target.is_file():
            last = date.fromisoformat(target.read_text(encoding='utf-8').strip()[:10])
            if (current - last).days < REMIND_AFTER_DAYS:
                return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(current.isoformat() + '\n', encoding='utf-8')
        return True
    except Exception:
        return False


def session_reminder(current_version: str, *, today: date | None = None,
                     config_dir: Path | None = None, stamp: Path | None = None) -> str:
    """Reminder text for a session hook, or '' — never raises."""
    try:
        if not due(today, stamp):
            return ''
        return reminder(current_version, today=today, config_dir=config_dir) or ''
    except Exception:
        return ''
