"""Conservative portable names; validate before host path normalization."""
import re
from pathlib import PureWindowsPath


def valid_component(name):
    stem = name.split('.')[0].rstrip(' ').upper()
    return bool(name and name not in {'.', '..'} and not name.endswith((' ', '.'))
                and not any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)
                and not any(0xD800 <= ord(c) <= 0xDFFF for c in name)
                and len(name.encode('utf-16-le')) // 2 <= 255
                and stem not in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}
                and not re.fullmatch(r'(COM|LPT)[1-9¹²³]', stem))


def windows_path(value):
    """Only ordinary absolute local drive paths; no UNC/device/ADS/aliases."""
    value = str(value)
    if not re.match(r'^[A-Za-z]:[\\/]', value):
        raise ValueError('unsafe_windows_path')
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError('unsafe_windows_path')
    if len(value.encode('utf-16-le')) // 2 >= 240:
        raise ValueError('unsupported_windows_path_length')
    # Do not let PurePath silently collapse dot or repeated separators.
    pieces = re.split(r'[\\/]', value[3:]) if value[3:] else []
    if any(not valid_component(p) for p in pieces):
        raise ValueError('unsafe_windows_path')
    return PureWindowsPath(value)
