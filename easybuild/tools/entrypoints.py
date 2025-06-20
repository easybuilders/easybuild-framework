"""Python module to manage entry points for EasyBuild.

Authors:

* Davide Grassano (CECAM)
"""
import sys
import importlib
from easybuild.tools.config import build_option

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError
from typing import TypeVar, List, Callable, Set, Any

_T = TypeVar('_T')


HAVE_ENTRY_POINTS = False
HAVE_ENTRY_POINTS_CLS = False
if sys.version_info >= (3, 8):
    HAVE_ENTRY_POINTS = True
    from importlib.metadata import entry_points, EntryPoint
else:
    EntryPoint = Any

if sys.version_info >= (3, 10):
    # Python >= 3.10 uses importlib.metadata.EntryPoints as a type for entry_points()
    HAVE_ENTRY_POINTS_CLS = True


_log = fancylogger.getLogger('entrypoints', fname=False)


class EasybuildEntrypoint:
    group = None
    expected_type = None
    registered = {}

    def __init__(self):
        if self.group is None:
            raise EasyBuildError(
                "Cannot use <EasybuildEntrypoint> drirectly. Please use a subclass that defines `group`",
            )

        self.wrapped = None
        self.module = None
        self.name = None
        self.file = None

    def __repr__(self):
        return f"{self.__class__.__name__} <{self.module}:{self.name}>"

    def __call__(self, wrap: _T) -> _T:
        """Use an instance of this class as a decorator to register an entrypoint."""
        if self.expected_type is not None:
            check = False
            try:
                check = isinstance(wrap, self.expected_type) or issubclass(wrap, self.expected_type)
            except Exception:
                pass
            if not check:
                raise EasyBuildError(
                    "Entrypoint '%s' expected type '%s', got '%s'",
                    self.name, self.expected_type, type(wrap)
                )
        self.wrapped = wrap
        self.module = getattr(wrap, '__module__', None)
        self.name = getattr(wrap, '__name__', None)
        if self.module:
            mod = importlib.import_module(self.module)
            self.file = getattr(mod, '__file__', None)

        grp = self.registered.setdefault(self.group, set())

        for ep in grp:
            if ep.name == self.name and ep.module != self.module:
                raise ValueError(
                    "Entrypoint '%s' already registered in group '%s' by module '%s' vs '%s'",
                    self.name, self.group, ep.module, self.module
                )
        grp.add(self)

        self.validate()

        _log.debug("Registered entrypoint: %s", self)

        return wrap

    @classmethod
    def retrieve_entrypoints(cls) -> Set[EntryPoint]:
        """"Get all entrypoints in this group."""
        strict_python = True
        use_eps = build_option('use_entrypoints', default=None)
        if use_eps is None:
            # Default True needed to work with commands like --list-toolchains that do not initialize the BuildOptions
            use_eps = True
            # Needed to work with older Python versions: do not raise errors when entry points are default enabled
            strict_python = False
        res = set()
        if use_eps:
            if not HAVE_ENTRY_POINTS:
                if strict_python:
                    msg = "`--use-entrypoints` requires importlib.metadata (Python >= 3.8)"
                    _log.warning(msg)
                    raise EasyBuildError(msg)
                else:
                    _log.debug("`get_group_entrypoints` called before BuildOptions initialized, with python < 3.8")
            else:
                if HAVE_ENTRY_POINTS_CLS:
                    res = set(entry_points(group=cls.group))
                else:
                    res = set(entry_points().get(cls.group, []))

        return res

    @classmethod
    def load_entrypoints(cls):
        """Load all the entrypoints in this group. This is needed for the modules contining the entrypoints to be
        actually imported in order to process the function decorators that will register them in the
        `registered` dict."""
        for ep in cls.retrieve_entrypoints():
            try:
                ep.load()
            except Exception as e:
                msg = f"Error loading entrypoint {ep}: {e}"
                _log.warning(msg)
                raise EasyBuildError(msg) from e

    @classmethod
    def get_loaded_entrypoints(cls: _T, name: str = None, **filter_params) -> List[_T]:
        """Get all entrypoints in this group."""
        cls.load_entrypoints()

        entrypoints = []
        for ep in cls.registered.get(cls.group, []):
            cond = name is None or ep.name == name
            for key, value in filter_params.items():
                cond = cond and getattr(ep, key, None) == value
            if cond:
                entrypoints.append(ep)

        return entrypoints

    @staticmethod
    def clear():
        """Clear the registered entrypoints. Used for testing when the same entrypoint is loaded multiple times
        from different temporary directories."""
        EasybuildEntrypoint.registered.clear()

    def validate(self):
        """Validate the entrypoint."""
        if self.module is None or self.name is None:
            raise EasyBuildError("Entrypoint `%s` has no module or name associated", self.wrapped)


class EntrypointHook(EasybuildEntrypoint):
    """Class to represent a hook entrypoint."""
    group = 'easybuild.hooks'

    def __init__(self, step, pre_step=False, post_step=False, priority=0):
        """Initialize the EntrypointHook."""
        super().__init__()
        self.step = step
        self.pre_step = pre_step
        self.post_step = post_step
        self.priority = priority

    def validate(self):
        """Validate the hook entrypoint."""
        from easybuild.tools.hooks import KNOWN_HOOKS, HOOK_SUFF, PRE_PREF, POST_PREF
        super().validate()

        prefix = ''
        if self.pre_step:
            prefix = PRE_PREF
        elif self.post_step:
            prefix = POST_PREF

        hook_name = f'{prefix}{self.step}{HOOK_SUFF}'

        if hook_name not in KNOWN_HOOKS:
            msg = f"Attempting to register unknown hook '{hook_name}'"
            _log.warning(msg)
            raise EasyBuildError(msg)


class EntrypointEasyblock(EasybuildEntrypoint):
    """Class to represent an easyblock entrypoint."""
    group = 'easybuild.easyblock'

    def __init__(self):
        super().__init__()
        # Avoid circular imports by importing EasyBlock here
        from easybuild.framework.easyblock import EasyBlock
        self.expected_type = EasyBlock


class EntrypointToolchain(EasybuildEntrypoint):
    """Class to represent a toolchain entrypoint."""
    group = 'easybuild.toolchain'

    def __init__(self, prepend=False):
        super().__init__()
        # Avoid circular imports by importing Toolchain here
        from easybuild.tools.toolchain.toolchain import Toolchain
        self.expected_type = Toolchain
        self.prepend = prepend
