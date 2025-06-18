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
Generic EasyBuild support for building and installing software.
The EasyBlock class should serve as a base class for all easyblocks.

Authors:

* Stijn De Weirdt (Ghent University)
* Dries Verdegem (Ghent University)
* Kenneth Hoste (Ghent University)
* Pieter De Baets (Ghent University)
* Jens Timmerman (Ghent University)
* Toon Willems (Ghent University)
* Ward Poelmans (Ghent University)
* Fotis Georgatos (Uni.Lu, NTUA)
* Damian Alvarez (Forschungszentrum Juelich GmbH)
* Maxime Boissonneault (Compute Canada)
* Davide Vanzo (Vanderbilt University)
* Caspar van Leeuwen (SURF)
* Jan Andre Reuter (Juelich Supercomputing Centre)
* Jasper Grimm (UoY)
"""
import concurrent
import copy
import functools
import glob
import inspect
import json
import os
import random
import re
import shutil
import stat
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from string import ascii_letters
from textwrap import indent

import easybuild.tools.environment as env
import easybuild.tools.toolchain as toolchain
from easybuild.base import fancylogger
from easybuild.framework.easyconfig import EASYCONFIGS_PKG_SUBDIR
from easybuild.framework.easyconfig.easyconfig import ITERATE_OPTIONS, EasyConfig, ActiveMNS, get_easyblock_class
from easybuild.framework.easyconfig.easyconfig import get_module_path, letter_dir_for, resolve_template
from easybuild.framework.easyconfig.format.format import SANITY_CHECK_PATHS_DIRS, SANITY_CHECK_PATHS_FILES
from easybuild.framework.easyconfig.parser import fetch_parameters_from_easyconfig
from easybuild.framework.easyconfig.style import MAX_LINE_LENGTH
from easybuild.framework.easyconfig.tools import dump_env_easyblock, get_paths_for
from easybuild.framework.easyconfig.templates import TEMPLATE_NAMES_EASYBLOCK_RUN_STEP, template_constant_dict
from easybuild.framework.extension import Extension, resolve_exts_filter_template
from easybuild.tools import LooseVersion, config
from easybuild.tools.build_details import get_build_stats
from easybuild.tools.build_log import EasyBuildError, EasyBuildExit, dry_run_msg, dry_run_warning, dry_run_set_dirs
from easybuild.tools.build_log import print_error, print_msg, print_warning
from easybuild.tools.config import CHECKSUM_PRIORITY_JSON, DEFAULT_ENVVAR_USERS_MODULES
from easybuild.tools.config import EASYBUILD_SOURCES_URL, EBPYTHONPREFIXES  # noqa
from easybuild.tools.config import FORCE_DOWNLOAD_ALL, FORCE_DOWNLOAD_PATCHES, FORCE_DOWNLOAD_SOURCES
from easybuild.tools.config import MOD_SEARCH_PATH_HEADERS, PYTHONPATH, SEARCH_PATH_BIN_DIRS, SEARCH_PATH_LIB_DIRS
from easybuild.tools.config import build_option, build_path, get_failed_install_build_dirs_path
from easybuild.tools.config import get_failed_install_logs_path, get_log_filename, get_repository, get_repositorypath
from easybuild.tools.config import install_path, log_path, package_path, source_paths, source_paths_data
from easybuild.tools.config import DATA, SOFTWARE
from easybuild.tools.environment import restore_env, sanitize_env
from easybuild.tools.filetools import CHECKSUM_TYPE_SHA256
from easybuild.tools.filetools import adjust_permissions, apply_patch, back_up_file, change_dir, check_lock
from easybuild.tools.filetools import compute_checksum, convert_name, copy_dir, copy_file, create_lock
from easybuild.tools.filetools import create_non_existing_paths, create_patch_info, derive_alt_pypi_url, diff_files
from easybuild.tools.filetools import download_file, encode_class_name, extract_file, find_backup_name_candidate
from easybuild.tools.filetools import get_cwd, get_source_tarball_from_git, is_alt_pypi_url, is_binary, is_parent_path
from easybuild.tools.filetools import is_sha256_checksum, mkdir, move_file, move_logs, read_file, remove_dir
from easybuild.tools.filetools import remove_file, remove_lock, symlink, verify_checksum, weld_paths, write_file
from easybuild.tools.hooks import (
    BUILD_STEP, CLEANUP_STEP, CONFIGURE_STEP, EASYBLOCK, EXTENSIONS_STEP, EXTRACT_STEP, FETCH_STEP, INSTALL_STEP,
    MODULE_STEP, MODULE_WRITE, PACKAGE_STEP, PATCH_STEP, PERMISSIONS_STEP, POSTITER_STEP, POSTPROC_STEP, PREPARE_STEP,
    READY_STEP, SANITYCHECK_STEP, SINGLE_EXTENSION, TEST_STEP, TESTCASES_STEP, load_hooks, run_hook,
)
from easybuild.tools.run import RunShellCmdError, raise_run_shell_cmd_error, run_shell_cmd
from easybuild.tools.jenkins import write_to_xml
from easybuild.tools.module_generator import ModuleGeneratorLua, ModuleGeneratorTcl, module_generator, dependencies_for
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.modules import ROOT_ENV_VAR_NAME_PREFIX, VERSION_ENV_VAR_NAME_PREFIX, DEVEL_ENV_VAR_NAME_PREFIX
from easybuild.tools.modules import Lmod, ModEnvVarType, ModuleLoadEnvironment, MODULE_LOAD_ENV_HEADERS
from easybuild.tools.modules import curr_module_paths, invalidate_module_caches_for, get_software_root
from easybuild.tools.modules import get_software_root_env_var_name, get_software_version_env_var_name
from easybuild.tools.output import PROGRESS_BAR_DOWNLOAD_ALL, PROGRESS_BAR_EASYCONFIG, PROGRESS_BAR_EXTENSIONS
from easybuild.tools.output import show_progress_bars, start_progress_bar, stop_progress_bar, update_progress_bar
from easybuild.tools.package.utilities import package
from easybuild.tools.repository.repository import init_repository
from easybuild.tools.systemtools import check_linked_shared_libs, det_parallelism
from easybuild.tools.systemtools import get_cuda_architectures
from easybuild.tools.systemtools import get_linked_libs_raw, get_shared_lib_ext, pick_system_specific_value, use_group
from easybuild.tools.utilities import INDENT_4SPACES, get_class_for, nub, quote_str
from easybuild.tools.utilities import remove_unwanted_chars, time2str, trace_msg
from easybuild.tools.version import this_is_easybuild, VERBOSE_VERSION, VERSION

DEFAULT_BIN_LIB_SUBDIRS = SEARCH_PATH_BIN_DIRS + SEARCH_PATH_LIB_DIRS

MODULE_ONLY_STEPS = [MODULE_STEP, PREPARE_STEP, READY_STEP, POSTITER_STEP, SANITYCHECK_STEP]

# string part of URL for Python packages on PyPI that indicates needs to be rewritten (see derive_alt_pypi_url)
PYPI_PKG_URL_PATTERN = 'pypi.python.org/packages/source/'

# Directory name in which to store reproducibility files
REPROD = 'reprod'

CHECKSUMS_JSON = 'checksums.json'

_log = fancylogger.getLogger('easyblock')


def _obtain_file_update_progress_bar_on_return(func):
    """Decorator for obtain_file() to update the progress bar upon return"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        filename = args[1]

        # We don't account for the checksums file in the progress bar
        if filename != CHECKSUMS_JSON:
            update_progress_bar(PROGRESS_BAR_DOWNLOAD_ALL)

        return result
    return wrapper


class EasyBlock:
    """Generic support for building and installing software, base class for actual easyblocks."""

    # static class method for extra easyconfig parameter definitions
    # this makes it easy to access the information without needing an instance
    # subclasses of EasyBlock should call this method with a dictionary
    @staticmethod
    def extra_options(extra=None):
        """
        Extra options method which will be passed to the EasyConfig constructor.
        """
        if extra is None:
            extra = {}

        if not isinstance(extra, dict):
            _log.nosupport("Found 'extra' value of type '%s' in extra_options, should be 'dict'" % type(extra), '2.0')

        return extra

    #
    # INIT
    #
    def __init__(self, ec, logfile=None):
        """
        Initialize the EasyBlock instance.
        :param ec: a parsed easyconfig file (EasyConfig instance)
        :param logfile: pass logfile from other EasyBlock. If not passed, create logfile (optional)
        """

        # keep track of original working directory, so we can go back there
        self.orig_workdir = get_cwd()

        # dict of all hooks (mapping of name to function)
        self.hooks = load_hooks(build_option('hooks'))

        # list of patch/source files, along with checksums
        self.patches = []
        self.src = []
        self.data_src = []
        self.checksums = []
        self.json_checksums = None

        # build/install directories
        self.builddir = None
        self.installdir = None  # software or data
        self.installdir_mod = None  # module file

        # extensions
        self.exts = []
        self.exts_all = None
        self.ext_instances = []
        self.skip = None
        self.module_extra_extensions = ''  # extra stuff for module file required by extensions

        # indicates whether or not this instance represents an extension or not;
        # may be set to True by ExtensionEasyBlock
        self.is_extension = False

        # easyconfig for this application
        if isinstance(ec, EasyConfig):
            self.cfg = ec
        else:
            raise EasyBuildError("Value of incorrect type passed to EasyBlock constructor: %s ('%s')", type(ec), ec)

        # modules interface with default MODULEPATH
        self.modules_tool = self.cfg.modules_tool
        # module generator
        self.module_generator = module_generator(self, fake=True)
        self.mod_filepath = self.module_generator.get_module_filepath()
        self.mod_file_backup = None
        self.set_default_module = self.cfg.set_default_module

        # modules footer/header
        self.modules_footer = None
        modules_footer_path = build_option('modules_footer')
        if modules_footer_path is not None:
            self.modules_footer = read_file(modules_footer_path)

        self.modules_header = None
        modules_header_path = build_option('modules_header')
        if modules_header_path is not None:
            self.modules_header = read_file(modules_header_path)

        # environment variables on module load
        mod_load_aliases = {}
        # apply --module-search-path-headers: easyconfig parameter has precedence
        mod_load_cpp_headers = self.cfg['module_search_path_headers'] or build_option('module_search_path_headers')

        try:
            mod_load_aliases[MODULE_LOAD_ENV_HEADERS] = MOD_SEARCH_PATH_HEADERS[mod_load_cpp_headers]
        except KeyError as err:
            raise EasyBuildError(
                f"Unknown value selected for option module-search-path-headers: {mod_load_cpp_headers}. "
                f"Choose one of: {', '.join(MOD_SEARCH_PATH_HEADERS)}"
            ) from err

        self.module_load_environment = ModuleLoadEnvironment(aliases=mod_load_aliases)

        # determine install subdirectory, based on module name
        self.install_subdir = None

        # indicates whether build should be performed in installation dir
        self.build_in_installdir = self.cfg['buildininstalldir']

        # list of locations to include in RPATH filter used by toolchain
        self.rpath_filter_dirs = []

        # list of locations to include in RPATH used by toolchain
        self.rpath_include_dirs = []

        # directory to export RPATH wrappers to
        self.rpath_wrappers_dir = None

        # logging
        self.log = None
        self.logfile = logfile
        self.external_logfile = logfile is not None
        self.logdebug = build_option('debug')
        self.postmsg = ''  # allow a post message to be set, which can be shown as last output
        self.current_step = None

        # Create empty progress bar
        self.progress_bar = None
        self.pbar_task = None

        # list of loaded modules
        self.loaded_modules = []

        # iterate configure/build/options
        self.iter_idx = 0
        self.iter_opts = {}

        # sanity check fail error messages to report (if any)
        self.sanity_check_fail_msgs = []

        # keep track of whether module is loaded during sanity check step (to avoid re-loading)
        self.sanity_check_module_loaded = False
        # info required to roll back loading of fake module during sanity check (see _sanity_check_step method)
        self.fake_mod_data = None

        # robot path
        self.robot_path = build_option('robot_path')

        # original module path
        self.orig_modulepath = os.getenv('MODULEPATH')

        # keep track of initial environment we start in, so we can restore it if needed
        self.initial_environ = copy.deepcopy(os.environ)
        self.reset_environ = None
        self.tweaked_env_vars = {}

        # should we keep quiet?
        self.silent = build_option('silent')

        # are we doing a dry run?
        self.dry_run = build_option('extended_dry_run')

        # initialize logger
        self._init_log()

        # try and use the specified group (if any)
        group_name = build_option('group')
        group_spec = self.cfg['group']
        if group_spec is not None:
            if isinstance(group_spec, tuple):
                if len(group_spec) == 2:
                    group_spec = group_spec[0]
                else:
                    raise EasyBuildError("Found group spec in tuple format that is not a 2-tuple: %s", str(group_spec))
            self.log.warning("Group spec '%s' is overriding config group '%s'." % (group_spec, group_name))
            group_name = group_spec

        self.group = None
        if group_name is not None:
            self.group = use_group(group_name)

        # generate build/install directories
        self.gen_builddir()
        self.gen_installdir()

        self.ignored_errors = False

        if self.dry_run:
            self.init_dry_run()

        self.log.info("Init completed for application name %s version %s" % (self.name, self.version))

    def post_init(self):
        """
        Run post-initialization tasks.
        """
        if self.build_in_installdir:
            # self.builddir is set by self.gen_builddir(),
            # but needs to be correct if the build is performed in the installation directory
            self.log.info("Changing build dir to %s", self.installdir)
            self.builddir = self.installdir
        self.set_parallel()

    # INIT/CLOSE LOG
    def _init_log(self):
        """
        Initialize the logger.
        """
        if self.log is not None:
            return

        if self.logfile is None:
            self.logfile = get_log_filename(self.name, self.version, add_salt=True)
            fancylogger.logToFile(self.logfile, max_bytes=0)

        self.log = fancylogger.getLogger(name=self.__class__.__name__, fname=False)
        self.log.info(this_is_easybuild())

        this_module = inspect.getmodule(self)
        eb_class = self.__class__.__name__
        eb_mod_name = this_module.__name__
        eb_mod_loc = this_module.__file__
        self.log.info("This is easyblock %s from module %s (%s)", eb_class, eb_mod_name, eb_mod_loc)

        if self.dry_run:
            self.dry_run_msg("*** DRY RUN using '%s' easyblock (%s @ %s) ***\n", eb_class, eb_mod_name, eb_mod_loc)

    def close_log(self):
        """
        Shutdown the logger.
        """
        # only close log if we created a logfile
        if self.external_logfile:
            return
        self.log.info("Closing log for application name %s version %s" % (self.name, self.version))
        fancylogger.logToFile(self.logfile, enable=False)

    #
    # DRY RUN UTILITIES
    #
    def init_dry_run(self):
        """Initialise easyblock instance for performing a dry run."""
        # replace build/install dirs with temporary directories in dry run mode
        tmp_root_dir = os.path.realpath(os.path.join(tempfile.gettempdir(), '__ROOT__'))
        self.builddir = os.path.join(tmp_root_dir, self.builddir.lstrip(os.path.sep))
        self.installdir = os.path.join(tmp_root_dir, self.installdir.lstrip(os.path.sep))
        self.installdir_mod = os.path.join(tmp_root_dir, self.installdir_mod.lstrip(os.path.sep))

        # register fake build/install dirs so the original values can be printed during dry run
        dry_run_set_dirs(tmp_root_dir, self.builddir, self.installdir, self.installdir_mod)

    def dry_run_msg(self, msg, *args):
        """Print dry run message."""
        if args:
            msg = msg % args
        dry_run_msg(msg, silent=self.silent)

    #
    # FETCH UTILITY FUNCTIONS
    #
    def get_checksum_for(self, checksums, filename=None, index=None):
        """
        Obtain checksum for given filename.

        :param checksums: a list or tuple of checksums (or None)
        :param filename: name of the file to obtain checksum for
        :param index: index of file in list
        """
        chksum_input = filename
        chksum_input_git = None
        # if filename is provided as dict, take 'filename' key
        if isinstance(filename, dict):
            chksum_input = filename.get('filename', None)
            chksum_input_git = filename.get('git_config', None)
        # early return if no filename given
        if chksum_input is None:
            self.log.debug("Cannot get checksum without a file name")
            return None

        checksum = None
        # if checksums are provided as a dict, lookup by source filename as key
        if isinstance(checksums, dict):
            try:
                checksum = checksums[chksum_input]
            except KeyError:
                self.log.debug("Checksum not found for file: %s", chksum_input)
        elif isinstance(checksums, (list, tuple)) and index is not None:
            try:
                checksum = checksums[index]
            except IndexError:
                self.log.debug("Checksum not found for index list: %s", index)
        elif checksums is not None:
            raise EasyBuildError("Invalid type for checksums (%s), should be dict, list, tuple or None.",
                                 type(checksums))

        if checksum is None or build_option("checksum_priority") == CHECKSUM_PRIORITY_JSON:
            json_checksums = self.get_checksums_from_json()
            checksum = json_checksums.get(chksum_input, None)

        if checksum and chksum_input_git is not None:
            # ignore any checksum for given filename due to changes in https://github.com/python/cpython/issues/90021
            # tarballs made for git repos are not reproducible when created with Python < 3.9
            if sys.version_info < (3, 9):
                print_warning(
                    "Reproducible tarballs of Git repos are only possible when using Python 3.9+ to run EasyBuild. "
                    f"Skipping checksum verification of {chksum_input} since Python < 3.9 is used."
                )
                return None
            # not all archives formats of git repos are reproducible
            # warn users that checksum might fail for non-reproducible archives
            _, file_ext = os.path.splitext(chksum_input)
            if file_ext not in ['', '.tar', '.txz', '.xz']:
                print_warning(
                    f"Checksum verification may fail! Archive file '{chksum_input}' contains sources of a git repo "
                    "in a non-reproducible format. Please re-create that archive with XZ compression instead."
                )

        return checksum

    def get_checksums_from_json(self, always_read=False):
        """
        Get checksums for this software that are provided in a checksums.json file

        :param always_read: always read the checksums.json file, even if it has been read before
        """
        if always_read or self.json_checksums is None:
            path = self.obtain_file(CHECKSUMS_JSON, no_download=True, warning_only=True)
            if path is not None:
                self.log.info("Loading checksums from file %s", path)
                json_txt = read_file(path)
                self.json_checksums = json.loads(json_txt)
            else:
                # if the file can't be found, return an empty dict
                self.json_checksums = {}

        return self.json_checksums

    def fetch_source(self, source, checksum=None, extension=False, download_instructions=None):
        """
        Get a specific source (tarball, iso, url)
        Will be tested for existence or can be located

        :param source: source to be found (single dictionary in 'sources' list, or filename)
        :param checksum: checksum corresponding to source
        :param extension: flag if being called from collect_exts_file_info()
        """
        filename, download_filename, extract_cmd = None, None, None
        source_urls, git_config, alt_location = None, None, None

        if source is None:
            raise EasyBuildError("fetch_source called with empty 'source' argument")
        elif isinstance(source, str):
            filename = source
        elif isinstance(source, dict):
            # Making a copy to avoid modifying the object with pops
            source = source.copy()
            filename = source.pop('filename', None)
            extract_cmd = source.pop('extract_cmd', None)
            download_filename = source.pop('download_filename', None)
            source_urls = source.pop('source_urls', None)
            git_config = source.pop('git_config', None)
            alt_location = source.pop('alt_location', None)
            if source:
                raise EasyBuildError("Found one or more unexpected keys in 'sources' specification: %s", source)

        elif isinstance(source, (list, tuple)) and len(source) == 2:
            self.log.deprecated("Using a 2-element list/tuple to specify sources is deprecated, "
                                "use a dictionary with 'filename', 'extract_cmd' keys instead", '4.0')
            filename, extract_cmd = source
        else:
            raise EasyBuildError("Unexpected source spec, not a string or dict: %s", source)

        # check if the sources can be located
        force_download = build_option('force_download') in [FORCE_DOWNLOAD_ALL, FORCE_DOWNLOAD_SOURCES]
        path = self.obtain_file(filename, extension=extension, download_filename=download_filename,
                                force_download=force_download, urls=source_urls, git_config=git_config,
                                download_instructions=download_instructions, alt_location=alt_location)
        if path is None:
            raise EasyBuildError('No file found for source %s', filename)

        self.log.debug('File %s found for source %s' % (path, filename))

        src = {
            'name': filename,
            'path': path,
            'cmd': extract_cmd,
            'checksum': checksum,
            # always set a finalpath
            'finalpath': self.builddir,
        }

        return src

    def fetch_sources(self, sources=None, checksums=None):
        """
        Add a list of source files (can be tarballs, isos, urls).
        All source files will be checked if a file exists (or can be located)

        :param sources: list of sources to fetch (if None, use 'sources' or 'data_sources' easyconfig parameter)
        :param checksums: list of checksums for sources
        """
        if sources is None:
            sources = self.cfg['sources'] or self.cfg['data_sources']
        if checksums is None:
            checksums = self.cfg['checksums']

        # Single source should be re-wrapped as a list, and checksums with it
        if isinstance(sources, dict):
            sources = [sources]
        if isinstance(checksums, str):
            checksums = [checksums]

        # Loop over the list of sources; list of checksums must match >= in size
        for index, source in enumerate(sources):
            if source is None:
                raise EasyBuildError("Empty source in sources list at index %d", index)

            checksum = self.get_checksum_for(checksums=checksums, filename=source, index=index)
            src_spec = self.fetch_source(source, checksum=checksum)
            if src_spec:
                self.src.append(src_spec)
            else:
                raise EasyBuildError("Unable to retrieve source %s", source)

        self.log.info("Added sources: %s", self.src)

    def fetch_patches(self, patch_specs=None, extension=False, checksums=None):
        """
        Add a list of patches.
        All patches will be checked if a file exists (or can be located)
        """
        post_install_patches = []
        if patch_specs is None:
            # if no patch_specs are specified, use all pre-install and post-install patches
            post_install_patches = self.cfg['postinstallpatches']
            patch_specs = self.cfg['patches'] + post_install_patches

        patches = []
        for index, patch_spec in enumerate(patch_specs):

            patch_info = create_patch_info(patch_spec)
            patch_info['postinstall'] = patch_spec in post_install_patches

            force_download = build_option('force_download') in [FORCE_DOWNLOAD_ALL, FORCE_DOWNLOAD_PATCHES]
            alt_location = patch_info.pop('alt_location', None)
            path = self.obtain_file(patch_info['name'], extension=extension, force_download=force_download,
                                    alt_location=alt_location)
            if path:
                self.log.debug('File %s found for patch %s', path, patch_spec)
                patch_info['path'] = path
                patch_info['checksum'] = self.get_checksum_for(checksums, filename=patch_info['name'], index=index)

                if extension:
                    patches.append(patch_info)
                else:
                    self.patches.append(patch_info)
            else:
                raise EasyBuildError('No file found for patch %s', patch_spec)

        if extension:
            self.log.info("Fetched extension patches: %s", patches)
            return patches
        else:
            self.log.info("Added patches: %s", self.patches)

    def collect_exts_file_info(self, fetch_files=True, verify_checksums=True):
        """
        Collect information on source and patch files for extensions.

        :param fetch_files: whether or not to fetch files (if False, path to files will be missing from info)
        :param verify_checksums: whether or not to verify checksums
        :return: list of dict values, one per extension, with information on source/patch files.
        """
        exts_sources = []
        exts_list = self.cfg.get_ref('exts_list')

        if verify_checksums and not fetch_files:
            raise EasyBuildError("Can't verify checksums for extension files if they are not being fetched")

        if self.dry_run:
            self.dry_run_msg("\nList of sources/patches for extensions:")

        force_download = build_option('force_download') in [FORCE_DOWNLOAD_ALL, FORCE_DOWNLOAD_SOURCES]

        for ext in exts_list:
            if isinstance(ext, (list, tuple)) and ext:
                # expected format: (name, version, options (dict))
                # name and version can use templates, resolved via parent EC

                ext_name = resolve_template(ext[0], self.cfg.template_values)
                if len(ext) == 1:
                    exts_sources.append({'name': ext_name})
                else:
                    ext_version = resolve_template(ext[1], self.cfg.template_values)

                    # make sure we grab *raw* dict of default options for extension,
                    # since it may use template values like %(name)s & %(version)s
                    ext_options = copy.deepcopy(self.cfg.get_ref('exts_default_options'))

                    if len(ext) == 3:
                        if isinstance(ext_options, dict):
                            ext_options.update(ext[2])
                        else:
                            raise EasyBuildError("Unexpected type (non-dict) for 3rd element of %s", ext)
                    elif len(ext) > 3:
                        raise EasyBuildError('Extension specified in unknown format (list/tuple too long)')

                    ext_src = {
                        'name': ext_name,
                        'version': ext_version,
                        'options': ext_options,
                    }

                    # if a particular easyblock is specified, make sure it's used
                    # (this is picked up by init_ext_instances)
                    ext_src['easyblock'] = ext_options.get('easyblock', None)

                    # construct dictionary with template values;
                    # inherited from parent, except for name/version templates which are specific to this extension
                    template_values = copy.deepcopy(self.cfg.template_values)
                    template_values.update(template_constant_dict(ext_src))

                    source_urls = resolve_template(ext_options.get('source_urls', []), template_values)
                    checksums = resolve_template(ext_options.get('checksums', []), template_values)

                    download_instructions = resolve_template(ext_options.get('download_instructions'), template_values)

                    if ext_options.get('nosource', None):
                        self.log.debug("No sources for extension %s, as indicated by 'nosource'", ext_name)

                    elif ext_options.get('sources', None):
                        sources = resolve_template(ext_options['sources'], template_values)

                        # only a single source file is supported for extensions currently,
                        # see https://github.com/easybuilders/easybuild-framework/issues/3463
                        if isinstance(sources, list):
                            if len(sources) == 1:
                                source = sources[0]
                            else:
                                error_msg = "'sources' spec for %s in exts_list must be single element list. Is: %s"
                                raise EasyBuildError(error_msg, ext_name, sources)
                        else:
                            source = sources

                        # always pass source spec as dict value to fetch_source method,
                        # mostly so we can inject stuff like source URLs
                        if isinstance(source, str):
                            source = {'filename': source}
                        elif not isinstance(source, dict):
                            raise EasyBuildError("Incorrect value type for source of extension %s: %s",
                                                 ext_name, source)

                        # if no custom source URLs are specified in sources spec,
                        # inject the ones specified for this extension
                        if 'source_urls' not in source:
                            source['source_urls'] = source_urls

                        if fetch_files:
                            src = self.fetch_source(source, checksums, extension=True,
                                                    download_instructions=download_instructions)
                            ext_src.update({
                                # keep track of custom extract command (if any)
                                'extract_cmd': src['cmd'],
                                # copy 'path' entry to 'src' for use with extensions
                                'src': src['path'],
                            })

                    else:

                        # if no sources are specified via 'sources', fall back to 'source_tmpl'
                        src_fn = ext_options.get('source_tmpl')
                        if src_fn is None:
                            # use default template for name of source file if none is specified
                            src_fn = '%(name)s-%(version)s.tar.gz'
                        elif not isinstance(src_fn, str):
                            error_msg = "source_tmpl value must be a string! (found value of type '%s'): %s"
                            raise EasyBuildError(error_msg, type(src_fn).__name__, src_fn)

                        src_fn = resolve_template(src_fn, template_values)

                        if fetch_files:
                            src_path = self.obtain_file(src_fn, extension=True, urls=source_urls,
                                                        force_download=force_download,
                                                        download_instructions=download_instructions)
                            if src_path:
                                ext_src.update({'src': src_path})
                            else:
                                raise EasyBuildError("Source for extension %s not found.", ext)

                    # verify checksum for extension sources
                    if verify_checksums and 'src' in ext_src:
                        src_path = ext_src['src']
                        src_fn = os.path.basename(src_path)

                        src_checksums = {}
                        for checksum_type in [CHECKSUM_TYPE_SHA256]:
                            src_checksum = compute_checksum(src_path, checksum_type=checksum_type)
                            src_checksums[checksum_type] = src_checksum
                            self.log.info("%s checksum for %s: %s", checksum_type, src_path, src_checksum)

                        # verify checksum (if provided)
                        self.log.debug('Verifying checksums for extension source...')
                        fn_checksum = self.get_checksum_for(checksums, filename=src_fn, index=0)
                        if verify_checksum(src_path, fn_checksum, src_checksums):
                            self.log.info('Checksum for extension source %s verified', src_fn)
                        elif build_option('ignore_checksums'):
                            print_warning("Ignoring failing checksum verification for %s" % src_fn)
                        else:
                            raise EasyBuildError(
                                'Checksum verification for extension source %s failed', src_fn,
                                exit_code=EasyBuildExit.FAIL_CHECKSUM
                            )

                    # locate extension patches (if any), and verify checksums
                    ext_patches = resolve_template(ext_options.get('patches', []), template_values)
                    if fetch_files:
                        ext_patches = self.fetch_patches(patch_specs=ext_patches, extension=True)
                    else:
                        ext_patches = [create_patch_info(p) for p in ext_patches]

                    if ext_patches:
                        self.log.debug('Found patches for extension %s: %s', ext_name, ext_patches)
                        ext_src.update({'patches': ext_patches})

                        if verify_checksums:
                            computed_checksums = {}
                            for patch in ext_patches:
                                patch = patch['path']
                                computed_checksums[patch] = {}
                                for checksum_type in [CHECKSUM_TYPE_SHA256]:
                                    checksum = compute_checksum(patch, checksum_type=checksum_type)
                                    computed_checksums[patch][checksum_type] = checksum
                                    self.log.info("%s checksum for %s: %s", checksum_type, patch, checksum)

                            # verify checksum (if provided)
                            self.log.debug('Verifying checksums for extension patches...')
                            for idx, patch in enumerate(ext_patches):
                                patch = patch['path']
                                patch_fn = os.path.basename(patch)

                                checksum = self.get_checksum_for(checksums, filename=patch_fn, index=idx+1)
                                if verify_checksum(patch, checksum, computed_checksums[patch]):
                                    self.log.info('Checksum for extension patch %s verified', patch_fn)
                                elif build_option('ignore_checksums'):
                                    print_warning("Ignoring failing checksum verification for %s" % patch_fn)
                                else:
                                    raise EasyBuildError(
                                        "Checksum verification for extension patch %s failed", patch_fn,
                                        exit_code=EasyBuildExit.FAIL_CHECKSUM
                                    )
                    else:
                        self.log.debug('No patches found for extension %s.' % ext_name)

                    exts_sources.append(ext_src)

            elif isinstance(ext, str):
                exts_sources.append({'name': ext})

            else:
                raise EasyBuildError("Extension specified in unknown format (not a string/list/tuple)")

        return exts_sources

    @_obtain_file_update_progress_bar_on_return
    def obtain_file(self, filename, extension=False, urls=None, download_filename=None, force_download=False,
                    git_config=None, no_download=False, download_instructions=None, alt_location=None,
                    warning_only=False):
        """
        Locate the file with the given name
        - searches in different subdirectories of source path
        - supports fetching file from the web if path is specified as an url (i.e. starts with "http://:")
        :param filename: filename of source
        :param extension: indicates whether locations for extension sources should also be considered
        :param urls: list of source URLs where this file may be available
        :param download_filename: filename with which the file should be downloaded, and then renamed to <filename>
        :param force_download: always try to download file, even if it's already available in source path
        :param git_config: dictionary to define how to download a git repository
        :param no_download: do not try to download the file
        :param download_instructions: instructions to manually add source (used for complex cases)
        :param alt_location: alternative location to use instead of self.name
        """
        if self.cfg['data_sources']:
            srcpaths = source_paths_data()
        else:
            srcpaths = source_paths()

        # We don't account for the checksums file in the progress bar
        if filename != CHECKSUMS_JSON:
            update_progress_bar(PROGRESS_BAR_DOWNLOAD_ALL, progress_size=0, label=filename)

        if alt_location is None:
            location = self.name
        else:
            location = alt_location

        # should we download or just try and find it?
        if re.match(r"^(https?|ftp)://", filename):
            # URL detected, so let's try and download it

            url = filename
            filename = url.split('/')[-1]

            # figure out where to download the file to
            filepath = os.path.join(srcpaths[0], letter_dir_for(location), location)
            if extension:
                filepath = os.path.join(filepath, "extensions")
            self.log.info("Creating path %s to download file to" % filepath)
            mkdir(filepath, parents=True)

            try:
                fullpath = os.path.join(filepath, filename)

                # only download when it's not there yet
                if os.path.exists(fullpath):
                    if force_download:
                        print_warning("Found file %s at %s, but re-downloading it anyway..." % (filename, filepath))
                    else:
                        self.log.info("Found file %s at %s, no need to download it", filename, filepath)
                        return fullpath

                if download_file(filename, url, fullpath):
                    return fullpath

            except IOError as err:
                msg = f"Downloading file {filename} from url {url} to {fullpath} failed: {err}"
                if not warning_only:
                    raise EasyBuildError(msg, exit_code=EasyBuildExit.FAIL_DOWNLOAD)
                else:
                    self.log.warning(msg)
                    return None

        else:
            # try and find file in various locations
            foundfile = None
            failedpaths = []

            # always look first in the dir of the current eb file unless alt_location is set
            if alt_location is None:
                ebpath = [os.path.dirname(self.cfg.path)]
                self.log.info("Considering directory in which easyconfig file is located when searching for %s: %s",
                              filename, ebpath[0])
            else:
                ebpath = []
                self.log.info("Not considering directory in which easyconfig file is located when searching for %s "
                              "because alt_location is set to %s", filename, alt_location)

            # always consider robot + easyconfigs install paths as a fall back (e.g. for patch files, test cases, ...)
            common_filepaths = []
            if self.robot_path:
                common_filepaths.extend(self.robot_path)
            common_filepaths.extend(get_paths_for(subdir=EASYCONFIGS_PKG_SUBDIR, robot_path=self.robot_path))

            for path in ebpath + common_filepaths + srcpaths:
                # create list of candidate filepaths
                namepath = os.path.join(path, location)
                letterpath = os.path.join(path, letter_dir_for(location), location)

                # most likely paths
                candidate_filepaths = [
                    letterpath,  # easyblocks-style subdir
                    namepath,  # subdir with software name
                    path,  # directly in directory
                ]

                # see if file can be found at that location
                for cfp in candidate_filepaths:

                    fullpath = os.path.join(cfp, filename)

                    # also check in 'extensions' subdir for extensions
                    if extension:
                        fullpaths = [
                            os.path.join(cfp, "extensions", filename),
                            os.path.join(cfp, "packages", filename),  # legacy
                            fullpath
                        ]
                    else:
                        fullpaths = [fullpath]

                    for fp in fullpaths:
                        if os.path.isfile(fp):
                            self.log.info("Found file %s at %s", filename, fp)
                            foundfile = os.path.abspath(fp)
                            break  # no need to try further
                        else:
                            failedpaths.append(fp)

                if foundfile:
                    if force_download:
                        print_warning("Found file %s at %s, but re-downloading it anyway..." % (filename, foundfile))
                        foundfile = None

                    break  # no need to try other source paths

            name_letter = location.lower()[0]
            targetdir = os.path.join(srcpaths[0], name_letter, location)

            if foundfile:
                if self.dry_run:
                    self.dry_run_msg("  * %s found at %s", filename, foundfile)
                return foundfile

            if no_download:
                if self.dry_run:
                    self.dry_run_msg("  * %s (MISSING)", filename)
                    return filename

                failedpaths_msg = "\n * ".join([""]+failedpaths)
                file_notfound_msg = (
                    f"Couldn't find file '{filename}' anywhere, and downloading it is disabled... "
                    f"Paths attempted (in order): {failedpaths_msg}"
                )

                if warning_only:
                    self.log.warning(file_notfound_msg)
                    return None

                raise EasyBuildError(file_notfound_msg, exit_code=EasyBuildExit.MISSING_SOURCES)

            if git_config:
                return get_source_tarball_from_git(filename, targetdir, git_config)

            # try and download source files from specified source URLs
            if urls:
                source_urls = urls[:]
            else:
                source_urls = []
            source_urls.extend(self.cfg['source_urls'])

            # Add additional URLs as configured.
            for url in build_option("extra_source_urls"):
                url += "/" + name_letter + "/" + location
                source_urls.append(url)

            mkdir(targetdir, parents=True)

            for url in source_urls:

                if extension:
                    targetpath = os.path.join(targetdir, "extensions", filename)
                else:
                    targetpath = os.path.join(targetdir, filename)

                url_filename = download_filename or filename

                if isinstance(url, str):
                    if url[-1] in ['=', '/']:
                        fullurl = "%s%s" % (url, url_filename)
                    else:
                        fullurl = "%s/%s" % (url, url_filename)
                elif isinstance(url, tuple):
                    # URLs that require a suffix, e.g., SourceForge download links
                    # e.g. http://sourceforge.net/projects/math-atlas/files/Stable/3.8.4/atlas3.8.4.tar.bz2/download
                    fullurl = "%s/%s/%s" % (url[0], url_filename, url[1])
                else:
                    self.log.warning("Source URL %s is of unknown type, so ignoring it." % url)
                    continue

                # PyPI URLs may need to be converted due to change in format of these URLs,
                # cfr. https://bitbucket.org/pypa/pypi/issues/438
                if PYPI_PKG_URL_PATTERN in fullurl and not is_alt_pypi_url(fullurl):
                    alt_url = derive_alt_pypi_url(fullurl)
                    if alt_url:
                        _log.debug("Using alternative PyPI URL for %s: %s", fullurl, alt_url)
                        fullurl = alt_url
                    else:
                        _log.debug("Failed to derive alternative PyPI URL for %s, so retaining the original",
                                   fullurl)

                if self.dry_run:
                    self.dry_run_msg("  * %s will be downloaded to %s", filename, targetpath)
                    if extension and urls:
                        # extensions typically have custom source URLs specified, only mention first
                        self.dry_run_msg("    (from %s, ...)", fullurl)
                    downloaded = True

                else:
                    self.log.debug("Trying to download file %s from %s to %s ..." % (filename, fullurl, targetpath))
                    downloaded = False
                    try:
                        if download_file(filename, fullurl, targetpath):
                            downloaded = True

                    except IOError as err:
                        self.log.debug("Failed to download %s from %s: %s" % (filename, url, err))
                        failedpaths.append(fullurl)
                        continue

                if downloaded:
                    # if fetching from source URL worked, we're done
                    self.log.info("Successfully downloaded source file %s from %s" % (filename, fullurl))
                    return targetpath
                else:
                    failedpaths.append(fullurl)

            if self.dry_run:
                self.dry_run_msg("  * %s (MISSING)", filename)
                return filename
            else:
                error_msg = "Couldn't find file %s anywhere, "
                if download_instructions is None:
                    download_instructions = self.cfg['download_instructions']
                if download_instructions is not None and download_instructions != "":
                    msg = "\nDownload instructions:\n\n" + indent(download_instructions, '    ') + '\n\n'
                    msg += "Make the files available in the active source path: %s\n" % ':'.join(source_paths())
                    print_msg(msg, prefix=False, stderr=True)
                    error_msg += "please follow the download instructions above, and make the file available "
                    error_msg += "in the active source path (%s)" % ':'.join(source_paths())
                else:
                    # flatten list to string with '%' characters escaped (literal '%' desired in 'sprintf')
                    failedpaths_msg = ', '.join(failedpaths).replace('%', '%%')
                    error_msg += "and downloading it didn't work either... "
                    error_msg += "Paths attempted (in order): %s " % failedpaths_msg

                if not warning_only:
                    raise EasyBuildError(error_msg, filename, exit_code=EasyBuildExit.FAIL_DOWNLOAD)
                else:
                    self.log.warning(error_msg, filename)
                    return None

    #
    # GETTER/SETTER UTILITY FUNCTIONS
    #
    @property
    def name(self):
        """
        Shortcut the get the module name.
        """
        return self.cfg['name']

    @property
    def version(self):
        """
        Shortcut the get the module version.
        """
        return self.cfg['version']

    @property
    def toolchain(self):
        """
        Toolchain used to build this easyblock
        """
        return self.cfg.toolchain

    @property
    def full_mod_name(self):
        """
        Full module name (including subdirectory in module install path)
        """
        return self.cfg.full_mod_name

    @property
    def short_mod_name(self):
        """
        Short module name (not including subdirectory in module install path)
        """
        return self.cfg.short_mod_name

    @property
    def mod_subdir(self):
        """
        Subdirectory in module install path
        """
        return self.cfg.mod_subdir

    @property
    def moduleGenerator(self):
        """
        Module generator (DEPRECATED, use self.module_generator instead).
        """
        self.log.nosupport("self.moduleGenerator is replaced by self.module_generator", '2.0')

    #
    # DIRECTORY UTILITY FUNCTIONS
    #
    def gen_builddir(self):
        """Generate the (unique) name for the builddir"""
        clean_name = remove_unwanted_chars(self.name)

        # if a toolchain version starts with a -, remove the - so prevent a -- in the path name
        tc = self.cfg['toolchain']
        tcversion = tc['version'].lstrip('-')
        lastdir = "%s%s-%s%s" % (self.cfg['versionprefix'], tc['name'], tcversion, self.cfg['versionsuffix'])

        builddir = os.path.join(os.path.abspath(build_path()), clean_name, self.version, lastdir)

        # make sure build dir is unique if cleanupoldbuild is False or not set
        if not self.cfg.get('cleanupoldbuild', False):
            uniq_builddir = builddir
            suff = 0
            while os.path.isdir(uniq_builddir):
                uniq_builddir = "%s.%d" % (builddir, suff)
                suff += 1
            builddir = uniq_builddir

        self.builddir = builddir
        self.log.info("Build dir set to %s" % self.builddir)

    def make_builddir(self):
        """
        Create the build directory.
        """
        if not self.build_in_installdir:
            # self.builddir should be already set by gen_builddir()
            if not self.builddir:
                raise EasyBuildError("self.builddir not set, make sure gen_builddir() is called first!")
            self.log.debug("Creating the build directory %s (cleanup: %s)", self.builddir, self.cfg['cleanupoldbuild'])
        else:
            self.log.info("Overriding 'cleanupoldinstall' (to False), 'cleanupoldbuild' (to True) "
                          "and 'keeppreviousinstall' because we're building in the installation directory.")
            # force cleanup before installation
            if build_option('module_only') or self.cfg['module_only']:
                self.log.debug("Disabling cleanupoldbuild because we run as module-only")
                self.cfg['cleanupoldbuild'] = False
            else:
                self.cfg['cleanupoldbuild'] = True

            self.cfg['keeppreviousinstall'] = False
            # avoid cleanup after installation
            self.cfg['cleanupoldinstall'] = False

        # always make build dir,
        # unless we're building in installation directory and we iterating over a list of (pre)config/build/installopts,
        # otherwise we wipe the already partially populated installation directory,
        # see https://github.com/easybuilders/easybuild-framework/issues/2556
        if not (self.build_in_installdir and self.iter_idx > 0):
            # make sure we no longer sit in the build directory before cleaning it.
            change_dir(self.orig_workdir)
            self.make_dir(self.builddir, self.cfg['cleanupoldbuild'])

        trace_msg("build dir: %s" % self.builddir)

    def reset_env(self):
        """
        Reset environment.
        When iterating over builddependencies, every time we start a new iteration
        we need to restore the environment to where it was before the relevant modules
        were loaded.
        """
        env.reset_changes()
        if self.reset_environ is None:
            self.reset_environ = copy.deepcopy(os.environ)
        else:
            restore_env(self.reset_environ)

    def gen_installdir(self):
        """
        Generate the name of the installation directory.
        """
        if self.cfg['data_sources']:
            basepath = install_path(DATA)
        else:
            basepath = install_path(SOFTWARE)
        if basepath:
            self.install_subdir = ActiveMNS().det_install_subdir(self.cfg)
            self.installdir = os.path.join(os.path.abspath(basepath), self.install_subdir)
            self.log.info("Software install dir set to %s" % self.installdir)

            mod_basepath = install_path('mod')
            mod_path_suffix = build_option('suffix_modules_path')
            self.installdir_mod = os.path.join(os.path.abspath(mod_basepath), mod_path_suffix)
            self.log.info("Module install dir set to %s" % self.installdir_mod)
        else:
            raise EasyBuildError("Can't set installation directory")

    def make_installdir(self, dontcreate=None):
        """
        Create the installation directory.
        """
        self.log.debug("Creating the installation directory %s (cleanup: %s)" % (self.installdir,
                                                                                 self.cfg['cleanupoldinstall']))
        if self.build_in_installdir:
            self.cfg['keeppreviousinstall'] = True
        dontcreate = (dontcreate is None and self.cfg['dontcreateinstalldir']) or dontcreate
        self.make_dir(self.installdir, self.cfg['cleanupoldinstall'], dontcreateinstalldir=dontcreate)

    def make_dir(self, dir_name, clean, dontcreateinstalldir=False):
        """
        Create the directory.
        """
        if os.path.exists(dir_name):
            self.log.info("Found old directory %s" % dir_name)
            if self.cfg['keeppreviousinstall']:
                self.log.info("Keeping old directory %s (hopefully you know what you are doing)", dir_name)
                return
            elif build_option('module_only') or self.cfg['module_only']:
                self.log.info("Not touching existing directory %s in module-only mode...", dir_name)
            elif clean:
                remove_dir(dir_name)
                self.log.info("Removed old directory %s", dir_name)
            else:
                self.log.info("Moving existing directory %s out of the way...", dir_name)
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                backupdir = "%s.%s" % (dir_name, timestamp)
                move_file(dir_name, backupdir)
                self.log.info("Moved old directory %s to %s", dir_name, backupdir)

        if dontcreateinstalldir:
            olddir = dir_name
            dir_name = os.path.dirname(dir_name)
            self.log.info("Cleaning only, no actual creation of %s, only verification/defining of dirname %s",
                          olddir, dir_name)
            if os.path.exists(dir_name):
                return
            # if not, create dir as usual

        mkdir(dir_name, parents=True)

    def set_up_cuda_cache(self):
        """Set up CUDA PTX cache."""

        cuda_cache_maxsize = build_option('cuda_cache_maxsize')
        if cuda_cache_maxsize is None:
            cuda_cache_maxsize = 1 * 1024  # 1 GiB default value
        else:
            cuda_cache_maxsize = int(cuda_cache_maxsize)

        if cuda_cache_maxsize == 0:
            self.log.info("Disabling CUDA PTX cache since cache size was set to zero")
            env.setvar('CUDA_CACHE_DISABLE', '1')
        else:
            cuda_cache_dir = build_option('cuda_cache_dir')
            if not cuda_cache_dir:
                cuda_cache_dir = os.path.join(self.builddir, 'eb-cuda-cache')
            self.log.info("Enabling CUDA PTX cache of size %s MiB at %s", cuda_cache_maxsize, cuda_cache_dir)
            env.setvar('CUDA_CACHE_DISABLE', '0')
            env.setvar('CUDA_CACHE_PATH', cuda_cache_dir)
            env.setvar('CUDA_CACHE_MAXSIZE', str(cuda_cache_maxsize * 1024 * 1024))

    #
    # MODULE UTILITY FUNCTIONS
    #

    def make_devel_module(self, create_in_builddir=False):
        """
        Create a develop module file which sets environment based on the build
        Usage: module load name, which loads the module you want to use. $EBDEVELNAME should then be the full path
        to the devel module file. So now you can module load $EBDEVELNAME.

        WARNING: you cannot unload using $EBDEVELNAME (for now: use module unload `basename $EBDEVELNAME`)
        """

        self.log.info("Making devel module...")

        header = self.module_generator.MODULE_SHEBANG
        if header:
            header += '\n'

        load_lines = []
        # capture all the EBDEVEL vars
        # these should be all the dependencies and we should load them
        recursive_unload = self.cfg['recursive_module_unload']
        depends_on = self.cfg['module_depends_on']
        if depends_on is not None:
            self.log.deprecated("'module_depends_on' easyconfig parameter should not be used anymore", '6.0')
        for key in os.environ:
            # legacy support
            if key.startswith(DEVEL_ENV_VAR_NAME_PREFIX):
                if not key.endswith(convert_name(self.name, upper=True)):
                    path = os.environ[key]
                    if os.path.isfile(path):
                        mod_name = path.rsplit(os.path.sep, 1)[-1]
                        load_statement = self.module_generator.load_module(mod_name, recursive_unload=recursive_unload,
                                                                           depends_on=depends_on)
                        load_lines.append(load_statement)
            elif key.startswith('SOFTDEVEL'):
                self.log.nosupport("Environment variable SOFTDEVEL* being relied on", '2.0')

        env_lines = []
        for (key, val) in env.get_changes().items():
            # check if non-empty string
            # TODO: add unset for empty vars?
            if val.strip():
                env_lines.append(self.module_generator.set_environment(key, val))

        if create_in_builddir:
            output_dir = self.builddir
        else:
            output_dir = os.path.join(self.installdir, log_path(ec=self.cfg))
            mkdir(output_dir, parents=True)

        filename = os.path.join(output_dir, ActiveMNS().det_devel_module_filename(self.cfg))
        self.log.debug("Writing devel module to %s" % filename)

        txt = ''.join([header] + load_lines + env_lines)
        write_file(filename, txt)

    def make_module_deppaths(self):
        """
        Add specific 'module use' actions to module file, in order to find
        dependencies outside the end user's MODULEPATH.
        """
        deppaths = self.cfg['moddependpaths']
        if not deppaths:
            return ''
        elif not isinstance(deppaths, (str, list, tuple)):
            raise EasyBuildError("moddependpaths value %s (type: %s) is not a string, list or tuple",
                                 deppaths, type(deppaths))

        if isinstance(deppaths, str):
            txt = self.module_generator.use([deppaths], guarded=True)
        else:
            txt = self.module_generator.use(deppaths, guarded=True)

        return txt

    def make_module_dep(self, unload_info=None):
        """
        Make the dependencies for the module file.

        :param unload_info: dictionary with full module names as keys and module name to unload first as corr. value
        """
        mns = ActiveMNS()
        unload_info = unload_info or {}

        # include toolchain as first dependency to load
        tc_mod = None
        if not self.toolchain.is_system_toolchain():
            tc_mod = self.toolchain.det_short_module_name()
            self.log.debug("Toolchain to load in generated module (before excluding any deps): %s", tc_mod)

        # expand toolchain into toolchain components if desired
        tc_dep_mods = None
        if mns.expand_toolchain_load(ec=self.cfg):
            tc_dep_mods = self.toolchain.toolchain_dep_mods
            self.log.debug("Toolchain components to load in generated module (before excluding any): %s", tc_dep_mods)

        # include load/unload statements for dependencies
        deps = []
        self.log.debug("List of deps considered to load in generated module: %s", self.toolchain.dependencies)
        for dep in self.toolchain.dependencies:
            if dep['build_only']:
                self.log.debug("Skipping build dependency %s", dep)
            else:
                modname = dep['short_mod_name']
                self.log.debug("Adding %s as a module dependency" % modname)
                deps.append(modname)
        self.log.debug("List of deps to load in generated module (before excluding any): %s", deps)

        # exclude dependencies that extend $MODULEPATH and form the path to the top of the module tree (if any)
        full_mod_subdir = os.path.join(self.installdir_mod, self.mod_subdir)
        init_modpaths = mns.det_init_modulepaths(self.cfg)
        top_paths = [self.installdir_mod] + [os.path.join(self.installdir_mod, p) for p in init_modpaths]

        all_deps = [d for d in [tc_mod] + (tc_dep_mods or []) + deps if d is not None]
        excluded_deps = self.modules_tool.path_to_top_of_module_tree(top_paths, self.cfg.short_mod_name,
                                                                     full_mod_subdir, all_deps)

        # if the toolchain is excluded, so should the toolchain components
        if tc_mod in excluded_deps and tc_dep_mods:
            excluded_deps.extend(tc_dep_mods)

        self.log.debug("List of excluded deps: %s", excluded_deps)

        # expand toolchain into toolchain components if desired
        if tc_dep_mods is not None:
            deps = tc_dep_mods + deps
        elif tc_mod is not None:
            deps = [tc_mod] + deps

        # filter dependencies to avoid including loads for toolchain or toolchain components that extend $MODULEPATH
        # with location to where this module is being installed (full_mod_subdir);
        # if the modules that extend $MODULEPATH are not loaded this module is not available, so there is not
        # point in loading them again (in fact, it may cause problems when reloading this module due to a load storm)
        deps = [d for d in deps if d not in excluded_deps]

        # load modules that open up the module tree before checking deps of deps (in reverse order)
        self.modules_tool.load(excluded_deps[::-1], allow_reload=False)

        for excluded_dep in excluded_deps:
            excluded_dep_deps = dependencies_for(excluded_dep, self.modules_tool)
            self.log.debug("List of dependencies for excluded dependency %s: %s" % (excluded_dep, excluded_dep_deps))
            deps = [d for d in deps if d not in excluded_dep_deps]

        self.log.debug("List of retained deps to load in generated module: %s", deps)

        # include load statements for retained dependencies
        recursive_unload = self.cfg['recursive_module_unload']
        depends_on = self.cfg['module_depends_on']
        if depends_on is not None:
            self.log.deprecated("'module_depends_on' easyconfig parameter should not be used anymore", '6.0')
        loads = []
        for dep in deps:
            unload_modules = []
            if dep in unload_info:
                unload_modules.append(unload_info[dep])
            loads.append(self.module_generator.load_module(dep, recursive_unload=recursive_unload,
                                                           depends_on=depends_on,
                                                           unload_modules=unload_modules))

        # force unloading any other modules
        if self.cfg['moduleforceunload']:
            unloads = [self.module_generator.unload_module(d) for d in deps[::-1]]
            dep_stmts = unloads + loads
        else:
            dep_stmts = loads

        # load first version listed in multi_deps as a default, if desired
        if self.cfg['multi_deps_load_default']:

            # build map of dep name to list of module names corresponding to each version
            # first entry in multi_deps is list of first versions for each multi-dep
            multi_dep_mod_names = {}
            for deplist in self.cfg.multi_deps:
                for dep in deplist:
                    multi_dep_mod_names.setdefault(dep['name'], []).append(dep['short_mod_name'])

            multi_dep_load_defaults = []
            for _, depmods in sorted(multi_dep_mod_names.items()):
                stmt = self.module_generator.load_module(depmods[0], multi_dep_mods=depmods,
                                                         recursive_unload=recursive_unload,
                                                         depends_on=depends_on)
                multi_dep_load_defaults.append(stmt)

            dep_stmts.extend(multi_dep_load_defaults)

        return ''.join(dep_stmts)

    def make_module_description(self):
        """
        Create the module description.
        """
        return self.module_generator.get_description()

    def make_module_pythonpath(self):
        """
        Add lines for module file to update $PYTHONPATH or $EBPYTHONPREFIXES,
        if they aren't already present and the standard lib/python*/site-packages subdirectory exists
        """
        if os.path.isfile(os.path.join(self.installdir, 'bin', 'python')):  # only needed when not a python install
            return []

        python_subdir_pattern = os.path.join(self.installdir, 'lib', 'python*', 'site-packages')
        candidate_paths = (os.path.relpath(path, self.installdir) for path in glob.glob(python_subdir_pattern))
        python_paths = [path for path in candidate_paths if re.match(r'lib/python\d+\.\d+/site-packages', path)]
        if not python_paths:
            return []

        # determine whether Python is a runtime dependency;
        # if so, we assume it was installed with EasyBuild, and hence is aware of $EBPYTHONPREFIXES
        runtime_deps = [dep['name'] for dep in self.cfg.dependencies(runtime_only=True)]

        # don't use $EBPYTHONPREFIXES unless we can and it's preferred or necesary (due to use of multi_deps)
        use_ebpythonprefixes = False
        multi_deps = self.cfg['multi_deps']

        if 'Python' in runtime_deps:
            self.log.info("Found Python runtime dependency, so considering $EBPYTHONPREFIXES...")

            if build_option('prefer_python_search_path') == EBPYTHONPREFIXES:
                self.log.info("Preferred Python search path is $EBPYTHONPREFIXES, so using that")
                use_ebpythonprefixes = True

        elif multi_deps and 'Python' in multi_deps:
            self.log.info("Python is listed in 'multi_deps', so using $EBPYTHONPREFIXES instead of $PYTHONPATH")
            use_ebpythonprefixes = True

        if use_ebpythonprefixes:
            path = ''  # EBPYTHONPREFIXES are relative to the install dir
            lines = self.module_generator.prepend_paths(EBPYTHONPREFIXES, path, warn_exists=False)
        else:
            lines = self.module_generator.prepend_paths(PYTHONPATH, python_paths, warn_exists=False)
        return [lines] if lines else []

    def make_module_extra(self, altroot=None, altversion=None):
        """
        Set extra stuff in module file, e.g. $EBROOT*, $EBVERSION*, etc.

        :param altroot: path to use to define $EBROOT*
        :param altversion: version to use to define $EBVERSION*
        """
        lines = ['']

        env_name = convert_name(self.name, upper=True)

        # $EBROOT<NAME>
        root_envvar = ROOT_ENV_VAR_NAME_PREFIX + env_name
        if altroot:
            set_root_envvar = self.module_generator.set_environment(root_envvar, altroot)
        else:
            set_root_envvar = self.module_generator.set_environment(root_envvar, '', relpath=True)
        lines.append(set_root_envvar)

        # $EBVERSION<NAME>
        version_envvar = VERSION_ENV_VAR_NAME_PREFIX + env_name
        lines.append(self.module_generator.set_environment(version_envvar, altversion or self.version))

        # $EBDEVEL<NAME>
        devel_path = os.path.join(log_path(ec=self.cfg), ActiveMNS().det_devel_module_filename(self.cfg))
        devel_path_envvar = DEVEL_ENV_VAR_NAME_PREFIX + env_name
        lines.append(self.module_generator.set_environment(devel_path_envvar, devel_path, relpath=True))

        lines.append('\n')
        for (key, value) in self.cfg['modextravars'].items():
            lines.append(self.module_generator.set_environment(key, value))

        # add lines to update $PYTHONPATH or $EBPYTHONPREFIXES
        lines.extend(self.make_module_pythonpath())

        modloadmsg = self.cfg['modloadmsg']
        if modloadmsg:
            # add trailing newline to prevent that shell prompt is 'glued' to module load message
            if not modloadmsg.endswith('\n'):
                modloadmsg += '\n'
            lines.append(self.module_generator.msg_on_load(modloadmsg))

        modunloadmsg = self.cfg['modunloadmsg']
        if modunloadmsg:
            # add trailing newline to prevent that shell prompt is 'glued' to module unload/purge message
            if not modunloadmsg.endswith('\n'):
                modunloadmsg += '\n'
            lines.append(self.module_generator.msg_on_unload(modunloadmsg))

        for (key, value) in self.cfg['modaliases'].items():
            lines.append(self.module_generator.set_alias(key, value))

        txt = ''.join(lines)
        self.log.debug("make_module_extra added this: %s", txt)

        return txt

    def make_module_extra_extensions(self):
        """
        Sets optional variables for extensions.
        """
        # add stuff specific to individual extensions
        lines = [self.module_extra_extensions]

        # set environment variable that specifies list of extensions
        # We need only name and version, so don't resolve templates
        exts_list = self.make_extension_string(ext_sep=',', sort=False)
        env_var_name = 'EBEXTSLIST' + convert_name(self.name, upper=True)
        lines.append(self.module_generator.set_environment(env_var_name, exts_list))

        return ''.join(lines)

    def make_module_footer(self):
        """
        Insert a footer section in the module file, primarily meant for contextual information
        """
        footer = [self.module_generator.comment("Built with EasyBuild version %s" % VERBOSE_VERSION)]

        # add extra stuff for extensions (if any)
        if self.cfg.get_ref('exts_list'):
            footer.append(self.make_module_extra_extensions())

        # include modules footer if one is specified
        if self.modules_footer is not None:
            self.log.debug("Including specified footer into module: '%s'" % self.modules_footer)
            footer.append(self.modules_footer)

        if self.cfg['modtclfooter']:
            if isinstance(self.module_generator, ModuleGeneratorTcl):
                self.log.debug("Including Tcl footer in module: %s", self.cfg['modtclfooter'])
                footer.extend([self.cfg['modtclfooter'], '\n'])
            else:
                self.log.warning("Not including footer in Tcl syntax in non-Tcl module file: %s",
                                 self.cfg['modtclfooter'])

        if self.cfg['modluafooter']:
            if isinstance(self.module_generator, ModuleGeneratorLua):
                self.log.debug("Including Lua footer in module: %s", self.cfg['modluafooter'])
                footer.extend([self.cfg['modluafooter'], '\n'])
            else:
                self.log.warning("Not including footer in Lua syntax in non-Lua module file: %s",
                                 self.cfg['modluafooter'])

        return ''.join(footer)

    def make_module_extend_modpath(self):
        """
        Include prepend-path statements for extending $MODULEPATH.
        """
        txt = ''
        if self.cfg['include_modpath_extensions']:
            modpath_exts = ActiveMNS().det_modpath_extensions(self.cfg)
            self.log.debug("Including module path extensions returned by module naming scheme: %s", modpath_exts)
            full_path_modpath_extensions = [os.path.join(self.installdir_mod, ext) for ext in modpath_exts]
            # module path extensions must exist, otherwise loading this module file will fail
            for modpath_extension in full_path_modpath_extensions:
                mkdir(modpath_extension, parents=True)
            txt = self.module_generator.use(full_path_modpath_extensions)

            # add user-specific module path; use statement will be guarded so no need to create the directories
            user_modpath = build_option('subdir_user_modules')
            if user_modpath:
                user_envvars = build_option('envvars_user_modules') or [DEFAULT_ENVVAR_USERS_MODULES]
                user_modpath_exts = ActiveMNS().det_user_modpath_extensions(self.cfg)
                self.log.debug("Including user module path extensions returned by naming scheme: %s", user_modpath_exts)
                for user_envvar in user_envvars:
                    self.log.debug("Requested environment variable $%s to host additional branch for modules",
                                   user_envvar)
                    default_value = user_envvar + "_NOT_DEFINED"
                    getenv_txt = self.module_generator.getenv_cmd(user_envvar, default=default_value)
                    txt += self.module_generator.use(user_modpath_exts, prefix=getenv_txt,
                                                     guarded=True, user_modpath=user_modpath)
        else:
            self.log.debug("Not including module path extensions, as specified.")
        return txt

    def make_module_group_check(self):
        """
        Create the necessary group check.
        """
        group_error_msg = None
        ec_group = self.cfg['group']
        if ec_group is not None and isinstance(ec_group, tuple):
            group_error_msg = ec_group[1]

        if self.group is not None:
            txt = self.module_generator.check_group(self.group[0], error_msg=group_error_msg)
        else:
            txt = ''

        return txt

    def make_module_req(self):
        """
        Generate the environment-variables required to run the module.
        """
        if self.make_module_req_guess.__qualname__ != "EasyBlock.make_module_req_guess":
            # Deprecated make_module_req_guess method used in child Easyblock
            # adjust environment with custom make_module_req_guess
            self.log.deprecated(
                "make_module_req_guess() is deprecated, use EasyBlock.module_load_environment instead.",
                "6.0",
            )
            self.module_load_environment.replace(self.make_module_req_guess())

        # update module load environment with extra paths defined in easyconfig
        self.inject_module_extra_paths()

        # Expand and inject path-like environment variables into module file
        env_var_requirements = {
            envar_name: envar_val
            for envar_name, envar_val in sorted(self.module_load_environment.items())
            if envar_val.is_path
        }
        self.log.debug(f"Tentative module environment requirements before path expansion: {env_var_requirements}")
        # TODO: handle non-path variables in make_module_extra
        # in the meantime, just report if any is found
        non_path_envars = set(self.module_load_environment) - set(env_var_requirements)
        if non_path_envars:
            self.log.warning(
                f"Non-path variables found in module load environment: {non_path_envars}."
                "This is not yet supported by this version of EasyBuild."
            )

        mod_lines = ['\n']

        if self.dry_run:
            self.dry_run_msg("List of paths that would be searched and added to module file:\n")
            note = "note: glob patterns are not expanded and existence checks "
            note += "for paths are skipped for the statements below due to dry run"
            mod_lines.append(self.module_generator.comment(note))

        for env_var, search_paths in env_var_requirements.items():
            if self.dry_run:
                # Don't expand globs or do any filtering for dry run
                mod_req_paths = search_paths
                self.dry_run_msg(f" ${env_var}:{', '.join(mod_req_paths)}")
            else:
                mod_req_paths = search_paths.expand_paths(self.installdir)

            if mod_req_paths:
                mod_req_paths = nub(mod_req_paths)  # remove duplicates
                extra_mod_lines = self.module_generator.update_paths(env_var, mod_req_paths, allow_abs=True,
                                                                     prepend=search_paths.mod_prepend,
                                                                     delim=search_paths.delimiter)
                mod_lines.append(extra_mod_lines)

        if self.dry_run:
            self.dry_run_msg('')

        return ''.join(mod_lines)

    def inject_module_extra_paths(self):
        """
        Parse search paths and delimiters defined in 'modextrapaths' easyconfig parameter
        and inject them into module load environment
        """
        ec_param = 'modextrapaths'
        known_aliases = [MODULE_LOAD_ENV_HEADERS]

        for env_var_name, extra_opts in self.cfg[ec_param].items():
            # default settings for environment variables
            env_var_opts = {
                'delimiter': os.pathsep,  # ':'
                'var_type': ModEnvVarType.PATH_WITH_FILES,
                'prepend': True,
            }

            if not isinstance(extra_opts, dict):
                extra_opts = {'paths': extra_opts}

            env_var_opts.update(extra_opts)

            if 'paths' not in env_var_opts:
                error_msg = f"'paths' key not set for ${env_var_name} in '{ec_param}' easyconfig parameter"
                raise EasyBuildError(error_msg)

            # make sure that we have a list of paths, even if there's only one
            if isinstance(env_var_opts['paths'], str):
                env_var_opts['paths'] = [env_var_opts['paths']]

            existing_env_vars = []
            if env_var_name in self.module_load_environment:
                # update existing variable
                existing_env_vars.append(env_var_name)
            elif env_var_name in known_aliases:
                # update existing alias to variables
                existing_env_vars = self.module_load_environment.alias_vars(env_var_name)

            for existing_env_var in existing_env_vars:
                env_var = getattr(self.module_load_environment, existing_env_var)
                env_var.extend(env_var_opts['paths'])
                env_var.delimiter = env_var_opts['delimiter']
                env_var.prepend = env_var_opts['prepend']
                env_var.type = env_var_opts['var_type']
                msg = f"Variable ${existing_env_var} from '{ec_param}' extended in module load environment with "
                msg += f"delimiter='{env_var.delimiter}', prepend='{env_var.prepend}', type='{env_var.type}' "
                msg += f"and paths='{env_var}'"
                self.log.debug(msg)

            if not existing_env_vars:
                # rename 'modextrapaths' options to match ModuleEnvironmentVariable constructor parameters
                env_var_opts['contents'] = env_var_opts.pop('paths')
                setattr(self.module_load_environment, env_var_name, env_var_opts)
                env_var = getattr(self.module_load_environment, env_var_name)
                msg = f"Variable ${env_var_name} from '{ec_param}' added to module load environment with "
                msg += f"delimiter='{env_var.delimiter}', prepend='{env_var.prepend}', type='{env_var.type}' "
                msg += f"and paths='{env_var}'"
                self.log.debug(msg)

    def expand_module_search_path(self, search_path, path_type=ModEnvVarType.PATH_WITH_FILES):
        """
        REMOVED in EasyBuild 5.1, use EasyBlock.module_load_environment.expand_paths instead
        """
        msg = "expand_module_search_path is replaced by EasyBlock.module_load_environment.expand_paths"
        self.log.nosupport(msg, '5.1')

    def make_module_req_guess(self):
        """
        A dictionary of common search path variables to be loaded by environment modules
        Each key contains the list of known directories related to the search path
        """
        self.log.deprecated(
            "make_module_req_guess() is deprecated, use EasyBlock.module_load_environment instead",
            '6.0',
        )
        return self.module_load_environment.as_dict

    def load_module(self, mod_paths=None, purge=True, extra_modules=None, verbose=True):
        """
        Load module for this software package/version, after purging all currently loaded modules.

        :param mod_paths: list of (additional) module paths to take into account
        :param purge: boolean indicating whether or not to purge currently loaded modules first
        :param extra_modules: list of extra modules to load (these are loaded *before* loading the 'self' module)
        :param verbose: print modules being loaded when trace mode is enabled
        """
        # self.full_mod_name might not be set (e.g. during unit tests)
        if self.full_mod_name is not None:
            if mod_paths is None:
                mod_paths = []
            all_mod_paths = mod_paths + ActiveMNS().det_init_modulepaths(self.cfg)

            mods = [self.short_mod_name]

            # if extra modules are specified, these are loaded first;
            # this is important in the context of sanity check for easyconfigs that use multi_deps,
            # especially if multi_deps_load_default is set...
            if extra_modules:
                mods = extra_modules + mods

            # for flat module naming schemes, we can load the module directly;
            # for non-flat (hierarchical) module naming schemes, we may need to load the toolchain module first
            # to update $MODULEPATH such that the module can be loaded using the short module name
            if self.mod_subdir and not self.toolchain.is_system_toolchain():
                mods.insert(0, self.toolchain.det_short_module_name())

            if verbose:
                trace_msg("loading modules: %s..." % ', '.join(mods))

            # pass initial environment, to use it for resetting the environment before loading the modules
            self.modules_tool.load(mods, mod_paths=all_mod_paths, purge=purge, init_env=self.initial_environ)

            # handle environment variables that need to be updated after loading modules
            for var, val in sorted(self.tweaked_env_vars.items()):
                self.log.info("Tweaking $%s: %s", var, val)
                env.setvar(var, val)

        else:
            self.log.warning("Not loading module, since self.full_mod_name is not set.")

    def load_fake_module(self, purge=False, extra_modules=None, verbose=False):
        """
        Create and load fake module.

        :param purge: boolean indicating whether or not to purge currently loaded modules first
        :param extra_modules: list of extra modules to load (these are loaded *before* loading the 'self' module)
        """
        self.log.info("Loading fake module (%s)", self.short_mod_name)

        # take a copy of the current environment before loading the fake module, so we can restore it
        env = copy.deepcopy(os.environ)

        # create fake module
        fake_mod_path = self.make_module_step(fake=True)

        # load fake module
        self.modules_tool.prepend_module_path(os.path.join(fake_mod_path, self.mod_subdir), priority=10000)
        self.load_module(purge=purge, extra_modules=extra_modules, verbose=verbose)
        return (fake_mod_path, env)

    def clean_up_fake_module(self, fake_mod_data):
        """
        Clean up fake module.
        """
        fake_mod_path, env = fake_mod_data
        # unload module and remove temporary module directory
        # self.short_mod_name might not be set (e.g. during unit tests)
        if fake_mod_path and self.short_mod_name is not None:
            try:
                self.modules_tool.unload([self.short_mod_name])
                self.modules_tool.remove_module_path(os.path.join(fake_mod_path, self.mod_subdir))
                remove_dir(os.path.dirname(fake_mod_path))
            except OSError as err:
                raise EasyBuildError("Failed to clean up fake module dir %s: %s", fake_mod_path, err)
        elif self.short_mod_name is None:
            self.log.warning("Not unloading module, since self.short_mod_name is not set.")

        # restore original environment
        restore_env(env)

    def load_dependency_modules(self):
        """Load dependency modules."""
        self.modules_tool.load([ActiveMNS().det_full_module_name(dep) for dep in self.cfg.dependencies()])

    #
    # EXTENSIONS UTILITY FUNCTIONS
    #

    def make_extension_string(self, name_version_sep='-', ext_sep=', ', sort=True):
        """
        Generate a string with a list of extensions returned by make_extension_list.

        The name and version are separated by name_version_sep and each extension is separated by ext_sep.
        For customization of extensions the make_extension_list method should be used.
        """
        exts_list = (name_version_sep.join(ext) for ext in self.make_extension_list())
        if sort:
            exts_list = sorted(exts_list, key=str.lower)
        return ext_sep.join(exts_list)

    def make_extension_list(self):
        """
        Return a list of extension names and their versions included in this installation

        Each entry should be a (name, version) tuple or just (name, ) if no version exists.
        Custom EasyBlocks may override this to add extensions that cannot be found automatically.
        """
        # Each extension in exts_list is either a string or a list/tuple with name, version as first entries
        # As name can be a templated value we must resolve templates
        if hasattr(self, '_make_extension_list'):
            self.log.nosupport("self._make_extension_list is replaced by self.make_extension_list", '5.0')
        if type(self).make_extension_string != EasyBlock.make_extension_string:
            self.log.nosupport("self.make_extension_string should not be overridden", '5.0')

        exts_list = []
        for ext in self.cfg.get_ref('exts_list'):
            if isinstance(ext, str):
                exts_list.append((resolve_template(ext, self.cfg.template_values), ))
            else:
                exts_list.append((resolve_template(ext[0], self.cfg.template_values),
                                  resolve_template(ext[1], self.cfg.template_values)))
        return exts_list

    def prepare_for_extensions(self):
        """Ran before installing extensions (eg to set templates)"""

    def skip_extensions(self):
        """
        Skip already installed extensions,
        by removing them from list of Extension instances to install (self.ext_instances).

        This is done in parallel when EasyBuild is configured to install extensions in parallel.
        """
        self.update_exts_progress_bar("skipping installed extensions")

        # obtaining untemplated reference value is required here to support legacy string templates like name/version
        exts_filter = self.cfg.get_ref('exts_filter')

        if not exts_filter or len(exts_filter) == 0:
            raise EasyBuildError("Skipping of extensions, but no exts_filter set in easyconfig")

        with self.fake_module_environment():
            if build_option('parallel_extensions_install'):
                self.skip_extensions_parallel(exts_filter)
            else:
                self.skip_extensions_sequential(exts_filter)

    def skip_extensions_sequential(self, exts_filter):
        """
        Skip already installed extensions (checking sequentially),
        by removing them from list of Extension instances to install (self.ext_instances).
        """
        print_msg("skipping installed extensions (sequentially)", log=self.log)

        exts_cnt = len(self.ext_instances)

        exts = []
        for idx, ext_inst in enumerate(self.ext_instances):
            cmd, stdin = resolve_exts_filter_template(exts_filter, ext_inst)
            res = run_shell_cmd(cmd, stdin=stdin, fail_on_error=False, hidden=True)
            self.log.info(f"exts_filter result for {ext_inst.name}: exit code {res.exit_code}; output: {res.output}")
            if res.exit_code == EasyBuildExit.SUCCESS:
                print_msg(f"skipping extension {ext_inst.name}", silent=self.silent, log=self.log)
            else:
                self.log.info(f"Not skipping {ext_inst.name}")
                exts.append(ext_inst)

            self.update_exts_progress_bar(f"skipping installed extensions ({idx + 1}/{exts_cnt} checked)")

        self.ext_instances = exts
        self.update_exts_progress_bar("already installed extensions filtered out", total=len(self.ext_instances))

    def skip_extensions_parallel(self, exts_filter):
        """
        Skip already installed extensions (checking in parallel),
        by removing them from list of Extension instances to install (self.ext_instances).
        """
        print_msg("skipping installed extensions (in parallel)", log=self.log)

        installed_exts_ids = []
        checked_exts_cnt = 0
        exts_cnt = len(self.ext_instances)
        cmds = [resolve_exts_filter_template(exts_filter, ext) for ext in self.ext_instances]

        with ThreadPoolExecutor(max_workers=self.cfg.parallel) as thread_pool:

            # list of command to run asynchronously
            async_cmds = [thread_pool.submit(run_shell_cmd, cmd, stdin=stdin, hidden=True, fail_on_error=False,
                                             asynchronous=True, task_id=idx) for (idx, (cmd, stdin)) in enumerate(cmds)]

            # process result of commands as they have completed running
            for done_task in concurrent.futures.as_completed(async_cmds):
                res = done_task.result()
                idx = res.task_id
                ext_name = self.ext_instances[idx].name
                self.log.info(f"exts_filter result for {ext_name}: exit code {res.exit_code}; output: {res.output}")
                if res.exit_code == EasyBuildExit.SUCCESS:
                    print_msg(f"skipping extension {ext_name}", log=self.log)
                    installed_exts_ids.append(idx)

                checked_exts_cnt += 1
                exts_pbar_label = "skipping installed extensions "
                exts_pbar_label += "(%d/%d checked)" % (checked_exts_cnt, exts_cnt)
                self.update_exts_progress_bar(exts_pbar_label)

        # compose new list of extensions, skip over the ones that are already installed;
        # note: original order in extensions list should be preserved!
        retained_ext_instances = []
        for idx, ext in enumerate(self.ext_instances):
            if idx not in installed_exts_ids:
                retained_ext_instances.append(ext)
                self.log.info("Not skipping %s", ext.name)

        self.ext_instances = retained_ext_instances

    def install_extensions(self, *args, **kwargs):
        """[DEPRECATED] Install extensions."""
        self.log.deprecated(
            "EasyBlock.install_extensions() is deprecated, use EasyBlock.install_all_extensions() instead.",
            '6.0',
        )
        self.install_all_extensions(*args, **kwargs)

    def install_all_extensions(self, install=True):
        """
        Install extensions.

        :param install: actually install extensions, don't just prepare environment for installing

        """
        self.log.debug("List of loaded modules: %s", self.modules_tool.list())

        if build_option('parallel_extensions_install'):
            try:
                self.install_extensions_parallel(install=install)
            except NotImplementedError:
                # If parallel extension install is not supported for this type of extension then install sequentially
                msg = "Parallel extensions install not supported for %s - using sequential install" % self.name
                self.log.info(msg)
                self.install_extensions_sequential(install=install)
        else:
            self.install_extensions_sequential(install=install)

    def install_extensions_sequential(self, install=True):
        """
        Install extensions sequentially.

        :param install: actually install extensions, don't just prepare environment for installing
        """
        self.log.info("Installing extensions sequentially...")

        exts_cnt = len(self.ext_instances)

        for idx, ext in enumerate(self.ext_instances):
            self.log.info("Starting extension %s", ext.name)

            run_hook(SINGLE_EXTENSION, self.hooks, pre_step_hook=True, args=[ext])

            # always go back to original work dir to avoid running stuff from a dir that no longer exists
            change_dir(self.orig_workdir)

            progress_info = "Installing '%s' extension (%s/%s)" % (ext.name, idx + 1, exts_cnt)
            self.update_exts_progress_bar(progress_info)

            tup = (ext.name, ext.version or '', idx + 1, exts_cnt)
            print_msg("installing extension %s %s (%d/%d)..." % tup, silent=self.silent, log=self.log)
            start_time = datetime.now()

            if self.dry_run:
                tup = (ext.name, ext.version, ext.__class__.__name__)
                msg = "\n* installing extension %s %s using '%s' easyblock\n" % tup
                self.dry_run_msg(msg)

            if self.dry_run:
                self.dry_run_msg("defining build environment based on toolchain (options) and dependencies...")

            # actual installation of the extension
            if install and not self.dry_run:
                with self.fake_module_environment(with_build_deps=True):
                    self.log.debug("List of loaded modules: %s", self.modules_tool.list())
                    # don't reload modules for toolchain, there is no need
                    # since they will be loaded already by the fake module
                    ext.toolchain.prepare(onlymod=self.cfg['onlytcmod'], silent=True, loadmod=False,
                                          rpath_filter_dirs=self.rpath_filter_dirs,
                                          rpath_include_dirs=self.rpath_include_dirs,
                                          rpath_wrappers_dir=self.rpath_wrappers_dir)
                    try:
                        ext.install_extension_substep("pre_install_extension")
                        with self.module_generator.start_module_creation():
                            txt = ext.install_extension_substep("install_extension")
                        if txt:
                            self.module_extra_extensions += txt
                        ext.install_extension_substep("post_install_extension")
                    finally:
                        ext_duration = datetime.now() - start_time
                        if ext_duration.total_seconds() >= 1:
                            print_msg("\t... (took %s)", time2str(ext_duration), log=self.log, silent=self.silent)
                        elif self.logdebug or build_option('trace'):
                            print_msg("\t... (took < 1 sec)", log=self.log, silent=self.silent)

            self.update_exts_progress_bar(progress_info, progress_size=1)

            run_hook(SINGLE_EXTENSION, self.hooks, post_step_hook=True, args=[ext])

    def install_extensions_parallel(self, install=True):
        """
        Install extensions in parallel.

        :param install: actually install extensions, don't just prepare environment for installing
        """
        self.log.info("Installing extensions in parallel...")

        thread_pool = ThreadPoolExecutor(max_workers=self.cfg.parallel)

        running_exts = []
        installed_ext_names = []

        all_ext_names = [x['name'] for x in self.exts_all]
        self.log.debug("List of names of all extensions: %s", all_ext_names)

        # take into account that some extensions may be installed already
        to_install_ext_names = [x.name for x in self.ext_instances]
        installed_ext_names = [n for n in all_ext_names if n not in to_install_ext_names]

        exts_cnt = len(all_ext_names)
        exts_queue = self.ext_instances[:]

        def update_exts_progress_bar_helper(running_exts, progress_size):
            """Helper function to update extensions progress bar."""
            running_exts_cnt = len(running_exts)
            if running_exts_cnt > 1:
                progress_info = "Installing %d extensions" % running_exts_cnt
            elif running_exts_cnt == 1:
                progress_info = "Installing extension "
            else:
                progress_info = "Not installing extensions (yet)"

            if running_exts_cnt:
                progress_info += " (%d/%d done): " % (len(installed_ext_names), exts_cnt)
                progress_info += ', '.join(e.name for e in running_exts)

            self.update_exts_progress_bar(progress_info, progress_size=progress_size)

        while exts_queue or running_exts:

            # always go back to original work dir to avoid running stuff from a dir that no longer exists
            change_dir(self.orig_workdir)

            # check for extension installations that have completed
            if running_exts:
                self.log.info(f"Checking for completed extension installations ({len(running_exts)} running)...")
                for ext in running_exts[:]:
                    if self.dry_run or ext.async_cmd_task.done():
                        res = ext.async_cmd_task.result()
                        if res.exit_code == EasyBuildExit.SUCCESS:
                            self.log.info(f"Installation of extension {ext.name} completed!")
                            # run post-install method for extension from same working dir as installation of extension
                            cwd = change_dir(res.work_dir)
                            ext.install_extension_substep("post_install_extension")
                            change_dir(cwd)
                            running_exts.remove(ext)
                            installed_ext_names.append(ext.name)
                            update_exts_progress_bar_helper(running_exts, 1)
                        else:
                            raise_run_shell_cmd_error(res)
                    else:
                        self.log.debug(f"Installation of extension {ext.name} is still running...")

            # try to start as many extension installations as we can, taking into account number of available cores,
            # but only consider first 100 extensions still in the queue
            max_iter = min(100, len(exts_queue))

            for _ in range(max_iter):

                if not (exts_queue and len(running_exts) < self.cfg.parallel):
                    break

                # check whether extension at top of the queue is ready to install
                ext = exts_queue.pop(0)

                required_deps = ext.required_deps
                if required_deps is None:
                    pending_deps = None
                    self.log.info("Required dependencies for %s are unknown!", ext.name)
                else:
                    self.log.info("Required dependencies for %s: %s", ext.name, ', '.join(required_deps))
                    pending_deps = [x for x in required_deps if x not in installed_ext_names]
                    self.log.info("Missing required dependencies for %s: %s", ext.name, ', '.join(pending_deps))

                # if required dependencies could not be determined, wait until all preceding extensions are installed
                if pending_deps is None:
                    if running_exts:
                        # add extension back at top of the queue,
                        # since we need to preverse installation order of extensions;
                        # break out of for loop since there is no point to keep checking
                        # until running installations have been completed
                        exts_queue.insert(0, ext)
                        break
                    else:
                        pending_deps = []

                if self.dry_run:
                    tup = (ext.name, ext.version, ext.__class__.__name__)
                    msg = "\n* installing extension %s %s using '%s' easyblock\n" % tup
                    self.dry_run_msg(msg)
                    running_exts.append(ext)

                # if some of the required dependencies are not installed yet, requeue this extension
                elif pending_deps:

                    # check whether all required dependency extensions are actually going to be installed;
                    # if not, we assume that they are provided by dependencies;
                    missing_deps = [x for x in required_deps if x not in all_ext_names]
                    if missing_deps:
                        msg = f"Missing required extensions for {ext.name} not found "
                        msg += "in list of extensions being installed, let's assume they are provided by "
                        msg += "dependencies and proceed: " + ', '.join(missing_deps)
                        self.log.info(msg)

                        msg = f"Pending dependencies for {ext.name} before taking into account missing dependencies: "
                        self.log.debug(msg + ', '.join(pending_deps))
                        pending_deps = [x for x in pending_deps if x not in missing_deps]
                        msg = f"Pending dependencies for {ext.name} after taking into account missing dependencies: "
                        self.log.debug(msg + ', '.join(pending_deps))

                    if pending_deps:
                        msg = f"Required dependencies not installed yet for extension {ext.name} ("
                        msg += ', '.join(pending_deps)
                        msg += "), adding it back to queue..."
                        self.log.info(msg)
                        # purposely adding extension back in the queue at Nth place rather than at the end,
                        # since we assume that the required dependencies will be installed soon...
                        exts_queue.insert(max_iter, ext)

                # list of pending dependencies may be empty now after taking into account required extensions
                # that are not being installed above, so extension may be ready to install
                if not pending_deps:
                    tup = (ext.name, ext.version or '')
                    print_msg("starting installation of extension %s %s..." % tup, silent=self.silent, log=self.log)

                    if install and not self.dry_run:
                        with self.fake_module_environment(with_build_deps=True):
                            # don't reload modules for toolchain, there is no
                            # need since they will be loaded by the fake module
                            ext.toolchain.prepare(onlymod=self.cfg['onlytcmod'], silent=True, loadmod=False,
                                                  rpath_filter_dirs=self.rpath_filter_dirs,
                                                  rpath_include_dirs=self.rpath_include_dirs,
                                                  rpath_wrappers_dir=self.rpath_wrappers_dir)
                            ext.install_extension_substep("pre_install_extension")
                            ext.async_cmd_task = ext.install_extension_substep("install_extension_async", thread_pool)
                            running_exts.append(ext)
                            self.log.info(f"Started installation of extension {ext.name} in the background...")
                        update_exts_progress_bar_helper(running_exts, 0)

            # print progress info after every iteration (unless that info is already shown via progress bar)
            if not show_progress_bars():
                msg = "%d out of %d extensions installed (%d queued, %d running: %s)"
                installed_cnt, queued_cnt, running_cnt = len(installed_ext_names), len(exts_queue), len(running_exts)
                if running_cnt <= 3:
                    running_ext_names = ', '.join(x.name for x in running_exts)
                else:
                    running_ext_names = ', '.join(x.name for x in running_exts[:3]) + ", ..."
                print_msg(msg % (installed_cnt, exts_cnt, queued_cnt, running_cnt, running_ext_names), log=self.log)

        thread_pool.shutdown()

    #
    # MISCELLANEOUS UTILITY FUNCTIONS
    #

    @property
    def start_dir(self):
        """Start directory in build directory"""
        return self.cfg['start_dir']

    @contextmanager
    def fake_module_environment(self, extra_modules=None, with_build_deps=False):
        """
        Load/Unload fake module
        """
        fake_mod_data = None

        if with_build_deps:
            # load modules for build dependencies as extra modules
            extra_modules = [dep['short_mod_name'] for dep in self.cfg.dependencies(build_only=True)]

        fake_mod_data = self.load_fake_module(purge=True, extra_modules=extra_modules)

        try:
            yield
        finally:
            # cleanup (unload fake module, remove fake module dir)
            if fake_mod_data:
                self.clean_up_fake_module(fake_mod_data)

    def guess_start_dir(self):
        """
        Return the directory where to start the whole configure/make/make install cycle from
        - typically self.src[0]['finalpath']
        - start_dir option
        -- if abspath: use that
        -- else, treat it as subdir for regular procedure
        """
        start_dir = ''
        # do not use the specified 'start_dir' when running as --module-only as
        # the directory will not exist (extract_step is skipped)
        if self.start_dir and not build_option('module_only') and not self.cfg['module_only']:
            start_dir = self.start_dir

        if not os.path.isabs(start_dir):
            if len(self.src) > 0 and not self.skip and self.src[0]['finalpath']:
                topdir = self.src[0]['finalpath']
            else:
                topdir = self.builddir

            # during dry run, use subdirectory that would likely result from unpacking
            if self.dry_run and os.path.samefile(topdir, self.builddir):
                topdir = os.path.join(self.builddir, '%s-%s' % (self.name, self.version))
                self.log.info("Modified parent directory of start dir in dry run mode to likely path %s", topdir)
                # make sure start_dir subdir exists (cfr. check below)
                mkdir(os.path.join(topdir, start_dir), parents=True)

            abs_start_dir = os.path.join(topdir, start_dir)
            if topdir.endswith(start_dir) and not os.path.exists(abs_start_dir):
                self.cfg['start_dir'] = topdir
            else:
                if os.path.exists(abs_start_dir):
                    self.cfg['start_dir'] = abs_start_dir
                else:
                    raise EasyBuildError("Specified start dir %s does not exist", abs_start_dir)

        self.log.info("Using %s as start dir", self.cfg['start_dir'])

        change_dir(self.start_dir)
        self.log.debug("Changed to real build directory %s (start_dir)", self.start_dir)

    def check_accepted_eula(self, name=None, more_info=None):
        """Check whether EULA for this software is accepted in current EasyBuild configuration."""

        if name is None:
            name = self.name

        accepted_eulas = build_option('accept_eula_for') or []
        if self.cfg['accept_eula'] or name in accepted_eulas or any(re.match(x, name) for x in accepted_eulas):
            self.log.info("EULA for %s is accepted", name)
        else:
            error_lines = [
                "The End User License Agreement (EULA) for %(name)s is currently not accepted!",
            ]
            if more_info:
                error_lines.append("(see %s for more information)" % more_info)

            error_lines.extend([
                "You should either:",
                "- add --accept-eula-for=%(name)s to the 'eb' command;",
                "- update your EasyBuild configuration to always accept the EULA for %(name)s;",
                "- add 'accept_eula = True' to the easyconfig file you are using;",
                '',
            ])
            raise EasyBuildError('\n'.join(error_lines) % {'name': name})

    def handle_iterate_opts(self):
        """Handle options relevant during iterated part of build/install procedure."""

        # if we were iterating already, bump iteration index
        if self.cfg.iterating:
            self.log.info("Done with iteration #%d!", self.iter_idx)
            self.iter_idx += 1

        # disable templating in this function, since we're messing about with values in self.cfg
        with self.cfg.disable_templating():

            # start iterative mode (only need to do this once)
            if self.iter_idx == 0:
                self.cfg.start_iterating()

            # handle configure/build/install options that are specified as lists (+ perhaps builddependencies)
            # set first element to be used, keep track of list in self.iter_opts
            # only needs to be done during first iteration, since after that the options won't be lists anymore
            if self.iter_idx == 0 and self.cfg.iterate_options:
                # keep track of list, supply first element as first option to handle
                for opt in ITERATE_OPTIONS:
                    self.iter_opts[opt] = self.cfg[opt]  # copy
                    self.log.debug("Iterating opt %s: %s", opt, self.iter_opts[opt])

            if self.iter_opts:
                print_msg("starting iteration #%s ..." % self.iter_idx, log=self.log, silent=self.silent)
                self.log.info("Current iteration index: %s", self.iter_idx)

            # pop first element from all iterative easyconfig parameters as next value to use
            for opt, value in self.iter_opts.items():
                if opt not in self.cfg.iterate_options:
                    # Use original value even for options that were specified as strings so don't change
                    # (ie. elements in ITERATE_OPTIONS but not in self.cfg.iterate_options), so they
                    # are restored after an easyblock such as CMakeMake changes them
                    self.cfg[opt] = value
                elif len(value) > self.iter_idx:
                    self.cfg[opt] = value[self.iter_idx]
                else:
                    self.cfg[opt] = ''  # empty list => empty option as next value
                self.log.debug("Next value for %s: %s" % (opt, str(self.cfg[opt])))

            # re-generate template values, which may be affected by changed parameters we're iterating over
            self.cfg.generate_template_values()

    def post_iter_step(self):
        """Restore options that were iterated over"""
        # disable templating, since we're messing about with values in self.cfg
        with self.cfg.disable_templating():
            for opt, value in self.iter_opts.items():
                self.cfg[opt] = value

                # also need to take into account extensions, since those were iterated over as well
                for ext in self.ext_instances:
                    ext.cfg[opt] = value

                self.log.debug("Restored value of '%s' that was iterated over: %s", opt, self.cfg[opt])

            self.cfg.stop_iterating()

    def det_iter_cnt(self):
        """Determine iteration count based on configure/build/install options that may be lists."""
        # Using get_ref to avoid resolving templates as their required attributes may not be available yet
        iter_opt_counts = [len(self.cfg.get_ref(opt)) for opt in ITERATE_OPTIONS
                           if opt not in ['builddependencies'] and isinstance(self.cfg.get_ref(opt), (list, tuple))]

        # we need to take into account that builddependencies is always a list
        # we're only iterating over it if it's a list of lists
        builddeps = self.cfg['builddependencies']
        if all(isinstance(x, list) for x in builddeps):
            iter_opt_counts.append(len(builddeps))

        iter_cnt = max([1] + iter_opt_counts)
        self.log.info("Number of iterations to perform for central part of installation procedure: %s", iter_cnt)

        return iter_cnt

    def set_parallel(self):
        """Set 'parallel' easyconfig parameter to determine how many cores can/should be used for parallel builds."""
        # set level of parallelism for build
        par = build_option('parallel')
        if par is not None:
            self.log.debug(f"Desired parallelism specified via 'parallel' build option: {par}")

        # Transitional only in case some easyblocks still set/change cfg['parallel']
        # Use _parallelLegacy to avoid deprecation warnings
        par_ec = self.cfg['_parallelLegacy']
        if par_ec is not None:
            if par is None:
                par = par_ec
            else:
                par = min(int(par), int(par_ec))

        # --max-parallel specifies global maximum for parallelism
        max_par_global = int(build_option('max_parallel'))
        # note: 'max_parallel' and 'maxparallel; are the same easyconfig parameter,
        # since 'max_parallel' is an alternative name for 'maxparallel'
        max_par_ec = self.cfg['max_parallel']
        # take into account that False is a valid value for max_parallel
        if max_par_ec is False:
            max_par_ec = 1
        # if max_parallel is not specified in easyconfig, we take the global value
        if max_par_ec is None:
            max_par = max_par_global
        # take minimum value if both are specified
        else:
            max_par = min(int(max_par_ec), max_par_global)

        par = det_parallelism(par=par, maxpar=max_par)
        self.log.info(f"Setting parallelism: {par}")
        self.cfg.parallel = par

    def remove_module_file(self):
        """Remove module file (if it exists), and check for ghost installation directory (and deal with it)."""

        if os.path.exists(self.mod_filepath):
            # if installation directory used by module file differs from the one used now,
            # either clean it up to avoid leaving behind a ghost installation, or warn about it
            # (see also https://github.com/easybuilders/easybuild-framework/issues/3026)
            old_installdir = self.module_generator.det_installdir(self.mod_filepath)

            if old_installdir is None:
                warning_msg = "Failed to determine installation directory from module file %s" % self.mod_filepath
                warning_msg += ", can't clean up potential ghost installation for %s %s" % (self.name, self.version)
                print_warning(warning_msg)

            elif os.path.exists(old_installdir) and not os.path.samefile(old_installdir, self.installdir):
                if build_option('remove_ghost_install_dirs'):
                    remove_dir(old_installdir)
                    self.log.info("Ghost installation directory %s removed", old_installdir)
                    print_msg("Ghost installation directory %s removed", old_installdir)
                else:
                    print_warning("Likely ghost installation directory detected: %s", old_installdir)

            self.log.info("Removing existing module file %s", self.mod_filepath)
            remove_file(self.mod_filepath)

    def report_test_failure(self, msg_or_error):
        """
        Report a failing test either via an exception or warning depending on ignore-test-failure

        :param msg_or_error: failure description (string value or an EasyBuildError instance)
        """
        if build_option('ignore_test_failure'):
            print_warning("Test failure ignored: " + str(msg_or_error), log=self.log)
        else:
            exception = msg_or_error if isinstance(msg_or_error, EasyBuildError) else EasyBuildError(msg_or_error)
            raise exception

    #
    # STEP FUNCTIONS
    #
    def check_readiness_step(self):
        """
        Verify if all is ok to start build.
        """
        # check whether modules are loaded
        loadedmods = self.modules_tool.loaded_modules()
        if len(loadedmods) > 0:
            self.log.warning("Loaded modules detected: %s" % loadedmods)

        # check if the application is not loaded at the moment
        (root, env_var) = get_software_root(self.name, with_env_var=True)
        if root:
            raise EasyBuildError("Module is already loaded (%s is set), installation cannot continue.", env_var)

        # create backup of existing module file (if requested)
        if os.path.exists(self.mod_filepath) and build_option('backup_modules'):
            # strip off .lua extension to ensure that Lmod ignores backed up module file
            # Lmod 7.x ignores any files not ending in .lua
            # Lmod 6.x ignores any files that don't have .lua anywhere in the filename
            strip_fn = None
            if isinstance(self.module_generator, ModuleGeneratorLua):
                strip_fn = ModuleGeneratorLua.MODULE_FILE_EXTENSION

            # backups of modules in Tcl syntax should be hidden to avoid that they're shown in 'module avail';
            # backups of modules in Lua syntax do not need to be hidden:
            # since they don't have .lua in the filename Lmod will not pick them up anymore,
            # which is better than hiding them (since --show-hidden still reveals them)
            hidden = isinstance(self.module_generator, ModuleGeneratorTcl)

            # with old Lmod versions, the backup module should also be hidden when using Lua syntax;
            # see https://github.com/easybuilders/easybuild-easyconfigs/issues/9302
            if isinstance(self.module_generator, ModuleGeneratorLua) and isinstance(self.modules_tool, Lmod):
                hidden = LooseVersion(self.modules_tool.version) < LooseVersion('7.0.0')

            self.mod_file_backup = back_up_file(self.mod_filepath, hidden=hidden, strip_fn=strip_fn)
            print_msg("backup of existing module file stored at %s" % self.mod_file_backup, log=self.log)

        # check if main install needs to be skipped
        # - if a current module can be found, skip is ok
        # -- this is potentially very dangerous
        if self.cfg['skip']:
            if self.modules_tool.exist([self.full_mod_name], skip_avail=True)[0]:
                self.skip = True
                self.log.info("Module %s found." % self.full_mod_name)
                self.log.info("Going to skip actual main build and potential existing extensions. Expert only.")
            else:
                self.log.info("No module %s found. Not skipping anything." % self.full_mod_name)

        # remove existing module file under --force (but only if --skip is not used)
        elif (build_option('force') or build_option('rebuild')) and not build_option('dump_env_script'):
            self.remove_module_file()

    def fetch_step(self, skip_checksums=False):
        """Fetch source files and patches (incl. extensions)."""

        # check EasyBuild version
        easybuild_version = self.cfg['easybuild_version']
        if not easybuild_version:
            self.log.warning("Easyconfig does not specify an EasyBuild-version (key 'easybuild_version')! "
                             "Assuming the latest version")
        else:
            if LooseVersion(easybuild_version) < VERSION:
                self.log.warning("EasyBuild-version %s is older than the currently running one. Proceed with caution!",
                                 easybuild_version)
            elif LooseVersion(easybuild_version) > VERSION:
                raise EasyBuildError("EasyBuild-version %s is newer than the currently running one. Aborting!",
                                     easybuild_version)

        start_progress_bar(PROGRESS_BAR_DOWNLOAD_ALL, self.cfg.count_files())

        if self.dry_run:

            self.dry_run_msg("Available download URLs for sources/patches:")
            if self.cfg['source_urls']:
                for source_url in self.cfg['source_urls']:
                    self.dry_run_msg("  * %s/$source", source_url)
            else:
                self.dry_run_msg('(none)')

            # actual list of sources is printed via _obtain_file_dry_run method
            self.dry_run_msg("\nList of sources:")

        # fetch sources
        if self.cfg['sources']:
            self.fetch_sources(self.cfg['sources'], checksums=self.cfg['checksums'])
        elif self.cfg['data_sources']:
            self.fetch_sources(self.cfg['data_sources'], checksums=self.cfg['checksums'])
        else:
            self.log.info('no sources or data_sources provided')

        if self.dry_run:
            # actual list of patches is printed via _obtain_file_dry_run method
            self.dry_run_msg("\nList of patches:")

        # fetch patches
        if self.cfg['patches'] + self.cfg['postinstallpatches']:
            if self.cfg['checksums'] and isinstance(self.cfg['checksums'], (list, tuple)):
                # if checksums are provided as a list, first entries are assumed to be for sources
                patches_checksums = self.cfg['checksums'][len(self.cfg['sources']):]
            else:
                patches_checksums = self.cfg['checksums']
            self.fetch_patches(checksums=patches_checksums)
        else:
            self.log.info('no patches provided')
            if self.dry_run:
                self.dry_run_msg('(none)')

        # compute checksums for all source and patch files
        if not (skip_checksums or self.dry_run):
            for fil in self.src + self.patches:
                for checksum_type in [CHECKSUM_TYPE_SHA256]:
                    fil[checksum_type] = compute_checksum(fil['path'], checksum_type=checksum_type)
                    self.log.info("%s checksum for %s: %s", checksum_type, fil['path'], fil[checksum_type])

        # trace output for sources & patches
        if self.src:
            trace_msg("sources:")
            for src in self.src:
                msg = src['path']
                if CHECKSUM_TYPE_SHA256 in src:
                    msg += " [SHA256: %s]" % src[CHECKSUM_TYPE_SHA256]
                trace_msg(msg)
        if self.patches:
            trace_msg("patches:")
            for patch in self.patches:
                msg = patch['path']
                if CHECKSUM_TYPE_SHA256 in patch:
                    msg += " [SHA256: %s]" % patch[CHECKSUM_TYPE_SHA256]
                trace_msg(msg)

        # fetch extensions
        if self.cfg.get_ref('exts_list'):
            self.exts = self.collect_exts_file_info(fetch_files=True, verify_checksums=not skip_checksums)

        # create parent dirs in install and modules path already
        # this is required when building in parallel
        mod_symlink_paths = ActiveMNS().det_module_symlink_paths(self.cfg)
        mod_subdir = os.path.dirname(ActiveMNS().det_full_module_name(self.cfg))
        pardirs = [
            self.installdir,
            os.path.join(self.installdir_mod, mod_subdir),
        ]
        for mod_symlink_path in mod_symlink_paths:
            pardirs.append(os.path.join(install_path('mod'), mod_symlink_path, mod_subdir))

        # skip directory creation if pre-create-installdir is set to False
        if build_option('pre_create_installdir'):
            self.log.info("Checking dirs that need to be created: %s" % pardirs)
            for pardir in pardirs:
                mkdir(pardir, parents=True)
        else:
            self.log.info("Skipped installation dirs check per user request")

        stop_progress_bar(PROGRESS_BAR_DOWNLOAD_ALL)

    def checksum_step(self):
        """Verify checksum of sources and patches, if a checksum is available."""
        for fil in self.src + self.patches:
            if self.dry_run:
                # dry run mode: only report checksums, don't actually verify them
                filename = os.path.basename(fil['path'])
                expected_checksum = fil['checksum'] or '(none)'
                self.dry_run_msg("* expected checksum for %s: %s", filename, expected_checksum)
            else:
                if verify_checksum(fil['path'], fil['checksum']):
                    self.log.info("Checksum verification for %s using %s passed." % (fil['path'], fil['checksum']))
                elif build_option('ignore_checksums'):
                    print_warning("Ignoring failing checksum verification for %s" % fil['name'])
                else:
                    raise EasyBuildError(
                        "Checksum verification for %s using %s failed.", fil['path'], fil['checksum'],
                        exit_code=EasyBuildExit.FAIL_CHECKSUM
                    )

    def check_checksums_for(self, ent, sub='', source_cnt=None):
        """
        Utility method: check whether SHA256 checksums for all sources/patches are available, for given entity
        """
        ec_fn = os.path.basename(self.cfg.path)
        checksum_issues = []

        # try to get value with templates resolved, but fall back to not resolving templates;
        # this is better for error reporting that includes names of source files
        try:
            sources = ent.get('sources', [])
            data_sources = ent.get('data_sources', [])
            patches = ent.get('patches', []) + ent.get('postinstallpatches', [])
            checksums = ent.get('checksums', [])
        except EasyBuildError:
            if isinstance(ent, EasyConfig):
                sources = ent.get_ref('sources')
                data_sources = ent.get_ref('data_sources')
                patches = ent.get_ref('patches') + ent.get_ref('postinstallpatches')
                checksums = ent.get_ref('checksums')

        # Single source should be re-wrapped as a list, and checksums with it
        if isinstance(sources, dict):
            sources = [sources]
        if isinstance(data_sources, dict):
            data_sources = [data_sources]
        if isinstance(checksums, str):
            checksums = [checksums]

        sources = sources + data_sources

        if not checksums:
            checksums_from_json = self.get_checksums_from_json()
            # recreate a list of checksums. If each filename is found, the generated list of checksums should match
            # what is expected in list format
            for fn in sources + patches:
                # if the filename is a tuple, the actual source file name is the first element
                if isinstance(fn, tuple):
                    fn = fn[0]
                # if the filename is a dict, the actual source file name is the "filename" element
                if isinstance(fn, dict):
                    fn = fn["filename"]
                if fn in checksums_from_json.keys():
                    checksums += [checksums_from_json[fn]]

        if source_cnt is None:
            source_cnt = len(sources)
        patch_cnt, checksum_cnt = len(patches), len(checksums)

        if (source_cnt + patch_cnt) != checksum_cnt:
            if sub:
                sub = "%s in %s" % (sub, ec_fn)
            else:
                sub = "in %s" % ec_fn
            msg = "Checksums missing for one or more sources/patches %s: " % sub
            msg += "found %d sources + %d patches " % (source_cnt, patch_cnt)
            msg += "vs %d checksums" % checksum_cnt
            checksum_issues.append(msg)

        for fn, checksum in zip(sources + patches, checksums):

            # a checksum may be specified as a dictionary which maps filename to actual checksum
            # for example when different source files are used for different CPU architectures
            if isinstance(checksum, dict):
                checksums_to_check = checksum.values()
            else:
                checksums_to_check = [checksum]

            for checksum in checksums_to_check:
                # take into account that we may encounter a tuple of valid SHA256 checksums
                # (see https://github.com/easybuilders/easybuild-framework/pull/2958)
                if isinstance(checksum, tuple):
                    # 1st tuple item may indicate checksum type, must be SHA256 or else it's blatently ignored here
                    if len(checksum) == 2 and checksum[0] == CHECKSUM_TYPE_SHA256:
                        valid_checksums = (checksum[1],)
                    else:
                        valid_checksums = checksum
                else:
                    valid_checksums = (checksum,)

                non_sha256_checksums = [c for c in valid_checksums if not is_sha256_checksum(c)]
                if non_sha256_checksums:
                    if all(c is None for c in non_sha256_checksums):
                        print_warning("Found %d None checksum value(s), please make sure this is intended!" %
                                      len(non_sha256_checksums))
                    else:
                        msg = "Non-SHA256 checksum(s) found for %s: %s" % (fn, valid_checksums)
                        checksum_issues.append(msg)

        return checksum_issues

    def check_checksums(self):
        """
        Check whether a SHA256 checksum is available for all sources & patches (incl. extensions).

        :return: list of strings describing checksum issues (missing checksums, wrong checksum type, etc.)
        """
        checksum_issues = []

        # check whether a checksum if available for every source + patch
        checksum_issues.extend(self.check_checksums_for(self.cfg))

        # also check checksums for extensions
        for ext in self.cfg.get_ref('exts_list'):
            # just skip extensions for which only a name is specified
            # those are just there to check for things that are in the "standard library"
            if not isinstance(ext, str):
                ext_name = ext[0]
                # take into account that extension may be a 2-tuple with just name/version
                ext_opts = ext[2] if len(ext) == 3 else {}
                # only a single source per extension is supported (see source_tmpl)
                source_cnt = 1 if not ext_opts.get('nosource') else 0
                res = self.check_checksums_for(ext_opts, sub="of extension %s" % ext_name, source_cnt=source_cnt)
                checksum_issues.extend(res)

        return checksum_issues

    def extract_step(self):
        """
        Unpack the source files.
        """
        for src in self.src:
            self.log.info("Unpacking source %s" % src['name'])
            srcdir = extract_file(src['path'], self.builddir, cmd=src['cmd'],
                                  extra_options=self.cfg['unpack_options'], change_into_dir=False)
            change_dir(srcdir)
            if srcdir:
                self.src[self.src.index(src)]['finalpath'] = srcdir
            else:
                raise EasyBuildError("Unpacking source %s failed", src['name'])

    def patch_step(self, beginpath=None, patches=None):
        """
        Apply the patches
        """
        if patches is None:
            # if no patches are specified, use all non-post-install patches
            patches = [p for p in self.patches if not p['postinstall']]

        for patch in patches:
            self.log.info("Applying patch %s" % patch['name'])
            trace_msg("applying patch %s" % patch['name'])

            # if patch level is specified, use that (otherwise let apply_patch derive patch level)
            level = patch.get('level', None)
            # determine suffix of source path to apply patch in (if any)
            srcpathsuffix = patch.get('sourcepath', patch.get('copy', ''))
            # determine whether 'patch' file should be copied rather than applied
            copy_patch = 'copy' in patch and 'sourcepath' not in patch
            options = patch.get('opts', None)  # Extra options for patch command

            self.log.debug("Patch level: %s; source path suffix: %s; copy patch: %s; options: %s",
                           level, srcpathsuffix, copy_patch, options)

            if beginpath is None:
                if not self.src:
                    raise EasyBuildError("Can't apply patch %s to source if no sources are given", patch['name'])
                beginpath = self.src[0]['finalpath']
                self.log.debug("Determined begin path for patch %s: %s" % (patch['name'], beginpath))
            else:
                self.log.debug("Using specified begin path for patch %s: %s" % (patch['name'], beginpath))

            # detect partial overlap between paths
            src = os.path.abspath(weld_paths(beginpath, srcpathsuffix))
            self.log.debug("Applying patch %s in path %s", patch, src)

            apply_patch(patch['path'], src, copy=copy_patch, level=level, options=options)

    def prepare_step(self, start_dir=True, load_tc_deps_modules=True):
        """
        Pre-configure step. Set's up the builddir just before starting configure

        :param start_dir: guess start directory based on unpacked sources
        :param load_tc_deps_modules: load modules for toolchain and dependencies in build environment
        """
        if self.dry_run:
            self.dry_run_msg("Defining build environment, based on toolchain (options) and specified dependencies...\n")

        # clean environment, undefine any unwanted environment variables that may be harmful
        self.cfg['unwanted_env_vars'] = env.unset_env_vars(self.cfg['unwanted_env_vars'])

        # list of paths to include in RPATH filter;
        # only include builddir if we're not building in installation directory
        self.rpath_filter_dirs = [tempfile.gettempdir()]
        if not self.build_in_installdir:
            self.rpath_filter_dirs.append(self.builddir)

        self.rpath_include_dirs = []

        # If we have override directories for RPATH, insert them first.
        # This means they override all other options (including the installation itself).
        if build_option('rpath_override_dirs') is not None:
            # make sure we have a list
            rpath_overrides = build_option('rpath_override_dirs')
            if isinstance(rpath_overrides, str):
                rpath_override_dirs = rpath_overrides.split(':')
                # Filter out any empty values
                rpath_override_dirs = list(filter(None, rpath_override_dirs))
                _log.debug("Converted RPATH override directories ('%s') to a list of paths: %s" % (rpath_overrides,
                                                                                                   rpath_override_dirs))
                for path in rpath_override_dirs:
                    if not os.path.isabs(path):
                        raise EasyBuildError(
                            "Path used in rpath_override_dirs is not an absolute path: %s", path)
            else:
                raise EasyBuildError("Value for rpath_override_dirs has invalid type (%s), should be string: %s",
                                     type(rpath_overrides), rpath_overrides)
            self.rpath_include_dirs.extend(rpath_override_dirs)

        # always include '<installdir>/lib', '<installdir>/lib64', $ORIGIN, $ORIGIN/../lib and $ORIGIN/../lib64
        # $ORIGIN will be resolved by the loader to be the full path to the executable or shared object
        # see also https://linux.die.net/man/8/ld-linux;
        self.rpath_include_dirs.extend([
            os.path.join(self.installdir, 'lib'),
            os.path.join(self.installdir, 'lib64'),
            '$ORIGIN',
            '$ORIGIN/../lib',
            '$ORIGIN/../lib64',
        ])

        # Location to store RPATH wrappers
        if self.rpath_wrappers_dir is not None:
            # Verify the path given is absolute
            if os.path.isabs(self.rpath_wrappers_dir):
                _log.info(f"Using {self.rpath_wrappers_dir} to store/use RPATH wrappers")
            else:
                raise EasyBuildError(f"Path used for rpath_wrappers_dir is not an absolute path: {path}")

        if self.iter_idx > 0:
            # reset toolchain for iterative runs before preparing it again
            self.toolchain.reset()

        # if active module naming scheme involves any top-level directories in the hierarchy (e.g. Core/ in HMNS)
        # make sure they are included in $MODULEPATH such that loading of dependencies (with short module names) works
        # https://github.com/easybuilders/easybuild-framework/issues/2186
        init_modpaths = ActiveMNS().det_init_modulepaths(self.cfg)
        curr_modpaths = curr_module_paths()
        for init_modpath in init_modpaths:
            full_mod_path = os.path.join(self.installdir_mod, init_modpath)
            if os.path.exists(full_mod_path) and full_mod_path not in curr_modpaths:
                self.modules_tool.prepend_module_path(full_mod_path)

        # prepare toolchain: load toolchain module and dependencies, set up build environment
        self.toolchain.prepare(onlymod=self.cfg['onlytcmod'], deps=self.cfg.dependencies(),
                               silent=self.silent, loadmod=load_tc_deps_modules,
                               rpath_filter_dirs=self.rpath_filter_dirs,
                               rpath_include_dirs=self.rpath_include_dirs,
                               rpath_wrappers_dir=self.rpath_wrappers_dir)

        # keep track of environment variables that were tweaked and need to be restored after environment got reset
        # $TMPDIR may be tweaked for OpenMPI 2.x, which doesn't like long $TMPDIR paths...
        self.tweaked_env_vars = {}
        for var in ['TMPDIR']:
            if os.environ.get(var) != self.initial_environ.get(var):
                self.tweaked_env_vars[var] = os.environ.get(var)
                self.log.info("Found tweaked value for $%s: %s (was: %s)",
                              var, self.tweaked_env_vars[var], self.initial_environ[var])

        # handle allowed system dependencies
        for (name, version) in self.cfg['allow_system_deps']:
            # root is set to name, not an actual path
            env.setvar(get_software_root_env_var_name(name), name)
            # version is expected to be something that makes sense
            env.setvar(get_software_version_env_var_name(name), version)

        extra_modules = build_option('extra_modules')
        if extra_modules:
            self.log.info("Loading extra modules: %s", extra_modules)
            self.modules_tool.load(extra_modules)

        # Setup CUDA cache if required. If we don't do this, CUDA will use the $HOME for its cache files
        if get_software_root('CUDA') or get_software_root('CUDAcore'):
            self.set_up_cuda_cache()

        # guess directory to start configure/build/install process in, and move there
        if start_dir:
            self.guess_start_dir()

    def configure_step(self):
        """Configure build  (abstract method)."""
        raise NotImplementedError

    def build_step(self):
        """Build software  (abstract method)."""
        raise NotImplementedError

    def test_step(self):
        """Run unit tests provided by software (if any)."""
        unit_test_cmd = self.cfg['runtest']
        if unit_test_cmd:
            self.log.debug(f"Trying to execute {unit_test_cmd} as a command for running unit tests...")
            res = run_shell_cmd(unit_test_cmd)
            return res.output

    def _test_step(self):
        """Run the test_step and handles failures"""
        try:
            self.test_step()
        except EasyBuildError as err:
            self.report_test_failure(f"An error was raised during test step: {err}")
        except RunShellCmdError as err:
            err.print()
            ec_path = os.path.basename(self.cfg.path)
            error_msg = f"shell command '{err.cmd_name} ...' failed in test step for {ec_path}"
            self.report_test_failure(error_msg)

    def stage_install_step(self):
        """Install in a stage directory before actual installation."""

    def install_step(self):
        """Install built software (abstract method)."""
        raise NotImplementedError

    def init_ext_instances(self):
        """
        Create class instances for all extensions.
        """
        exts_list = self.cfg.get_ref('exts_list')

        # early exit if there are no extensions
        if not exts_list:
            return

        self.ext_instances = []
        exts_classmap = self.cfg['exts_classmap']

        # self.exts may already be populated at this point through collect_exts_file_info;
        # if it's not, we do it lightweight here, by skipping fetching of the files;
        # information on location of source/patch files will be lacking in that case (but that should be fine)
        if exts_list and not self.exts:
            self.exts = self.collect_exts_file_info(fetch_files=False, verify_checksums=False)

        # obtain name and module path for default extention class
        exts_defaultclass = self.cfg['exts_defaultclass']
        if isinstance(exts_defaultclass, str):
            # proper way: derive module path from specified class name
            default_class = exts_defaultclass
            default_class_modpath = get_module_path(default_class, generic=True)
        else:
            error_msg = "Improper default extension class specification, should be string: %s (%s)"
            raise EasyBuildError(error_msg, exts_defaultclass, type(exts_defaultclass))

        exts_cnt = len(self.exts)

        self.update_exts_progress_bar("creating internal datastructures for extensions")
        for idx, ext in enumerate(self.exts):
            ext_name = ext['name']
            self.log.debug("Creating class instance for extension %s...", ext_name)

            # if a specific easyblock is specified for this extension, honor it;
            # just passing this to get_easyblock_class is sufficient
            easyblock = ext.get('easyblock', None)
            if easyblock:
                class_name = easyblock
                mod_path = get_module_path(class_name)
            else:
                class_name = encode_class_name(ext_name)
                mod_path = get_module_path(class_name, generic=False)

            cls, inst = None, None

            # try instantiating extension-specific class, or honor specified easyblock
            try:
                # no error when importing class fails, in case we run into an existing easyblock
                # with a similar name (e.g., Perl Extension 'GO' vs 'Go' for which 'EB_Go' is available)
                cls = get_easyblock_class(easyblock, name=ext_name, error_on_failed_import=False,
                                          error_on_missing_easyblock=False)

                self.log.debug("Obtained class %s for extension %s", cls, ext_name)
                if cls is not None:
                    # make sure that this easyblock can be used to install extensions
                    if not issubclass(cls, Extension):
                        raise EasyBuildError("%s easyblock can not be used to install extensions!", cls.__name__)

                    inst = cls(self, ext)
            except (ImportError, NameError) as err:
                self.log.debug("Failed to use extension-specific class for extension %s: %s", ext_name, err)

            # alternative attempt: use class specified in class map (if any)
            if inst is None and ext_name in exts_classmap:
                class_name = exts_classmap[ext_name]
                mod_path = get_module_path(class_name)
                try:
                    cls = get_class_for(mod_path, class_name)
                    self.log.debug("Obtained class %s for extension %s from exts_classmap", cls, ext_name)
                    inst = cls(self, ext)
                except Exception as err:
                    raise EasyBuildError("Failed to load specified class %s (from %s) specified via exts_classmap "
                                         "for extension %s: %s",
                                         class_name, mod_path, ext_name, err)

            # fallback attempt: use default class
            if inst is None:
                try:
                    cls = get_class_for(default_class_modpath, default_class)
                    self.log.debug("Obtained class %s for installing extension %s", cls, ext_name)
                    inst = cls(self, ext)
                    self.log.debug("Installing extension %s with default class %s (from %s)",
                                   ext_name, default_class, default_class_modpath)
                except (ImportError, NameError) as err:
                    raise EasyBuildError("Also failed to use default class %s from %s for extension %s: %s, giving up",
                                         default_class, default_class_modpath, ext_name, err)
            else:
                self.log.debug("Installing extension %s with class %s (from %s)", ext_name, class_name, mod_path)

            self.ext_instances.append(inst)
            pbar_label = "creating internal datastructures for extensions "
            pbar_label += "(%d/%d done)" % (idx + 1, exts_cnt)
            self.update_exts_progress_bar(pbar_label)

    def update_exts_progress_bar(self, info, progress_size=0, total=None):
        """
        Update extensions progress bar with specified info and amount of progress made
        """
        update_progress_bar(PROGRESS_BAR_EXTENSIONS, label=info, progress_size=progress_size, total=total)

    def extensions_step(self, fetch=False, install=True):
        """
        After make install, run this.
        - only if variable len(exts_list) > 0
        - optionally: load module that was just created using temp module file
        - find source for extensions, in 'extensions' (and 'packages' for legacy reasons)
        - run extra_extensions
        """
        if not self.cfg.get_ref('exts_list'):
            self.log.debug("No extensions in exts_list")
            return

        start_progress_bar(PROGRESS_BAR_EXTENSIONS, len(self.cfg.get_ref('exts_list')))

        self.prepare_for_extensions()

        # we really need a default class
        if not self.cfg['exts_defaultclass'] and install:
            raise EasyBuildError("ERROR: No default extension class set for %s", self.name)

        if fetch:
            self.update_exts_progress_bar("fetching extension sources/patches")
            self.exts = self.collect_exts_file_info(fetch_files=True)

        self.exts_all = self.exts[:]  # retain a copy of all extensions, regardless of filtering/skipping

        # actually install extensions
        if install:
            self.log.info("Installing extensions")

        self.init_ext_instances()

        if self.skip:
            self.skip_extensions()

        self.install_all_extensions(install=install)

        stop_progress_bar(PROGRESS_BAR_EXTENSIONS, visible=False)

    def package_step(self):
        """Package installed software (e.g., into an RPM), if requested, using selected package tool."""

        if build_option('package'):

            pkgtype = build_option('package_type')
            pkgdir_dest = os.path.abspath(package_path())
            opt_force = build_option('force') or build_option('rebuild')

            self.log.info("Generating %s package in %s", pkgtype, pkgdir_dest)
            pkgdir_src = package(self)

            mkdir(pkgdir_dest)

            for src_file in glob.glob(os.path.join(pkgdir_src, "*.%s" % pkgtype)):
                dest_file = os.path.join(pkgdir_dest, os.path.basename(src_file))
                if os.path.exists(dest_file) and not opt_force:
                    raise EasyBuildError("Unable to copy package %s to %s (already exists).", src_file, dest_file)
                else:
                    copy_file(src_file, pkgdir_dest)
                    self.log.info("Copied package %s to %s", src_file, pkgdir_dest)

        else:
            self.log.info("Skipping package step (not enabled)")

    def fix_shebang(self):
        """Fix shebang lines for specified files."""

        env_for_shebang = build_option('env_for_shebang')
        sysroot = build_option('sysroot')
        if sysroot and not env_for_shebang.startswith(sysroot):
            env_for_shebang = os.path.join(sysroot, env_for_shebang.lstrip('/'))
        if os.path.exists(env_for_shebang.split(' ')[0]):
            self.log.info("Path to 'env' command to use in patched shebang lines: %s", env_for_shebang)
        else:
            raise EasyBuildError("Path to 'env' command to use in shebang lines does not exist: %s", env_for_shebang)

        for lang in ['bash', 'perl', 'python']:
            shebang_regex = re.compile(r'^#![ ]*.*[/ ]%s.*' % lang)
            fix_shebang_for = self.cfg['fix_%s_shebang_for' % lang]
            if fix_shebang_for:
                if isinstance(fix_shebang_for, str):
                    fix_shebang_for = [fix_shebang_for]

                shebang = '#!%s %s' % (env_for_shebang, lang)
                for glob_pattern in fix_shebang_for:
                    paths = glob.glob(os.path.join(self.installdir, glob_pattern))
                    self.log.info("Fixing '%s' shebang to '%s' for files that match '%s': %s",
                                  lang, shebang, glob_pattern, paths)
                    for path in paths:
                        # check whether file should be patched by checking whether it has a shebang we want to tweak;
                        # this also helps to skip binary files we may be hitting (but only with Python 3)
                        if os.path.isdir(path):
                            self.log.debug("Skipping shebang fix for directory '%s'", path)
                            continue

                        try:
                            contents = read_file(path, mode='r')
                            should_patch = shebang_regex.match(contents)
                        except (TypeError, UnicodeDecodeError):
                            should_patch = False
                            contents = None

                        # if an existing shebang is found, patch it
                        if should_patch:
                            contents = shebang_regex.sub(shebang, contents)
                            write_file(path, contents)

                        # if no shebang is present at all, add one (but only for non-binary files!)
                        elif contents is not None and not is_binary(contents) and not contents.startswith('#!'):
                            self.log.info("The file '%s' doesn't have any shebang present, inserting it as first line.",
                                          path)
                            contents = shebang + '\n' + contents
                            write_file(path, contents)

    def run_post_install_commands(self, commands=None):
        """
        Run post install commands that are specified via 'postinstallcmds' easyconfig parameter.
        """
        if commands is None:
            commands = self.cfg['postinstallcmds']

        if commands:
            self.log.debug(f"Specified post install commands: {commands}")

            # make sure we have a list of commands
            if not isinstance(commands, (list, tuple)):
                error_msg = f"Invalid value for 'postinstallcmds', should be list or tuple of strings: {commands}"
                raise EasyBuildError(error_msg)

            for cmd in commands:
                if not isinstance(cmd, str):
                    raise EasyBuildError(f"Invalid element in 'postinstallcmds', not a string: {cmd}")
                run_shell_cmd(cmd)

    def apply_post_install_patches(self, patches=None):
        """
        Apply post-install patch files that are specified via the 'postinstallpatches' easyconfig parameter.
        """
        if patches is None:
            patches = [p for p in self.patches if p['postinstall']]

        self.log.debug("Post-install patches to apply: %s", patches)
        if patches:
            # self may be inherited from the Bundle easyblock and that patch_step is a no-op
            # To allow postinstallpatches for Bundle, and derived, easyblocks we directly call EasyBlock.patch_step
            EasyBlock.patch_step(self, beginpath=self.installdir, patches=patches)

    def print_post_install_messages(self):
        """
        Print post-install messages that are specified via the 'postinstallmsgs' easyconfig parameter.
        """
        msgs = self.cfg['postinstallmsgs'] or []
        for msg in msgs:
            print_msg(msg, log=self.log)

    def post_install_step(self):
        """
        [DEPRECATED] Do some postprocessing
        - run post install commands if any were specified
        """
        # even though post_install_step is deprecated in easyblocks we need to keep this here until it is
        # removed in 6.0 for easyblocks calling super().post_install_step()
        # The deprecation warning for those is below, in post_processing_step().

        lib_dir = os.path.join(self.installdir, 'lib')
        lib64_dir = os.path.join(self.installdir, 'lib64')

        # GCC linker searches system /lib64 path before the $LIBRARY_PATH paths.
        # However for each <dir> in $LIBRARY_PATH (where <dir> is often <prefix>/lib) it searches <dir>/../lib64 first.
        # So we create <prefix>/lib64 as a symlink to <prefix>/lib to make it prefer EB installed libraries.
        # See https://github.com/easybuilders/easybuild-easyconfigs/issues/5776
        if build_option('lib64_lib_symlink') and os.path.exists(lib_dir) and not os.path.exists(lib64_dir):
            # create *relative* 'lib64' symlink to 'lib';
            # see https://github.com/easybuilders/easybuild-framework/issues/3564
            symlink('lib', lib64_dir, use_abspath_source=False)

        # symlink lib to lib64, which is helpful on OpenSUSE;
        # see https://github.com/easybuilders/easybuild-framework/issues/3549
        if build_option('lib_lib64_symlink') and os.path.exists(lib64_dir) and not os.path.exists(lib_dir):
            # create *relative* 'lib' symlink to 'lib64';
            symlink('lib64', lib_dir, use_abspath_source=False)

        self.run_post_install_commands()
        self.apply_post_install_patches()
        self.print_post_install_messages()

        self.fix_shebang()

    def post_processing_step(self):
        """
        Do some postprocessing
        - run post install commands if any were specified
        """
        # if post_install_step() is present in the easyblock print a deprecation warning
        # with EB 6.0, post_install_step() can be renamed to post_processing_step, and this method deleted.

        if self.post_install_step.__qualname__ != "EasyBlock.post_install_step":
            self.log.deprecated(
                "EasyBlock.post_install_step() is deprecated, use EasyBlock.post_processing_step() instead.",
                '6.0',
            )
        return self.post_install_step()

    def _dispatch_sanity_check_step(self, *args, **kwargs):
        """Decide whether to run the dry-run or the real version of the sanity-check step"""
        if self.dry_run:
            self._sanity_check_step_dry_run(*args, **kwargs)
        else:
            self._sanity_check_step(*args, **kwargs)

    def sanity_check_step(self, *args, **kwargs):
        """
        Do a sanity check on the installation
        - if *any* of the files/subdirectories in the installation directory listed
          in sanity_check_paths are non-existent (or empty), the sanity check fails
        """
        # handling of extensions that were installed for multiple dependency versions is done in ExtensionEasyBlock
        if self.cfg['multi_deps'] and not self.is_extension:
            self._sanity_check_step_multi_deps(*args, **kwargs)
        else:
            self._dispatch_sanity_check_step(*args, **kwargs)

    def _sanity_check_step_multi_deps(self, *args, **kwargs):
        """Perform sanity check for installations that iterate over a list a versions for particular dependencies."""

        # take into account provided list of extra modules (if any)
        common_extra_modules = kwargs.get('extra_modules') or []

        # if multi_deps was used to do an iterative installation over multiple sets of dependencies,
        # we need to perform the sanity check for each one of these;
        # this implies iterating over the list of lists of build dependencies again...

        # get list of (lists of) builddependencies, without templating values
        builddeps = self.cfg.get_ref('builddependencies')

        # start iterating again;
        # required to ensure build dependencies are taken into account to resolve templates like %(pyver)s
        self.cfg.iterating = True

        for iter_deps in self.cfg.multi_deps:

            # need to re-generate template values to get correct values for %(pyver)s and %(pyshortver)s
            self.cfg['builddependencies'] = iter_deps
            self.cfg.generate_template_values()

            extra_modules = common_extra_modules + [d['short_mod_name'] for d in iter_deps]

            info_msg = "Running sanity check with extra modules: %s" % ', '.join(extra_modules)
            trace_msg(info_msg)
            self.log.info(info_msg)

            kwargs['extra_modules'] = extra_modules
            self._dispatch_sanity_check_step(*args, **kwargs)

        # restore list of lists of build dependencies & stop iterating again
        self.cfg['builddependencies'] = builddeps
        self.cfg.iterating = False

    def sanity_check_cuda(self, cuda_dirs=None):
        """Sanity check that binaries/libraries contain device code for the correct architecture targets."""

        self.log.info("Checking binaries/libraries for CUDA device code...")

        fail_msgs = []
        cfg_ccs = build_option('cuda_compute_capabilities') or self.cfg.get('cuda_compute_capabilities', None)
        ignore_failures = not build_option('cuda_sanity_check_error_on_failed_checks')
        strict_cc_check = build_option('cuda_sanity_check_strict')
        accept_ptx_as_devcode = build_option('cuda_sanity_check_accept_ptx_as_devcode')
        accept_missing_ptx = build_option('cuda_sanity_check_accept_missing_ptx')

        # Construct the list of files to ignore as full paths (cuda_sanity_ignore_files contains the paths
        # to ignore, relative to the installation prefix)
        ignore_file_list = [os.path.join(self.installdir, d) for d in self.cfg['cuda_sanity_ignore_files']]

        # If there are no CUDA compute capabilities defined, return
        if cfg_ccs is None or len(cfg_ccs) == 0:
            self.log.info("Skipping CUDA sanity check, as no CUDA compute capabilities were configured")
            return fail_msgs

        if cuda_dirs is None:
            cuda_dirs = self.cfg['bin_lib_subdirs'] or self.bin_lib_subdirs()

        if not cuda_dirs:
            cuda_dirs = DEFAULT_BIN_LIB_SUBDIRS
            self.log.info("Using default subdirectories for binaries/libraries to verify CUDA device code: %s",
                          cuda_dirs)
        else:
            self.log.info("Using configured subdirectories for binaries/libraries to verify CUDA device code: %s",
                          cuda_dirs)

        # collect all files to consider
        files_to_check = []
        for dirpath in [os.path.join(self.installdir, d) for d in cuda_dirs]:
            if os.path.exists(dirpath):
                self.log.debug(f"Sanity checking files for CUDA device code under directory {dirpath}:")
                for entry in os.listdir(dirpath):
                    path = os.path.join(dirpath, entry)
                    if os.path.isfile(path):
                        self.log.debug("Sanity checking file {path} for CUDA device code")
                        files_to_check.append(path)
            else:
                self.log.debug(f"Not sanity checking files in non-existing directory {dirpath}")

        # also consider compiled Python modules as shared libraries (*.so) under lib/python*/site-packages
        python_pkgs_path = os.path.join(self.installdir, 'lib', 'python*', 'site-packages')
        shlib_ext = get_shared_lib_ext()
        python_shared_libs = glob.glob(os.path.join(python_pkgs_path, '**', '*.' + shlib_ext), recursive=True)
        if python_shared_libs:
            self.log.debug("Sanity check shared libraries found in {python_pkgs_path}: {python_shared_libs}")
            files_to_check.extend(python_shared_libs)

        # Tracking number of CUDA files for a summary report:
        num_cuda_files = 0

        # Creating lists of files for summary report:
        files_missing_devcode = []
        files_missing_devcode_fails = []
        files_missing_devcode_ignored = []
        files_additional_devcode = []
        files_additional_devcode_fails = []
        files_additional_devcode_ignored = []
        files_missing_ptx = []
        files_missing_ptx_fails = []
        files_missing_ptx_ignored = []
        files_missing_devcode_but_has_ptx = []

        # A local function to create nicely formatted file lists for the files_* lists
        def format_file_list(files_list):
            return "\n" + "\n".join(f"  {f}" for f in files_list)

        # Looping through all files to check CUDA device and PTX code
        for path in files_to_check:
            self.log.debug(f"Sanity checking for CUDA device code in {path}")

            found_dev_code_ccs = get_cuda_architectures(path, 'elf')
            found_ptx_ccs = get_cuda_architectures(path, 'ptx')
            if found_dev_code_ccs is None and found_ptx_ccs is None:
                msg = f"{path} does not appear to be a CUDA executable (no CUDA device code found), "
                msg += "so skipping CUDA sanity check."
                self.log.debug(msg)
            else:
                # Here, we check if CUDA device code is present for all compute capabilities in
                # --cuda-compute-capabilities for the file pointed to by 'path'
                # We also check for the presence of ptx code for the highest CUDA compute capability
                # The following is considered fail/warning/success:
                # - Missing device code is considered a failure (unless there is PTX code for
                #   a lower CC AND --accept-ptx-for-cc-support is True, in which case it is a warning)
                # - Device code for additional compute capabilities is considered a failure if
                #   --cuda-sanity-check-strict is True (otherwise, it's a warning)
                # - Missing PTX code for the highest CUDA compute capability in --cuda-compute-capabilities
                #   is considered a failure, unless --cuda-sanity-check-accept-missing-ptx is True (in which
                #   case it is a warning)

                # If found_dev_code_ccs is None, but found_ptx_ccs isn't, or vice versa, it IS a CUDA file
                # but there was simply no device/ptx code, respectively. So, make that an empty list
                # then continue
                if found_dev_code_ccs is None:
                    found_dev_code_ccs = []
                elif found_ptx_ccs is None:
                    found_ptx_ccs = []

                num_cuda_files += 1

                # check whether device code architectures match cuda_compute_capabilities
                additional_devcodes = list(set(found_dev_code_ccs) - set(cfg_ccs))
                missing_devcodes = list(set(cfg_ccs) - set(found_dev_code_ccs))

                # There are two reasons for ignoring failures:
                # - We are running with --disable-cuda-sanity-check-error-on-failed-checks
                # - The specific {path} is on the cuda_sanity_ignore_files in the easyconfig
                # In case we run with both, we'll just report that we're running with
                # --disable-cuda-sanity-check-error-on-failed-checks
                if ignore_failures:
                    ignore_msg = f"Failure for {path} will be ignored since we are not running with "
                    ignore_msg += "--cuda-sanity-check-error-on-failed-checks"
                else:
                    ignore_msg = f"This failure will be ignored as '{path}' is listed in "
                    ignore_msg += "'cuda_sanity_ignore_files'."

                if not missing_devcodes and not additional_devcodes:
                    # Device code for all architectures requested in --cuda-compute-capabilities was found
                    msg = (f"Output of 'cuobjdump' checked for '{path}'; device code architectures match "
                           "those in cuda_compute_capabilities")
                    self.log.debug(msg)
                else:
                    if additional_devcodes:
                        # Device code found for more architectures than requested in cuda-compute-capabilities
                        fail_msg = f"Mismatch between cuda_compute_capabilities and device code in {path}. "
                        # Count and log for summary report
                        files_additional_devcode.append(os.path.relpath(path, self.installdir))
                        additional_devcode_str = ', '.join(sorted(additional_devcodes, key=LooseVersion))
                        fail_msg += "Additional compute capabilities: %s. " % additional_devcode_str
                        if strict_cc_check:
                            # cuda-sanity-check-strict, so no additional compute capabilities allowed
                            if path in ignore_file_list or ignore_failures:
                                # No error, because either path is on the cuda_sanity_ignore_files list in the
                                # easyconfig, or we are running with --disable-cuda-sanity-check-error-on-failed-checks
                                files_additional_devcode_ignored.append(os.path.relpath(path, self.installdir))
                                fail_msg += ignore_msg
                            else:
                                # Sanity error
                                files_additional_devcode_fails.append(os.path.relpath(path, self.installdir))
                        # Do reporting for the additional_devcodes case
                        self.log.warning(fail_msg)

                    # Both additional_devcodes and missing_devcodes could exist, so use if, not elif
                    if missing_devcodes:
                        # One or more device code architectures requested in cuda-compute-capabilities was
                        # not found in the binary
                        fail_msg = f"Mismatch between cuda_compute_capabilities and device code in {path}. "
                        # Count and log for summary report
                        missing_devcodes_str = ', '.join(sorted(missing_devcodes, key=LooseVersion))
                        fail_msg += "Missing compute capabilities: %s. " % missing_devcodes_str
                        # If accept_ptx_as_devcode, this might not be a failure IF there is suitable PTX
                        # code to JIT compile from that supports the CCs in missing_devcodes
                        if accept_ptx_as_devcode:
                            # Check that for each item in missing_devcodes there is PTX code for lower or equal
                            # CUDA compute capability
                            comparisons = []
                            for cc in missing_devcodes:
                                has_smaller_equal_ptx = any(
                                    LooseVersion(ptx_cc) <= LooseVersion(cc) for ptx_cc in found_ptx_ccs
                                )
                                comparisons.append(has_smaller_equal_ptx)
                            # Only if that's the case for ALL cc's in missing_devcodes, this is a warning, not a
                            # failure
                            if all(comparisons):
                                files_missing_devcode_but_has_ptx.append(os.path.relpath(path, self.installdir))
                            else:
                                # If there are CCs for which there is no suiteable PTX that can be JIT-compiled
                                # from, this is considered a failure
                                files_missing_devcode.append(os.path.relpath(path, self.installdir))
                                if path in ignore_file_list or ignore_failures:
                                    # No error, because either path is on the cuda_sanity_ignore_files list in
                                    # the easyconfig, or we are running with
                                    # --disable-cuda-sanity-check-error-on-failed-checks
                                    files_missing_devcode_ignored.append(os.path.relpath(path, self.installdir))
                                    fail_msg += ignore_msg
                                else:
                                    # Sanity error
                                    files_missing_devcode_fails.append(os.path.relpath(path, self.installdir))
                        else:
                            # Device code was missing, and we're not accepting PTX code as alternative
                            # This is considered a failure
                            files_missing_devcode.append(os.path.relpath(path, self.installdir))
                            if path in ignore_file_list or ignore_failures:
                                # No error, because either path is on the cuda_sanity_ignore_files list in the
                                # easyconfig, or we are running with --disable-cuda-sanity-check-error-on-failed-checks
                                files_missing_devcode_ignored.append(os.path.relpath(path, self.installdir))
                                fail_msg += ignore_msg
                            else:
                                # Sanity error
                                files_missing_devcode_fails.append(os.path.relpath(path, self.installdir))
                        # Do reporting for the missing_devcodes case
                        self.log.warning(fail_msg)

                # Check whether there is ptx code for the highest CC in cfg_ccs
                # Make sure to use LooseVersion so that e.g. 9.0 < 9.0a < 9.2 < 9.10
                highest_cc = [sorted(cfg_ccs, key=LooseVersion)[-1]]
                missing_ptx_ccs = list(set(highest_cc) - set(found_ptx_ccs))

                if missing_ptx_ccs:
                    # There is no PTX code for the highest compute capability in --cuda-compute-capabilities
                    files_missing_ptx.append(os.path.relpath(path, self.installdir))
                    fail_msg = "Configured highest compute capability was '%s', "
                    fail_msg += "but no PTX code for this compute capability was found in '%s' "
                    fail_msg += "(PTX architectures supported in that file: %s). "
                    if path in ignore_file_list or ignore_failures:
                        # No error, because either path is on the cuda_sanity_ignore_files list in the
                        # easyconfig, or we are running with --disable-cuda-sanity-check-error-on-failed-checks
                        files_missing_ptx_ignored.append(os.path.relpath(path, self.installdir))
                        fail_msg += ignore_msg
                        self.log.warning(fail_msg, highest_cc[0], path, found_ptx_ccs)
                    elif accept_missing_ptx:
                        # No error, because we are running with --cuda-sanity-check-accept-missing-ptx
                        self.log.warning(fail_msg, highest_cc[0], path, found_ptx_ccs)
                    else:
                        # Sanity error
                        files_missing_ptx_fails.append(os.path.relpath(path, self.installdir))
                        self.log.warning(fail_msg % (highest_cc[0], path, found_ptx_ccs))
                else:
                    msg = (f"Output of 'cuobjdump' checked for '{path}'; ptx code was present for (at "
                           "least) the highest CUDA compute capability in cuda_compute_capabilities")
                    self.log.debug(msg)

        # Send to trace and log
        def trace_and_log(msg):
            self.log.info(msg)
            trace_msg(msg)

        # Short summary
        trace_and_log("CUDA sanity check summary report:")
        trace_and_log(f"Number of CUDA files checked: {num_cuda_files}")
        if len(files_missing_devcode) == 0:
            trace_and_log("Number of files missing one or more CUDA Compute Capabilities: 0")
        elif ignore_failures:
            msg = f"Number of files missing one or more CUDA Compute Capabilities: {len(files_missing_devcode)}"
            trace_and_log(msg)
            trace_and_log("(not running with --cuda-sanity-check-error-on-failed-checks, so not considered failures)")
        else:
            msg = f"Number of files missing one or more CUDA Compute Capabilities: {len(files_missing_devcode)}"
            msg += f" (ignored: {len(files_missing_devcode_ignored)}, "
            msg += f"fails: {len(files_missing_devcode_fails)})"
            trace_and_log(msg)
        if accept_ptx_as_devcode:
            msg = "Number of files missing one or more CUDA Compute Capabilities, but having suitable "
            msg += "PTX code that can be JIT compiled for the requested CUDA Compute Capabilities: "
            msg += f"{len(files_missing_devcode_but_has_ptx)}"
            trace_and_log(msg)
        if len(files_additional_devcode) == 0:
            trace_and_log("Number of files with device code for more CUDA Compute Capabilities than requested: 0")
        elif ignore_failures:
            msg = "Number of files with device code for more CUDA Compute Capabilities than requested: "
            msg += f"{len(files_additional_devcode)}"
            trace_and_log(msg)
            trace_and_log("(not running with --cuda-sanity-check-error-on-failed-checks, so not considered failures)")
        elif strict_cc_check:
            msg = "Number of files with device code for more CUDA Compute Capabilities than requested: "
            msg += f"{len(files_additional_devcode)} (ignored: {len(files_additional_devcode_ignored)}, "
            msg += f"fails: {len(files_additional_devcode_fails)})"
            trace_and_log(msg)
        else:
            msg = "Number of files with device code for more CUDA Compute Capabilities than requested: "
            msg += f"{len(files_additional_devcode)}"
            trace_and_log(msg)
            trace_and_log("(not running with --cuda-sanity-check-strict, so not considered failures)")
        if len(files_missing_ptx) == 0:
            trace_and_log("Number of files missing PTX code for the highest configured CUDA Compute Capability: 0")
        elif ignore_failures:
            msg = "Number of files missing PTX code for the highest configured CUDA Compute Capability: "
            msg += f"{len(files_missing_ptx)}"
            trace_and_log(msg)
            trace_and_log("(not running with --cuda-sanity-check-error-on-failed-checks, so not considered failures)")
        elif accept_missing_ptx:
            msg = "Number of files missing PTX code for the highest configured CUDA Compute Capability: "
            msg += f"{len(files_missing_ptx)}"
            trace_and_log(msg)
            trace_and_log("(running with --cuda-sanity-check-accept-missing-ptx, so not considered failures)")
        else:
            msg = "Number of files missing PTX code for the highest configured CUDA Compute Capability: "
            msg += f"{len(files_missing_ptx)} (ignored: {len(files_missing_ptx_ignored)}, fails: "
            msg += f"{len(files_missing_ptx_fails)})"
            trace_and_log(msg)
        # Give some advice
        if len(files_missing_devcode) > 0 and not accept_ptx_as_devcode:
            short_msg = "You may consider rerunning with --cuda-sanity-check-accept-ptx-as-devcode to accept "
            short_msg += "suitable PTX code instead of device code."
            trace_msg(short_msg)
            msg = "You may consider rerunning with --cuda-sanity-check-accept-ptx-as-devcode to accept "
            msg += "binaries that don't contain the device code for your requested CUDA Compute Capabilities, "
            msg += "but that do have PTX code that can be compiled for your requested CUDA Compute "
            msg += "Capabilities. Note that this may increase startup delay due to JIT compilation "
            msg += "and may also lead to suboptimal runtime performance, as the PTX code may not exploit "
            msg += "all features specific to your hardware architecture."
            self.log.info(msg)
        if len(files_additional_devcode) > 0 and strict_cc_check:
            short_msg = "You may consider running with --disable-cuda-sanity-check-strict to accept binaries "
            short_msg += "containing device code for more architectures than requested."
            trace_msg(short_msg)
            msg = "You may consider running with --disable-cuda-sanity-check-strict. This means you'll "
            msg += "accept that some binaries may have CUDA Device Code for more architectures than you "
            msg += "requested, i.e. the binary is 'fatter' than you need. Bigger binaries may generally "
            msg += "cause some startup delay, and code path selection could introduce a small overhead, "
            msg += "though this is generally negligible."
            self.log.info(msg)
        if len(files_missing_ptx) > 0 and not accept_missing_ptx:
            short_msg = "You may consider running with --cuda-sanity-check-accept-missing-ptx to accept binaries "
            short_msg += "missing PTX code for the highest configured CUDA Compute Capability."
            trace_msg(short_msg)
            msg = "You may consider running with --cuda-sanity-check-accept-missing-ptx to accept binaries "
            msg += "that don't contain PTX code for the highest CUDA Compute Capability you requested. This "
            msg += "breaks forwards compatibility for newer CUDA Compute Capabilities (i.e. your compiled "
            msg += "binaries will not run on cards with higher CUDA Compute Capabilities than what "
            msg += "you requested in --cuda-compute-capabilities), but that may be acceptable to you."
            self.log.info(msg)
        if (
            len(files_missing_devcode) > 0 or len(files_additional_devcode) > 0 or len(files_missing_ptx) > 0
        ):
            trace_and_log("See build log for detailed lists of files not passing the CUDA Sanity Check")

        # Long report, which prints the files that have potential issues
        summary_msg_files = ""
        if len(files_missing_devcode) > 0:
            summary_msg_files += f"{len(files_missing_devcode)} files missing one or more CUDA compute capabilities:"
            summary_msg_files += f"{format_file_list(files_missing_devcode)}\n"
        if len(files_missing_devcode_ignored) > 0:
            summary_msg_files += f"These failures are ignored for {len(files_missing_devcode_ignored)} files:"
            summary_msg_files += f"{format_file_list(files_missing_devcode_ignored)}\n"
        if accept_ptx_as_devcode:
            summary_msg_files += f"{len(files_missing_devcode_but_has_ptx)} files missing one or more CUDA Compute "
            summary_msg_files += "Capabilities, but has suitable PTX code that can be JIT compiled for the requested "
            summary_msg_files += f"CUDA Compute Capabilities:{format_file_list(files_missing_devcode_but_has_ptx)}\n"
        if len(files_additional_devcode) > 0:
            summary_msg_files += f"{len(files_additional_devcode)} files with device code for more CUDA Compute "
            summary_msg_files += f"Capabilities than requested:{format_file_list(files_additional_devcode)}\n"
        if len(files_additional_devcode_ignored) > 0:
            summary_msg_files += f"These failures are ignored for {len(files_additional_devcode_ignored)} files:"
            summary_msg_files += f"{format_file_list(files_additional_devcode_ignored)}\n"
        if len(files_missing_ptx) > 0:
            summary_msg_files += f"{len(files_missing_ptx)} files missing PTX code for the highest configured CUDA"
            summary_msg_files += f" Compute Capability:{format_file_list(files_missing_ptx)}\n"
        if len(files_missing_ptx_ignored) > 0:
            summary_msg_files += f"These failures are ignored for {len(files_missing_ptx_ignored)} files:"
            summary_msg_files += f"{format_file_list(files_missing_ptx_ignored)}"
        if summary_msg_files:
            msg = "CUDA sanity check detailed report:\n"
            msg += summary_msg_files
            self.log.info(msg)

        # If any failure happened, compose a message to be raised as error
        if (
            len(files_missing_devcode_fails) > 0 or
            len(files_additional_devcode_fails) > 0 or
            len(files_missing_ptx_fails) > 0
        ):
            fail_msgs = ['']
            if len(files_missing_devcode_fails) > 0:
                fail_msgs.append(f"Files missing CUDA device code: {len(files_missing_devcode_fails)}.")
            if len(files_additional_devcode_fails) > 0:
                fail_msgs.append(f"Files with additional CUDA device code: {len(files_additional_devcode_fails)}.")
            if len(files_missing_ptx_fails) > 0:
                fail_msgs.append(f"Files missing CUDA PTX code: {len(files_missing_ptx_fails)}.")
            msg = "Check the build log for the 'CUDA sanity check detailed report' for a full list of files that "
            msg += "failed to pass the sanity check."
            fail_msgs.append(msg)

        return fail_msgs

    def sanity_check_rpath(self, rpath_dirs=None, check_readelf_rpath=None):
        """Sanity check binaries/libraries w.r.t. RPATH linking."""

        self.log.info("Checking RPATH linkage for binaries/libraries...")

        fails = []

        if check_readelf_rpath is None:
            # Configure RPATH checking by readelf using easyconfig variable 'check_readelf_rpath' (default True)
            check_readelf_rpath = self.cfg["check_readelf_rpath"]

        if check_readelf_rpath:
            self.log.info("Checks on RPATH section of binaries/libraries (via 'readelf -d') enabled")
        else:
            self.log.info("Checks on RPATH section of binaries/libraries (via 'readelf -d') disabled")

        if build_option('strict_rpath_sanity_check'):
            self.log.info("Unsetting $LD_LIBRARY_PATH since strict RPATH sanity check is enabled...")
            # hard reset $LD_LIBRARY_PATH before running RPATH sanity check
            orig_env = env.unset_env_vars(['LD_LIBRARY_PATH'])
        else:
            self.log.info("Not unsetting $LD_LIBRARY_PATH since strict RPATH sanity check is disabled...")
            orig_env = None

        ld_library_path = os.getenv('LD_LIBRARY_PATH', '(empty)')
        self.log.debug(f"$LD_LIBRARY_PATH during RPATH sanity check: {ld_library_path}")
        modules_list = self.modules_tool.list()
        self.log.debug(f"List of loaded modules: {modules_list}")

        not_found_regex = re.compile(r'(\S+)\s*\=\>\s*not found')
        lib_path_regex = re.compile(r'\S+\s*\=\>\s*(\S+)')
        readelf_rpath_regex = re.compile(r'\(RPATH\)', re.M)

        # List of libraries that should be exempt from the RPATH sanity check;
        # For example, libcuda.so.1 should never be RPATH-ed by design,
        # see https://github.com/easybuilders/easybuild-framework/issues/4095
        filter_rpath_sanity_libs = build_option('filter_rpath_sanity_libs')
        self.log.info("Ignoring the following libraries if they are not found by RPATH sanity check: %s",
                      filter_rpath_sanity_libs)

        if rpath_dirs is None:
            rpath_dirs = self.cfg['bin_lib_subdirs'] or self.bin_lib_subdirs()

        if not rpath_dirs:
            rpath_dirs = DEFAULT_BIN_LIB_SUBDIRS
            self.log.info(f"Using default subdirs for binaries/libraries to verify RPATH linking: {rpath_dirs}")
        else:
            self.log.info(f"Using specified subdirs for binaries/libraries to verify RPATH linking: {rpath_dirs}")

        for dirpath in [os.path.join(self.installdir, d) for d in rpath_dirs]:
            if os.path.exists(dirpath):
                self.log.debug(f"Sanity checking RPATH for files in {dirpath}")

                for path in [os.path.join(dirpath, x) for x in os.listdir(dirpath)]:
                    # skip the check for any symlinks that resolve to outside the installation directory
                    if not is_parent_path(self.installdir, path):
                        realpath = os.path.realpath(path)
                        msg = (f"Skipping RPATH sanity check for {path}, since its absolute path {realpath} resolves to"
                               f" outside the installation directory {self.installdir}")
                        self.log.info(msg)
                        continue

                    self.log.debug(f"Sanity checking RPATH for {path}")

                    out = get_linked_libs_raw(path)

                    if out is None:
                        msg = "Failed to determine dynamically linked libraries for {path}, "
                        msg += "so skipping it in RPATH sanity check"
                        self.log.debug(msg)
                    else:
                        # check whether all required libraries are found via 'ldd'
                        matches = re.findall(not_found_regex, out)
                        if len(matches) > 0:  # Some libraries are not found via 'ldd'
                            # For each match, check if the library is in the exception list
                            for match in matches:
                                if match in filter_rpath_sanity_libs:
                                    msg = f"Library {match} not found for {path}, but ignored "
                                    msg += f"since it is on the rpath exception list: {filter_rpath_sanity_libs}"
                                    self.log.info(msg)
                                else:
                                    fail_msg = f"Library {match} not found for {path}"
                                    self.log.warning(fail_msg)
                                    fails.append(fail_msg)

                            # if any libraries were not found, log whether dependency libraries have an RPATH section
                            if fails:
                                lib_paths = re.findall(lib_path_regex, out)
                                for lib_path in lib_paths:
                                    self.log.info(f"Checking whether dependency library {lib_path} has RPATH section")
                                    res = run_shell_cmd(f"readelf -d {lib_path}", fail_on_error=False)
                                    if res.exit_code:
                                        self.log.info(f"No RPATH section found in {lib_path}")
                        else:
                            self.log.debug(f"Output of 'ldd {path}' checked, looks OK")

                        # check whether RPATH section in 'readelf -d' output is there
                        if check_readelf_rpath:
                            fail_msg = None
                            res = run_shell_cmd(f"readelf -d {path}", fail_on_error=False, hidden=True)
                            if res.exit_code != EasyBuildExit.SUCCESS:
                                fail_msg = f"Failed to run 'readelf -d {path}': {res.output}"
                            elif not readelf_rpath_regex.search(res.output):
                                fail_msg = f"No '(RPATH)' found in 'readelf -d' output for {path}"

                            if fail_msg:
                                self.log.warning(fail_msg)
                                fails.append(fail_msg)
                            else:
                                self.log.debug(f"Output of 'readelf -d {path}' checked, looks OK")
                        else:
                            self.log.debug("Skipping the RPATH section check with 'readelf -d', as requested")
            else:
                self.log.debug(f"Not sanity checking files in non-existing directory {dirpath}")

        if orig_env:
            env.restore_env_vars(orig_env)

        return fails

    def bin_lib_subdirs(self):
        """
        List of subdirectories for binaries and libraries for this software installation.
        This is used during the sanity check to check RPATH linking and banned/required linked shared libraries.
        """
        return None

    def banned_linked_shared_libs(self):
        """
        List of shared libraries which are not allowed to be linked in any installed binary/library.
        Supported values are pure library names without 'lib' prefix or extension ('example'),
        file names ('libexample.so'), and full paths ('/usr/lib64/libexample.so').
        """
        return []

    def required_linked_shared_libs(self):
        """
        List of shared libraries which must be linked in all installed binaries/libraries.
        Supported values are pure library names without 'lib' prefix or extension ('example'),
        file names ('libexample.so'), and full paths ('/usr/lib64/libexample.so').
        """
        return []

    def sanity_check_linked_shared_libs(self, subdirs=None):
        """
        Check whether specific shared libraries are (not) linked into installed binaries/libraries.
        """
        self.log.info("Checking for banned/required linked shared libraries...")

        # list of libraries that can *not* be linked in any installed binary/library
        banned_libs = []
        banned_libs.extend(build_option('banned_linked_shared_libs') or [])
        banned_libs.extend(self.toolchain.banned_linked_shared_libs())
        banned_libs.extend(self.banned_linked_shared_libs())
        banned_libs.extend(self.cfg['banned_linked_shared_libs'])

        # list of libraries that *must* be linked in every installed binary/library
        required_libs = []
        required_libs.extend(build_option('required_linked_shared_libs') or [])
        required_libs.extend(self.toolchain.required_linked_shared_libs())
        required_libs.extend(self.required_linked_shared_libs())
        required_libs.extend(self.cfg['required_linked_shared_libs'])

        # early return if there are no banned/required libraries
        if not banned_libs + required_libs:
            self.log.info("No banned/required libraries specified")
            return []
        else:
            if banned_libs:
                self.log.info("Banned libraries to check for: %s", ', '.join(banned_libs))
            if required_libs:
                self.log.info("Required libraries to check for: %s", ', '.join(banned_libs))

        shlib_ext = get_shared_lib_ext()

        # compose regular expressions for banned/required libraries
        def regex_for_lib(lib):
            """Compose regular expression for specified banned/required library."""
            # absolute path to library ('/usr/lib64/libexample.so')
            if os.path.isabs(lib):
                regex = re.compile(re.escape(lib))
            # full filename for library ('libexample.so')
            elif lib.startswith('lib'):
                regex = re.compile(r'(/|\s)' + re.escape(lib))
            # pure library name, without 'lib' prefix or extension ('example')
            else:
                regex = re.compile(r'(/|\s)lib%s\.%s' % (lib, shlib_ext))

            return regex

        banned_lib_regexs = [regex_for_lib(x) for x in banned_libs]
        if banned_lib_regexs:
            self.log.debug("Regular expressions to check for banned libraries: %s",
                           '\n'.join("'%s'" % regex.pattern for regex in banned_lib_regexs))

        required_lib_regexs = [regex_for_lib(x) for x in required_libs]
        if required_lib_regexs:
            self.log.debug("Regular expressions to check for required libraries: %s",
                           '\n'.join("'%s'" % regex.pattern for regex in required_lib_regexs))

        if subdirs is None:
            subdirs = self.cfg['bin_lib_subdirs'] or self.bin_lib_subdirs()

        if subdirs:
            self.log.info("Using specified subdirectories to check for banned/required linked shared libraries: %s",
                          subdirs)
        else:
            subdirs = DEFAULT_BIN_LIB_SUBDIRS
            self.log.info("Using default subdirectories to check for banned/required linked shared libraries: %s",
                          subdirs)

        # filter to existing directories that are unique (after resolving symlinks)
        dirpaths = []
        for subdir in subdirs:
            dirpath = os.path.join(self.installdir, subdir)
            if os.path.exists(dirpath) and os.path.isdir(dirpath):
                dirpath = os.path.realpath(dirpath)
                if dirpath not in dirpaths:
                    dirpaths.append(dirpath)

        failed_paths = []

        for dirpath in dirpaths:
            if os.path.exists(dirpath):
                self.log.debug("Checking banned/required linked shared libraries in %s", dirpath)

                for path in [os.path.join(dirpath, x) for x in os.listdir(dirpath)]:
                    self.log.debug("Checking banned/required linked shared libraries for %s", path)

                    libs_check = check_linked_shared_libs(path, banned_patterns=banned_lib_regexs,
                                                          required_patterns=required_lib_regexs)

                    # None indicates the path is not a dynamically linked binary or shared library, so ignore it
                    if libs_check is not None:
                        if libs_check:
                            self.log.debug("Check for banned/required linked shared libraries passed for %s", path)
                        else:
                            failed_paths.append(path)

        fail_msg = None
        if failed_paths:
            fail_msg = "Check for banned/required shared libraries failed for %s" % ', '.join(failed_paths)

        return fail_msg

    def sanity_check_mod_files(self):
        """
        Check installation for Fortran .mod files
        """
        self.log.debug(f"Checking for .mod files in install directory {self.installdir}...")
        mod_files = glob.glob(os.path.join(self.installdir, '**', '*.mod'), recursive=True)

        fail_msg = None
        if mod_files:
            fail_msg = f"One or more .mod files found in {self.installdir}: " + ', '.join(mod_files)

        return fail_msg

    def _sanity_check_step_common(self, custom_paths, custom_commands):
        """
        Determine sanity check paths and commands to use.

        :param custom_paths: custom sanity check paths to check existence for
        :param custom_commands: custom sanity check commands to run
        """

        # supported/required keys in for sanity check paths, along with function used to check the paths
        path_keys_and_check = {
            # files must exist and not be a directory
            SANITY_CHECK_PATHS_FILES: ('file', lambda fp: os.path.exists(fp) and not os.path.isdir(fp)),
            # directories must exist and be non-empty
            SANITY_CHECK_PATHS_DIRS: ("(non-empty) directory", lambda dp: os.path.isdir(dp) and os.listdir(dp)),
        }

        enhance_sanity_check = self.cfg['enhance_sanity_check']
        ec_commands = self.cfg['sanity_check_commands']
        ec_paths = self.cfg['sanity_check_paths']

        # if enhance_sanity_check is not enabled, only sanity_check_paths specified in the easyconfig file are used,
        # the ones provided by the easyblock (via custom_paths) are ignored
        if ec_paths and not enhance_sanity_check:
            paths = ec_paths
            self.log.info("Using (only) sanity check paths specified by easyconfig file: %s", paths)
        else:
            # if no sanity_check_paths are specified in easyconfig,
            # we fall back to the ones provided by the easyblock via custom_paths
            if custom_paths:
                paths = self.cfg.resolve_template(custom_paths)
                self.log.info("Using customized sanity check paths: %s", paths)
            # if custom_paths is empty, we fall back to a generic set of paths:
            # non-empty bin/ + /lib or /lib64 directories
            else:
                paths = {}
                for key in path_keys_and_check:
                    paths.setdefault(key, [])
                paths.update({SANITY_CHECK_PATHS_DIRS: ['bin', ('lib', 'lib64')]})
                self.log.info("Using default sanity check paths: %s", paths)

            # if enhance_sanity_check is enabled *and* sanity_check_paths are specified in the easyconfig,
            # those paths are used to enhance the paths provided by the easyblock
            if enhance_sanity_check and ec_paths:
                for key, val in ec_paths.items():
                    if isinstance(val, list):
                        paths[key] = paths.get(key, []) + val
                    else:
                        error_msg = "Incorrect value type in sanity_check_paths, should be a list: "
                        error_msg += "%s (type: %s)" % (val, type(val))
                        raise EasyBuildError(error_msg)
                self.log.info("Enhanced sanity check paths after taking into account easyconfig file: %s", paths)

        sorted_keys = sorted(paths.keys())
        known_keys = sorted(path_keys_and_check.keys())

        # verify sanity_check_paths value: only known keys, correct value types, at least one non-empty value
        only_list_values = all(isinstance(x, list) for x in paths.values())
        only_empty_lists = all(not x for x in paths.values())
        if sorted_keys != known_keys or not only_list_values or only_empty_lists:
            error_msg = "Incorrect format for sanity_check_paths: should (only) have %s keys, "
            error_msg += "values should be lists (at least one non-empty)."
            raise EasyBuildError(error_msg % ', '.join("'%s'" % k for k in known_keys))

        # Resolve arch specific entries
        for values in paths.values():
            new_values = []
            for value in values:
                value = pick_system_specific_value('sanity_check_paths', value, allow_none=True)
                if value is not None:
                    new_values.append(value)
            values[:] = new_values

        # if enhance_sanity_check is not enabled, only sanity_check_commands specified in the easyconfig file are used,
        # the ones provided by the easyblock (via custom_commands) are ignored
        if ec_commands and not enhance_sanity_check:
            commands = ec_commands
            self.log.info("Using (only) sanity check commands specified by easyconfig file: %s", commands)
        else:
            if custom_commands:
                commands = self.cfg.resolve_template(custom_commands)
                self.log.info("Using customised sanity check commands: %s", commands)
            else:
                commands = []

            # if enhance_sanity_check is enabled, the sanity_check_commands specified in the easyconfig file
            # are combined with those provided by the easyblock via custom_commands
            if enhance_sanity_check and ec_commands:
                commands = commands + ec_commands
                self.log.info("Enhanced sanity check commands after taking into account easyconfig file: %s", commands)

        for i, command in enumerate(commands):
            # set command to default. This allows for config files with
            # non-tuple commands
            if isinstance(command, str):
                self.log.debug("Using %s as sanity check command" % command)
                commands[i] = command
            else:
                if not isinstance(command, tuple):
                    self.log.debug("Setting sanity check command to default")
                    command = (None, None)

                # Build substition dictionary
                check_cmd = {
                    'name': self.name.lower(),
                    'options': '-h',
                }
                if command[0] is not None:
                    check_cmd['name'] = command[0]
                if command[1] is not None:
                    check_cmd['options'] = command[1]

                commands[i] = "%(name)s %(options)s" % check_cmd

        return paths, path_keys_and_check, commands

    def _sanity_check_step_dry_run(self, custom_paths=None, custom_commands=None, **_):
        """
        Dry run version of sanity_check_step method.

        :param custom_paths: custom sanity check paths to check existence for
        :param custom_commands: custom sanity check commands to run
        """
        paths, path_keys_and_check, commands = self._sanity_check_step_common(custom_paths, custom_commands)

        for key in [SANITY_CHECK_PATHS_FILES, SANITY_CHECK_PATHS_DIRS]:
            (typ, _) = path_keys_and_check[key]
            self.dry_run_msg("Sanity check paths - %s ['%s']", typ, key)
            entries = paths[key]
            if entries:
                # some entries may be tuple values,
                # we need to convert them to strings first so we can print them sorted
                for idx, entry in enumerate(entries):
                    if isinstance(entry, tuple):
                        entries[idx] = ' or '.join(entry)

                for path in sorted(paths[key]):
                    self.dry_run_msg("  * %s", str(path))
            else:
                self.dry_run_msg("  (none)")

        self.dry_run_msg("Sanity check commands")
        if commands:
            for command in sorted(commands):
                self.dry_run_msg("  * %s", str(command))
        else:
            self.dry_run_msg("  (none)")

        self.sanity_check_linked_shared_libs()

        if self.toolchain.use_rpath:
            self.sanity_check_rpath()
        else:
            self.log.debug("Skipping RPATH sanity check")

    def _sanity_check_step_extensions(self):
        """Sanity check on extensions (if any)."""
        failed_exts = []

        if not self.ext_instances:
            # class instances for extensions may not be initialized yet here,
            # for example when using --module-only or --sanity-check-only
            self.prepare_for_extensions()
            self.init_ext_instances()

        for ext in self.ext_instances:
            success, fail_msg = None, None
            res = ext.sanity_check_step()
            # if result is a tuple, we expect a (<bool (success)>, <custom_message>) format
            if isinstance(res, tuple):
                if len(res) != 2:
                    raise EasyBuildError("Wrong sanity check result type for '%s' extension: %s", ext.name, res)
                success, fail_msg = res
            else:
                # if result of extension sanity check is not a 2-tuple, treat it as a boolean indicating success
                success, fail_msg = res, "(see log for details)"

            if not success:
                fail_msg = "failing sanity check for '%s' extension: %s" % (ext.name, fail_msg)
                failed_exts.append((ext.name, fail_msg))
                self.log.warning(fail_msg)
            else:
                self.log.info("Sanity check for '%s' extension passed!", ext.name)

        if failed_exts:
            overall_fail_msg = "extensions sanity check failed for %d extensions: " % len(failed_exts)
            self.log.warning(overall_fail_msg)
            self.sanity_check_fail_msgs.append(overall_fail_msg + ', '.join(x[0] for x in failed_exts))
            self.sanity_check_fail_msgs.extend(x[1] for x in failed_exts)

    def sanity_check_load_module(self, extension=False, extra_modules=None):
        """
        Load module to prepare environment for sanity check
        """

        # skip loading of fake module when using --sanity-check-only, load real module instead
        if build_option('sanity_check_only') and not extension:
            self.log.info("Loading real module for %s %s: %s", self.name, self.version, self.short_mod_name)
            self.load_module(extra_modules=extra_modules)
            self.sanity_check_module_loaded = True

        # only load fake module for non-extensions, and not during dry run
        elif not (extension or self.dry_run):

            if extra_modules:
                self.log.info("Loading extra modules for sanity check: %s", ', '.join(extra_modules))

            try:
                # unload all loaded modules before loading fake module
                # this ensures that loading of dependencies is tested, and avoids conflicts with build dependencies
                self.fake_mod_data = self.load_fake_module(purge=True, extra_modules=extra_modules, verbose=True)
                self.sanity_check_module_loaded = True
            except EasyBuildError as err:
                self.sanity_check_fail_msgs.append("loading fake module failed: %s" % err)
                self.log.warning("Sanity check: %s" % self.sanity_check_fail_msgs[-1])

        return self.fake_mod_data

    def _sanity_check_step(self, custom_paths=None, custom_commands=None, extension=False, extra_modules=None):
        """
        Real version of sanity_check_step method.

        :param custom_paths: custom sanity check paths to check existence for
        :param custom_commands: custom sanity check commands to run
        :param extension: indicates whether or not sanity check is run for an extension
        :param extra_modules: extra modules to load before running sanity check commands
        """
        paths, path_keys_and_check, commands = self._sanity_check_step_common(custom_paths, custom_commands)

        # helper function to sanity check (alternatives for) one particular path
        def check_path(xs, typ, check_fn):
            """Sanity check for one particular path."""
            found = False
            for name in xs:
                path = os.path.join(self.installdir, name)
                if check_fn(path):
                    self.log.debug("Sanity check: found %s %s in %s" % (typ, name, self.installdir))
                    found = True
                    break
                else:
                    self.log.debug("Could not find %s %s in %s" % (typ, name, self.installdir))

            return found

        def xs2str(xs):
            """Human-readable version of alternative locations for a particular file/directory."""
            return ' or '.join("'%s'" % x for x in xs)

        # check sanity check paths
        for key in [SANITY_CHECK_PATHS_FILES, SANITY_CHECK_PATHS_DIRS]:

            (typ, check_fn) = path_keys_and_check[key]

            for xs in paths[key]:
                if isinstance(xs, str):
                    xs = (xs,)
                elif not isinstance(xs, tuple):
                    raise EasyBuildError("Unsupported type %s encountered in '%s', not a string or tuple",
                                         type(xs), key)

                found = check_path(xs, typ, check_fn)

                # for library files in lib/, also consider fallback to lib64/ equivalent (and vice versa)
                if not found and build_option('lib64_fallback_sanity_check'):
                    xs_alt = None
                    if all(x.startswith('lib/') or x == 'lib' for x in xs):
                        xs_alt = [os.path.join('lib64', *x.split(os.path.sep)[1:]) for x in xs]
                    elif all(x.startswith('lib64/') or x == 'lib64' for x in xs):
                        xs_alt = [os.path.join('lib', *x.split(os.path.sep)[1:]) for x in xs]

                    if xs_alt:
                        self.log.info("%s not found at %s in %s, consider fallback locations: %s",
                                      typ, xs2str(xs), self.installdir, xs2str(xs_alt))
                        found = check_path(xs_alt, typ, check_fn)

                if not found:
                    sanity_check_fail_msg = "no %s found at %s in %s" % (typ, xs2str(xs), self.installdir)
                    self.sanity_check_fail_msgs.append(sanity_check_fail_msg)
                    self.exit_code = EasyBuildExit.FAIL_SANITY_CHECK
                    self.log.warning("Sanity check: %s", sanity_check_fail_msg)

                trace_msg("%s %s found: %s" % (typ, xs2str(xs), ('FAILED', 'OK')[found]))

        if not self.sanity_check_module_loaded:
            self.sanity_check_load_module(extension=extension, extra_modules=extra_modules)

        # allow oversubscription of P processes on C cores (P>C) for software installed on top of Open MPI;
        # this is useful to avoid failing of sanity check commands that involve MPI
        if self.toolchain.mpi_family() and self.toolchain.mpi_family() in toolchain.OPENMPI:
            env.setvar('OMPI_MCA_rmaps_base_oversubscribe', '1')

        # run sanity checks from an empty temp directory
        # using the build or installation directory can produce false positives and polute them with files
        sanity_check_work_dir = tempfile.mkdtemp(prefix='eb-sanity-check-')

        # run sanity check commands
        for cmd in commands:

            trace_msg(f"running command '{cmd}' ...")

            res = run_shell_cmd(cmd, work_dir=sanity_check_work_dir, fail_on_error=False, hidden=True)
            if res.exit_code != EasyBuildExit.SUCCESS:
                fail_msg = f"sanity check command {cmd} failed with exit code {res.exit_code} (output: {res.output})"
                self.sanity_check_fail_msgs.append(fail_msg)
                self.exit_code = EasyBuildExit.FAIL_SANITY_CHECK
                self.log.warning(f"Sanity check: {fail_msg}")
            else:
                self.log.info(f"sanity check command {cmd} ran successfully! (output: {res.output})")

            cmd_result_str = ('FAILED', 'OK')[res.exit_code == EasyBuildExit.SUCCESS]
            trace_msg(f"result for command '{cmd}': {cmd_result_str}")

        # also run sanity check for extensions (unless we are an extension ourselves)
        if not extension:
            if build_option('skip_extensions'):
                self.log.info("Skipping sanity check for extensions since skip-extensions is enabled...")
            else:
                self._sanity_check_step_extensions()

        linked_shared_lib_fails = self.sanity_check_linked_shared_libs()
        if linked_shared_lib_fails:
            self.log.warning("Check for required/banned linked shared libraries failed!")
            self.sanity_check_fail_msgs.append(linked_shared_lib_fails)

        # software installed with GCCcore toolchain should not have Fortran module files (.mod),
        # unless that's explicitly allowed
        if self.toolchain.name in ('GCCcore',) and not self.cfg['skip_mod_files_sanity_check']:
            mod_files_found_msg = self.sanity_check_mod_files()
            if mod_files_found_msg:
                if build_option('fail_on_mod_files_gcccore'):
                    self.sanity_check_fail_msgs.append(mod_files_found_msg)
                else:
                    print_warning(mod_files_found_msg)

        # cleanup
        if self.fake_mod_data:
            self.clean_up_fake_module(self.fake_mod_data)
            self.sanity_check_module_loaded = False
            self.fake_mod_data = None

        if self.toolchain.use_rpath:
            rpath_fails = self.sanity_check_rpath()
            if rpath_fails:
                self.log.warning("RPATH sanity check failed!")
                self.sanity_check_fail_msgs.extend(rpath_fails)
        else:
            self.log.debug("Skipping RPATH sanity check")

        if 'CUDA' in [dep['name'] for dep in self.cfg.dependencies()]:
            if shutil.which('cuobjdump'):
                cuda_fails = self.sanity_check_cuda()
                if cuda_fails:
                    self.log.warning("CUDA device code sanity check failed!")
                    self.sanity_check_fail_msgs.extend(cuda_fails)
            else:
                msg = "Failed to execute CUDA sanity check: cuobjdump not found\n"
                msg += "CUDA module must be loaded for sanity check (or cuobjdump available in PATH)"
                raise EasyBuildError(msg)
        else:
            self.log.debug("Skipping CUDA sanity check: CUDA is not in dependencies")

        # pass or fail
        if self.sanity_check_fail_msgs:
            raise EasyBuildError(
                "Sanity check failed: " + '\n'.join(self.sanity_check_fail_msgs),
                exit_code=EasyBuildExit.FAIL_SANITY_CHECK,
            )

        self.log.debug("Sanity check passed!")

    def _set_module_as_default(self, fake=False):
        """
        Sets the default module version except if we are in dry run

        :param fake: set default for 'fake' module in temporary location
        """
        version = self.full_mod_name.split('/')[-1]
        if self.dry_run:
            dry_run_msg("Marked %s v%s as default version" % (self.name, version))
        else:
            mod_dir_path = os.path.dirname(self.module_generator.get_module_filepath(fake=fake))
            if fake:
                mod_symlink_paths = []
            else:
                mod_symlink_paths = ActiveMNS().det_module_symlink_paths(self.cfg)
            self.module_generator.set_as_default(mod_dir_path, version, mod_symlink_paths=mod_symlink_paths)

    def cleanup_step(self):
        """
        Cleanup leftover mess: remove/clean build directory

        except when we're building in the installation directory or
        cleanup_builddir is False, otherwise we remove the installation
        """
        if not self.build_in_installdir and build_option('cleanup_builddir'):

            # make sure we're out of the dir we're removing
            change_dir(self.orig_workdir)
            self.log.info("Cleaning up builddir %s (in %s)", self.builddir, get_cwd())

            try:
                remove_dir(self.builddir)
                base = os.path.dirname(self.builddir)

                # keep removing empty directories until we either find a non-empty one
                # or we end up in the root builddir
                while len(os.listdir(base)) == 0 and not os.path.samefile(base, build_path()):
                    os.rmdir(base)
                    base = os.path.dirname(base)

            except OSError as err:
                raise EasyBuildError("Cleaning up builddir %s failed: %s", self.builddir, err)

        if not build_option('cleanup_builddir'):
            self.log.info("Keeping builddir %s" % self.builddir)

        self.toolchain.cleanup()

        env.restore_env_vars(self.cfg['unwanted_env_vars'])

    def invalidate_module_caches(self, modpath):
        """Helper method to invalidate module caches for specified module path."""
        # invalidate relevant 'module avail'/'module show' cache entries
        # consider both paths: for short module name, and subdir indicated by long module name
        paths = [modpath]
        if self.mod_subdir:
            paths.append(os.path.join(modpath, self.mod_subdir))

        for path in paths:
            invalidate_module_caches_for(path)

    def make_module_step(self, fake=False):
        """
        Generate module file

        :param fake: generate 'fake' module in temporary location, rather than actual module file
        """
        modpath = self.module_generator.get_modules_path(fake=fake)
        mod_filepath = self.mod_filepath
        if fake:
            mod_filepath = self.module_generator.get_module_filepath(fake=fake)
        else:
            trace_msg("generating module file @ %s" % self.mod_filepath)

        with self.module_generator.start_module_creation() as txt:
            if self.modules_header:
                txt += self.modules_header + '\n'

            txt += self.make_module_description()
            txt += self.make_module_group_check()
            txt += self.make_module_deppaths()
            txt += self.make_module_dep()
            txt += self.make_module_extend_modpath()
            txt += self.make_module_req()
            txt += self.make_module_extra()
            txt += self.make_module_footer()

        hook_txt = run_hook(MODULE_WRITE, self.hooks, args=[self, mod_filepath, txt])
        if hook_txt is not None:
            txt = hook_txt

        if self.dry_run:
            # only report generating actual module file during dry run, don't mention temporary module files
            if not fake:
                self.dry_run_msg("Generating module file %s, with contents:\n", mod_filepath)
                for line in txt.split('\n'):
                    self.dry_run_msg(INDENT_4SPACES + line)
        else:
            try:
                write_file(mod_filepath, txt)
                self.log.info("Module file %s written: %s", mod_filepath, txt)
            except EasyBuildError:
                raise EasyBuildError(
                    f"Unable to write Module file {mod_filepath}", exit_code=EasyBuildExit.FAIL_MODULE_WRITE
                )

            # if backup module file is there, print diff with newly generated module file
            if self.mod_file_backup and not fake:
                diff_msg = "comparing module file with backup %s; " % self.mod_file_backup
                mod_diff = diff_files(self.mod_file_backup, mod_filepath)
                if mod_diff:
                    diff_msg += 'diff is:\n%s' % mod_diff
                else:
                    diff_msg += 'no differences found'
                self.log.info(diff_msg)
                print_msg(diff_msg, log=self.log)

            self.invalidate_module_caches(modpath)

            # only update after generating final module file
            if not fake:
                self.modules_tool.update()

            mod_symlink_paths = ActiveMNS().det_module_symlink_paths(self.cfg)
            self.module_generator.create_symlinks(mod_symlink_paths, fake=fake)

            if ActiveMNS().mns.det_make_devel_module() and not fake and build_option('generate_devel_module'):
                with self.fake_module_environment():
                    try:
                        self.make_devel_module()
                    except EasyBuildError as error:
                        if build_option('module_only') or self.cfg['module_only']:
                            self.log.info("Using --module-only so can recover from error: %s", error)
                        else:
                            raise error
            else:
                self.log.info("Skipping devel module...")

        # always set default for temporary module file,
        # to avoid that it gets overruled by an existing module file that is set as default
        if fake or self.set_default_module:
            self._set_module_as_default(fake=fake)

        return modpath

    def permissions_step(self):
        """
        Finalize installation procedure: adjust permissions as configured, change group ownership (if requested).
        Installing user must be member of the group that it is changed to.
        """
        if self.group is not None:
            # remove permissions for others, and set group ID
            try:
                perms = stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH
                adjust_permissions(self.installdir, perms, add=False, recursive=True, group_id=self.group[1],
                                   relative=True, ignore_errors=True)
            except EasyBuildError as err:
                raise EasyBuildError("Unable to change group permissions of file(s): %s", err)
            self.log.info("Successfully made software only available for group %s (gid %s)" % self.group)

        if build_option('read_only_installdir'):
            # remove write permissions for everyone
            perms = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
            adjust_permissions(self.installdir, perms, add=False, recursive=True, relative=True, ignore_errors=True)
            self.log.info("Successfully removed write permissions recursively for *EVERYONE* on install dir.")

        elif build_option('group_writable_installdir'):
            # enable write permissions for group
            perms = stat.S_IWGRP
            adjust_permissions(self.installdir, perms, add=True, recursive=True, relative=True, ignore_errors=True)
            self.log.info("Successfully enabled write permissions recursively for group on install dir.")

        else:
            # remove write permissions for group and other
            perms = stat.S_IWGRP | stat.S_IWOTH
            adjust_permissions(self.installdir, perms, add=False, recursive=True, relative=True, ignore_errors=True)
            self.log.info("Successfully removed write permissions recursively for group/other on install dir.")

        # add read permissions for everybody on all files, taking into account group (if any)
        perms = stat.S_IRUSR | stat.S_IRGRP
        # directory permissions: readable (r) & searchable (x)
        dir_perms = stat.S_IXUSR | stat.S_IXGRP
        self.log.debug("Ensuring read permissions for user/group on install dir (recursively)")

        if self.group is None:
            perms |= stat.S_IROTH
            dir_perms |= stat.S_IXOTH
            self.log.debug("Also ensuring read permissions for others on install dir (no group specified)")

        umask = build_option('umask')
        if umask is not None:
            # umask is specified as a string, so interpret it first as integer in octal, then take complement (~)
            perms &= ~int(umask, 8)
            dir_perms &= ~int(umask, 8)
            self.log.debug("Taking umask '%s' into account when ensuring read permissions to install dir", umask)

        self.log.debug("Adding file read permissions in %s using '%s'", self.installdir, oct(perms))
        adjust_permissions(self.installdir, perms, add=True, recursive=True, relative=True, ignore_errors=True)

        # also ensure directories have exec permissions (so they can be opened)
        self.log.debug("Adding directory search permissions in %s using '%s'", self.installdir, oct(dir_perms))
        adjust_permissions(self.installdir, dir_perms, add=True, recursive=True, relative=True, onlydirs=True,
                           ignore_errors=True)

        self.log.info("Successfully added read permissions recursively on install dir %s", self.installdir)

    def test_cases_step(self):
        """
        Run provided test cases.
        """
        for test in self.cfg['tests']:
            change_dir(self.orig_workdir)
            if os.path.isabs(test):
                test_cmd = test
            else:
                for source_path in source_paths():
                    test_cmd = os.path.join(source_path, self.name, test)
                    if os.path.exists(test_cmd):
                        break
                if not os.path.exists(test_cmd):
                    raise EasyBuildError(f"Test specifies invalid path: {test_cmd}")

            try:
                self.log.debug(f"Running test {test_cmd}")
                run_shell_cmd(test_cmd)
            except EasyBuildError as err:
                raise EasyBuildError(f"Running test {test_cmd} failed: {err}")

    def update_config_template_run_step(self):
        """Update the the easyconfig template dictionary with easyconfig.TEMPLATE_NAMES_EASYBLOCK_RUN_STEP names"""

        for name in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP:
            self.cfg.template_values[name] = str(getattr(self, name, None))
        self.cfg.generate_template_values()

    def skip_step(self, step, skippable):
        """Decide whether or not to skip the specified step."""
        skip = False
        force = build_option('force')
        module_only = build_option('module_only') or self.cfg['module_only']
        sanity_check_only = build_option('sanity_check_only')
        skip_extensions = build_option('skip_extensions')
        skip_sanity_check = build_option('skip_sanity_check')
        skip_test_step = build_option('skip_test_step')
        skipsteps = self.cfg['skipsteps']

        # under --skip, sanity check is not skipped
        cli_skip = self.skip and step != SANITYCHECK_STEP

        # skip step if specified as individual (skippable) step, or if --skip is used
        if skippable and (cli_skip or step in skipsteps):
            self.log.info("Skipping %s step (skip: %s, skipsteps: %s)", step, self.skip, skipsteps)
            skip = True

        # skip step when only generating module file
        # * still run sanity check without use of force
        # * always run ready & prepare step to set up toolchain + deps
        elif module_only and step not in MODULE_ONLY_STEPS:
            self.log.info("Skipping %s step (only generating module)", step)
            skip = True

        # allow skipping sanity check too when only generating module and force is used
        elif module_only and step == SANITYCHECK_STEP and force:
            self.log.info("Skipping %s step because of forced module-only mode", step)
            skip = True

        elif sanity_check_only and step != SANITYCHECK_STEP:
            self.log.info("Skipping %s step because of sanity-check-only mode", step)
            skip = True

        elif skip_sanity_check and step == SANITYCHECK_STEP:
            self.log.info("Skipping %s step as request via skip-sanity-check", step)
            skip = True

        elif skip_extensions and step == EXTENSIONS_STEP:
            self.log.info("Skipping %s step as requested via skip-extensions", step)
            skip = True

        elif skip_test_step and step == TEST_STEP:
            self.log.info("Skipping %s step as requested via skip-test-step", step)
            skip = True

        else:
            msg = "Not skipping %s step (skippable: %s, skip: %s, skipsteps: %s, module_only: %s, force: %s, "
            msg += "sanity_check_only: %s, skip_extensions: %s, skip_test_step: %s, skip_sanity_check: %s)"
            self.log.debug(msg, step, skippable, self.skip, skipsteps, module_only, force,
                           sanity_check_only, skip_extensions, skip_test_step, skip_sanity_check)

        return skip

    def run_step(self, step, step_methods):
        """
        Run step, returns false when execution should be stopped
        """
        self.log.info("Starting %s step", step)
        self.update_config_template_run_step()

        run_hook(step, self.hooks, pre_step_hook=True, args=[self])

        for step_method in step_methods:
            # step_method is a lambda function that takes an EasyBlock instance as an argument,
            # and returns the actual method
            current_method = step_method(self)
            # Remove leading underscore from e.g. "_test_step"
            method_name = current_method.__name__.lstrip('_')
            self.log.info("Running method %s part of step %s", method_name, step)

            if self.dry_run:
                self.dry_run_msg("[%s method]", method_name)

                # if an known possible error occurs, just report it and continue
                try:
                    current_method()
                except Exception as err:
                    if build_option('extended_dry_run_ignore_errors'):
                        dry_run_warning("ignoring error %s" % err, silent=self.silent)
                        self.ignored_errors = True
                    else:
                        raise
                self.dry_run_msg('')
            else:
                current_method()

        run_hook(step, self.hooks, post_step_hook=True, args=[self])

        if self.cfg['stop'] == step:
            update_progress_bar(PROGRESS_BAR_EASYCONFIG)
            self.log.info("Stopping after %s step.", step)
            raise StopException(step)

    @staticmethod
    def get_steps(run_test_cases=True, iteration_count=1):
        """Return a list of all steps to be performed."""

        def get_step(tag, descr, substeps, skippable, initial=True):
            """Determine step definition based on whether it's an initial run or not."""
            substeps = [substep for (always_include, substep) in substeps if (initial or always_include)]
            return (tag, descr, substeps, skippable)

        # list of substeps for steps that are slightly different from 2nd iteration onwards
        ready_substeps = [
            (False, lambda x: x.check_readiness_step),
            (True, lambda x: x.make_builddir),
            (True, lambda x: x.reset_env),
            (True, lambda x: x.handle_iterate_opts),
        ]

        def ready_step_spec(initial):
            """Return ready step specified."""
            return get_step(READY_STEP, "creating build dir, resetting environment", ready_substeps, False,
                            initial=initial)

        install_substeps = [
            (False, lambda x: x.stage_install_step),
            (False, lambda x: x.make_installdir),
            (True, lambda x: x.install_step),
        ]

        def install_step_spec(initial):
            """Return install step specification."""
            return get_step(INSTALL_STEP, "installing", install_substeps, True, initial=initial)

        # format for step specifications: (step_name, description, list of functions, skippable)

        # core steps that are part of the iterated loop
        extract_step_spec = (EXTRACT_STEP, "unpacking", [lambda x: x.extract_step], True)
        patch_step_spec = (PATCH_STEP, 'patching', [lambda x: x.patch_step], True)
        prepare_step_spec = (PREPARE_STEP, 'preparing', [lambda x: x.prepare_step], False)
        configure_step_spec = (CONFIGURE_STEP, 'configuring', [lambda x: x.configure_step], True)
        build_step_spec = (BUILD_STEP, 'building', [lambda x: x.build_step], True)
        test_step_spec = (TEST_STEP, 'testing', [lambda x: x._test_step], True)
        extensions_step_spec = (EXTENSIONS_STEP, 'taking care of extensions', [lambda x: x.extensions_step], False)

        # part 1: pre-iteration + first iteration
        steps_part1 = [
            (FETCH_STEP, "fetching files and verifying checksums",
             [lambda x: x.fetch_step, lambda x: x.checksum_step], False),
            ready_step_spec(True),
            extract_step_spec,
            patch_step_spec,
            prepare_step_spec,
            configure_step_spec,
            build_step_spec,
            test_step_spec,
            install_step_spec(True),
            extensions_step_spec,
        ]
        # part 2: iterated part, from 2nd iteration onwards
        # repeat core procedure again depending on specified iteration count
        # not all parts of all steps need to be rerun (see e.g., ready, prepare)
        steps_part2 = [
            ready_step_spec(False),
            extract_step_spec,
            patch_step_spec,
            prepare_step_spec,
            configure_step_spec,
            build_step_spec,
            test_step_spec,
            install_step_spec(False),
            extensions_step_spec,
        ] * (iteration_count - 1)
        # part 3: post-iteration part
        steps_part3 = [
            (POSTITER_STEP, 'restore after iterating', [lambda x: x.post_iter_step], False),
            (POSTPROC_STEP, 'postprocessing', [lambda x: x.post_processing_step], True),
            (SANITYCHECK_STEP, 'sanity checking', [lambda x: x.sanity_check_step], True),
            (CLEANUP_STEP, 'cleaning up', [lambda x: x.cleanup_step], False),
            (MODULE_STEP, 'creating module', [lambda x: x.make_module_step], False),
            (PERMISSIONS_STEP, 'permissions', [lambda x: x.permissions_step], False),
            (PACKAGE_STEP, 'packaging', [lambda x: x.package_step], False),
        ]

        # full list of steps, included iterated steps
        steps = steps_part1 + steps_part2 + steps_part3

        if run_test_cases:
            steps.append((TESTCASES_STEP, 'running test cases', [
                lambda x: x.load_module,
                lambda x: x.test_cases_step,
            ], False))

        return steps

    def run_all_steps(self, run_test_cases):
        """
        Build and install this software.
        run_test_cases (bool): run tests after building (e.g.: make test)
        """
        if self.cfg['stop'] == 'cfg':
            return True

        steps = self.get_steps(run_test_cases=run_test_cases, iteration_count=self.det_iter_cnt())

        # figure out how many steps will actually be run (not be skipped)
        step_cnt = 0
        for (step_name, _, _, _) in steps:
            step_cnt += 1
            if self.cfg['stop'] == step_name:
                break

        start_progress_bar(PROGRESS_BAR_EASYCONFIG, step_cnt, label="Installing %s" % self.full_mod_name)

        print_msg("building and installing %s..." % self.full_mod_name, log=self.log, silent=self.silent)
        trace_msg("installation prefix: %s" % self.installdir)

        ignore_locks = build_option('ignore_locks')

        lock_created = False
        try:
            if ignore_locks:
                self.log.info("Ignoring locks...")
            else:
                lock_name = self.installdir.replace('/', '_')

                # check if lock already exists;
                # either aborts with an error or waits until it disappears (depends on --wait-on-lock)
                check_lock(lock_name)

                # create lock to avoid that another installation running in parallel messes things up
                create_lock(lock_name)
                lock_created = True

            # run post-initialization tasks first, before running any steps
            self.post_init()

            for step_name, descr, step_methods, skippable in steps:
                if self.skip_step(step_name, skippable):
                    print_msg("%s [skipped]" % descr, log=self.log, silent=self.silent)
                else:
                    progress_label = "Installing %s: %s" % (self.full_mod_name, descr)
                    update_progress_bar(PROGRESS_BAR_EASYCONFIG, label=progress_label, progress_size=0)

                    if self.dry_run:
                        self.dry_run_msg("%s... [DRY RUN]\n", descr)
                    else:
                        print_msg("%s..." % descr, log=self.log, silent=self.silent)
                    self.current_step = step_name
                    start_time = datetime.now()
                    try:
                        self.run_step(step_name, step_methods)
                    except RunShellCmdError as err:
                        err.print()
                        error_msg = (
                            f"shell command '{err.cmd_name} ...' failed with exit code {err.exit_code} "
                            f"in {step_name} step for {os.path.basename(self.cfg.path)}"
                        )
                        try:
                            step_exit_code = EasyBuildExit[f"FAIL_{step_name.upper()}_STEP"]
                        except KeyError:
                            step_exit_code = EasyBuildExit.ERROR
                        raise EasyBuildError(error_msg, exit_code=step_exit_code) from err
                    finally:
                        if not self.dry_run:
                            step_duration = datetime.now() - start_time
                            if step_duration.total_seconds() >= 1:
                                print_msg("... (took %s)", time2str(step_duration), log=self.log, silent=self.silent)
                            elif self.logdebug or build_option('trace'):
                                print_msg("... (took < 1 sec)", log=self.log, silent=self.silent)

                update_progress_bar(PROGRESS_BAR_EASYCONFIG)

        except StopException:
            pass
        finally:
            # remove lock, but only if it was created in this session (not if it was there already)
            if lock_created:
                remove_lock(lock_name)

            stop_progress_bar(PROGRESS_BAR_EASYCONFIG)

        # return True for successfull build (or stopped build)
        return True


def print_dry_run_note(loc, silent=True):
    """Print note on interpreting dry run output."""
    msg = '\n'.join([
        '',
        "Important note: the actual build & install procedure that will be performed may diverge",
        "(slightly) from what is outlined %s, due to conditions in the easyblock which are" % loc,
        "incorrectly handled in a dry run.",
        "Any errors that may occur are ignored and reported as warnings, on a per-step basis.",
        "Please be aware of this, and only use the information %s for quick debugging purposes." % loc,
        '',
    ])
    dry_run_msg(msg, silent=silent)


def copy_build_dirs_logs_failed_install(application_log, silent, app, easyconfig):
    """
    Copy build directories and log files for failed installation (if desired)
    """
    logs_path = get_failed_install_logs_path(easyconfig)
    build_dirs_path = get_failed_install_build_dirs_path(easyconfig)

    # there may be multiple log files, or the file name may be different due to zipping
    logs = glob.glob(f"{application_log}*")

    timestamp = time.strftime('%Y%m%d-%H%M%S')
    salt = ''.join(random.choices(ascii_letters, k=5))
    unique_subdir = f'{timestamp}-{salt}'

    operation_args = []

    if logs_path and logs:
        logs_path = os.path.join(logs_path, unique_subdir)

        if is_parent_path(app.builddir, logs_path):
            msg = "Path to copy log files of failed installs to is subdirectory of build directory; not copying"
            print_warning(msg, log=_log, silent=silent)
        else:
            msg = f"Log file(s) of failed installation copied to {logs_path}"
            operation_args.append((copy_file, logs, logs_path, msg))

    if build_dirs_path and os.path.isdir(app.builddir):
        build_dirs_path = os.path.join(build_dirs_path, unique_subdir)

        if is_parent_path(app.builddir, build_dirs_path):
            msg = "Path to copy build dirs of failed installs to is subdirectory of build directory; not copying"
            print_warning(msg, log=_log, silent=silent)
        else:
            msg = f"Build directory of failed installation copied to {build_dirs_path}"

            def operation(src, dest):
                copy_dir(src, dest, dirs_exist_ok=True)

            operation_args.append((operation, [app.builddir], build_dirs_path, msg))

    persistence_paths = create_non_existing_paths(target_path for (_, _, target_path, _) in operation_args)

    for idx, (operation, paths, _, msg) in enumerate(operation_args):
        for path in paths:
            operation(path, persistence_paths[idx])
        print_msg(msg, log=_log, silent=silent)


def build_and_install_one(ecdict, init_env):
    """
    Build the software
    :param ecdict: dictionary contaning parsed easyconfig + metadata
    :param init_env: original environment (used to reset environment)
    """
    silent = build_option('silent')

    start_timestamp = datetime.now()

    spec = ecdict['spec']
    rawtxt = ecdict['ec'].rawtxt
    name = ecdict['ec']['name']

    dry_run = build_option('extended_dry_run')

    if dry_run:
        dry_run_msg('', silent=silent)
    print_msg("processing EasyBuild easyconfig %s" % spec, log=_log, silent=silent)

    if ecdict['ec']['build_info_msg']:
        msg = "This easyconfig provides the following build information:\n\n%s\n"
        print_msg(msg % ecdict['ec']['build_info_msg'], log=_log, silent=silent)

    if dry_run:
        # print note on interpreting dry run output (argument is reference to location of dry run messages)
        print_dry_run_note('below', silent=silent)

    # restore original environment, and then sanitize it
    _log.info("Resetting environment")
    restore_env(init_env)
    sanitize_env()

    cwd = get_cwd()

    # load easyblock
    easyblock = build_option('easyblock')
    if easyblock:
        # set the value in the dict so this is included in the reproducibility dump of the easyconfig
        ecdict['ec']['easyblock'] = easyblock
    else:
        easyblock = fetch_parameters_from_easyconfig(rawtxt, ['easyblock'])[0]

    try:
        app_class = get_easyblock_class(easyblock, name=name)
        app = app_class(ecdict['ec'])
        _log.info("Obtained application instance for %s (easyblock: %s)" % (name, easyblock))
    except EasyBuildError as err:
        print_error("Failed to get application instance for %s (easyblock: %s): %s" % (name, easyblock, err.msg),
                    silent=silent)

    # application settings
    stop = build_option('stop')
    if stop is not None:
        _log.debug("Stop set to %s" % stop)
        app.cfg['stop'] = stop

    skip = build_option('skip')
    if skip is not None:
        _log.debug("Skip set to %s" % skip)
        app.cfg['skip'] = skip

    hooks = load_hooks(build_option('hooks'))

    # build easyconfig
    error_msg = '(no error)'
    exit_code = None
    # timing info
    start_time = time.time()
    try:
        run_test_cases = not build_option('skip_test_cases') and app.cfg['tests']

        if not dry_run:
            # create our reproducibility files before carrying out the easyblock steps
            reprod_dir_root = os.path.dirname(app.logfile)
            reprod_dir = reproduce_build(app, reprod_dir_root)

            if os.path.exists(app.installdir) and build_option('read_only_installdir') and (
                    build_option('rebuild') or build_option('force')):
                enabled_write_permissions = True
                # re-enable write permissions so we can install additional modules
                adjust_permissions(app.installdir, stat.S_IWUSR, add=True, recursive=True)
            else:
                enabled_write_permissions = False

        run_hook(EASYBLOCK, hooks, pre_step_hook=True, args=[app])

        result = app.run_all_steps(run_test_cases=run_test_cases)

        if not dry_run:
            # Copy over the build environment used during the configuraton
            reprod_spec = os.path.join(reprod_dir, app.cfg.filename())
            try:
                dump_env_easyblock(app, ec_path=reprod_spec, silent=True)
                _log.debug("Created build environment dump for easyconfig %s", reprod_spec)
            except EasyBuildError as err:
                _log.warning("Failed to create build environment dump for easyconfig %s: %s", reprod_spec, err)

            # also add any extension easyblocks used during the build for reproducibility
            if app.ext_instances:
                copy_easyblocks_for_reprod(app.ext_instances, reprod_dir)
            # If not already done remove the granted write permissions if we did so
            if enabled_write_permissions and os.lstat(app.installdir)[stat.ST_MODE] & stat.S_IWUSR:
                adjust_permissions(app.installdir, stat.S_IWUSR, add=False, recursive=True)

    except EasyBuildError as err:
        error_msg = err.msg
        try:
            exit_code = err.exit_code
        except AttributeError:
            exit_code = EasyBuildExit.ERROR
        result = False

    ended = 'ended'

    # make sure we're back in original directory before we finish up
    change_dir(cwd)

    application_log = None

    # successful (non-dry-run) build
    if result and not dry_run:
        def ensure_writable_log_dir(log_dir):
            """Make sure we can write into the log dir"""
            if build_option('read_only_installdir'):
                # temporarily re-enable write permissions for copying log/easyconfig to install dir,
                # ensuring that we resolve symlinks
                log_dir = os.path.realpath(log_dir)
                if os.path.exists(log_dir):
                    adjust_permissions(log_dir, stat.S_IWUSR, add=True, recursive=True)
                else:
                    parent_dir = os.path.dirname(log_dir)
                    if os.path.exists(parent_dir) and not (os.stat(parent_dir).st_mode & stat.S_IWUSR):
                        adjust_permissions(parent_dir, stat.S_IWUSR, add=True, recursive=False)
                        mkdir(log_dir, parents=True)
                        adjust_permissions(parent_dir, stat.S_IWUSR, add=False, recursive=False)
                    else:
                        mkdir(log_dir, parents=True)
                        adjust_permissions(log_dir, stat.S_IWUSR, add=True, recursive=True)

        if app.cfg['stop']:
            ended = 'STOPPED'
            if app.builddir is not None:
                new_log_dir = os.path.join(app.builddir, config.log_path(ec=app.cfg))
            else:
                new_log_dir = os.path.dirname(app.logfile)
            ensure_writable_log_dir(new_log_dir)

        # if we're only running the sanity check, we should not copy anything new to the installation directory
        elif build_option('sanity_check_only'):
            _log.info("Only running sanity check, so skipping build stats, easyconfigs archive, reprod files...")

        else:
            new_log_dir = os.path.join(app.installdir, config.log_path(ec=app.cfg))
            ensure_writable_log_dir(new_log_dir)

            # collect build stats
            _log.info("Collecting build stats...")

            buildstats = get_build_stats(app, start_time, build_option('command_line'))
            _log.info("Build stats: %s" % buildstats)

            try:
                # move the reproducibility files to the final log directory
                archive_reprod_dir = os.path.join(new_log_dir, REPROD)
                if os.path.exists(archive_reprod_dir):
                    backup_dir = find_backup_name_candidate(archive_reprod_dir)
                    move_file(archive_reprod_dir, backup_dir)
                    _log.info("Existing reproducibility directory %s backed up to %s", archive_reprod_dir, backup_dir)
                move_file(reprod_dir, archive_reprod_dir)
                _log.info("Wrote files for reproducibility to %s", archive_reprod_dir)
            except EasyBuildError as error:
                if build_option('module_only'):
                    _log.info("Using --module-only so can recover from error: %s", error)
                else:
                    raise error

            try:
                # upload easyconfig (and patch files) to central repository
                currentbuildstats = app.cfg['buildstats']
                repo = init_repository(get_repository(), get_repositorypath())
                if 'original_spec' in ecdict:
                    block = det_full_ec_version(app.cfg) + ".block"
                    repo.add_easyconfig(ecdict['original_spec'], app.name, block, buildstats, currentbuildstats)
                repo.add_easyconfig(spec, app.name, det_full_ec_version(app.cfg), buildstats, currentbuildstats)
                for patch in app.patches:
                    repo.add_patch(patch['path'], app.name)
                repo.commit("Built %s" % app.full_mod_name)
                del repo
            except EasyBuildError as err:
                _log.warning("Unable to commit easyconfig to repository: %s", err)

        run_hook(EASYBLOCK, hooks, post_step_hook=True, args=[app])

        # cleanup logs
        app.close_log()

        if build_option('sanity_check_only'):
            _log.info("Only running sanity check, so not copying anything to software install directory...")
        else:
            log_fn = os.path.basename(get_log_filename(app.name, app.version))
            try:
                application_log = os.path.join(new_log_dir, log_fn)
                move_logs(app.logfile, application_log)

                newspec = os.path.join(new_log_dir, app.cfg.filename())
                copy_file(spec, newspec)
                _log.debug("Copied easyconfig file %s to %s", spec, newspec)

                # copy patches
                for patch in app.patches:
                    target = os.path.join(new_log_dir, os.path.basename(patch['path']))
                    copy_file(patch['path'], target)
                    _log.debug("Copied patch %s to %s", patch['path'], target)

                if build_option('read_only_installdir') and not app.cfg['stop']:
                    # take away user write permissions (again)
                    perms = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
                    adjust_permissions(new_log_dir, perms, add=False, recursive=True)
            except EasyBuildError as error:
                if build_option('module_only'):
                    application_log = None
                    _log.debug("Using --module-only so can recover from error: %s", error)
                else:
                    raise error

    end_timestamp = datetime.now()

    if result:
        success = True
        summary = 'COMPLETED'
        succ = 'successfully'
        exit_code = EasyBuildExit.SUCCESS
    else:
        # build failed
        success = False
        summary = 'FAILED'
        succ = "unsuccessfully: " + error_msg
        exit_code = EasyBuildExit.ERROR if exit_code is None else exit_code

        # cleanup logs
        app.close_log()
        application_log = app.logfile

    req_time = time2str(end_timestamp - start_timestamp)
    print_msg("%s: Installation %s %s (took %s)" % (summary, ended, succ, req_time), log=_log, silent=silent)

    if app.postmsg:
        print_msg("\nWARNING: %s\n" % app.postmsg, log=_log, silent=silent)

    if dry_run:
        # print note on interpreting dry run output (argument is reference to location of dry run messages)
        print_dry_run_note('above', silent=silent)

        if app.ignored_errors:
            dry_run_warning("One or more errors were ignored, see warnings above", silent=silent)
        else:
            dry_run_msg("(no ignored errors during dry run)\n", silent=silent)

    if application_log:
        # there may be multiple log files, or the file name may be different due to zipping
        logs = glob.glob('%s*' % application_log)
        print_msg("Results of the build can be found in the log file(s) %s" % ', '.join(logs), log=_log, silent=silent)

    if not success:
        copy_build_dirs_logs_failed_install(application_log, silent, app, ecdict['ec'])

    del app

    return (success, application_log, error_msg, exit_code)


def copy_easyblocks_for_reprod(easyblock_instances, reprod_dir):
    reprod_easyblock_dir = os.path.join(reprod_dir, 'easyblocks')
    easyblock_paths = set()
    for easyblock_instance in easyblock_instances:
        for easyblock_class in inspect.getmro(type(easyblock_instance)):
            easyblock_path = inspect.getsourcefile(easyblock_class)
            # if we reach EasyBlock, Extension or ExtensionEasyBlock class, we are done
            # (Extension and ExtensionEasyBlock are hardcoded to avoid a cyclical import)
            if easyblock_class.__name__ in [EasyBlock.__name__, 'Extension', 'ExtensionEasyBlock']:
                break
            else:
                easyblock_paths.add(easyblock_path)
    for easyblock_path in easyblock_paths:
        easyblock_filename = os.path.basename(easyblock_path)
        copy_file(easyblock_path, os.path.join(reprod_easyblock_dir, easyblock_filename))
        _log.info("Dumped easyblock %s required for reproduction to %s", easyblock_filename, reprod_easyblock_dir)


def reproduce_build(app, reprod_dir_root):
    """
    Create reproducibility files (processed easyconfig and easyblocks used) from class instance

    :param app: easyblock class instance
    :param reprod_dir_root: root directory in which to create the 'reprod' directory

    :return: reprod_dir directory containing reproducibility files
    """

    ec_filename = app.cfg.filename()

    # Let's use a unique timestamped directory (facilitated by find_backup_name_candidate())
    reprod_dir = find_backup_name_candidate(os.path.join(reprod_dir_root, REPROD))
    reprod_spec = os.path.join(reprod_dir, ec_filename)
    try:
        app.cfg.dump(reprod_spec, explicit_toolchains=True)
        _log.info("Dumped easyconfig instance to %s", reprod_spec)
    except NotImplementedError as err:
        _log.warning("Unable to dump easyconfig instance to %s: %s", reprod_spec, err)

    # also archive all the relevant easyblocks (including any used by extensions)
    copy_easyblocks_for_reprod([app], reprod_dir)

    # if there is a hook file we should also archive it
    hooks_path = build_option('hooks')
    if hooks_path:
        target = os.path.join(reprod_dir, 'hooks', os.path.basename(hooks_path))
        copy_file(hooks_path, target)
        _log.info("Dumped hooks file %s which is (potentially) required for reproduction to %s", hooks_path, target)

    return reprod_dir


def get_easyblock_instance(ecdict):
    """
    Get an instance for this easyconfig
    :param ecdict: parsed easyconfig (EasyConfig instance)

    returns an instance of EasyBlock (or subclass thereof)
    """
    rawtxt = ecdict['ec'].rawtxt
    name = ecdict['ec']['name']

    # handle easyconfigs with custom easyblocks
    # determine easyblock specification from easyconfig file, if any
    easyblock = fetch_parameters_from_easyconfig(rawtxt, ['easyblock'])[0]

    app_class = get_easyblock_class(easyblock, name=name)
    return app_class(ecdict['ec'])


def build_easyconfigs(easyconfigs, output_dir, test_results):
    """Build the list of easyconfigs."""

    build_stopped = []

    # sanitize environment before initialising easyblocks
    sanitize_env()

    # initialize all instances
    apps = []
    for ec in easyconfigs:
        instance = get_easyblock_instance(ec)
        apps.append(instance)

    base_dir = get_cwd()

    # keep track of environment right before initiating builds
    # note: may be different from ORIG_OS_ENVIRON, since EasyBuild may have defined additional env vars itself by now
    # e.g. via easyconfig.handle_allowed_system_deps
    base_env = copy.deepcopy(os.environ)
    succes = []

    for app in apps:

        # if initialisation step failed, app will be None
        if app:
            applog = os.path.join(output_dir, "%s-%s.log" % (app.name, det_full_ec_version(app.cfg)))

            start_time = time.time()

            # start with a clean slate
            change_dir(base_dir)
            restore_env(base_env)
            sanitize_env()

            run_test_cases = not build_option('skip_test_cases') and app.cfg['tests']

            try:
                result = app.run_all_steps(run_test_cases=run_test_cases)
            # catch all possible errors, also crashes in EasyBuild code itself
            except Exception as err:
                fullerr = str(err)
                if not isinstance(err, EasyBuildError):
                    tb = traceback.format_exc()
                    fullerr = '\n'.join([tb, str(err)])
                test_results.append((app, app.current_step, fullerr, applog))
                # keep a dict of so we can check in O(1) if objects can still be build
                build_stopped.append(app)

            # close log and move it
            app.close_log()
            move_logs(app.logfile, applog)

            if app not in build_stopped:
                # gather build stats
                buildstats = get_build_stats(app, start_time, build_option('command_line'))
                succes.append((app, buildstats))

    for result in test_results:
        _log.info("%s crashed with an error during fase: %s, error: %s, log file: %s" % result)

    failed = len(build_stopped)
    total = len(apps)

    _log.info("%s of %s packages failed to build!" % (failed, total))

    output_file = os.path.join(output_dir, "easybuild-test.xml")
    _log.debug("writing xml output to %s" % output_file)
    write_to_xml(succes, test_results, output_file)

    return failed == 0


class StopException(Exception):
    """Exception thrown to stop running steps"""


def inject_checksums_to_json(ecs, checksum_type):
    """
    Inject checksums of given type in corresponding json files

    :param ecs: list of EasyConfig instances to calculate checksums and inject them into checksums.json
    :param checksum_type: type of checksum to use
    """
    for ec in ecs:
        ec_fn = os.path.basename(ec['spec'])
        ec_dir = os.path.dirname(ec['spec'])
        print_msg("injecting %s checksums for %s in checksums.json" % (checksum_type, ec['spec']), log=_log)

        # get easyblock instance and make sure all sources/patches are available by running fetch_step
        print_msg("fetching sources & patches for %s..." % ec_fn, log=_log)
        app = get_easyblock_instance(ec)
        app.update_config_template_run_step()
        app.fetch_step(skip_checksums=True)

        # compute & inject checksums for sources/patches
        print_msg("computing %s checksums for sources & patches for %s..." % (checksum_type, ec_fn), log=_log)
        checksums = {}
        for entry in app.src + app.patches:
            checksum = compute_checksum(entry['path'], checksum_type)
            print_msg("* %s: %s" % (os.path.basename(entry['path']), checksum), log=_log)
            checksums[os.path.basename(entry['path'])] = checksum

        # compute & inject checksums for extension sources/patches
        if app.exts:
            print_msg("computing %s checksums for extensions for %s..." % (checksum_type, ec_fn), log=_log)

            for ext in app.exts:
                # compute checksums for extension sources & patches
                if 'src' in ext:
                    src_fn = os.path.basename(ext['src'])
                    checksum = compute_checksum(ext['src'], checksum_type)
                    print_msg(" * %s: %s" % (src_fn, checksum), log=_log)
                    checksums[src_fn] = checksum
                for ext_patch in ext.get('patches', []):
                    patch_fn = os.path.basename(ext_patch['path'])
                    checksum = compute_checksum(ext_patch['path'], checksum_type)
                    print_msg(" * %s: %s" % (patch_fn, checksum), log=_log)
                    checksums[patch_fn] = checksum

        # actually inject new checksums or overwrite existing ones (if --force)
        existing_checksums = app.get_checksums_from_json(always_read=True)
        for filename, checksum in checksums.items():
            if filename not in existing_checksums:
                existing_checksums[filename] = checksum
            # don't do anything if the checksum already exist and is the same
            elif checksum != existing_checksums[filename]:
                if build_option('force'):
                    print_warning("Found existing checksums for %s, overwriting them (due to --force)..." % ec_fn)
                    existing_checksums[filename] = checksum
                else:
                    raise EasyBuildError("Found existing checksum for %s, use --force to overwrite them" % filename)

        # actually write the checksums
        with open(os.path.join(ec_dir, CHECKSUMS_JSON), 'w') as outfile:
            json.dump(existing_checksums, outfile, indent=2, sort_keys=True)


def inject_checksums(ecs, checksum_type):
    """
    Inject checksums of given type in specified easyconfig files

    :param ecs: list of EasyConfig instances to inject checksums into corresponding files
    :param checksum_type: type of checksum to use
    """
    def make_list_lines(values, indent_level):
        """Make lines for list of values."""
        def to_str(s):
            if isinstance(s, str):
                return "'%s'" % s
            else:
                return str(s)

        line_indent = INDENT_4SPACES * indent_level
        return [line_indent + to_str(x) + ',' for x in values]

    def make_checksum_lines(checksums, indent_level):
        """Make lines for list of checksums."""
        line_indent = INDENT_4SPACES * indent_level
        checksum_lines = []
        for fn, checksum in checksums:
            checksum_line = "%s{'%s': '%s'}," % (line_indent, fn, checksum)
            if len(checksum_line) > MAX_LINE_LENGTH:
                checksum_lines.extend([
                    "%s{'%s':" % (line_indent, fn),
                    "%s '%s'}," % (line_indent, checksum),
                ])
            else:
                checksum_lines.append(checksum_line)
        return checksum_lines

    for ec in ecs:
        ec_fn = os.path.basename(ec['spec'])
        ectxt = read_file(ec['spec'])
        print_msg("injecting %s checksums in %s" % (checksum_type, ec['spec']), log=_log)

        # get easyblock instance and make sure all sources/patches are available by running fetch_step
        print_msg("fetching sources & patches for %s..." % ec_fn, log=_log)
        app = get_easyblock_instance(ec)
        app.update_config_template_run_step()
        app.fetch_step(skip_checksums=True)

        # check for any existing checksums, require --force to overwrite them
        found_checksums = bool(app.cfg['checksums'])
        for ext in app.exts:
            found_checksums |= bool(ext.get('checksums'))
        if found_checksums:
            if build_option('force'):
                print_warning("Found existing checksums in %s, overwriting them (due to use of --force)..." % ec_fn)
            else:
                raise EasyBuildError("Found existing checksums, use --force to overwrite them")

        # back up easyconfig file before injecting checksums
        ec_backup = back_up_file(ec['spec'])
        print_msg("backup of easyconfig file saved to %s" % ec_backup, log=_log)

        # compute & inject checksums for sources/patches
        print_msg("injecting %s checksums for sources & patches in %s..." % (checksum_type, ec_fn), log=_log)
        checksums = []
        for entry in app.src + app.patches:
            checksum = compute_checksum(entry['path'], checksum_type)
            print_msg("* %s: %s" % (os.path.basename(entry['path']), checksum), log=_log)
            checksums.append((os.path.basename(entry['path']), checksum))

        if len(checksums) == 1:
            checksum_lines = ["checksums = ['%s']\n" % checksums[0][1]]
        else:
            checksum_lines = ['checksums = [']
            checksum_lines.extend(make_checksum_lines(checksums, indent_level=1))
            checksum_lines.append(']\n')

        checksums_txt = '\n'.join(checksum_lines)

        # if 'checksums' is specified in easyconfig file, get rid of it (even if it's just an empty list)
        checksums_regex = re.compile(r'^checksums(?:.|\n)+?\]\s*$', re.M)
        if checksums_regex.search(ectxt):
            _log.debug("Removing existing 'checksums' easyconfig parameter definition...")
            ectxt = checksums_regex.sub('', ectxt)

        # it is possible no sources (and hence patches) are listed, e.g. for 'bundle' easyconfigs
        if app.src:
            placeholder = '# PLACEHOLDER FOR SOURCES/PATCHES WITH CHECKSUMS'

            # grab raw lines for source_urls, sources, data_sources, patches
            keys = ['data_sources', 'patches', 'source_urls', 'sources']
            raw = {}
            for key in keys:
                regex = re.compile(r'^(%s(?:.|\n)*?\])\s*$' % key, re.M)
                res = regex.search(ectxt)
                if res:
                    raw[key] = res.group(0).strip() + '\n'
                    ectxt = regex.sub(placeholder, ectxt)

            _log.debug("Raw lines for %s easyconfig parameters: %s", '/'.join(keys), raw)

            # inject combination of source_urls/sources/patches/checksums into easyconfig
            # by replacing first occurence of placeholder that was put in place
            sources_raw = raw.get('sources', '')
            data_sources_raw = raw.get('data_sources', '')
            source_urls_raw = raw.get('source_urls', '')
            patches_raw = raw.get('patches', '')
            regex = re.compile(placeholder + '\n', re.M)
            ectxt = regex.sub(source_urls_raw + sources_raw + data_sources_raw + patches_raw + checksums_txt + '\n',
                              ectxt, count=1)

            # get rid of potential remaining placeholders
            ectxt = regex.sub('', ectxt)

        # compute & inject checksums for extension sources/patches
        if app.exts:
            print_msg("injecting %s checksums for extensions in %s..." % (checksum_type, ec_fn), log=_log)

            exts_list_lines = ['exts_list = [']
            for ext in app.exts:
                if ext['name'] == app.name:
                    ext_name = 'name'
                else:
                    ext_name = "'%s'" % ext['name']

                # for some extensions, only a name if specified (so no sources/patches)
                if list(ext.keys()) == ['name']:
                    exts_list_lines.append("%s%s," % (INDENT_4SPACES, ext_name))
                else:
                    if ext['version'] == app.version:
                        ext_version = 'version'
                    else:
                        ext_version = "'%s'" % ext['version']

                    ext_options = ext.get('options', {})

                    # compute checksums for extension sources & patches
                    ext_checksums = []
                    if 'src' in ext:
                        src_fn = os.path.basename(ext['src'])
                        checksum = compute_checksum(ext['src'], checksum_type)
                        print_msg(" * %s: %s" % (src_fn, checksum), log=_log)
                        ext_checksums.append((src_fn, checksum))
                    for ext_patch in ext.get('patches', []):
                        patch_fn = os.path.basename(ext_patch['path'])
                        checksum = compute_checksum(ext_patch['path'], checksum_type)
                        print_msg(" * %s: %s" % (patch_fn, checksum), log=_log)
                        ext_checksums.append((patch_fn, checksum))

                    exts_list_lines.append("%s(%s, %s," % (INDENT_4SPACES, ext_name, ext_version))
                    if ext_options or ext_checksums:
                        exts_list_lines[-1] += ' {'

                    # make sure we grab *raw* dict of default options for extension,
                    # since it may use template values like %(name)s & %(version)s
                    exts_default_options = app.cfg.get_ref('exts_default_options')

                    for key, val in sorted(ext_options.items()):
                        if key != 'checksums' and val != exts_default_options.get(key):
                            strval = quote_str(val, prefer_single_quotes=True)
                            line = "%s'%s': %s," % (INDENT_4SPACES * 2, key, strval)
                            # fix long lines for list-type values (e.g. patches)
                            if isinstance(val, list) and len(val) > 1:
                                exts_list_lines.append("%s'%s': [" % (INDENT_4SPACES * 2, key))
                                exts_list_lines.extend(make_list_lines(val, indent_level=3))
                                exts_list_lines.append(INDENT_4SPACES * 2 + '],',)
                            else:
                                exts_list_lines.append(line)

                    # if any checksums were collected, inject them for this extension
                    if ext_checksums:
                        if len(ext_checksums) == 1:
                            exts_list_lines.append("%s'checksums': ['%s']," % (INDENT_4SPACES * 2, checksum))
                        else:
                            exts_list_lines.append("%s'checksums': [" % (INDENT_4SPACES * 2))
                            exts_list_lines.extend(make_checksum_lines(ext_checksums, indent_level=3))
                            exts_list_lines.append("%s]," % (INDENT_4SPACES * 2))

                    if ext_options or ext_checksums:
                        exts_list_lines.append("%s})," % INDENT_4SPACES)
                    else:
                        exts_list_lines[-1] += '),'

            exts_list_lines.append(']\n')

            regex = re.compile(r'^exts_list(.|\n)*?\n\]\s*$', re.M)
            ectxt = regex.sub('\n'.join(exts_list_lines), ectxt)

        write_file(ec['spec'], ectxt)
