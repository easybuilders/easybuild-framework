##
# Copyright 2012-2026 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
"""
Utility module for modifying os.environ

Authors:

* Toon Willems (Ghent University)
* Ward Poelmans (Ghent University)
"""
import copy
import os
from contextlib import contextmanager

from easybuild.os_hook import OSProxy
from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError, dry_run_msg
from easybuild.tools.config import build_option
from easybuild.tools.utilities import shell_quote


# take copy of original environemt, so we can restore (parts of) it later
ORIG_OS_ENVIRON = copy.deepcopy(os.environ)


_log = fancylogger.getLogger('environment', fname=False)

_contextes = {'': {}}
_curr_context = ''


# class EnvironmentContext(dict):
#     """Environment context manager to track changes to the environment in a specific context."""
#     def __init__(self):
#         self.__dict__

def set_context(context_name, context=None):
    """
    Set context for tracking environment changes.
    """
    global _curr_context
    _curr_context = context_name
    if context_name not in _contextes:
        if context is not None:
            context = copy.deepcopy(context)
        else:
            context = {}
        _contextes[context_name] = context


def get_context():
    """
    Return current context for tracking environment changes.
    """
    return _contextes[_curr_context]

def write_changes(filename):
    """
    Write current changes to filename and reset environment afterwards
    """
    try:
        with open(filename, 'w') as script:
            for key, changed_value in get_changes().items():
                script.write('export %s=%s\n' % (key, shell_quote(changed_value)))
    except IOError as err:
        raise EasyBuildError("Failed to write to %s: %s", filename, err)
    reset_changes()


def reset_changes():
    """
    Reset the changes tracked by this module
    """
    # TODO: old clear only stop tracking changes, but the changes themselves remain
    # get_context().clear()


def get_changes(show_unset=False):
    """
    Return tracked changes made in environment.
    """
    changes = get_context()
    if not show_unset:
        return {k: v for k, v in changes.items() if v is not None}
    return changes.copy()


def apply_context(context=None):
    """Return the current environment with the changes tracked in the context applied.

    Args:
        context (str, optional): The context to apply. Defaults to the current onee.
    """
    if context is None:
        context = _curr_context
    changes = get_context()
    # print(f'Applying context {context} with changes: {changes}')
    curr_env = ORIG_OS_ENVIRON.copy()
    for key, changed_value in changes.items():
        if changed_value is None:
            curr_env.pop(key, None)
        else:
            curr_env[key] = changed_value
    return curr_env


def getvar(key, default='', strict=False):
    """
    Return value of key in the environment, or default if not found
    """
    context = get_context()
    if key in context:
        val = context[key]
        if val is None:
            if strict:
                raise KeyError(f"Key '{key}' is explicitly unset in the current context")
            return default
        return val
    else:
        if strict:
            return ORIG_OS_ENVIRON[key]
        else:
            return ORIG_OS_ENVIRON.get(key, default)


@contextmanager
def with_environment(copy_current=False):
    """Context manager to run code in a dedicated context"""
    # Get a key that does not exist in _contextes
    base = '_context_'
    cnt = 0
    context = f"{base}{cnt}"
    while context in _contextes:
        cnt += 1
        context = f"{base}{cnt}"

    prev_context = _curr_context
    kwargs = {}
    if copy_current:
        kwargs['context'] = get_context()
    set_context(context, **kwargs)
    try:
        yield
    finally:
        set_context(prev_context)
        _contextes.pop(context, None)


def setvar(key, value, verbose=True, log_changes=True):
    """
    put key in the environment with value
    tracks added keys until write_changes has been called

    :param verbose: include message in dry run output for defining this environment variable
    :param log_changes: show the change in the log
    """
    try:
        oldval_info = "previous value: '%s'" % os.environ[key]
    except KeyError:
        oldval_info = "previously undefined"
    get_context()[key] = value
    if log_changes:
        _log.info("Environment variable %s set to %s (%s)", key, value, oldval_info)

    if verbose and build_option('extended_dry_run'):
        quoted_value = shell_quote(value)
        if quoted_value[0] not in ['"', "'"]:
            quoted_value = '"%s"' % quoted_value
        dry_run_msg("  export %s=%s" % (key, quoted_value), silent=build_option('silent'))


def unset_env_vars(keys, verbose=True):
    """
    Unset the keys given in the environment
    Returns a dict with the old values of the unset keys
    """
    old_environ = {}

    if keys and verbose and build_option('extended_dry_run'):
        dry_run_msg("Undefining environment variables:\n", silent=build_option('silent'))

    for key in list(keys):
        if key in os.environ:
            _log.info("Unsetting environment variable %s (value: %s)" % (key, os.environ[key]))
            old_environ[key] = os.environ[key]
            get_context()[key] = None
            if verbose and build_option('extended_dry_run'):
                dry_run_msg("  unset %s  # value was: %s" % (key, old_environ[key]), silent=build_option('silent'))

    return old_environ


def restore_env_vars(env_keys):
    """
    Restore the environment by setting the keys in the env_keys dict again with their old value
    """
    for key in env_keys:
        if env_keys[key] is not None:
            _log.info("Restoring environment variable %s (value: %s)" % (key, env_keys[key]))
            os.environ[key] = env_keys[key]
            # get_context()[key] = env_keys[key]


def read_environment(env_vars, strict=False):
    """
    Read variables from the environment
    :param env_vars: a dict with key a name, value a environment variable name
    :param strict: boolean, if True enforces that all specified environment variables are found
    """
    result = {k: os.environ.get(v) for k, v in env_vars.items() if v in os.environ}

    if not len(env_vars) == len(result):
        missing = ','.join(["%s / %s" % (k, v) for k, v in env_vars.items() if k not in result])
        msg = 'Following name/variable not found in environment: %s' % missing
        if strict:
            raise EasyBuildError(msg)
        else:
            _log.debug(msg)

    return result


def modify_env(old, new, verbose=True, log_changes=True):
    """
    Compares two os.environ dumps. Adapts final environment.
    :param log_changes: show the change in the log
    """
    old_keys = list(old.keys())
    new_keys = list(new.keys())

    for key in new_keys:
        if key in old_keys:
            if new[key] != old[key]:
                _log.debug("Key in new environment found that is different from old one: %s (%s)", key, new[key])
                setvar(key, new[key], verbose=verbose, log_changes=log_changes)
        else:
            _log.debug("Key in new environment found that is not in old one: %s (%s)", key, new[key])
            setvar(key, new[key], verbose=verbose, log_changes=log_changes)

    for key in old_keys:
        if key not in new_keys:
            _log.debug("Key in old environment found that is not in new one: %s (%s)", key, old[key])
            del os.environ[key]


def restore_env(env, log_changes=True):
    """
    Restore active environment based on specified dictionary.
    :param log_changes: show the change in the log
    """
    modify_env(os.environ, env, verbose=False, log_changes=log_changes)


def sanitize_env():
    """
    Sanitize environment.

    This function:

    * Filters out empty entries from environment variables like $PATH, $LD_LIBRARY_PATH, etc.
      Empty entries make no sense, and can cause problems,
      see for example https://github.com/easybuilders/easybuild-easyconfigs/issues/9843 .

    * Undefines all $PYTHON* environment variables,
      since they may affect the build/install procedure of Python packages.

      cfr. https://docs.python.org/2/using/cmdline.html#environment-variables

      While the $PYTHON* environment variables may be relevant/required for EasyBuild itself,
      and for any non-stdlib Python packages it uses,
      they are irrelevant (and potentially harmful) when installing Python packages.

      Note that this is not an airtight protection against the Python being used in the build/install procedure
      picking up non-stdlib Python packages (e.g., setuptools, vsc-base, ...), thanks to the magic of .pth files,
      cfr. https://docs.python.org/2/library/site.html .
    """

    # remove empty entries from $*PATH variables
    for key in ['CPATH', 'LD_LIBRARY_PATH', 'LIBRARY_PATH', 'LD_PRELOAD', 'PATH']:
        val = os.getenv(key)
        if val:
            entries = val.split(os.pathsep)
            if '' in entries:
                _log.info("Found %d empty entries in $%s, filtering them out...", entries.count(''), key)
                newval = os.pathsep.join(x for x in entries if x)
                if newval:
                    setvar(key, newval)
                else:
                    unset_env_vars([key], verbose=False)

    # unset all $PYTHON* environment variables
    keys_to_unset = [key for key in os.environ if key.startswith('PYTHON')]
    unset_env_vars(keys_to_unset, verbose=False)

class UndefinedParam():
    """Class to represent an undefined parameter different from None"""

class MockEnviron(dict):
    """Hook into os.environ and replace it with calls from this module to track changes to the environment."""
    def __getitem__(self, key):
        return getvar(key, strict=True)

    def __setitem__(self, key, value):
        setvar(key, value, verbose=False, log_changes=False)

    def __delitem__(self, key):
        unset_env_vars([key], verbose=False)

    def __iter__(self):
        return iter(apply_context())

    def __contains__(self, key):
        return key in apply_context()

    def pop(self, key, default=UndefinedParam):
        if key in apply_context():
            value = getvar(key)
            unset_env_vars([key], verbose=False)
            return value
        else:
            if default is UndefinedParam:
                raise KeyError(key)
            return default

    def get(self, key, default=None):
        return getvar(key, default)

    def keys(self):
        return apply_context().keys()

    def items(self):
        return apply_context().items()

    def copy(self):
        return apply_context()

    def __deepcopy__(self, memo):
        return apply_context()


OSProxy.register_override('environ', MockEnviron())
OSProxy.register_override('getenv', lambda key, default=None: getvar(key, default))
OSProxy.register_override('unsetenv', lambda key: unset_env_vars([key], verbose=False))
