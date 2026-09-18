"""Native Win32 boundary. Local NTFS only; failed capability checks deny.

Handles pin every ancestor against rename/deletion and reject reparse points.
Files are held without write/delete sharing while inspected. No POSIX emulation,
chmod security assumption, path-based lstat fallback, or shell commands.
"""
from contextlib import contextmanager, ExitStack
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import time
import unicodedata
import uuid
from trojaino.preflight_paths import valid_component, windows_path

if os.name != 'nt':
    raise OSError('Win32 backend requires native Windows')

K = C.WinDLL('kernel32', use_last_error=True)
A = C.WinDLL('advapi32', use_last_error=True)
INVALID = C.c_void_p(-1).value


def bind(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = result, list(args)
    return fn


class FileInfo(C.Structure):
    _fields_ = [('attributes', W.DWORD), ('creation', W.FILETIME),
                ('access', W.FILETIME), ('write', W.FILETIME),
                ('volume', W.DWORD), ('size_hi', W.DWORD), ('size_lo', W.DWORD),
                ('links', W.DWORD), ('index_hi', W.DWORD), ('index_lo', W.DWORD)]


class StreamInfo(C.Structure):
    _fields_ = [('size', C.c_longlong), ('name', W.WCHAR * 296)]


class SecurityAttributes(C.Structure):
    _fields_ = [('length', W.DWORD), ('descriptor', W.LPVOID), ('inherit', W.BOOL)]


class BasicLimits(C.Structure):
    _fields_ = [('process_time', C.c_longlong), ('job_time', C.c_longlong),
                ('flags', W.DWORD), ('min_working', C.c_size_t), ('max_working', C.c_size_t),
                ('active', W.DWORD), ('affinity', C.c_size_t), ('priority', W.DWORD),
                ('scheduling', W.DWORD)]


class IoCounters(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in
                ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimits(C.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IoCounters),
                ('process_memory', C.c_size_t), ('job_memory', C.c_size_t),
                ('peak_process', C.c_size_t), ('peak_job', C.c_size_t)]


create_file = bind(K, 'CreateFileW', W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD,
                   W.LPVOID, W.DWORD, W.DWORD, W.HANDLE)
close = bind(K, 'CloseHandle', W.BOOL, W.HANDLE)
get_info = bind(K, 'GetFileInformationByHandle', W.BOOL, W.HANDLE, C.POINTER(FileInfo))
read_file = bind(K, 'ReadFile', W.BOOL, W.HANDLE, W.LPVOID, W.DWORD, C.POINTER(W.DWORD), W.LPVOID)
write_file = bind(K, 'WriteFile', W.BOOL, W.HANDLE, W.LPCVOID, W.DWORD, C.POINTER(W.DWORD), W.LPVOID)
first_stream = bind(K, 'FindFirstStreamW', W.HANDLE, W.LPCWSTR, C.c_int, C.POINTER(StreamInfo), W.DWORD)
next_stream = bind(K, 'FindNextStreamW', W.BOOL, W.HANDLE, C.POINTER(StreamInfo))
find_close = bind(K, 'FindClose', W.BOOL, W.HANDLE)
create_directory = bind(K, 'CreateDirectoryW', W.BOOL, W.LPCWSTR, C.POINTER(SecurityAttributes))
convert_sd = bind(A, 'ConvertStringSecurityDescriptorToSecurityDescriptorW', W.BOOL,
                  W.LPCWSTR, W.DWORD, C.POINTER(W.LPVOID), C.POINTER(W.DWORD))
local_free = bind(K, 'LocalFree', W.HLOCAL, W.HLOCAL)
get_system = bind(K, 'GetSystemDirectoryW', W.UINT, W.LPWSTR, W.UINT)
get_drive_type = bind(K, 'GetDriveTypeW', W.UINT, W.LPCWSTR)
get_volume = bind(K, 'GetVolumeInformationW', W.BOOL, W.LPCWSTR, W.LPWSTR, W.DWORD,
                  W.LPVOID, W.LPVOID, W.LPVOID, W.LPWSTR, W.DWORD)
get_long_path = bind(K, 'GetLongPathNameW', W.DWORD, W.LPCWSTR, W.LPWSTR, W.DWORD)
create_job = bind(K, 'CreateJobObjectW', W.HANDLE, W.LPVOID, W.LPCWSTR)
set_job = bind(K, 'SetInformationJobObject', W.BOOL, W.HANDLE, C.c_int, W.LPVOID, W.DWORD)
assign_job = bind(K, 'AssignProcessToJobObject', W.BOOL, W.HANDLE, W.HANDLE)
current_process = bind(K, 'GetCurrentProcess', W.HANDLE)
open_token = bind(A, 'OpenProcessToken', W.BOOL, W.HANDLE, W.DWORD, C.POINTER(W.HANDLE))
get_token = bind(A, 'GetTokenInformation', W.BOOL, W.HANDLE, C.c_int, W.LPVOID, W.DWORD, C.POINTER(W.DWORD))
sid_string = bind(A, 'ConvertSidToStringSidW', W.BOOL, W.LPVOID, C.POINTER(W.LPWSTR))


def checked(result):
    if not result:
        raise C.WinError(C.get_last_error())
    return result


def system_directory():
    buf = C.create_unicode_buffer(32768)
    count = checked(get_system(buf, len(buf)))
    if count >= len(buf):
        raise OSError('system_directory_limit')
    return buf.value


def contain_process():
    job = checked(create_job(None, None))
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, no breakaway
    try:
        checked(set_job(job, 9, C.byref(limits), C.sizeof(limits)))
        checked(assign_job(job, current_process()))
    except BaseException:
        close(job)
        raise
    return job


def current_user_sid():
    token = W.HANDLE()
    checked(open_token(current_process(), 8, C.byref(token)))
    try:
        size = W.DWORD()
        get_token(token, 1, None, 0, C.byref(size))  # TokenUser
        if C.get_last_error() != 122 or not 0 < size.value <= 65536:
            raise OSError('token_information_unavailable')
        buffer = C.create_string_buffer(size.value)
        checked(get_token(token, 1, buffer, size.value, C.byref(size)))
        # TOKEN_USER starts with SID_AND_ATTRIBUTES, whose first field is PSID.
        sid = C.cast(buffer, C.POINTER(W.LPVOID)).contents.value
        text = W.LPWSTR()
        checked(sid_string(sid, C.byref(text)))
        try:
            return text.value
        finally:
            local_free(C.cast(text, W.HLOCAL))
    finally:
        close(token)


def private_directory(path):
    # Explicit TokenUser SID rather than OWNER RIGHTS: an elevated token's default
    # owner can be Administrators. Protected DACL excludes inherited broad ACEs.
    descriptor = W.LPVOID()
    checked(convert_sd('D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;' + current_user_sid() + ')',
                       1, C.byref(descriptor), None))
    try:
        attributes = SecurityAttributes(C.sizeof(SecurityAttributes), descriptor, False)
        checked(create_directory(str(path), C.byref(attributes)))
    finally:
        local_free(descriptor)


def streams(path):
    info = StreamInfo()
    handle = first_stream(str(path), 0, C.byref(info), 0)
    if handle == INVALID:
        if C.get_last_error() == 38:  # ERROR_HANDLE_EOF: empty directory
            return
        raise C.WinError(C.get_last_error())
    try:
        while True:
            if info.name != '::$DATA':
                raise OSError('alternate_data_stream')
            if not next_stream(handle, C.byref(info)):
                if C.get_last_error() != 38:
                    raise C.WinError(C.get_last_error())
                break
    finally:
        find_close(handle)


def info_for(handle, directory):
    info = FileInfo()
    checked(get_info(handle, C.byref(info)))
    # Reparse, offline, recall-on-open/data: do not hydrate or follow cloud files.
    if (info.attributes & (0x400 | 0x1000 | 0x40000 | 0x400000)
            or bool(info.attributes & 0x10) != directory
            or (not directory and info.links != 1)):
        raise OSError('unsafe_windows_object')
    return info


@contextmanager
def opened(path, directory):
    handle = create_file(str(path), 0x80000000, 1, None, 3,
                         0x02000000 | 0x00200000, None)  # BACKUP_SEMANTICS, OPEN_REPARSE_POINT
    if handle == INVALID:
        raise C.WinError(C.get_last_error())
    try:
        info_for(handle, directory)
        streams(path)
        yield handle
    finally:
        close(handle)


@contextmanager
def locked_path(value, directory=True, create=False):
    path = windows_path(value)
    fs = C.create_unicode_buffer(32)
    if get_drive_type(path.anchor) != 3:  # DRIVE_FIXED; no network/removable devices
        raise OSError('local_fixed_ntfs_required')
    checked(get_volume(path.anchor, None, 0, None, None, None, fs, len(fs)))
    if fs.value != 'NTFS':
        raise OSError('local_fixed_ntfs_required')
    with ExitStack() as stack:
        current = Path(path.anchor)
        handle = stack.enter_context(opened(current, True))
        for index, component in enumerate(path.parts[1:]):
            current = current / component
            is_dir = directory or index < len(path.parts) - 2
            if create and is_dir:
                try:
                    private_directory(current)
                except OSError as exc:
                    if exc.winerror != 183:  # existing paths still fully checked
                        raise
            handle = stack.enter_context(opened(current, is_dir))
        # Reject 8.3 short-name aliases, not just textual device names.
        long = C.create_unicode_buffer(32768)
        count = checked(get_long_path(str(current), long, len(long)))
        if count >= len(long) or long.value.casefold() != str(current).casefold():
            raise OSError('windows_path_alias')
        yield handle


def read_handle(handle, limit):
    chunks = bytearray()
    buffer = C.create_string_buffer(65536)
    while len(chunks) <= limit:
        count = W.DWORD()
        checked(read_file(handle, buffer, min(len(buffer), limit + 1 - len(chunks)), C.byref(count), None))
        if not count.value:
            return bytes(chunks)
        chunks.extend(buffer.raw[:count.value])
    raise OSError('staging_limit')


def read_locked(path, limit):
    with locked_path(path, directory=False) as handle:
        return read_handle(handle, limit)


def snapshot(root):
    from trojaino.preflight import MAX_DEPTH, MAX_ENTRIES, MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, Denied
    files, seen = {}, set()
    entries = total = 0
    deadline = time.monotonic() + 5

    def walk(path, prefix, depth):
        nonlocal entries, total
        if depth > MAX_DEPTH:
            raise Denied('staging_limit')
        with os.scandir(path) as iterator:
            for entry in iterator:
                entries += 1
                if entries > MAX_ENTRIES or time.monotonic() > deadline:
                    raise Denied('staging_limit')
                if not valid_component(entry.name):
                    raise Denied('unsafe_source')
                relative = prefix + entry.name
                key = unicodedata.normalize('NFC', relative).casefold()
                if key in seen:
                    raise Denied('unsafe_source')
                seen.add(key)
                child = path / entry.name
                windows_path(child)  # enforce length before any Win32 open
                directory = entry.is_dir(follow_symlinks=False)
                with opened(child, directory) as handle:
                    if directory:
                        walk(child, relative + '/', depth + 1)
                    else:
                        before = info_for(handle, False)
                        if len(files) >= MAX_FILES or before.size_hi or before.size_lo > MAX_FILE_BYTES:
                            raise Denied('staging_limit')
                        data = read_handle(handle, MAX_FILE_BYTES)
                        after = info_for(handle, False)
                        if ((before.size_hi, before.size_lo, before.write.dwHighDateTime, before.write.dwLowDateTime)
                                != (after.size_hi, after.size_lo, after.write.dwHighDateTime, after.write.dwLowDateTime)):
                            raise Denied('unsafe_source')
                        total += len(data)
                        if total > MAX_TOTAL_BYTES:
                            raise Denied('staging_limit')
                        files[relative] = data
    with locked_path(root):
        walk(Path(root), '', 0)
    return files


@contextmanager
def private_job(state):
    with locked_path(state, create=True):
        job = Path(state) / ('scan-' + uuid.uuid4().hex)
        private_directory(job)
        with locked_path(job):
            yield job


def write_tree(staged, files):
    with locked_path(staged.parent):
        private_directory(staged)  # must be new, never merge into an existing tree
        for name, data in files.items():
            if any(not valid_component(part) for part in name.split('/')):
                raise OSError('unsafe_staged_name')
            dest = staged / name
            windows_path(dest)
            with locked_path(dest.parent, create=True):
                handle = create_file(str(dest), 0x40000000, 0, None, 1, 0x00200000, None)
                if handle == INVALID:
                    raise C.WinError(C.get_last_error())
                try:
                    written = W.DWORD()
                    checked(write_file(handle, data, len(data), C.byref(written), None))
                    if written.value != len(data):
                        raise OSError('short_stage_write')
                finally:
                    close(handle)
