##
# Copyright 2012-2014 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
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

@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import os
from vsc import fancylogger

_log = fancylogger.getLogger('environment', fname=False)

changes = {}

def write_changes(filename):
    """
    Write current changes to filename and reset environment afterwards
    """
    script = None
    try:
        script = open(filename, 'w')

        for key in changes:
            script.write('export %s="%s"\n' % (key, changes[key]))

        script.close()
    except IOError, err:
        if script is not None:
            script.close()
        _log.error("Failed to write to %s: %s" % (filename, err))
    reset_changes()


def reset_changes():
    """
    Reset the changes tracked by this module
    """
    global changes
    changes = {}


def setvar(key, value):
    """
    put key in the environment with value
    tracks added keys until write_changes has been called
    """
    # os.putenv() is not necessary. os.environ will call this.
    os.environ[key] = value
    changes[key] = value
    _log.info("Environment variable %s set to %s" % (key, value))


def unset_env_vars(keys):
    """
    Unset the keys given in the environment
    Returns a dict with the old values of the unset keys
    """
    old_environ = {}

    for key in keys:
        if key in os.environ:
            _log.info("Unsetting environment variable %s (value: %s)" % (key, os.environ[key]))
            old_environ[key] = os.environ[key]
            del os.environ[key]

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
        @param: env_vars: a dict with key a name, value a environment variable name
        @param: strict, boolean, if True enforces that all specified environment variables are found
    """
    result = dict([(k, os.environ.get(v)) for k, v in env_vars.items() if v in os.environ])

    if not len(env_vars) == len(result):
        missing = ','.join(["%s / %s" % (k, v) for k, v in env_vars.items() if not k in result])
        msg = 'Following name/variable not found in environment: %s' % missing
        if strict:
            _log.error(msg)
        else:
            _log.debug(msg)

    return result


def modify_env(old, new):
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
                setvar(key, new[key])
        else:
            _log.debug("Key in new environment found that is not in old one: %s (%s)" % (key, new[key]))
            setvar(key, new[key])

    for key in oldKeys:
        if not key in newKeys:
            _log.debug("Key in old environment found that is not in new one: %s (%s)" % (key, old[key]))
            os.unsetenv(key)
            del os.environ[key]

