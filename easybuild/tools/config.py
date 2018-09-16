# #
# Copyright 2009-2018 Ghent University
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
# #
"""
EasyBuild configuration (paths, preferences, etc.)

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
:author: Damian Alvarez (Forschungszentrum Juelich GmbH)
"""
import copy
import glob
import os
import random
import string
import tempfile
import time
from vsc.utils import fancylogger
from vsc.utils.missing import FrozenDictKnownKeys
from vsc.utils.patterns import Singleton

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.module_naming_scheme import GENERAL_CLASS


_log = fancylogger.getLogger('config', fname=False)


ERROR = 'error'
IGNORE = 'ignore'
PURGE = 'purge'
UNLOAD = 'unload'
UNSET = 'unset'
WARN = 'warn'

PKG_TOOL_FPM = 'fpm'
PKG_TYPE_RPM = 'rpm'

CONT_IMAGE_FORMAT_EXT3 = 'ext3'
CONT_IMAGE_FORMAT_SANDBOX = 'sandbox'
CONT_IMAGE_FORMAT_SQUASHFS = 'squashfs'
CONT_IMAGE_FORMATS = [CONT_IMAGE_FORMAT_EXT3, CONT_IMAGE_FORMAT_SANDBOX, CONT_IMAGE_FORMAT_SQUASHFS]

CONT_TYPE_DOCKER = 'docker'
CONT_TYPE_SINGULARITY = 'singularity'
CONT_TYPES = [CONT_TYPE_DOCKER, CONT_TYPE_SINGULARITY]
DEFAULT_CONT_TYPE = CONT_TYPE_SINGULARITY

DEFAULT_JOB_BACKEND = 'GC3Pie'
DEFAULT_LOGFILE_FORMAT = ("easybuild", "easybuild-%(name)s-%(version)s-%(date)s.%(time)s.log")
DEFAULT_MAX_FAIL_RATIO_PERMS = 0.5
DEFAULT_MNS = 'EasyBuildMNS'
DEFAULT_MODULE_SYNTAX = 'Lua'
DEFAULT_MODULES_TOOL = 'Lmod'
DEFAULT_PATH_SUBDIRS = {
    'buildpath': 'build',
    'containerpath': 'containers',
    'installpath': '',
    'packagepath': 'packages',
    'repositorypath': 'ebfiles_repo',
    'sourcepath': 'sources',
    'subdir_modules': 'modules',
    'subdir_software': 'software',
}
DEFAULT_PKG_RELEASE = '1'
DEFAULT_PKG_TOOL = PKG_TOOL_FPM
DEFAULT_PKG_TYPE = PKG_TYPE_RPM
DEFAULT_PNS = 'EasyBuildPNS'
DEFAULT_PREFIX = os.path.join(os.path.expanduser('~'), ".local", "easybuild")
DEFAULT_REPOSITORY = 'FileRepository'

EBROOT_ENV_VAR_ACTIONS = [ERROR, IGNORE, UNSET, WARN]
LOADED_MODULES_ACTIONS = [ERROR, IGNORE, PURGE, UNLOAD, WARN]
DEFAULT_ALLOW_LOADED_MODULES = ('EasyBuild',)

FORCE_DOWNLOAD_ALL = 'all'
FORCE_DOWNLOAD_PATCHES = 'patches'
FORCE_DOWNLOAD_SOURCES = 'sources'
FORCE_DOWNLOAD_CHOICES = [FORCE_DOWNLOAD_ALL, FORCE_DOWNLOAD_PATCHES, FORCE_DOWNLOAD_SOURCES]
DEFAULT_FORCE_DOWNLOAD = FORCE_DOWNLOAD_SOURCES

DOCKER_BASE_IMAGE_UBUNTU = 'ubuntu:16.04'
DOCKER_BASE_IMAGE_CENTOS = 'centos:7'


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
        'backup_modules',
        'container_base',
        'container_image_format',
        'container_image_name',
        'container_tmpdir',
        'download_timeout',
        'dump_test_report',
        'easyblock',
        'extra_modules',
        'filter_deps',
        'filter_env_vars',
        'hide_deps',
        'hide_toolchains',
        'force_download',
        'from_pr',
        'git_working_dirs_path',
        'github_user',
        'github_org',
        'group',
        'hooks',
        'ignore_dirs',
        'job_backend_config',
        'job_cores',
        'job_max_jobs',
        'job_max_walltime',
        'job_output_dir',
        'job_polling_interval',
        'job_target_resource',
        'modules_footer',
        'modules_header',
        'mpi_cmd_template',
        'only_blocks',
        'optarch',
        'package_tool_options',
        'parallel',
        'pr_branch_name',
        'pr_target_account',
        'pr_target_branch',
        'pr_target_repo',
        'rpath_filter',
        'regtest_output_dir',
        'skip',
        'stop',
        'subdir_user_modules',
        'test_report_env_filter',
        'testoutput',
        'umask',
        'zip_logs',
    ],
    False: [
        'add_dummy_to_minimal_toolchains',
        'allow_modules_tool_mismatch',
        'consider_archived_easyconfigs',
        'container_build_image',
        'debug',
        'debug_lmod',
        'dump_autopep8',
        'enforce_checksums',
        'extended_dry_run',
        'experimental',
        'fixed_installdir_naming_scheme',
        'force',
        'group_writable_installdir',
        'hidden',
        'ignore_checksums',
        'install_latest_eb_release',
        'lib64_fallback_sanity_check',
        'logtostdout',
        'minimal_toolchains',
        'module_only',
        'package',
        'read_only_installdir',
        'rebuild',
        'robot',
        'rpath',
        'search_paths',
        'sequential',
        'set_gid_bit',
        'skip_test_cases',
        'sticky_bit',
        'trace',
        'upload_test_report',
        'update_modules_tool_cache',
        'use_ccache',
        'use_f90cache',
        'use_existing_modules',
        'set_default_module',
    ],
    True: [
        'cleanup_builddir',
        'cleanup_easyconfigs',
        'cleanup_tmpdir',
        'extended_dry_run_ignore_errors',
        'mpi_tests',
    ],
    WARN: [
        'check_ebroot_env_vars',
        'detect_loaded_modules',
        'strict',
    ],
    DEFAULT_CONT_TYPE: [
        'container_type',
    ],
    DEFAULT_MAX_FAIL_RATIO_PERMS: [
        'max_fail_ratio_adjust_permissions',
    ],
    DEFAULT_PKG_RELEASE: [
        'package_release',
    ],
    DEFAULT_PKG_TOOL: [
        'package_tool',
    ],
    DEFAULT_PKG_TYPE: [
        'package_type',
    ],
    GENERAL_CLASS: [
        'suffix_modules_path',
    ],
    'defaultopt': [
        'default_opt_level',
    ],
    DEFAULT_ALLOW_LOADED_MODULES: [
        'allow_loaded_modules',
    ],
}
# build option that do not have a perfectly matching command line option
BUILD_OPTIONS_OTHER = {
    None: [
        'build_specs',
        'command_line',
        'external_modules_metadata',
        'pr_path',
        'robot_path',
        'valid_module_classes',
        'valid_stops',
    ],
    False: [
        'dry_run',
        'recursive_mod_unload',
        'mod_depends_on',
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
        'buildpath',
        'config',
        'containerpath',
        'installpath',
        'installpath_modules',
        'installpath_software',
        'job_backend',
        'logfile_format',
        'moduleclasses',
        'module_naming_scheme',
        'module_syntax',
        'modules_tool',
        'packagepath',
        'package_naming_scheme',
        'prefix',
        'repository',
        'repositorypath',
        'sourcepath',
        'subdir_modules',
        'subdir_software',
        'tmp_logdir',
    ]
    KNOWN_KEYS = REQUIRED  # KNOWN_KEYS must be defined for FrozenDictKnownKeys functionality

    def get_items_check_required(self):
        """
        For all known/required keys, check if exists and return all key/value pairs.
            no_missing: boolean, when True, will throw error message for missing values
        """
        missing = [x for x in self.KNOWN_KEYS if x not in self]
        if len(missing) > 0:
            raise EasyBuildError("Cannot determine value for configuration variables %s. Please specify it.", missing)

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
        raise EasyBuildError("Value for sourcepath has invalid type (%s): %s", type(sourcepath), sourcepath)

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

        if cmdline_options.new_pr or cmdline_options.update_pr:
            _log.info("Retaining all dependencies of specified easyconfigs to create/update pull request")
            retain_all_deps = True

        auto_ignore_osdeps_options = [cmdline_options.check_conflicts, cmdline_options.containerize,
                                      cmdline_options.dep_graph, cmdline_options.dry_run,
                                      cmdline_options.dry_run_short, cmdline_options.extended_dry_run,
                                      cmdline_options.dump_env_script, cmdline_options.new_pr,
                                      cmdline_options.update_pr]
        if any(auto_ignore_osdeps_options):
            _log.info("Auto-enabling ignoring of OS dependencies")
            cmdline_options.ignore_osdeps = True

        cmdline_build_option_names = [k for ks in BUILD_OPTIONS_CMDLINE.values() for k in ks]
        active_build_options.update(dict([(key, getattr(cmdline_options, key)) for key in cmdline_build_option_names]))
        # other options which can be derived but have no perfectly matching cmdline option
        active_build_options.update({
            'check_osdeps': not cmdline_options.ignore_osdeps,
            'dry_run': cmdline_options.dry_run or cmdline_options.dry_run_short,
            'recursive_mod_unload': cmdline_options.recursive_module_unload,
            'mod_depends_on': cmdline_options.module_depends_on,
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


def build_option(key, **kwargs):
    """Obtain value specified build option."""
    build_options = BuildOptions()
    if key in build_options:
        return build_options[key]
    elif 'default' in kwargs:
        return kwargs['default']
    else:
        raise EasyBuildError("Undefined build option: %s", key)


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

    known_types = ['modules', 'software']
    if typ not in known_types:
        raise EasyBuildError("Unknown type specified in install_path(): %s (known: %s)", typ, ', '.join(known_types))

    variables = ConfigurationVariables()

    key = 'installpath_%s' % typ
    res = variables[key]
    if res is None:
        key = 'subdir_%s' % typ
        res = os.path.join(variables['installpath'], variables[key])
        _log.debug("%s install path as specified by 'installpath' and '%s': %s", typ, key, res)
    else:
        _log.debug("%s install path as specified by '%s': %s", typ, key, res)

    return res


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


def get_package_naming_scheme():
    """
    Return the package naming scheme
    """
    return ConfigurationVariables()['package_naming_scheme']


def package_path():
    """
    Return the path where built packages are copied to
    """
    return ConfigurationVariables()['packagepath']


def container_path():
    """
    Return the path for container recipes & images
    """
    return ConfigurationVariables()['containerpath']


def get_modules_tool():
    """
    Return modules tool (EnvironmentModulesC, Lmod, ...)
    """
    # 'modules_tool' key will only be present if EasyBuild config is initialized
    return ConfigurationVariables().get('modules_tool', None)


def get_module_naming_scheme():
    """
    Return module naming scheme (EasyBuildMNS, HierarchicalMNS, ...)
    """
    return ConfigurationVariables()['module_naming_scheme']


def get_job_backend():
    """
    Return job execution backend (PBS, GC3Pie, ...)
    """
    # 'job_backend' key will only be present after EasyBuild config is initialized
    return ConfigurationVariables().get('job_backend', None)


def get_module_syntax():
    """
    Return module syntax (Lua, Tcl)
    """
    return ConfigurationVariables()['module_syntax']


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


def get_log_filename(name, version, add_salt=False, date=None, timestamp=None):
    """
    Generate a filename to be used for logging

    :param name: software name ('%(name)s')
    :param version: software version ('%(version)s')
    :param add_salt: add salt (5 random characters)
    :param date: string representation of date to use ('%(date)s')
    :param timestamp: timestamp to use ('%(time)s')
    """
    if date is None:
        date = time.strftime("%Y%m%d")
    if timestamp is None:
        timestamp = time.strftime("%H%M%S")

    filename = log_file_format() % {
        'name': name,
        'version': version,
        'date': date,
        'time': timestamp,
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


def find_last_log(curlog):
    """
    Find location to last log file that is still available.

    :param curlog: location to log file of current session
    :return: path to last log file (or None if no log files were found)
    """
    variables = ConfigurationVariables()
    log_dir = get_build_log_path()
    if variables['tmp_logdir'] is None:
        # take info account that last part of default temporary logdir is random, if --tmp-logdir is not specified
        log_dir = os.path.join(os.path.dirname(log_dir), '*')

    glob_pattern = os.path.join(log_dir, 'easybuild*.log')  # see init_logging
    _log.info("Looking for log files that match filename pattern '%s'...", glob_pattern)

    try:
        my_uid = os.getuid()
        paths = []
        for path in glob.glob(glob_pattern):
            path_info = os.stat(path)
            # only retain logs owned by current user
            if path_info.st_uid == my_uid:
                paths.append((path_info.st_mtime, path))
            else:
                _log.debug("Skipping %s, not owned by current user", path)

        # sorted retained paths by modification time, most recent last
        sorted_paths = [p for (_, p) in sorted(paths)]

    except OSError as err:
        raise EasyBuildError("Failed to locate/select/order log files matching '%s': %s", glob_pattern, err)

    try:
        # log of current session is typically listed last, should be taken into account
        res = sorted_paths[-1]
        if os.path.exists(curlog) and os.path.samefile(res, curlog):
            res = sorted_paths[-2]

    except IndexError:
        _log.debug("No last log file found (sorted retained paths: %s)", sorted_paths)
        res = None

    _log.debug("Picked %s as last log file (current: %s) from %s", res, curlog, sorted_paths)
    return res


def module_classes():
    """
    Return list of module classes specified in config file.
    """
    return ConfigurationVariables()['moduleclasses']


def read_environment(env_vars, strict=False):
    """NO LONGER SUPPORTED: use read_environment from easybuild.tools.environment instead"""
    _log.nosupport("read_environment has moved to easybuild.tools.environment", '2.0')
