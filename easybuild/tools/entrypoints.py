"""Python module to manage entry points for EasyBuild.

Authors:

* Davide Grassano (CECAM)
"""

import importlib
from importlib.metadata import EntryPoint, entry_points
from easybuild.tools.config import build_option
from typing import Callable

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError


_log = fancylogger.getLogger('entrypoints', fname=False)


def get_group_entrypoints(group: str) -> set[EntryPoint]:
    """Get all entrypoints for a group"""
    # print(f"--- Getting entry points for group: {group}")
    # Default True needed to work with commands like --list-toolchains that do not initialize the BuildOptions
    if not build_option('use_entrypoints', default=True):
        return set()
    return set(ep for ep in entry_points(group=group))


# EASYCONFIG_ENTRYPOINT = "easybuild.easyconfig"
EASYBLOCK_ENTRYPOINT = "easybuild.easyblock"
EASYBLOCK_ENTRYPOINT_MARK = "_is_easybuild_easyblock"

TOOLCHAIN_ENTRYPOINT = "easybuild.toolchain"
TOOLCHAIN_ENTRYPOINT_MARK = "_is_easybuild_toolchain"
TOOLCHAIN_ENTRYPOINT_PREPEND = "_prepend"

HOOKS_ENTRYPOINT = "easybuild.hooks"
HOOKS_ENTRYPOINT_STEP = "_step"
HOOKS_ENTRYPOINT_PRE_STEP = "_pre_step"
HOOKS_ENTRYPOINT_POST_STEP = "_post_step"
HOOKS_ENTRYPOINT_MARK = "_is_easybuild_hook"
HOOKS_ENTRYPOINT_PRIORITY = "_priority"


#########################################################################################
# Easyblock entrypoints
def register_easyblock_entrypoint():
    """Decorator to register an easyblock entrypoint."""
    def decorator(cls: type) -> type:
        if not isinstance(cls, type):
            raise EasyBuildError("Easyblock entrypoint `%s` is not a class", cls.__name__)
        setattr(cls, EASYBLOCK_ENTRYPOINT_MARK, True)
        _log.debug("Registering easyblock entrypoint: %s", cls.__name__)
        return cls

    return decorator


def validate_easyblock_entrypoints() -> list[str]:
    """Validate all easyblock entrypoints.

    Returns:
        List of invalid easyblocks.
    """
    invalid_easyblocks = []
    for ep in get_group_entrypoints(EASYBLOCK_ENTRYPOINT):
        full_name = f'{ep.name} <{ep.value}>'

        eb = ep.load()
        if not hasattr(eb, EASYBLOCK_ENTRYPOINT_MARK):
            invalid_easyblocks.append(full_name)
            _log.warning(f"Easyblock {ep.name} <{ep.value}> is not a valid EasyBuild easyblock")
            continue

        if not isinstance(eb, type):
            _log.warning(f"Easyblock {ep.name} <{ep.value}> is not a class")
            invalid_easyblocks.append(full_name)
            continue

    return invalid_easyblocks


def get_easyblock_entrypoints(name=None) -> dict:
    """Get all easyblock entrypoints.

    Returns:
        List of easyblocks.
    """
    easyblocks = {}
    for ep in get_group_entrypoints(EASYBLOCK_ENTRYPOINT):
        try:
            eb = ep.load()
        except Exception as e:
            _log.error(f"Error loading easyblock entry point {ep.name}: {e}")
            raise EasyBuildError(f"Error loading easyblock entry point {ep.name}: {e}")
        mod = importlib.import_module(eb.__module__)

        ptr = {
            'class': eb.__name__,
            'loc': mod.__file__,
        }
        easyblocks[f'{ep.module}'] = ptr
    if name is not None:
        for key, value in easyblocks.items():
            if value['class'] == name:
                return {key: value}
            if key == name:
                return {key: value}
        return {}

    return easyblocks


#########################################################################################
# Hooks entrypoints
def register_entrypoint_hooks(step, pre_step=False, post_step=False, priority=0):
    """Decorator to add metadata on functions to be used as hooks.

    priority: integer, the priority of the hook, higher value means higher priority
    """
    def decorator(func):
        setattr(func, HOOKS_ENTRYPOINT_MARK, True)
        setattr(func, HOOKS_ENTRYPOINT_STEP, step)
        setattr(func, HOOKS_ENTRYPOINT_PRE_STEP, pre_step)
        setattr(func, HOOKS_ENTRYPOINT_POST_STEP, post_step)
        setattr(func, HOOKS_ENTRYPOINT_PRIORITY, priority)

        # Register the function as an entry point
        _log.info(
            "Registering entry point hook '%s' 'pre=%s' 'post=%s' with priority %d",
            func.__name__, pre_step, post_step, priority
        )
        return func
    return decorator


def validate_entrypoint_hooks(known_hooks: list[str], pre_prefix: str, post_prefix: str, suffix: str) -> list[str]:
    """Validate all entrypoints hooks.

    Args:
        known_hooks: List of known hooks.
        pre_prefix: Prefix for pre hooks.
        post_prefix: Prefix for post hooks.
        suffix: Suffix for hooks.

    Returns:
        List of invalid hooks.
    """
    invalid_hooks = []
    for ep in get_group_entrypoints(HOOKS_ENTRYPOINT):
        full_name = f'{ep.name} <{ep.value}>'

        hook = ep.load()
        if not hasattr(hook, HOOKS_ENTRYPOINT_MARK):
            invalid_hooks.append(f"{ep.name} <{ep.value}>")
            _log.warning(f"Hook {ep.name} <{ep.value}> is not a valid EasyBuild hook")
            continue

        if not callable(hook):
            _log.warning(f"Hook {ep.name} <{ep.value}> is not callable")
            invalid_hooks.append(full_name)
            continue

        label = getattr(hook, HOOKS_ENTRYPOINT_STEP)
        pre_cond = getattr(hook, HOOKS_ENTRYPOINT_PRE_STEP)
        post_cond = getattr(hook, HOOKS_ENTRYPOINT_POST_STEP)

        prefix = ''
        if pre_cond:
            prefix = pre_prefix
        elif post_cond:
            prefix = post_prefix

        hook_name = prefix + label + suffix

        if hook_name not in known_hooks:
            _log.warning(f"Hook {full_name} does not match known hooks patterns")
            invalid_hooks.append(full_name)
            continue

    return invalid_hooks


def find_entrypoint_hooks(label, pre_step_hook=False, post_step_hook=False) -> list[Callable]:
    """Get all hooks defined in entry points."""
    hooks = []
    for ep in get_group_entrypoints(HOOKS_ENTRYPOINT):
        try:
            hook = ep.load()
        except Exception as e:
            _log.error(f"Error loading entry point {ep.name}: {e}")
            raise EasyBuildError(f"Error loading entry point {ep.name}: {e}")

        cond = all([
            getattr(hook, HOOKS_ENTRYPOINT_STEP) == label,
            getattr(hook, HOOKS_ENTRYPOINT_PRE_STEP) == pre_step_hook,
            getattr(hook, HOOKS_ENTRYPOINT_POST_STEP) == post_step_hook,
        ])
        if cond:
            hooks.append(hook)

    return hooks


#########################################################################################
# Toolchain entrypoints
def register_toolchain_entrypoint(prepend=False):
    def decorator(cls):
        from easybuild.tools.toolchain.toolchain import Toolchain
        if not isinstance(cls, type) or not issubclass(cls, Toolchain):
            raise EasyBuildError("Toolchain entrypoint `%s` is not a subclass of `Toolchain`", cls.__name__)
        setattr(cls, TOOLCHAIN_ENTRYPOINT_MARK, True)
        setattr(cls, TOOLCHAIN_ENTRYPOINT_PREPEND, prepend)

        _log.debug("Registering toolchain entrypoint: %s", cls.__name__)
        return cls

    return decorator


def get_toolchain_entrypoints() -> set[EntryPoint]:
    """Get all toolchain entrypoints."""
    toolchains = []
    for ep in get_group_entrypoints(TOOLCHAIN_ENTRYPOINT):
        try:
            tc = ep.load()
        except Exception as e:
            _log.error(f"Error loading toolchain entry point {ep.name}: {e}")
            raise EasyBuildError(f"Error loading toolchain entry point {ep.name}: {e}")
        toolchains.append(tc)
    return toolchains


def validate_toolchain_entrypoints() -> list[str]:
    """Validate all toolchain entrypoints."""
    invalid_toolchains = []
    for ep in get_group_entrypoints(TOOLCHAIN_ENTRYPOINT):
        full_name = f'{ep.name} <{ep.value}>'

        tc = ep.load()
        if not hasattr(tc, TOOLCHAIN_ENTRYPOINT_MARK):
            invalid_toolchains.append(full_name)
            _log.warning(f"Toolchain {ep.name} <{ep.value}> is not a valid EasyBuild toolchain")
            continue

    return invalid_toolchains
