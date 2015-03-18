# #
# Copyright 2009-2015 Ghent University
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


DEFAULT_LOGFILE_FORMAT = ("easybuild", "easybuild-%(name)s-%(version)s-%(date)s.%(time)s.log")
DEFAULT_MNS = 'EasyBuildMNS'
DEFAULT_MODULES_TOOL = 'EnvironmentModulesC'
DEFAULT_PATH_SUBDIRS = {
    'buildpath': 'build',
    'installpath': '',
    'repositorypath': 'ebfiles_repo',
    'sourcepath': 'sources',
    'subdir_modules': 'modules',
    'subdir_software': 'software',
}
DEFAULT_PREFIX = os.path.join(os.path.expanduser('~'), ".local", "easybuild")
DEFAULT_REPOSITORY = 'FileRepository'


# utility function for obtaining default paths
def mk_full_default_path(name, prefix=DEFAULT_PREFIX):
    """Create full path, avoid '/' at the end."""
    args = [prefix]
    path = DEFAULT_PATH_SUBDIRS[name]
    if path:
        args.append(path)
    return os.path.join(*args)

# build options that have a perfectly matching command line option, listed by default value
BUILD_OPTIONS_CMDLINE = {
    None: [
        'aggregate_regtest',
        'download_timeout',
        'dump_test_report',
        'easyblock',
        'filter_deps',
        'from_pr',
        'github_user',
        'group',
        'ignore_dirs',
        'modules_footer',
        'only_blocks',
        'optarch',
        'regtest_output_dir',
        'skip',
        'stop',
        'suffix_modules_path',
        'system_modules',
        'test_report_env_filter',
        'testoutput',
        'umask',
    ],
    False: [
        'allow_modules_tool_mismatch',
        'debug',
        'experimental',
        'force',
        'hidden',
        'robot',
        'sequential',
        'set_gid_bit',
        'skip_test_cases',
        'sticky_bit',
        'upload_test_report',
        'update_modules_tool_cache',
    ],
    True: [
        'cleanup_builddir',
    ],
}
# build option that do not have a perfectly matching command line option
BUILD_OPTIONS_OTHER = {
    None: [
        'build_specs',
        'command_line',
        'pr_path',
        'robot_path',
        'valid_module_classes',
        'valid_stops',
    ],
    False: [
        'dry_run',
        'recursive_mod_unload',
        'retain_all_deps',
        'silent',
        'try_to_generate',
    ],
    True: [
        'check_osdeps',
        'validate',
    ],
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


class ConfigurationVariables(FrozenDictKnownKeys):
    """This is a dict that supports legacy config names transparently."""

    # singleton metaclass: only one instance is created
    __metaclass__ = Singleton

    # list of known/required keys
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
    KNOWN_KEYS = REQUIRED  # KNOWN_KEYS must be defined for FrozenDictKnownKeys functionality

    def get_items_check_required(self):
        """
        For all known/required keys, check if exists and return all key/value pairs.
            no_missing: boolean, when True, will throw error message for missing values
        """
        missing = [x for x in self.KNOWN_KEYS if not x in self]
        if len(missing) > 0:
            msg = 'Cannot determine value for configuration variables %s. Please specify it.' % missing
            self.log.error(msg)

        return self.items()


class BuildOptions(FrozenDictKnownKeys):
    """Representation of a set of build options, acts like a dictionary."""

    # singleton metaclass: only one instance is created
    __metaclass__ = Singleton

    KNOWN_KEYS = [k for kss in [BUILD_OPTIONS_CMDLINE, BUILD_OPTIONS_OTHER] for ks in kss.values() for k in ks]


def get_pretend_installpath():
    """Get the installpath when --pretend option is used"""
    return os.path.join(os.path.expanduser('~'), 'easybuildinstall')


def init(options, config_options_dict):
    """
    Gather all variables and check if they're valid
    Variables are read in this order of preference: generaloption > legacy environment > legacy config file
    """
    tmpdict = copy.deepcopy(config_options_dict)

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


def init_build_options(build_options=None, cmdline_options=None):
    """Initialize build options."""

    active_build_options = {}

    if cmdline_options is not None:
        # building a dependency graph implies force, so that all dependencies are retained
        # and also skips validation of easyconfigs (e.g. checking os dependencies)
        retain_all_deps = False
        if cmdline_options.dep_graph:
            _log.info("Enabling force to generate dependency graph.")
            cmdline_options.force = True
            retain_all_deps = True

        if cmdline_options.dep_graph or cmdline_options.dry_run or cmdline_options.dry_run_short:
            _log.info("Ignoring OS dependencies for --dep-graph/--dry-run")
            cmdline_options.ignore_osdeps = True

        cmdline_build_option_names = [k for ks in BUILD_OPTIONS_CMDLINE.values() for k in ks]
        active_build_options.update(dict([(key, getattr(cmdline_options, key)) for key in cmdline_build_option_names]))
        # other options which can be derived but have no perfectly matching cmdline option
        active_build_options.update({
            'check_osdeps': not cmdline_options.ignore_osdeps,
            'dry_run': cmdline_options.dry_run or cmdline_options.dry_run_short,
            'recursive_mod_unload': cmdline_options.recursive_module_unload,
            'retain_all_deps': retain_all_deps,
            'validate': not cmdline_options.force,
            'valid_module_classes': module_classes(),
        })

    if build_options is not None:
        active_build_options.update(build_options)

    # seed in defaults to make sure all build options are defined, and that build_option() doesn't fail on valid keys
    bo = {}
    for build_options_by_default in [BUILD_OPTIONS_CMDLINE, BUILD_OPTIONS_OTHER]:
        for default in build_options_by_default:
            bo.update(dict([(opt, default) for opt in build_options_by_default[default]]))
    bo.update(active_build_options)

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
    """NO LONGER SUPPORTED: use source_paths instead"""
    _log.nosupport("source_path() is replaced by source_paths()", '2.0')


def install_path(typ=None):
    """
    Returns the install path
    - subdir 'software' for actual installation (default)
    - subdir 'modules' for environment modules (typ='mod')
    """
    if typ is None:
        typ = 'software'
    elif typ == 'mod':
        typ = 'modules'

    variables = ConfigurationVariables()
    suffix = variables['subdir_%s' % typ]
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
    Return module naming scheme (EasyBuild, ...)
    """
    return ConfigurationVariables()['module_naming_scheme']


def log_file_format(return_directory=False):
    """Return the format for the logfile or the directory"""
    idx = int(not return_directory)
    return ConfigurationVariables()['logfile_format'][idx]


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
    Return (temporary) directory for build log
    """
    variables = ConfigurationVariables()
    if variables['tmp_logdir'] is not None:
        res = variables['tmp_logdir']
    else:
        res = tempfile.gettempdir()
    return res


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
    return ConfigurationVariables()['moduleclasses']


def read_environment(env_vars, strict=False):
    """NO LONGER SUPPORTED: use read_environment from easybuild.tools.environment instead"""
    _log.nosupport("read_environment has moved to easybuild.tools.environment", '2.0')


def set_tmpdir(tmpdir=None, raise_error=False):
    """Set temporary directory to be used by tempfile and others."""
    try:
        if tmpdir is not None:
            if not os.path.exists(tmpdir):
                os.makedirs(tmpdir)
            current_tmpdir = tempfile.mkdtemp(prefix='eb-', dir=tmpdir)
        else:
            # use tempfile default parent dir
            current_tmpdir = tempfile.mkdtemp(prefix='eb-')
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
            if raise_error:
                _log.error(msg)
            else:
                _log.warning(msg)
        else:
            _log.debug("Temporary directory %s allows to execute files, good!" % tempfile.gettempdir())
        os.remove(tmptest_file)

    except OSError, err:
        _log.error("Failed to test whether temporary directory allows to execute files: %s" % err)

    return current_tmpdir
