import importlib
import importlib.abc
import importlib.util
import sys
import types


class OSProxy(types.ModuleType):
    """Proxy module to intercept os attribute access."""
    overrides = {}

    def __init__(self, real_os):
        super().__init__("os")
        self._real_os = real_os

    def __getattr__(self, name):
        # Intercept specific attributes
        return OSProxy.overrides.get(name, getattr(self._real_os, name))

    def __dir__(self):
        return dir(self._real_os)

    @classmethod
    def register_override(cls, name, value):
        cls.overrides[name] = value


class OSFinder(importlib.abc.MetaPathFinder):
    """Meta path finder to intercept imports of 'os' and return our proxy."""
    def find_spec(self, fullname, path, target=None):
        if fullname == "os":
            return importlib.util.spec_from_loader(fullname, OSLoader())
        return None


class OSLoader(importlib.abc.Loader):
    """Loader to create our OSProxy instead of the real os module."""
    def create_module(self, spec):
        # Import real os safely
        sys.meta_path = [f for f in sys.meta_path if not isinstance(f, OSFinder)]
        real_os = importlib.import_module("os")
        sys.meta_path.insert(0, OSFinder())

        # Return proxy instead of real module
        return OSProxy(real_os)


def install_os_hook():
    """Install the os hooking mechanism to intercept imports of 'os' and return our proxy."""
    sys.meta_path.insert(0, OSFinder())

    # If already imported, replace in place
    if "os" in sys.modules:
        real_os = sys.modules["os"]
        sys.modules["os"] = OSProxy(real_os)

    # https://stackoverflow.com/questions/79420610/undertanding-python-import-process-importing-custom-os-module
    # Reload system modules that might have already imported os with a different name, at python initialization
    # EG tempfile imports os as _os and this is happening before we have a chance to install our hook.
    system_modules = [
        "sys", "tempfile"
    ]
    for name in system_modules:
        if name in sys.modules:
            importlib.reload(sys.modules[name])
