##
# Copyright 2012-2018 Ghent University
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

:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
"""
import copy
import os
from vsc.utils import fancylogger
from vsc.utils.missing import shell_quote

from easybuild.tools.build_log import EasyBuildError, dry_run_msg
from easybuild.tools.config import build_option


# take copy of original environemt, so we can restore (parts of) it later
ORIG_OS_ENVIRON = copy.deepcopy(os.environ)


_log = fancylogger.getLogger('environment', fname=False)

_changes = {}


def write_changes(filename):
    """
    Write current changes to filename and reset environment afterwards
    """
    script = None
    try:
        script = open(filename, 'w')

        for key in _changes:
            script.write('export %s=%s\n' % (key, shell_quote(_changes[key])))

        script.close()
    except IOError, err:
        if script is not None:
            script.close()
        raise EasyBuildError("Failed to write to %s: %s", filename, err)
    reset_changes()


def reset_changes():
    """
    Reset the changes tracked by this module
    """
    global _changes
    _changes = {}


def get_changes():
    """
    Return tracked changes made in environment.
    """
    return _changes


def setvar(key, value, verbose=True):
    """
    put key in the environment with value
    tracks added keys until write_changes has been called

    :param verbose: include message in dry run output for defining this environment variable
    """
    if key in os.environ:
        oldval_info = "previous value: '%s'" % os.environ[key]
    else:
        oldval_info = "previously undefined"
    # os.putenv() is not necessary. os.environ will call this.
    os.environ[key] = value
    _changes[key] = value
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

    for key in keys:
        if key in os.environ:
            _log.info("Unsetting environment variable %s (value: %s)" % (key, os.environ[key]))
            old_environ[key] = os.environ[key]
            del os.environ[key]
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


def read_environment(env_vars, strict=False):
    """
    Read variables from the environment
    :param env_vars: a dict with key a name, value a environment variable name
    :param strict: boolean, if True enforces that all specified environment variables are found
    """
    result = dict([(k, os.environ.get(v)) for k, v in env_vars.items() if v in os.environ])

    if not len(env_vars) == len(result):
        missing = ','.join(["%s / %s" % (k, v) for k, v in env_vars.items() if not k in result])
        msg = 'Following name/variable not found in environment: %s' % missing
        if strict:
            raise EasyBuildError(msg)
        else:
            _log.debug(msg)

    return result


def modify_env(old, new, verbose=True):
    """
    Compares 2 os.environ dumps. Adapts final environment.
    """
    oldKeys = old.keys()
    newKeys = new.keys()
    for key in newKeys:
        ## set them all. no smart checking for changed/identical values
        if key in oldKeys:
            ## hmm, smart checking with debug logging
            if not new[key] == old[key]:
                _log.debug("Key in new environment found that is different from old one: %s (%s)" % (key, new[key]))
                setvar(key, new[key], verbose=verbose)
        else:
            _log.debug("Key in new environment found that is not in old one: %s (%s)" % (key, new[key]))
            setvar(key, new[key], verbose=verbose)

    for key in oldKeys:
        if not key in newKeys:
            _log.debug("Key in old environment found that is not in new one: %s (%s)" % (key, old[key]))
            os.unsetenv(key)
            del os.environ[key]


def restore_env(env):
    """
    Restore active environment based on specified dictionary.
    """
    modify_env(os.environ, env, verbose=False)


def sanitize_env():
    """
    Sanitize environment.

    This function undefines all $PYTHON* environment variables,
    since they may affect the build/install procedure of Python packages.

    cfr. https://docs.python.org/2/using/cmdline.html#environment-variables

    While the $PYTHON* environment variables may be relevant/required for EasyBuild itself,
    and for any non-stdlib Python packages it uses,
    they are irrelevant (and potentially harmful) when installing Python packages.

    Note that this is not an airtight protection against the Python being used in the build/install procedure
    picking up non-stdlib Python packages (e.g., setuptools, vsc-base, ...), thanks to the magic of .pth files,
    cfr. https://docs.python.org/2/library/site.html .
    """
    keys_to_unset = [key for key in os.environ if key.startswith('PYTHON')]
    unset_env_vars(keys_to_unset, verbose=False)
