"""Write new prepared bytes via pinned parents. Never merge or follow links."""
from contextlib import ExitStack
import os
from pathlib import Path, PurePosixPath
import stat


def write_tree(destination, payload):
    destination = Path(destination)
    if not destination.is_absolute() or '..' in destination.parts:
        raise ValueError('new absolute destination required')
    for name in payload:
        parts = name.split('/')
        if (not parts or any(p in ('', '.', '..') for p in parts)
                or '\\' in name or PurePosixPath(name).is_absolute()):
            raise ValueError('unsafe payload path')
    if os.name == 'nt':
        return _windows(destination, payload)
    return _posix(destination, payload)


def _posix(destination, payload):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        chain = []
        def opened(name, parent=None, expected=None):
            fd = os.open(name, flags, dir_fd=parent)
            stack.callback(os.close, fd)
            held = os.fstat(fd)
            if expected is not None:
                if (held.st_dev, held.st_ino) != (expected.st_dev, expected.st_ino):
                    raise ValueError('created directory replaced before open')
                if held.st_uid != os.geteuid() or stat.S_IMODE(held.st_mode) & 0o077:
                    raise ValueError('private directory required')
                with os.scandir(fd) as entries:
                    if next(entries, None) is not None:
                        raise ValueError('new directory is not empty')
            if parent is not None:
                chain.append((parent, name, fd))
            return fd
        parent = opened(destination.anchor)
        for component in destination.parts[1:-1]:
            parent = opened(component, parent)
        os.mkdir(destination.name, 0o700, dir_fd=parent)
        created = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
        root = opened(destination.name, parent, created)
        info = os.fstat(root)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('private destination required')
        directories = {'': root}
        identities = []
        for name, data in sorted(payload.items()):
            parts = name.split('/')
            for index in range(1, len(parts)):
                rel = '/'.join(parts[:index])
                if rel not in directories:
                    parent_rel = '/'.join(parts[:index-1])
                    os.mkdir(parts[index-1], 0o700, dir_fd=directories[parent_rel])
                    created = os.stat(parts[index-1], dir_fd=directories[parent_rel], follow_symlinks=False)
                    directories[rel] = opened(parts[index-1], directories[parent_rel], created)
            parent_fd = directories['/'.join(parts[:-1])]
            fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent_fd)
            with os.fdopen(fd, 'wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
                identities.append((name, os.fstat(output.fileno())))
        expected_children = {rel: set() for rel in directories}
        for name in [*payload, *(rel for rel in directories if rel)]:
            parts = name.split('/')
            expected_children['/'.join(parts[:-1])].add(parts[-1])
        for rel, fd in directories.items():
            with os.scandir(fd) as entries:
                if {entry.name for entry in entries} != expected_children[rel]:
                    raise ValueError('unexpected prepared content')
        for parent_fd, name, fd in chain:
            actual = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            held = os.fstat(fd)
            if (actual.st_dev, actual.st_ino) != (held.st_dev, held.st_ino):
                raise ValueError('publication ancestor replaced')
        # Check publication spelling using the pinned parent; a moved tree is a
        # failure, never permission to follow a replacement through a symlink.
        published = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
        if (published.st_dev, published.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError('destination replaced')
        for rel, fd in directories.items():
            if not rel:
                continue
            parts = rel.split('/')
            actual = os.stat(parts[-1], dir_fd=directories['/'.join(parts[:-1])], follow_symlinks=False)
            held = os.fstat(fd)
            if (actual.st_dev, actual.st_ino) != (held.st_dev, held.st_ino):
                raise ValueError('directory replaced')
        for name, held in identities:
            parts = name.split('/')
            actual = os.stat(parts[-1], dir_fd=directories['/'.join(parts[:-1])], follow_symlinks=False)
            if (actual.st_dev, actual.st_ino) != (held.st_dev, held.st_ino):
                raise ValueError('file replaced')


def _windows(destination, payload):
    # Keep every created directory and file held through publication. Native
    # execution is a release gate; POSIX tests do not validate Win32 sharing.
    from trojaino import preflight_windows as win
    from trojaino.preflight_paths import windows_path, valid_component
    windows_path(str(destination))
    with ExitStack() as stack:
        stack.enter_context(win.locked_path(str(destination.parent)))
        directories = {}
        def create_directory(path, rel):
            win.private_directory(path)  # never accept an already existing name
            created = path.stat(follow_symlinks=False)
            stack.enter_context(win.locked_path(str(path)))
            held = path.stat(follow_symlinks=False)  # full path now held against rename
            if (created.st_dev, created.st_ino) != (held.st_dev, held.st_ino):
                raise ValueError('created directory replaced before lock')
            with os.scandir(path) as entries:
                if next(entries, None) is not None:
                    raise ValueError('new directory is not empty')
            directories[rel] = path
        create_directory(destination, '')
        for name, data in sorted(payload.items()):
            parts = name.split('/')
            if any(not valid_component(p) for p in parts):
                raise ValueError('unsafe windows payload path')
            for index in range(1, len(parts)):
                rel = '/'.join(parts[:index])
                if rel not in directories:
                    create_directory(destination / rel, rel)
            target = destination / name
            windows_path(str(target))
            handle = win.create_file(str(target), 0x40000000, 0, None, 1, 0x00200000, None)
            if handle == win.INVALID:
                raise win.C.WinError(win.C.get_last_error())
            stack.callback(win.close, handle)
            written = win.W.DWORD()
            win.checked(win.write_file(handle, data, len(data), win.C.byref(written), None))
            if written.value != len(data):
                raise OSError('short prepared write')
        expected = {rel: set() for rel in directories}
        for name in [*payload, *(rel for rel in directories if rel)]:
            parts = name.split('/')
            expected['/'.join(parts[:-1])].add(parts[-1])
        for rel, path in directories.items():
            with os.scandir(path) as entries:
                if {entry.name for entry in entries} != expected[rel]:
                    raise ValueError('unexpected prepared content')
