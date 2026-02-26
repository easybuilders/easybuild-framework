import importlib
import importlib.abc
import importlib.util
import sys
import types


class SubprocessProxy(types.ModuleType):
    """Proxy module to intercept subprocess attribute access."""
    overrides = {}

    def __init__(self, real):
        super().__init__("subprocess")
        self._real = real

    def __getattr__(self, name):
        # Intercept specific attributes
        return SubprocessProxy.overrides.get(name, getattr(self._real, name))

    def __dir__(self):
        return dir(self._real)

    @classmethod
    def register_override(cls, name, value):
        cls.overrides[name] = value

class OSProxy(types.ModuleType):
    """Proxy module to intercept os attribute access."""
    overrides = {}

    def __init__(self, real):
        super().__init__("os")
        self._real = real

    def __getattr__(self, name):
        # Intercept specific attributes
        return OSProxy.overrides.get(name, getattr(self._real, name))

    def __dir__(self):
        return dir(self._real)

    @classmethod
    def register_override(cls, name, value):
        cls.overrides[name] = value


class HookFinder(importlib.abc.MetaPathFinder):
    """Meta path finder to intercept imports of 'os' and return our proxy."""
    def find_spec(self, fullname, path, target=None):
        if fullname == "os":
            return importlib.util.spec_from_loader(fullname, OSLoader())
        if fullname == "subprocess":
            return importlib.util.spec_from_loader(fullname, SubprocessLoader())
        return None


class OSLoader(importlib.abc.Loader):
    """Loader to create our OSProxy instead of the real os module."""
    def create_module(self, spec):
        # Import real os safely
        sys.meta_path = [f for f in sys.meta_path if not isinstance(f, HookFinder)]
        real_os = importlib.import_module("os")
        sys.meta_path.insert(0, HookFinder())

        # Return proxy instead of real module
        return OSProxy(real_os)

    def exec_module(self, module):
        """Needs to be defined, can be used to alter the module after creation if needed."""

class SubprocessLoader(importlib.abc.Loader):
    """Loader to create our SubprocessProxy instead of the real subprocess module."""
    def create_module(self, spec):
        # Import real subprocess safely
        sys.meta_path = [f for f in sys.meta_path if not isinstance(f, HookFinder)]
        real_subprocess = importlib.import_module("subprocess")
        sys.meta_path.insert(0, HookFinder())

        # Return proxy instead of real module
        return SubprocessProxy(real_subprocess)

    def exec_module(self, module):
        """Needs to be defined, can be used to alter the module after creation if needed."""


def install_os_hook():
    """Install the os hooking mechanism to intercept imports of 'os' and return our proxy."""
    if not any(isinstance(f, HookFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, HookFinder())

    # If already imported, replace in place
    for name, proxy in [
            ("os", OSProxy),
            ("subprocess", SubprocessProxy)
        ]:
        if name in sys.modules and not isinstance(sys.modules[name], proxy):
            real_module = sys.modules[name]
            sys.modules[name] = proxy(real_module)

    # https://stackoverflow.com/questions/79420610/undertanding-python-import-process-importing-custom-os-module
    # Reload system modules that might have already imported os with a different name, at python initialization
    # - tempfile imports os as _os and this is happening before we have a chance to install our hook.
    # - os.path is a separate module (eg posixpath) that imports os into itself and needs to be reloaded to import
    #   our hook for eg `os.path.expanduser` to work with `os.environ['HOME'] = '...'`
    # - shutil is used in CUDA sanity check with `shutil.which` to find `cuobjdum`
    system_modules = [
        "sys", "tempfile", "os.path", "shutil"
    ]
    for name in system_modules:
        if name in sys.modules:
            importlib.reload(sys.modules[name])
