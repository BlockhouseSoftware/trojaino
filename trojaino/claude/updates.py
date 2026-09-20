"""Ask PyPI whether a newer Trojaino exists. The only part that uses the network.

Runs solely when a person types `tjscan check-updates`. It announces the host it
is about to contact before contacting it, sends no identifying information
beyond an ordinary HTTPS request, and reports plainly when it cannot reach the
index rather than failing loudly.
"""
from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

INDEX_HOST = 'pypi.org'
INDEX_URL = f'https://{INDEX_HOST}/pypi/trojaino/json'
TIMEOUT_SECONDS = 15
_MAX_BYTES = 5_000_000


def latest_released_version(url: str = INDEX_URL, timeout: int = TIMEOUT_SECONDS) -> str:
    request = Request(url, headers={'Accept': 'application/json'})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https index URL
        document = json.loads(response.read(_MAX_BYTES).decode('utf-8'))
    version = document.get('info', {}).get('version')
    if not isinstance(version, str) or not version:
        raise ValueError('package index returned no version')
    return version


def check(current_version: str, *, url: str = INDEX_URL) -> dict:
    """Never raises: the caller reports 'reachable' rather than crashing."""
    from trojaino.freshness import advertised_version, age_in_days, is_newer

    outcome = {
        'current': current_version,
        'age_days': age_in_days(),
        'advertised_locally': advertised_version(),
        'latest': None,
        'newer_available': None,
        'reachable': True,
        'error': None,
    }
    try:
        outcome['latest'] = latest_released_version(url)
        outcome['newer_available'] = is_newer(outcome['latest'], current_version)
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        outcome['reachable'] = False
        outcome['error'] = str(exc)[:200]
    return outcome
