# #
# Copyright 2009-2014 Ghent University
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
# #
"""
EasyBuild configuration (paths, preferences, etc.)

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import copy
import os
import random
import string
import tempfile
import time
from vsc.utils import fancylogger
from vsc.utils.missing import nub, FrozenDictKnownKeys
from vsc.utils.patterns import Singleton

import easybuild.tools.build_log  # this import is required to obtain a correct (EasyBuild) logger!
import easybuild.tools.environment as env
from easybuild.tools.environment import read_environment as _read_environment
from easybuild.tools.run import run_cmd


_log = fancylogger.getLogger('config', fname=False)

# class constant to prepare migration to generaloption as only way of configuration (maybe for v2.X)
SUPPORT_OLDSTYLE = True


DEFAULT_LOGFILE_FORMAT = ("easybuild", "easybuild-%(name)s-%(version)s-%(date)s.%(time)s.log")


DEFAULT_PATH_SUBDIRS = {
    'buildpath': 'build',
    'installpath': '',
    'repositorypath': 'ebfiles_repo',
    'sourcepath': 'sources',
    'subdir_modules': 'modules',
    'subdir_software': 'software',
}


DEFAULT_BUILD_OPTIONS = {
    'aggregate_regtest': None,
    'allow_modules_tool_mismatch': False,
    'check_osdeps': True,
    'cleanup_builddir': True,
    'command_line': None,
    'debug': False,
    'dry_run': False,
    'easyblock': None,
    'experimental': False,
    'force': False,
    'github_user': None,
    'group': None,
    'ignore_dirs': None,
    'modules_footer': None,
    'only_blocks': None,
    'recursive_mod_unload': False,
    'regtest_output_dir': None,
    'retain_all_deps': False,
    'robot_path': None,
    'sequential': False,
    'set_gid_bit': False,
    'silent': False,
    'skip': None,
    'skip_test_cases': False,
    'sticky_bit': False,
    'stop': None,
    'umask': None,
    'valid_module_classes': None,
    'valid_stops': None,
    'validate': True,
}


# based on
# https://wickie.hlrs.de/platforms/index.php/Module_Overview
# https://wickie.hlrs.de/platforms/index.php/Application_software_packages
DEFAULT_MODULECLASSES = [
    ('base', "Default module class"),
    ('bio', "Bioinformatics, biology and biomedical"),
    ('cae', "Computer Aided Engineering (incl. CFD)"),
    ('chem', "Chemistry, Computational Chemistry and Quantum Chemistry"),
    ('compiler', "Compilers"),
    ('data', "Data management & processing tools"),
    ('debugger', "Debuggers"),
    ('devel', "Development tools"),
    ('geo', "Earth Sciences"),
    ('ide', "Integrated Development Environments (e.g. editors)"),
    ('lang', "Languages and programming aids"),
    ('lib', "General purpose libraries"),
    ('math', "High-level mathematical software"),
    ('mpi', "MPI stacks"),
    ('numlib', "Numerical Libraries"),
    ('perf', "Performance tools"),
    ('phys', "Physics and physical systems simulations"),
    ('system', "System utilities (e.g. highly depending on system OS and hardware)"),
    ('toolchain', "EasyBuild toolchains"),
    ('tools', "General purpose tools"),
    ('vis', "Visualization, plotting, documentation and typesetting"),
]


OLDSTYLE_ENVIRONMENT_VARIABLES = {
    'build_path': 'EASYBUILDBUILDPATH',
    'config_file': 'EASYBUILDCONFIG',
    'install_path': 'EASYBUILDINSTALLPATH',
    'log_format': 'EASYBUILDLOGFORMAT',
    'log_dir': 'EASYBUILDLOGDIR',
    'source_path': 'EASYBUILDSOURCEPATH',
    'test_output_path': 'EASYBUILDTESTOUTPUT',
}


OLDSTYLE_NEWSTYLE_MAP = {
    'build_path': 'buildpath',
    'install_path': 'installpath',
    'log_dir': 'tmp_logdir',
    'config_file': 'config',
    'source_path': 'sourcepath',
    'log_format': 'logfile_format',
    'test_output_path': 'testoutput',
    'module_classes': 'moduleclasses',
    'repository_path': 'repositorypath',
    'modules_install_suffix': 'subdir_modules',
    'software_install_suffix': 'subdir_software',
}


def map_to_newstyle(adict):
    """Map a dictionary with oldstyle keys to the new style."""
    res = {}
    for key, val in adict.items():
        if key in OLDSTYLE_NEWSTYLE_MAP:
            newkey = OLDSTYLE_NEWSTYLE_MAP.get(key)
            _log.deprecated("oldstyle key %s usage found, replacing with newkey %s" % (key, newkey), "2.0")
            key = newkey
        res[key] = val
    return res


class ConfigurationVariables(FrozenDictKnownKeys):
    """This is a dict that supports legacy config names transparently."""

    # singleton metaclass: only one instance is created
    __metaclass__ = Singleton

    REQUIRED = [
        'config',
        'prefix',
        'buildpath',
        'installpath',
        'sourcepath',
        'repository',
        'repositorypath',
        'logfile_format',
        'tmp_logdir',
        'moduleclasses',
        'subdir_modules',
        'subdir_software',
        'modules_tool',
        'module_naming_scheme',
    ]

    KNOWN_KEYS = nub(OLDSTYLE_NEWSTYLE_MAP.values() + REQUIRED)

    def get_items_check_required(self, no_missing=True):
        """
        For all REQUIRED, check if exists and return all key,value pairs.
            no_missing: boolean, when True, will throw error message for missing values
        """
        missing = [x for x in self.REQUIRED if not x in self]
        if len(missing) > 0:
            msg = 'Cannot determine value for configuration variables %s. Please specify it.' % missing
            if no_missing:
                self.log.error(msg)
            else:
                self.log.debug(msg)

        return self.items()


class BuildOptions(FrozenDictKnownKeys):
    """Representation of a set of build options, acts like a dictionary."""

    # singleton metaclass: only one instance is created
    __metaclass__ = Singleton

    KNOWN_KEYS = DEFAULT_BUILD_OPTIONS.keys()


def get_user_easybuild_dir():
    """Return the per-user easybuild dir (e.g. to store config files)"""
    oldpath = os.path.join(os.path.expanduser('~'), ".easybuild")
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser('~'), ".config"))
    newpath = os.path.join(xdg_config_home, "easybuild")

    if os.path.isdir(newpath):
        return newpath
    else:
        _log.deprecated("The user easybuild dir has moved from %s to %s." % (oldpath, newpath), "2.0")
        return oldpath


def get_default_oldstyle_configfile():
    """Get the default location of the oldstyle config file to be set as default in the options"""
    # TODO these _log.debug here can't be controlled/set with the generaloption
    # - check environment variable EASYBUILDCONFIG
    # - next, check for an EasyBuild config in $HOME/.easybuild/config.py
    # - last, use default config file easybuild_config.py in main.py directory
    config_env_var = OLDSTYLE_ENVIRONMENT_VARIABLES['config_file']
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

    _log.deprecated("get_default_oldstyle_configfile oldstyle configfile %s used" % config_file, "2.0")

    return config_file


def get_default_oldstyle_configfile_defaults(prefix=None):
    """
    Return a dict with the defaults from the shipped legacy easybuild_config.py and/or environment variables
        prefix: string, when provided, it used as prefix for the other defaults (where applicable)
    """
    if prefix is None:
        prefix = os.path.join(os.path.expanduser('~'), ".local", "easybuild")

    def mk_full_path(name):
        """Create full path, avoid '/' at the end."""
        args = [prefix]
        path = DEFAULT_PATH_SUBDIRS[name]
        if path:
            args.append(path)
        return os.path.join(*args)

    # keys are the options dest
    defaults = {
        'config': get_default_oldstyle_configfile(),
        'prefix': prefix,
        'buildpath': mk_full_path('buildpath'),
        'installpath': mk_full_path('installpath'),
        'sourcepath': mk_full_path('sourcepath'),
        'repository': 'FileRepository',
        'repositorypath': {'FileRepository': [mk_full_path('repositorypath')]},
        'logfile_format': DEFAULT_LOGFILE_FORMAT[:],  # make a copy
        'tmp_logdir': tempfile.gettempdir(),
        'moduleclasses': [x[0] for x in DEFAULT_MODULECLASSES],
        'subdir_modules': DEFAULT_PATH_SUBDIRS['subdir_modules'],
        'subdir_software': DEFAULT_PATH_SUBDIRS['subdir_software'],
        'modules_tool': 'EnvironmentModulesC',
        'module_naming_scheme': 'EasyBuildModuleNamingScheme',
    }

    # sanity check
    if not defaults['repository'] in defaults['repositorypath']:
        _log.error('Failed to get repository path default for default %s' % (defaults['repository']))

    _log.deprecated("get_default_oldstyle_configfile_defaults", "2.0")

    return defaults


def get_default_configfiles():
    """Return a list of default configfiles for tools.options/generaloption"""
    return [os.path.join(get_user_easybuild_dir(), "config.cfg")]


def get_pretend_installpath():
    """Get the installpath when --pretend option is used"""
    return os.path.join(os.path.expanduser('~'), 'easybuildinstall')


def init(options, config_options_dict):
    """
    Gather all variables and check if they're valid
    Variables are read in this order of preference: generaloption > legacy environment > legacy config file
    """
    tmpdict = {}

    if SUPPORT_OLDSTYLE:

        _log.deprecated('oldstyle init with modifications to support oldstyle options', '2.0')
        tmpdict.update(oldstyle_init(options.config))

        # add the DEFAULT_MODULECLASSES as default (behavior is now that this extends the default list)
        tmpdict['moduleclasses'] = nub(list(tmpdict.get('moduleclasses', [])) +
                                         [x[0] for x in DEFAULT_MODULECLASSES])

        # make sure we have new-style keys
        tmpdict = map_to_newstyle(tmpdict)

        # all defaults are now set in generaloption
        # distinguish between default generaloption values and values actually passed by generaloption
        for dest in config_options_dict.keys():
            if not options._action_taken.get(dest, False):
                if dest == 'installpath' and options.pretend:
                    # the installpath has been set by pretend option in postprocess
                    continue
                # remove the default options if they are set in variables
                # this way, all defaults are set
                if dest in tmpdict:
                    _log.debug("Oldstyle support: no action for dest %s." % dest)
                    del config_options_dict[dest]

    # update the variables with the generaloption values
    _log.debug("Updating config variables with generaloption dict %s" % config_options_dict)
    tmpdict.update(config_options_dict)

    # make sure source path is a list
    sourcepath = tmpdict['sourcepath']
    if isinstance(sourcepath, basestring):
        tmpdict['sourcepath'] = sourcepath.split(':')
        _log.debug("Converted source path ('%s') to a list of paths: %s" % (sourcepath, tmpdict['sourcepath']))
    elif not isinstance(sourcepath, (tuple, list)):
        _log.error("Value for sourcepath has invalid type (%s): %s" % (type(sourcepath), sourcepath))

    # initialize configuration variables (any future calls to ConfigurationVariables() will yield the same instance
    variables = ConfigurationVariables(tmpdict, ignore_unknown_keys=True)

    _log.debug("Config variables: %s" % variables)


def init_build_options(build_options=None):
    """Initialize build options."""
    # seed in defaults to make sure all build options are defined, and that build_option() doesn't fail on valid keys
    bo = copy.deepcopy(DEFAULT_BUILD_OPTIONS)
    if build_options is not None:
        bo.update(build_options)
    # BuildOptions is a singleton, so any future calls to BuildOptions will yield the same instance
    return BuildOptions(bo)


def build_option(key):
    """Obtain value specified build option."""
    return BuildOptions()[key]


def build_path():
    """
    Return the build path
    """
    return ConfigurationVariables()['buildpath']


def source_paths():
    """
    Return the list of source paths
    """
    return ConfigurationVariables()['sourcepath']


def source_path():
    """
    Return the source path (deprecated)
    """
    _log.deprecated("Use of source_path() is deprecated, use source_paths() instead.", '2.0')
    return source_paths()


def install_path(typ=None):
    """
    Returns the install path
    - subdir 'software' for actual installation (default)
    - subdir 'modules' for environment modules (typ='mod')
    """
    variables = ConfigurationVariables()

    if typ is None:
        typ = 'software'
    if typ == 'mod':
        typ = 'modules'

    key = "subdir_%s" % typ
    if key in variables:
        suffix = variables[key]
    else:
        # TODO remove default setting. it should have been set through options
        _log.deprecated('%s not set in config, returning default' % key, "2.0")
        defaults = get_default_oldstyle_configfile_defaults()
        try:
            suffix = defaults[key]
        except:
            _log.error('install_path trying to get unknown suffix %s' % key)

    return os.path.join(variables['installpath'], suffix)


def get_repository():
    """
    Return the repository (git, svn or file)
    """
    return ConfigurationVariables()['repository']


def get_repositorypath():
    """
    Return the repository path
    """
    return ConfigurationVariables()['repositorypath']


def get_modules_tool():
    """
    Return modules tool (EnvironmentModulesC, Lmod, ...)
    """
    # 'modules_tool' key will only be present if EasyBuild config is initialized
    return ConfigurationVariables().get('modules_tool', None)


def get_module_naming_scheme():
    """
    Return module naming scheme (EasyBuildModuleNamingScheme, ...)
    """
    return ConfigurationVariables()['module_naming_scheme']


def log_file_format(return_directory=False):
    """Return the format for the logfile or the directory"""
    idx = int(not return_directory)

    variables = ConfigurationVariables()
    if 'logfile_format' in variables:
        res = variables['logfile_format'][idx]
    else:
        # TODO remove default setting. it should have been set through options
        _log.deprecated('logfile_format not set in config, returning default', "2.0")
        defaults = get_default_oldstyle_configfile_defaults()
        res = defaults['logfile_format'][idx]
    return res


def log_format():
    """
    Return the logfilename format
    """
    # TODO needs renaming, is actually a formatter for the logfilename
    return log_file_format(return_directory=False)


def log_path():
    """
    Return the log path
    """
    return log_file_format(return_directory=True)


def get_build_log_path():
    """
    return temporary log directory
    """
    variables = ConfigurationVariables()
    if 'tmp_logdir' in variables:
        return variables['tmp_logdir']
    else:
        # TODO remove default setting. it should have been set through options
        _log.deprecated('tmp_logdir not set in config, returning default', "2.0")
        defaults = get_default_oldstyle_configfile_defaults()
        return defaults['tmp_logdir']


def get_log_filename(name, version, add_salt=False):
    """
    Generate a filename to be used for logging
    """
    date = time.strftime("%Y%m%d")
    timeStamp = time.strftime("%H%M%S")

    filename = log_file_format() % {
        'name': name,
        'version': version,
        'date': date,
        'time': timeStamp,
    }

    if add_salt:
        salt = ''.join(random.choice(string.letters) for i in range(5))
        filename_parts = filename.split('.')
        filename = '.'.join(filename_parts[:-1] + [salt, filename_parts[-1]])

    filepath = os.path.join(get_build_log_path(), filename)

    # Append numbers if the log file already exist
    counter = 1
    while os.path.isfile(filepath):
        counter += 1
        filepath = "%s.%d" % (filepath, counter)

    return filepath


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
    variables = ConfigurationVariables()
    if 'moduleclasses' in variables:
        return variables['moduleclasses']
    else:
        # TODO remove default setting. it should have been set through options
        _log.deprecated('moduleclasses not set in config, returning default', "2.0")
        defaults = get_default_oldstyle_configfile_defaults()
        return defaults['moduleclasses']


def read_environment(env_vars, strict=False):
    """Depreacted location for read_environment, use easybuild.tools.environment"""
    _log.deprecated("Deprecated location for read_environment, use easybuild.tools.environment", '2.0')
    return _read_environment(env_vars, strict)


def oldstyle_init(filename, **kwargs):
    """
    Gather all variables and check if they're valid
    Variables are read in this order of preference: CLI option > environment > config file
    """
    res = {}
    _log.deprecated("oldstyle_init filename %s kwargs %s" % (filename, kwargs), "2.0")

    _log.debug('variables before oldstyle_init %s' % res)
    res.update(oldstyle_read_configuration(filename))  # config file
    _log.debug('variables after oldstyle_init read_configuration (%s) %s' % (filename, res))
    res.update(oldstyle_read_environment())  # environment
    _log.debug('variables after oldstyle_init read_environment %s' % res)
    if kwargs:
        res.update(kwargs)  # CLI options
        _log.debug('variables after oldstyle_init kwargs (passed %s) %s' % (kwargs, res))

    return res


def oldstyle_read_configuration(filename):
    """
    Read variables from the config file
    """
    _log.deprecated("oldstyle_read_configuration filename %s" % filename, "2.0")

    # import avail_repositories here to avoid cyclic dependencies
    # this block of code is going to be removed in EB v2.0
    from easybuild.tools.repository.repository import avail_repositories
    file_variables = avail_repositories(check_useable=False)
    try:
        execfile(filename, {}, file_variables)
    except (IOError, SyntaxError), err:
        _log.exception("Failed to read config file %s %s" % (filename, err))

    return file_variables


def oldstyle_read_environment(env_vars=None, strict=False):
    """
    Read variables from the environment
        - strict=True enforces that all possible environment variables are found
    """
    _log.deprecated(('Adapt code to use read_environment from easybuild.tools.utilities '
                     'and do not use oldstyle environment variables'), '2.0')
    if env_vars is None:
        env_vars = OLDSTYLE_ENVIRONMENT_VARIABLES
    result = {}
    for key in env_vars.keys():
        env_var = env_vars[key]
        if env_var in os.environ:
            result[key] = os.environ[env_var]
            _log.deprecated("Found oldstyle environment variable %s for %s: %s" % (env_var, key, result[key]), "2.0")
        elif strict:
            _log.error("Can't determine value for %s. Environment variable %s is missing" % (key, env_var))
        else:
            _log.debug("Old style env var %s not defined." % env_var)

    return result


def set_tmpdir(tmpdir=None):
    """Set temporary directory to be used by tempfile and others."""
    try:
        if tmpdir is not None:
            if not os.path.exists(tmpdir):
                os.makedirs(tmpdir)
            current_tmpdir = tempfile.mkdtemp(prefix='easybuild-', dir=tmpdir)
        else:
            # use tempfile default parent dir
            current_tmpdir = tempfile.mkdtemp(prefix='easybuild-')
    except OSError, err:
        _log.error("Failed to create temporary directory (tmpdir: %s): %s" % (tmpdir, err))

    _log.info("Temporary directory used in this EasyBuild run: %s" % current_tmpdir)

    for var in ['TMPDIR', 'TEMP', 'TMP']:
        env.setvar(var, current_tmpdir)

    # reset to make sure tempfile picks up new temporary directory to use
    tempfile.tempdir = None

    # test if temporary directory allows to execute files, warn if it doesn't
    try:
        fd, tmptest_file = tempfile.mkstemp()
        os.close(fd)
        os.chmod(tmptest_file, 0700)
        if not run_cmd(tmptest_file, simple=True, log_ok=False, regexp=False):
            msg = "The temporary directory (%s) does not allow to execute files. " % tempfile.gettempdir()
            msg += "This can cause problems in the build process, consider using --tmpdir."
            _log.warning(msg)
        else:
            _log.debug("Temporary directory %s allows to execute files, good!" % tempfile.gettempdir())
        os.remove(tmptest_file)

    except OSError, err:
        _log.error("Failed to test whether temporary directory allows to execute files: %s" % err)

    return current_tmpdir
