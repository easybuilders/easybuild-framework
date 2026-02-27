import importlib
import importlib._bootstrap_external
import importlib.abc
import importlib.util
import sys
import types


class ProxyLoader(importlib.abc.Loader):
    """Loader to create our proxy instead of the real module."""
    proxy_cls = None  # To be defined in subclasses

    def create_module(self, spec):
        # Import real module safely
        sys.meta_path = [f for f in sys.meta_path if not isinstance(f, HookFinder)]
        real_module = importlib.import_module(spec.name)
        sys.meta_path.insert(0, HookFinder())

        # Return proxy instead of real module
        return self.proxy_cls(real_module)

    def exec_module(self, module):
        """Needs to be defined, can be used to alter the module after creation if needed."""


class ModuleProxy(types.ModuleType):
    """Generic proxy module to intercept attribute access."""
    overrides = None
    module_name = None

    def __init__(self, real):
        super().__init__(self.module_name)
        self._real = real
        # self._not_found = set()

    def __getattr__(self, name):
        # Intercept specific attributes
        # if name in self.overrides:
        #     # print(f"Intercepted access to {self.module_name}.{name}, returning override value.")
        #     pass
        # else:
        #     self._not_found.add(name)
        #     print("NOTFOUND", self.module_name, sorted(self._not_found))
        return self.overrides.get(name, getattr(self._real, name))

    def __dir__(self):
        return dir(self._real)

    @classmethod
    def register_override(cls, name, value):
        cls.overrides[name] = value

    @classmethod
    def loader(cls):
        class Loader(ProxyLoader):
            proxy_cls = cls
        return Loader()


class SubprocessProxy(ModuleProxy):
    """Proxy module to intercept subprocess attribute access."""
    overrides = {}
    module_name = "subprocess"


class OSProxy(ModuleProxy):
    """Proxy module to intercept os attribute access."""
    overrides = {}
    module_name = "os"


class PosixProxy(ModuleProxy):
    """Proxy module to intercept posix attribute access."""
    overrides = {}
    module_name = "posix"


class PosixpathProxy(ModuleProxy):
    """Proxy module to intercept posixpath attribute access."""
    overrides = {}
    module_name = "posixpath"


proxy_map: dict[str, ModuleProxy] = {
    "os": OSProxy,
    "subprocess": SubprocessProxy,
    "posix": PosixProxy,
    "posixpath": PosixpathProxy,
    # "builtins": BuiltinProxy,
}


class HookFinder(importlib.abc.MetaPathFinder):
    """Meta path finder to intercept imports of 'os' and return our proxy."""
    def find_spec(self, fullname, path, target=None):
        if fullname in proxy_map:
            return importlib.util.spec_from_loader(fullname, proxy_map[fullname].loader())
        return None


def install_os_hook():
    """Install the os hooking mechanism to intercept imports of 'os' and return our proxy."""
    if not any(isinstance(f, HookFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, HookFinder())

    # If already imported, replace in place
    for name, proxy in proxy_map.items():
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
        "os", "sys", "tempfile", "posixpath", "shutil", "importlib", "io"
    ]
    for name in system_modules:
        if name in sys.modules:
            # print(f"Reloading system module {name} to ensure it imports our os hook.")
            importlib.reload(sys.modules[name])

    # Needed to override how import paths are resolved in case '' is in sys.path indicating the CWD.
    # Cannot be reloaded without breaking stuff
    importlib._bootstrap_external._os = sys.modules["posix"]
