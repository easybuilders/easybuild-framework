##
# Copyright 2009-2013 Ghent University
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
EasyBuild configuration (paths, preferences, etc.)

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
"""

import os
import tempfile
import time

from easybuild.tools.build_log import get_log
import easybuild.tools.repository as repo

_log = get_log('config')

variables = {}
requiredVariables = ['build_path', 'install_path', 'source_path', 'log_format', 'repository']
environmentVariables = {
    'build_path': 'EASYBUILDBUILDPATH',  # temporary build path
    'install_path': 'EASYBUILDINSTALLPATH',  # final install path
    'log_dir': 'EASYBUILDLOGDIR',  # log directory where temporary log files are stored
    'config_file': 'EASYBUILDCONFIG',  # path to the config file
    'test_output_path': 'EASYBUILDTESTOUTPUT',  # path to where jobs should place test output
    'source_path': 'EASYBUILDSOURCEPATH',  # path to where sources should be downloaded
    'log_format': 'EASYBUILDLOGFORMAT',  # format of the log file
}

def get_user_easybuild_dir():
    """Return the per-user easybuild dir (e.g. to store config files)"""
    return os.path.join(os.path.expanduser('~'), ".easybuild")

def get_default_oldstyle_configfile():
    """Get the default location of the oldstyle config file to be set as default in the options"""
    # TODO these _log here can't be controlled/shown with the generaloption
    # - check environment variable EASYBUILDCONFIG
    # - next, check for an EasyBuild config in $HOME/.easybuild/config.py
    # - last, use default config file easybuild_config.py in main.py directory
    config_env_var = environmentVariables['config_file']
    home_config_file = os.path.join(get_user_easybuild_dir(), "config.py")
    if os.getenv(config_env_var):
        _log.debug("Environment variable %s, so using that as config file." % config_env_var)
        config_file = os.getenv(config_env_var)
    elif os.path.exists(home_config_file):
        config_file = home_config_file
        _log.debug("Found EasyBuild configuration file at %s." % config_file)
    else:
        # this should be easybuild.tools.config, the default config file is
        # part of framework in easybuild (ie in tool/..)
        appPath = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        config_file = os.path.join(appPath, "easybuild_config.py")
        _log.debug("Falling back to default config: %s" % config_file)
    return config_file

def get_default_configfiles():
    """Return a list of default configfiles for tools.options/generaloption"""
    return [os.path.join(get_user_easybuild_dir(), "config.cfg")]

def init(filename, **kwargs):
    """
    Gather all variables and check if they're valid
    Variables are read in this order of preference: CLI option > environment > config file
    """

    variables.update(read_configuration(filename))  # config file
    variables.update(read_environment(environmentVariables))  # environment
    variables.update(kwargs)  # CLI options

    def create_dir(dirtype, dirname):
        _log.warn('Will try to create the %s directory %s.' % (dirtype, dirname))
        try:
            os.makedirs(dirname)
        except OSError, err:
            _log.error("Failed to create directory %s: %s" % (dirname, err))
        _log.warn("%s directory %s created" % (dirtype, dirname))

    for key in requiredVariables:
        if not key in variables:
            _log.error('Cannot determine value for configuration variable %s. ' \
                      'Please specify it in your config file %s.' % (key, filename))
            continue

        # verify directories, try and create them if they don't exist
        value = variables[key]
        dirNotFound = key in ['build_path', 'install_path'] and not os.path.isdir(value)
        srcDirNotFound = key in ['source_path'] and type(value) == str and not os.path.isdir(value)
        if dirNotFound or srcDirNotFound:
            _log.warn('The %s directory %s does not exist or does not have proper permissions' % (key, value))
            create_dir(key, value)
            continue
        if key in ['source_path'] and type(value) == list:
            for d in value:
                if not os.path.isdir(d):
                    create_dir(key, d)
                    continue

    # update MODULEPATH if required
    ebmodpath = os.path.join(install_path(typ='mod'), 'all')
    modulepath = os.getenv('MODULEPATH')
    if not modulepath or not ebmodpath in modulepath:
        if modulepath:
            os.environ['MODULEPATH'] = "%s:%s" % (ebmodpath, modulepath)
        else:
            os.environ['MODULEPATH'] = ebmodpath
        _log.info("Extended MODULEPATH with module install path used by EasyBuild: %s" % os.getenv('MODULEPATH'))

def read_configuration(filename):
    """
    Read variables from the config file
    """
    fileVariables = {'FileRepository': repo.FileRepository,
                     'GitRepository': repo.GitRepository,
                     'SvnRepository': repo.SvnRepository
                    }
    try:
        execfile(filename, {}, fileVariables)
    except (IOError, SyntaxError), err:
        _log.exception("Failed to read config file %s %s" % (filename, err))

    return fileVariables

def read_environment(envVars, strict=False):
    """
    Read variables from the environment
        - strict=True enforces that all possible environment variables are found
    """
    result = {}
    for key in envVars.keys():
        environmentKey = envVars[key]
        if environmentKey in os.environ:
            result[key] = os.environ[environmentKey]
        elif strict:
            _log.error("Can't determine value for %s. Environment variable %s is missing" % (key, environmentKey))

    return result

def build_path():
    """
    Return the build path
    """
    return variables['build_path']

def source_path():
    """
    Return the source path
    """
    return variables['source_path']

def install_path(typ=None):
    """
    Returns the install path
    - subdir 'software' for actual installation (default)
    - subdir 'modules' for environment modules (typ='mod')
    """
    if typ and typ == 'mod':
        suffix = variables.get('modules_install_suffix', None)
        if not suffix:
            suffix = 'modules'
    else:
        suffix = variables.get('software_install_suffix', None)
        if not suffix:
            suffix = 'software'

    return os.path.join(variables['install_path'], suffix)

def get_repository():
    """
    Return the repository (git, svn or file)
    """
    return variables['repository']

def log_format():
    """
    Return the logfilename format
    """
    # TODO needs renaming, is actually a formatter for the logfilename
    if 'log_format' in variables:
        return variables['log_format'][1]
    else:
        return "easybuild-%(name)s-%(version)s-%(date)s.%(time)s.log"

def log_path():
    """
    Return the log path
    """
    return variables['log_format'][0]

def get_build_log_path():
    """
    return temporary log directory
    """
    return variables.get('log_dir', tempfile.gettempdir())

def get_log_filename(name, version):
    """
    Generate a filename to be used for logging
    """
    # this can't be imported at the top, otherwise we'd have a cyclic dependency
    date = time.strftime("%Y%m%d")
    timeStamp = time.strftime("%H%M%S")

    filename = os.path.join(get_build_log_path(), log_format() % {'name':name,
                                                                  'version':version,
                                                                  'date':date,
                                                                  'time':timeStamp
                                                                  })

    # Append numbers if the log file already exist
    counter = 1
    while os.path.isfile(filename):
        counter += 1
        filename = "%s.%d" % (filename, counter)

    return filename

def read_only_installdir():
    """
    Return whether installation dir should be fully read-only after installation.
    """
    # FIXME (see issue #123): add a config option to set this, should be True by default (?)
    # this also needs to be checked when --force is used;
    # install dir will have to (temporarily) be made writeable again for owner in that case
    return False

def module_classes():
    """
    Return list of module classes specified in config file.
    """
    if 'module_classes' in variables:
        return variables['module_classes']
    else:
        legacy_module_classes = ['base', 'compiler', 'lib']
        _log.debug('module_classes not set in config, so returning legacy list (%s)' % legacy_module_classes)
        return legacy_module_classes
