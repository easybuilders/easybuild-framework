import builtins
import copy
import os
import posixpath
import subprocess

from functools import wraps

from easybuild import os_hook


# take copy of original environemt, so we can restore (parts of) it later
ORIG_OS_ENVIRON = copy.deepcopy(os.environ)
ORIG_CWD = os.getcwd()


class EnvironmentContext(dict):
    """Environment context manager to track changes to the environment in a specific context."""
    def __init__(self, copy_from=None):
        super().__init__()
        if copy_from is None:
            copy_from = ORIG_OS_ENVIRON
        self.update(copy_from.copy())
        self._changes = {}
        self._cwd = ORIG_CWD

    @property
    def changes(self):
        return self._changes

    def clear_changes(self):
        """Clear the tracked changes, but keep the current environment state."""
        self._changes.clear()

    def get_context_path(self, path):
        """Get the absolute path for a given path in the context of this environment."""
        # print(str(path))
        # if not isinstance(path, str):
        #     print(f'GET_CONTEXT_PATH: type(path)={type(path)} path={path}, cwd={self._cwd}')
        #     # print(path.__dict__)
        if isinstance(path, int):
            return path
        _path = path
        if path and not os.path.isabs(path):
            _path = os.path.normpath(os.path.join(self._cwd, path))
        return _path

    def getcwd(self):
        """Get the current working directory in this context."""
        if not os.path.exists(self._cwd):
            raise FileNotFoundError("Current working directory '%s' does not exist in this context" % self._cwd)
        return self._cwd

    def chdir(self, path):
        """Change the current working directory in this context."""
        path = self.get_context_path(path)
        if not os.path.exists(path):
            raise OSError("Cannot change directory to '%s': No such file or directory" % path)
        self._cwd = path


_curr_context: EnvironmentContext = EnvironmentContext()


def get_context() -> EnvironmentContext:
    """
    Return current context for tracking environment changes.
    """
    # TODO: Make this function thread-aware so that different threads can have their own context if needed.
    return _curr_context


class EnvironProxy():
    """Hook into os.environ and replace it with calls from this module to track changes to the environment."""
    def __getattribute__(self, name):
        return get_context().__getattribute__(name)

    # This methods do not go through the instance __getattribute__
    def __getitem__(self, key):
        return get_context().__getitem__(key)

    def __setitem__(self, key, value):
        get_context().__setitem__(key, value)

    def __delitem__(self, key):
        get_context().__delitem__(key)

    def __iter__(self):
        return get_context().__iter__()

    def __contains__(self, key):
        return get_context().__contains__(key)

    def __len__(self):
        return get_context().__len__()


################################################################################
# os environment specific overrides
os_hook.OSProxy.register_override('environ', EnvironProxy())
os_hook.OSProxy.register_override('getenv', lambda key, default=None: get_context().get(key, default))
os_hook.OSProxy.register_override('unsetenv', lambda key: get_context().pop(key, None))
os_hook.OSProxy.register_override('pushenv', lambda key, value: get_context().__setitem__(key, value))


################################################################################
# os CWD specific overrides
def _gcp(path):
    """Utility function to get the context path for a given path."""
    return get_context().get_context_path(path)


def _gcp_one(func):
    """Utility function to wrap a function that takes a single path argument, that can be relative to a directory
    file descriptor"""
    @wraps(func)
    def wrapped(path, *args, **kwargs):
        # Exception specific for behavior of pathlib in python<3.11 where the first argument passed can be a
        # _NormalAccessor object
        # print(f'_gcp_one: path={path} args={args} kwargs={kwargs}')
        if path.__class__.__name__ == '_NormalAccessor':
            args = list(args)
            path = args.pop(0)

        # If dir_fd is specified, the path is relative to that directory and not to the context's CWD,
        # to preserve the expected behavior of dir_fd. EG: when calling shutil.rmtree, it can internally use
        # os.scandir and recursively delete relative paths, w.r.t the directory file descriptor.
        if kwargs.get('dir_fd') is None:
            path = _gcp(path)
        return func(path, *args, **kwargs)
    return wrapped


def _gcp_two(func):
    """Utility function to wrap a function that takes two path arguments, that can be relative to a directory
    file descriptor"""
    @wraps(func)
    def wrapped(src, dst, *args, **kwargs):
        if kwargs.get('src_dir_fd') is None:
            src = _gcp(src)
        if kwargs.get('dst_dir_fd') is None:
            dst = _gcp(dst)
        return func(src, dst, *args, **kwargs)
    return wrapped


_os = os._real
one_path_funcs = [
    'open', 'listdir', 'mkdir', 'remove', 'rmdir', 'chmod', 'stat', 'lstat', 'chown',
    'access', 'walk', 'readlink', 'unlink', 'utime', 'chroot',
    'makedirs', 'removedirs', 'rmdir', 'statvfs', 'link', 'readlink',
    'mkfifo', 'mknod', 'pathconf',
    'getxattr', 'setxattr', 'listxattr', 'removexattr',
    'scandir',
]
two_path_funcs_dirfd = [
    'rename', 'link', 'replace'
]

for proxy in [os_hook.OSProxy, os_hook.PosixProxy]:
    proxy.register_override('chdir', lambda path: get_context().chdir(path))
    proxy.register_override('getcwd', lambda: get_context().getcwd())
    for func_name in one_path_funcs:
        orig = getattr(_os, func_name)
        proxy.register_override(func_name, _gcp_one(orig))

    for func_name in two_path_funcs_dirfd:
        orig = getattr(_os, func_name)
        proxy.register_override(func_name, _gcp_two(orig))


@wraps(_os.symlink)
def _wrapped_symlink(src, dst, *args, **kwargs):
    """Dedicated wrapper for os.symlink.
    The behavior of symlink is a bit special, as the src is not interpreted.
    Similar to doing ln -s SRC DST, SRC is not relative to the CWD but will be evaluated when accessing the symlink."""

    if kwargs.get('dir_fd') is None:
        dst = _gcp(dst)

    return _os.symlink(src, dst, *args, **kwargs)


os_hook.OSProxy.register_override('symlink', _wrapped_symlink)

################################################################################
# posixpath overrides
_posixpath = posixpath._real
os_hook.OSProxy.register_override('path', posixpath)
for func_name in [
    'abspath', 'exists',
    # 'expanduser',
    # 'expandvars',
    'getatime', 'getctime', 'getmtime', 'getsize',
    'isfile', 'isdir', 'islink', 'ismount',
    'realpath',
]:
    orig = getattr(_posixpath, func_name)
    os_hook.PosixpathProxy.register_override(func_name, _gcp_one(orig))

for func_name in ['samefile', ]:
    orig = getattr(_posixpath, func_name)
    os_hook.PosixpathProxy.register_override(func_name, _gcp_two(orig))


def my_relpath(path, start=os.curdir, *args):
    return _posixpath.relpath(_gcp(path), _gcp(start), *args)


os_hook.PosixpathProxy.register_override(
    'relpath', my_relpath
)


################################################################################
# subprocess.Popen override
class ContextPopen(subprocess._real.Popen):
    """Custom Popen class to apply the current context's environment changes when spawning subprocesses."""
    def __init__(self, *args, **kwargs):
        context = get_context()
        if kwargs.get('env', None) is None:
            kwargs['env'] = context

        kwargs['cwd'] = context.get_context_path(kwargs.get('cwd', '.'))

        super().__init__(*args, **kwargs)


os_hook.SubprocessProxy.register_override('Popen', ContextPopen)

################################################################################
# open() overrides
# os_hook.BuiltinProxy.register_override('open', _gcp_one(open))

original_open = builtins.open
# open called as is calls builtins.open under the hood, but proxying builtin itself does not work so we directly
# override builtins.open here to replace `open` calls across the code.
builtins.open = _gcp_one(original_open)
# io.open = context_open(original_open)


# import io
# print(os.open)
# print(os._real.open)
# print(io.open)
# import importlib
# importlib.invalidate_caches()
# importlib.reload(io)
# print(io.open)
# exit(0)

# Needed for python <= 3.7. EG `shutil.copytree` -> `copystat` will behave differently depending on whether `stat` is in
# `supports_follow_symlinks` or not. Since the code tests for `function in os.supports_follow_symlinks` and not for
# `function.__name__ in os.supports_follow_symlinks`, we have to replace the functions in `os.supports_follow_symlinks`
# with the wrapped versions.
if hasattr(os, 'supports_follow_symlinks'):
    new_follow_symlinks = set()
    for func in os.supports_follow_symlinks:
        new_follow_symlinks.add(getattr(os, func.__name__))
    os.supports_follow_symlinks = new_follow_symlinks
