# #
# Copyright 2009-2025 Ghent University
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

Authors:

* Stijn De Weirdt (Ghent University)
* Dries Verdegem (Ghent University)
* Kenneth Hoste (Ghent University)
* Pieter De Baets (Ghent University)
* Jens Timmerman (Ghent University)
* Toon Willems (Ghent University)
* Ward Poelmans (Ghent University)
* Damian Alvarez (Forschungszentrum Juelich GmbH)
* Andy Georges (Ghent University)
* Maxime Boissonneault (Compute Canada)
"""
import copy
import glob
import os
import random
import tempfile
import time
from abc import ABCMeta
from string import ascii_letters

from easybuild.base import fancylogger
from easybuild.base.frozendict import FrozenDictKnownKeys
from easybuild.base.wrapper import create_base_metaclass
from easybuild.tools.build_log import EasyBuildError, EasyBuildExit

try:
    import rich  # noqa
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False


_log = fancylogger.getLogger('config', fname=False)


ERROR = 'error'
IGNORE = 'ignore'
PURGE = 'purge'
UNLOAD = 'unload'
UNSET = 'unset'
WARN = 'warn'

EMPTY_LIST = 'empty_list'

DATA = 'data'
MODULES = 'modules'
SOFTWARE = 'software'

PKG_TOOL_FPM = 'fpm'
PKG_TYPE_RPM = 'rpm'

CONT_IMAGE_FORMAT_EXT3 = 'ext3'
CONT_IMAGE_FORMAT_SANDBOX = 'sandbox'
CONT_IMAGE_FORMAT_SIF = 'sif'
CONT_IMAGE_FORMAT_SQUASHFS = 'squashfs'
CONT_IMAGE_FORMATS = [
    CONT_IMAGE_FORMAT_EXT3,
    CONT_IMAGE_FORMAT_SANDBOX,
    CONT_IMAGE_FORMAT_SIF,
    CONT_IMAGE_FORMAT_SQUASHFS,
]

CONT_TYPE_APPTAINER = 'apptainer'
CONT_TYPE_DOCKER = 'docker'
CONT_TYPE_SINGULARITY = 'singularity'
CONT_TYPES = [CONT_TYPE_APPTAINER, CONT_TYPE_DOCKER, CONT_TYPE_SINGULARITY]
DEFAULT_CONT_TYPE = CONT_TYPE_SINGULARITY

DEFAULT_BRANCH = 'develop'
DEFAULT_DOWNLOAD_INITIAL_WAIT_TIME = 10
DEFAULT_DOWNLOAD_MAX_ATTEMPTS = 6
DEFAULT_DOWNLOAD_TIMEOUT = 10
DEFAULT_ENV_FOR_SHEBANG = '/usr/bin/env'
DEFAULT_ENVVAR_USERS_MODULES = 'HOME'
DEFAULT_INDEX_MAX_AGE = 7 * 24 * 60 * 60  # 1 week (in seconds)
DEFAULT_JOB_BACKEND = 'Slurm'
DEFAULT_JOB_EB_CMD = 'eb'
DEFAULT_LOGFILE_FORMAT = ("easybuild", "easybuild-%(name)s-%(version)s-%(date)s.%(time)s.log")
DEFAULT_MAX_FAIL_RATIO_PERMS = 0.5
DEFAULT_MAX_PARALLEL = 16
DEFAULT_MINIMAL_BUILD_ENV = 'CC:gcc,CXX:g++'
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
    'sourcepath_data': 'sources',
    'subdir_data': DATA,
    'subdir_modules': MODULES,
    'subdir_software': SOFTWARE,
}
DEFAULT_PKG_RELEASE = '1'
DEFAULT_PKG_TOOL = PKG_TOOL_FPM
DEFAULT_PKG_TYPE = PKG_TYPE_RPM
DEFAULT_PNS = 'EasyBuildPNS'
DEFAULT_PR_TARGET_ACCOUNT = 'easybuilders'
DEFAULT_PREFIX = os.path.join(os.path.expanduser('~'), ".local", "easybuild")
DEFAULT_REPOSITORY = 'FileRepository'
EASYBUILD_SOURCES_URL = 'https://sources.easybuild.io'
DEFAULT_EXTRA_SOURCE_URLS = (EASYBUILD_SOURCES_URL,)
# Filter these CUDA libraries by default from the RPATH sanity check.
# These are the only four libraries for which the CUDA toolkit ships stubs. By design, one is supposed to build
# against the stub versions, but use the libraries that come with the CUDA driver at runtime. That means they should
# never be RPATH-ed, and thus the sanity check should also accept that they aren't RPATH-ed.
DEFAULT_FILTER_RPATH_SANITY_LIBS = (
    'libcuda.so',
    'libcuda.so.1',
    'libnvidia-ml.so',
    'libnvidia-ml.so.1'
)
DEFAULT_WAIT_ON_LOCK_INTERVAL = 60
DEFAULT_WAIT_ON_LOCK_LIMIT = 0

EBROOT_ENV_VAR_ACTIONS = [ERROR, IGNORE, UNSET, WARN]
LOADED_MODULES_ACTIONS = [ERROR, IGNORE, PURGE, UNLOAD, WARN]
DEFAULT_ALLOW_LOADED_MODULES = ('EasyBuild',)

FORCE_DOWNLOAD_ALL = 'all'
FORCE_DOWNLOAD_PATCHES = 'patches'
FORCE_DOWNLOAD_SOURCES = 'sources'
FORCE_DOWNLOAD_CHOICES = [FORCE_DOWNLOAD_ALL, FORCE_DOWNLOAD_PATCHES, FORCE_DOWNLOAD_SOURCES]
DEFAULT_FORCE_DOWNLOAD = FORCE_DOWNLOAD_SOURCES

CHECKSUM_PRIORITY_JSON = "json"
CHECKSUM_PRIORITY_EASYCONFIG = "easyconfig"
CHECKSUM_PRIORITY_CHOICES = [CHECKSUM_PRIORITY_JSON, CHECKSUM_PRIORITY_EASYCONFIG]
DEFAULT_CHECKSUM_PRIORITY = CHECKSUM_PRIORITY_EASYCONFIG

# package name for generic easyblocks
GENERIC_EASYBLOCK_PKG = 'generic'

# general module class
GENERAL_CLASS = 'all'

JOB_DEPS_TYPE_ABORT_ON_ERROR = 'abort_on_error'
JOB_DEPS_TYPE_ALWAYS_RUN = 'always_run'

DOCKER_BASE_IMAGE_UBUNTU = 'ubuntu:20.04'
DOCKER_BASE_IMAGE_CENTOS = 'centos:7'

LOCAL_VAR_NAMING_CHECK_ERROR = 'error'
LOCAL_VAR_NAMING_CHECK_LOG = 'log'
LOCAL_VAR_NAMING_CHECK_WARN = WARN
LOCAL_VAR_NAMING_CHECKS = [LOCAL_VAR_NAMING_CHECK_ERROR, LOCAL_VAR_NAMING_CHECK_LOG, LOCAL_VAR_NAMING_CHECK_WARN]

OUTPUT_STYLE_AUTO = 'auto'
OUTPUT_STYLE_BASIC = 'basic'
OUTPUT_STYLE_NO_COLOR = 'no_color'
OUTPUT_STYLE_RICH = 'rich'
OUTPUT_STYLES = (OUTPUT_STYLE_AUTO, OUTPUT_STYLE_BASIC, OUTPUT_STYLE_NO_COLOR, OUTPUT_STYLE_RICH)

SEARCH_PATH_BIN_DIRS = ['bin']
SEARCH_PATH_HEADER_DIRS = ['include']
SEARCH_PATH_LIB_DIRS = ['lib', 'lib64']

PYTHONPATH = 'PYTHONPATH'
EBPYTHONPREFIXES = 'EBPYTHONPREFIXES'
PYTHON_SEARCH_PATH_TYPES = [PYTHONPATH, EBPYTHONPREFIXES]

# options to handle header search paths in environment of modules
MOD_SEARCH_PATH_HEADERS_CPATH = 'cpath'
MOD_SEARCH_PATH_HEADERS_INCLUDE_PATHS = 'include_paths'
MOD_SEARCH_PATH_HEADERS = {
    MOD_SEARCH_PATH_HEADERS_CPATH: ['CPATH'],
    MOD_SEARCH_PATH_HEADERS_INCLUDE_PATHS: ['C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH'],
}
DEFAULT_MOD_SEARCH_PATH_HEADERS = MOD_SEARCH_PATH_HEADERS_CPATH


class Singleton(ABCMeta):
    """Serves as metaclass for classes that should implement the Singleton pattern.

    See http://stackoverflow.com/questions/6760685/creating-a-singleton-in-python
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


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
        'banned_linked_shared_libs',
        'checksum_priority',
        'container_config',
        'container_image_format',
        'container_image_name',
        'container_template_recipe',
        'container_tmpdir',
        'cuda_cache_dir',
        'cuda_cache_maxsize',
        'cuda_compute_capabilities',
        'dump_test_report',
        'easyblock',
        'envvars_user_modules',
        'extra_modules',
        'filter_deps',
        'filter_ecs',
        'filter_env_vars',
        'filter_rpath_sanity_libs',
        'force_download',
        'from_commit',
        'git_working_dirs_path',
        'github_user',
        'github_org',
        'group',
        'hide_deps',
        'hide_toolchains',
        'http_header_fields_urlpat',
        'hooks',
        'ignore_dirs',
        'include_easyblocks_from_commit',
        'insecure_download',
        'job_backend_config',
        'job_cores',
        'job_deps_type',
        'job_max_jobs',
        'job_max_walltime',
        'job_output_dir',
        'job_polling_interval',
        'job_target_resource',
        'locks_dir',
        'module_cache_suffix',
        'modules_footer',
        'modules_header',
        'mpi_cmd_template',
        'only_blocks',
        'optarch',
        'package_tool_options',
        'parallel',
        'pr_branch_name',
        'pr_commit_msg',
        'pr_descr',
        'pr_target_repo',
        'pr_title',
        'regtest_output_dir',
        'rpath_filter',
        'rpath_override_dirs',
        'required_linked_shared_libs',
        'search_path_cpp_headers',
        'search_path_linker',
        'skip',
        'software_commit',
        'stop',
        'subdir_user_modules',
        'sysroot',
        'test_report_env_filter',
        'testoutput',
        'umask',
        'zip_logs',
    ],
    False: [
        'add_system_to_minimal_toolchains',
        'allow_modules_tool_mismatch',
        'allow_unresolved_templates',
        'backup_patched_files',
        'consider_archived_easyconfigs',
        'container_build_image',
        'debug',
        'debug_lmod',
        'dump_autopep8',
        'dump_env_script',
        'enforce_checksums',
        'experimental',
        'extended_dry_run',
        'fail_on_mod_files_gcccore',
        'force',
        'generate_devel_module',
        'group_writable_installdir',
        'hidden',
        'ignore_checksums',
        'ignore_index',
        'ignore_locks',
        'ignore_test_failure',
        'install_latest_eb_release',
        'keep_debug_symbols',
        'logtostdout',
        'minimal_toolchains',
        'module_only',
        'package',
        'parallel_extensions_install',
        'read_only_installdir',
        'rebuild',
        'remove_ghost_install_dirs',
        'rpath',
        'sanity_check_only',
        'sequential',
        'set_default_module',
        'set_gid_bit',
        'silence_hook_trigger',
        'skip_extensions',
        'skip_sanity_check',
        'skip_test_cases',
        'skip_test_step',
        'sticky_bit',
        'terse',
        'unit_testing_mode',
        'upload_test_report',
        'update_modules_tool_cache',
        'use_ccache',
        'use_existing_modules',
        'use_f90cache',
        'wait_on_lock_limit',
    ],
    True: [
        'cleanup_builddir',
        'cleanup_easyconfigs',
        'cleanup_tmpdir',
        'extended_dry_run_ignore_errors',
        'fixed_installdir_naming_scheme',
        'lib_lib64_symlink',
        'lib64_fallback_sanity_check',
        'lib64_lib_symlink',
        'map_toolchains',
        'module_extensions',
        'modules_tool_version_check',
        'mpi_tests',
        'pre_create_installdir',
        'show_progress_bar',
        'strict_rpath_sanity_check',
        'trace',
    ],
    EMPTY_LIST: [
        'accept_eula_for',
        'from_pr',
        'include_easyblocks_from_pr',
        'robot',
        'search_paths',
        'silence_deprecation_warnings',
    ],
    WARN: [
        'check_ebroot_env_vars',
        'detect_loaded_modules',
        'local_var_naming_check',
        'strict',
    ],
    DEFAULT_CONT_TYPE: [
        'container_type',
    ],
    DEFAULT_BRANCH: [
        'pr_target_branch',
    ],
    DEFAULT_DOWNLOAD_TIMEOUT: [
        'download_timeout',
    ],
    DEFAULT_ENV_FOR_SHEBANG: [
        'env_for_shebang',
    ],
    DEFAULT_INDEX_MAX_AGE: [
        'index_max_age',
    ],
    DEFAULT_JOB_EB_CMD: [
        'job_eb_cmd',
    ],
    DEFAULT_MAX_FAIL_RATIO_PERMS: [
        'max_fail_ratio_adjust_permissions',
    ],
    DEFAULT_MAX_PARALLEL: [
        'max_parallel',
    ],
    DEFAULT_MINIMAL_BUILD_ENV: [
        'minimal_build_env',
    ],
    DEFAULT_MOD_SEARCH_PATH_HEADERS: [
        'module_search_path_headers',
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
    DEFAULT_PR_TARGET_ACCOUNT: [
        'pr_target_account',
    ],
    GENERAL_CLASS: [
        'suffix_modules_path',
    ],
    'defaultopt': [
        'default_opt_level',
    ],
    DEFAULT_EXTRA_SOURCE_URLS: [
        'extra_source_urls',
    ],
    DEFAULT_ALLOW_LOADED_MODULES: [
        'allow_loaded_modules',
    ],
    DEFAULT_WAIT_ON_LOCK_INTERVAL: [
        'wait_on_lock_interval',
    ],
    OUTPUT_STYLE_AUTO: [
        'output_style',
    ],
    PYTHONPATH: [
        'prefer_python_search_path',
    ]
}
# build option that do not have a perfectly matching command line option
BUILD_OPTIONS_OTHER = {
    None: [
        'build_specs',
        'command_line',
        'external_modules_metadata',
        'extra_ec_paths',
        'mod_depends_on',  # deprecated
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


# loosely based on
# https://wickie.hlrs.de/platforms/index.php/Module_Overview
# https://wickie.hlrs.de/platforms/index.php/Application_software_packages
MODULECLASS_BASE = 'base'
DEFAULT_MODULECLASSES = [
    (MODULECLASS_BASE, "Default module class"),
    ('ai', "Artificial Intelligence (incl. Machine Learning)"),
    ('astro', "Astronomy, Astrophysics and Cosmology"),
    ('bio', "Bioinformatics, biology and biomedical"),
    ('cae', "Computer Aided Engineering (incl. CFD)"),
    ('chem', "Chemistry, Computational Chemistry and Quantum Chemistry"),
    ('compiler', "Compilers"),
    ('data', "Data management & processing tools"),
    ('dataset', "Datasets"),
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
    ('quantum', "Quantum Computing"),
    ('phys', "Physics and physical systems simulations"),
    ('system', "System utilities (e.g. highly depending on system OS and hardware)"),
    ('toolchain', "EasyBuild toolchains"),
    ('tools', "General purpose tools"),
    ('vis', "Visualization, plotting, documentation and typesetting"),
]


# singleton metaclass: only one instance is created
BaseConfigurationVariables = create_base_metaclass('BaseConfigurationVariables', Singleton, FrozenDictKnownKeys)


class ConfigurationVariables(BaseConfigurationVariables):
    """This is a dict that supports legacy config names transparently."""

    # list of known/required keys
    REQUIRED = [
        'buildpath',
        'config',
        'containerpath',
        'failed_install_build_dirs_path',
        'failed_install_logs_path',
        'installpath',
        'installpath_data',
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
        'sourcepath_data',
        'subdir_data',
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
            raise EasyBuildError(
                "Cannot determine value for configuration variables %s. Please specify it.", ', '.join(missing),
                exit_code=EasyBuildExit.OPTION_ERROR
            )

        return self.items()


# singleton metaclass: only one instance is created
BaseBuildOptions = create_base_metaclass('BaseBuildOptions', Singleton, FrozenDictKnownKeys)


class BuildOptions(BaseBuildOptions):
    """Representation of a set of build options, acts like a dictionary."""

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

    if tmpdict['sourcepath_data'] is None:
        tmpdict['sourcepath_data'] = tmpdict['sourcepath'][:]

    for srcpath in ['sourcepath', 'sourcepath_data']:
        # make sure source path is a list
        sourcepath = tmpdict[srcpath]
        if isinstance(sourcepath, str):
            tmpdict[srcpath] = sourcepath.split(':')
            _log.debug("Converted source path ('%s') to a list of paths: %s" % (sourcepath, tmpdict[srcpath]))
        elif not isinstance(sourcepath, (tuple, list)):
            raise EasyBuildError(
                "Value for %s has invalid type (%s): %s", srcpath, type(sourcepath), sourcepath,
                exit_code=EasyBuildExit.OPTION_ERROR
            )

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
        if cmdline_options.dep_graph or cmdline_options.check_conflicts:
            _log.info("Enabling force to generate dependency graph.")
            cmdline_options.force = True
            retain_all_deps = True

        new_update_opt = cmdline_options.new_branch_github or cmdline_options.new_pr
        new_update_opt = new_update_opt or cmdline_options.update_branch_github or cmdline_options.update_pr

        if new_update_opt:
            _log.info("Retaining all dependencies of specified easyconfigs to create/update branch or pull request")
            retain_all_deps = True

        auto_ignore_osdeps_options = [cmdline_options.check_conflicts, cmdline_options.check_contrib,
                                      cmdline_options.check_style, cmdline_options.containerize,
                                      cmdline_options.dep_graph, cmdline_options.dry_run,
                                      cmdline_options.dry_run_short, cmdline_options.dump_env_script,
                                      cmdline_options.extended_dry_run, cmdline_options.fix_deprecated_easyconfigs,
                                      cmdline_options.missing_modules, cmdline_options.new_branch_github,
                                      cmdline_options.new_pr, cmdline_options.preview_pr,
                                      cmdline_options.update_branch_github, cmdline_options.update_pr]
        if any(auto_ignore_osdeps_options):
            _log.info("Auto-enabling ignoring of OS dependencies")
            cmdline_options.ignore_osdeps = True

        cmdline_build_option_names = [k for ks in BUILD_OPTIONS_CMDLINE.values() for k in ks]
        active_build_options.update({key: getattr(cmdline_options, key) for key in cmdline_build_option_names})
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
        for default, options in build_options_by_default.items():
            if default == EMPTY_LIST:
                for opt in options:
                    bo[opt] = []
            else:
                bo.update({opt: default for opt in options})
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
        error_msg = "Undefined build option: '%s'. " % key
        error_msg += "Make sure you have set up the EasyBuild configuration using set_up_configuration() "
        error_msg += "(from easybuild.tools.options) in case you're not using EasyBuild via the 'eb' CLI."
        raise EasyBuildError(error_msg, exit_code=EasyBuildExit.OPTION_ERROR)


def update_build_option(key, value):
    """
    Update build option with specified name to given value.

    WARNING: Use this with care, the build options are not expected to be changed during an EasyBuild session!
    """
    # BuildOptions() is a (singleton) frozen dict, so this is less straightforward that it seems...
    build_options = BuildOptions()
    orig_value = build_options._FrozenDict__dict[key]
    build_options._FrozenDict__dict[key] = value
    _log.warning("Build option '%s' was updated to: %s", key, build_option(key))

    # Return original value, so it can be restored later if needed
    return orig_value


def update_build_options(key_value_dict):
    """
    Update build options as specified by the given dictionary (where keys are assumed to be build option names).
    Returns dictionary with original values for the updated build options.
    """
    orig_key_value_dict = {}
    for key, value in key_value_dict.items():
        orig_key_value_dict[key] = update_build_option(key, value)

    # Return original key-value pairs in a dictionary.
    # This way, they can later be restored by a single call to update_build_options(orig_key_value_dict)
    return orig_key_value_dict


def build_path():
    """
    Return the build path
    """
    return ConfigurationVariables()['buildpath']


def source_paths():
    """
    Return the list of source paths for software
    """
    return ConfigurationVariables()['sourcepath']


def source_paths_data():
    """
    Return the list of source paths for data
    """
    return ConfigurationVariables()['sourcepath_data']


def source_path():
    """NO LONGER SUPPORTED: use source_paths instead"""
    _log.nosupport("source_path() is replaced by source_paths()", '2.0')


def install_path(typ=None):
    """
    Returns the install path
    - subdir 'software' for actual software installation (default)
    - subdir 'modules' for environment modules (typ='mod')
    - subdir 'data' for data installation (typ='data')
    """
    if typ is None:
        typ = SOFTWARE
    elif typ == 'mod':
        typ = MODULES

    known_types = [MODULES, SOFTWARE, DATA]
    if typ not in known_types:
        raise EasyBuildError(
            "Unknown type specified in install_path(): %s (known: %s)", typ, ', '.join(known_types),
            exit_code=EasyBuildExit.OPTION_ERROR
        )

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
    Return modules tool (EnvironmentModules, Lmod, ...)
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


def get_output_style():
    """Return output style to use."""
    output_style = build_option('output_style')

    if output_style == OUTPUT_STYLE_AUTO:
        if HAVE_RICH:
            output_style = OUTPUT_STYLE_RICH
        else:
            output_style = OUTPUT_STYLE_BASIC

    if output_style == OUTPUT_STYLE_RICH and not HAVE_RICH:
        raise EasyBuildError(
            "Can't use '%s' output style, Rich Python package is not available!", OUTPUT_STYLE_RICH,
            exit_code=EasyBuildExit.MISSING_EB_DEPENDENCY
        )

    return output_style


def log_file_format(return_directory=False, ec=None, date=None, timestamp=None):
    """
    Return the format for the logfile or the directory

    :param ec: dict-like value that provides values for %(name)s and %(version)s template values
    :param date: string representation of date to use ('%(date)s')
    :param timestamp: timestamp to use ('%(time)s')
    """
    if ec is None:
        ec = {}

    name, version = ec.get('name', '%(name)s'), ec.get('version', '%(version)s')

    if date is None:
        date = '%(date)s'
    if timestamp is None:
        timestamp = '%(time)s'

    logfile_format = ConfigurationVariables()['logfile_format']
    if not isinstance(logfile_format, tuple) or len(logfile_format) != 2:
        raise EasyBuildError(
            "Incorrect log file format specification, should be 2-tuple (<dir>, <filename>): %s", logfile_format,
            exit_code=EasyBuildExit.OPTION_ERROR
        )

    idx = int(not return_directory)
    res = ConfigurationVariables()['logfile_format'][idx] % {
        'date': date,
        'name': name,
        'time': timestamp,
        'version': version,
    }

    return res


def log_format(ec=None):
    """
    Return the logfilename format
    """
    # TODO needs renaming, is actually a formatter for the logfilename
    return log_file_format(return_directory=False, ec=ec)


def log_path(ec=None):
    """
    Return the log path
    """
    date = time.strftime("%Y%m%d")
    timestamp = time.strftime("%H%M%S")
    return log_file_format(return_directory=True, ec=ec, date=date, timestamp=timestamp)


def get_failed_install_build_dirs_path(ec):
    """
    Return the location where the build directory is copied to if installation failed

    :param ec:  dict-like value with 'name' and 'version' keys defined
    """
    base_path = ConfigurationVariables()['failed_install_build_dirs_path']
    if not base_path:
        return None

    try:
        name, version = ec['name'], ec['version']
    except KeyError:
        raise EasyBuildError("The 'name' and 'version' keys are required.")

    return os.path.join(base_path, f'{name}-{version}')


def get_failed_install_logs_path(ec):
    """
    Return the location where log files are copied to if installation failed

    :param ec:  dict-like value with 'name' and 'version' keys defined
    """
    base_path = ConfigurationVariables()['failed_install_logs_path']
    if not base_path:
        return None

    try:
        name, version = ec['name'], ec['version']
    except KeyError:
        raise EasyBuildError("The 'name' and 'version' keys are required.")

    return os.path.join(base_path, f'{name}-{version}')


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

    filename = log_file_format(ec={'name': name, 'version': version}, date=date, timestamp=timestamp)

    if add_salt:
        salt = ''.join(random.choice(ascii_letters) for i in range(5))
        filename_parts = filename.split('.')
        filename = '.'.join(filename_parts[:-1] + [salt, filename_parts[-1]])

    filepath = os.path.join(get_build_log_path(), filename)

    # Append numbers if the log file already exist
    counter = 0
    while os.path.exists(filepath):
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
        raise EasyBuildError(
            "Failed to locate/select/order log files matching '%s': %s", glob_pattern, err,
            exit_code=EasyBuildExit.OPTION_ERROR
        )

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
