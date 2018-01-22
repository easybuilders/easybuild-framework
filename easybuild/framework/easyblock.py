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
Generic EasyBuild support for building and installing software.
The EasyBlock class should serve as a base class for all easyblocks.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
:author: Damian Alvarez (Forschungszentrum Juelich GmbH)
"""

import copy
import glob
import inspect
import os
import re
import shutil
import stat
import tempfile
import time
import traceback
from distutils.version import LooseVersion
from vsc.utils import fancylogger
from vsc.utils.missing import get_class_for

import easybuild.tools.environment as env
from easybuild.tools import config, filetools
from easybuild.framework.easyconfig import EASYCONFIGS_PKG_SUBDIR
from easybuild.framework.easyconfig.easyconfig import ITERATE_OPTIONS, EasyConfig, ActiveMNS, get_easyblock_class
from easybuild.framework.easyconfig.easyconfig import get_module_path, letter_dir_for, resolve_template
from easybuild.framework.easyconfig.format.format import INDENT_4SPACES
from easybuild.framework.easyconfig.parser import fetch_parameters_from_easyconfig
from easybuild.framework.easyconfig.tools import get_paths_for
from easybuild.framework.easyconfig.templates import TEMPLATE_NAMES_EASYBLOCK_RUN_STEP
from easybuild.tools.build_details import get_build_stats
from easybuild.tools.build_log import EasyBuildError, dry_run_msg, dry_run_warning, dry_run_set_dirs
from easybuild.tools.build_log import print_error, print_msg, print_warning
from easybuild.tools.config import FORCE_DOWNLOAD_ALL, FORCE_DOWNLOAD_PATCHES, FORCE_DOWNLOAD_SOURCES
from easybuild.tools.config import build_option, build_path, get_log_filename, get_repository, get_repositorypath
from easybuild.tools.config import install_path, log_path, package_path, source_paths
from easybuild.tools.environment import restore_env, sanitize_env
from easybuild.tools.filetools import CHECKSUM_TYPE_MD5, CHECKSUM_TYPE_SHA256
from easybuild.tools.filetools import adjust_permissions, apply_patch, back_up_file, change_dir, convert_name
from easybuild.tools.filetools import compute_checksum, copy_file, derive_alt_pypi_url, diff_files, download_file
from easybuild.tools.filetools import encode_class_name, extract_file, is_alt_pypi_url, mkdir, move_logs, read_file
from easybuild.tools.filetools import remove_file, rmtree2, verify_checksum, weld_paths, write_file
from easybuild.tools.hooks import BUILD_STEP, CLEANUP_STEP, CONFIGURE_STEP, EXTENSIONS_STEP, FETCH_STEP, INSTALL_STEP
from easybuild.tools.hooks import MODULE_STEP, PACKAGE_STEP, PATCH_STEP, PERMISSIONS_STEP, POSTPROC_STEP, PREPARE_STEP
from easybuild.tools.hooks import READY_STEP, SANITYCHECK_STEP, SOURCE_STEP, TEST_STEP, TESTCASES_STEP, run_hook
from easybuild.tools.run import run_cmd
from easybuild.tools.jenkins import write_to_xml
from easybuild.tools.module_generator import ModuleGeneratorLua, ModuleGeneratorTcl, module_generator, dependencies_for
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.modules import Lmod, ROOT_ENV_VAR_NAME_PREFIX, VERSION_ENV_VAR_NAME_PREFIX, DEVEL_ENV_VAR_NAME_PREFIX
from easybuild.tools.modules import invalidate_module_caches_for, get_software_root, get_software_root_env_var_name
from easybuild.tools.modules import get_software_version_env_var_name, modules_tool
from easybuild.tools.package.utilities import package
from easybuild.tools.repository.repository import init_repository
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.systemtools import det_parallelism, use_group
from easybuild.tools.utilities import quote_str, remove_unwanted_chars, trace_msg
from easybuild.tools.version import this_is_easybuild, VERBOSE_VERSION, VERSION


MODULE_ONLY_STEPS = [MODULE_STEP, PREPARE_STEP, READY_STEP, SANITYCHECK_STEP]

# string part of URL for Python packages on PyPI that indicates needs to be rewritten (see derive_alt_pypi_url)
PYPI_PKG_URL_PATTERN = 'pypi.python.org/packages/source/'


_log = fancylogger.getLogger('easyblock')


class EasyBlock(object):
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
            _log.nosupport("Obtained 'extra' value of type '%s' in extra_options, should be 'dict'" % type(extra), '2.0')

        return extra

    #
    # INIT
    #
    def __init__(self, ec, hooks=None):
        """
        Initialize the EasyBlock instance.
        :param ec: a parsed easyconfig file (EasyConfig instance)
        """

        # keep track of original working directory, so we can go back there
        self.orig_workdir = os.getcwd()

        # list of pre- and post-step hooks
        self.hooks = hooks or []

        # list of patch/source files, along with checksums
        self.patches = []
        self.src = []
        self.checksums = []

        # build/install directories
        self.builddir = None
        self.installdir = None  # software
        self.installdir_mod = None  # module file

        # extensions
        self.exts = []
        self.exts_all = None
        self.ext_instances = []
        self.skip = None
        self.module_extra_extensions = ''  # extra stuff for module file required by extensions

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

        # modules footer/header
        self.modules_footer = None
        modules_footer_path = build_option('modules_footer')
        if modules_footer_path is not None:
            self.modules_footer = read_file(modules_footer_path)

        self.modules_header = None
        modules_header_path = build_option('modules_header')
        if modules_header_path is not None:
            self.modules_header = read_file(modules_header_path)

        # determine install subdirectory, based on module name
        self.install_subdir = None

        # indicates whether build should be performed in installation dir
        self.build_in_installdir = self.cfg['buildininstalldir']

        # list of locations to include in RPATH filter used by toolchain
        self.rpath_filter_dirs = []

        # list of locations to include in RPATH used by toolchain
        self.rpath_include_dirs = []

        # logging
        self.log = None
        self.logfile = None
        self.logdebug = build_option('debug')
        self.postmsg = ''  # allow a post message to be set, which can be shown as last output
        self.current_step = None

        # list of loaded modules
        self.loaded_modules = []

        # iterate configure/build/options
        self.iter_idx = 0
        self.iter_opts = {}

        # sanity check fail error messages to report (if any)
        self.sanity_check_fail_msgs = []

        # robot path
        self.robot_path = build_option('robot_path')

        # original module path
        self.orig_modulepath = os.getenv('MODULEPATH')

        # keep track of initial environment we start in, so we can restore it if needed
        self.initial_environ = copy.deepcopy(os.environ)

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

    # INIT/CLOSE LOG
    def _init_log(self):
        """
        Initialize the logger.
        """
        if not self.log is None:
            return

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
        # if checksums are provided as a dict, lookup by source filename as key
        if isinstance(checksums, (list, tuple)):
            if index is not None and index < len(checksums) and (index >= 0 or abs(index) <= len(checksums)):
                return checksums[index]
            else:
                return None
        elif checksums is None:
            return None
        else:
            raise EasyBuildError("Invalid type for checksums (%s), should be list, tuple or None.", type(checksums))

    def fetch_sources(self, sources=None, checksums=None):
        """
        Add a list of source files (can be tarballs, isos, urls).
        All source files will be checked if a file exists (or can be located)

        :param sources: list of sources to fetch (if None, use 'sources' easyconfig parameter)
        :param checksums: list of checksums for sources
        """
        if sources is None:
            sources = self.cfg['sources']
        if checksums is None:
            checksums = self.cfg['checksums']

        for index, source in enumerate(sources):
            extract_cmd, download_filename = None, None

            if isinstance(source, basestring):
                filename = source

            elif isinstance(source, dict):
                source = source.copy()
                filename = source.pop('filename', None)
                extract_cmd = source.pop('extract_cmd', None)
                download_filename = source.pop('download_filename', None)
                if source:
                    raise EasyBuildError("Found one or more unexpected keys in source specification: %s", source)

            elif isinstance(source, (list, tuple)) and len(source) == 2:
                self.log.deprecated("Using a 2-element list/tuple to specify sources is deprecated, "
                                    "use a dictionary with 'filename', 'extract_cmd' keys instead", '4.0')
                filename, extract_cmd = source
            else:
                raise EasyBuildError("Unexpected source spec, not a string or dict: %s", source)

            # check if the sources can be located
            force_download = build_option('force_download') in [FORCE_DOWNLOAD_ALL, FORCE_DOWNLOAD_SOURCES]
            path = self.obtain_file(filename, download_filename=download_filename, force_download=force_download)
            if path:
                self.log.debug('File %s found for source %s' % (path, filename))
                self.src.append({
                    'name': filename,
                    'path': path,
                    'cmd': extract_cmd,
                    'checksum': self.get_checksum_for(checksums, filename=filename, index=index),
                    # always set a finalpath
                    'finalpath': self.builddir,
                })
            else:
                raise EasyBuildError('No file found for source %s', filename)

        self.log.info("Added sources: %s", self.src)

    def fetch_patches(self, patch_specs=None, extension=False, checksums=None):
        """
        Add a list of patches.
        All patches will be checked if a file exists (or can be located)
        """
        if patch_specs is None:
            patch_specs = self.cfg['patches']

        patches = []
        for index, patch_spec in enumerate(patch_specs):

            # check if the patches can be located
            copy_file = False
            suff = None
            level = None
            if isinstance(patch_spec, (list, tuple)):
                if not len(patch_spec) == 2:
                    raise EasyBuildError("Unknown patch specification '%s', only 2-element lists/tuples are supported!",
                                         str(patch_spec))
                patch_file = patch_spec[0]

                # this *must* be of typ int, nothing else
                # no 'isinstance(..., int)', since that would make True/False also acceptable
                if type(patch_spec[1]) == int:
                    level = patch_spec[1]
                elif isinstance(patch_spec[1], basestring):
                    # non-patch files are assumed to be files to copy
                    if not patch_spec[0].endswith('.patch'):
                        copy_file = True
                    suff = patch_spec[1]
                else:
                    raise EasyBuildError("Wrong patch spec '%s', only int/string are supported as 2nd element",
                                         str(patch_spec))
            else:
                patch_file = patch_spec

            force_download = build_option('force_download') in [FORCE_DOWNLOAD_ALL, FORCE_DOWNLOAD_PATCHES]
            path = self.obtain_file(patch_file, extension=extension, force_download=force_download)
            if path:
                self.log.debug('File %s found for patch %s' % (path, patch_spec))
                patchspec = {
                    'name': patch_file,
                    'path': path,
                    'checksum': self.get_checksum_for(checksums, filename=patch_file, index=index),
                }
                if suff:
                    if copy_file:
                        patchspec['copy'] = suff
                    else:
                        patchspec['sourcepath'] = suff
                if level is not None:
                    patchspec['level'] = level

                if extension:
                    patches.append(patchspec)
                else:
                    self.patches.append(patchspec)
            else:
                raise EasyBuildError('No file found for patch %s', patch_spec)

        if extension:
            self.log.info("Fetched extension patches: %s" % patches)
            return [patch['path'] for patch in patches]
        else:
            self.log.info("Added patches: %s" % self.patches)

    def fetch_extension_sources(self, skip_checksums=False):
        """
        Find source file for extensions.
        """
        exts_sources = []
        self.cfg.enable_templating = False
        exts_list = self.cfg['exts_list']
        self.cfg.enable_templating = True

        if self.dry_run:
            self.dry_run_msg("\nList of sources/patches for extensions:")

        for ext in exts_list:
            if (isinstance(ext, list) or isinstance(ext, tuple)) and ext:

                # expected format: (name, version, options (dict))

                ext_name = ext[0]
                if len(ext) == 1:
                    exts_sources.append({'name': ext_name})
                else:
                    ext_version = ext[1]

                    # make sure we grab *raw* dict of default options for extension,
                    # since it may use template values like %(name)s & %(version)s
                    self.cfg.enable_templating = False
                    ext_options = copy.deepcopy(self.cfg['exts_default_options'])
                    self.cfg.enable_templating = True

                    def_src_tmpl = "%(name)s-%(version)s.tar.gz"

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

                    checksums = ext_options.get('checksums', None)

                    if ext_options.get('source_tmpl', None):
                        fn = resolve_template(ext_options['source_tmpl'], ext_src)
                    else:
                        fn = resolve_template(def_src_tmpl, ext_src)

                    if ext_options.get('nosource', None):
                        exts_sources.append(ext_src)
                    else:
                        source_urls = [resolve_template(url, ext_src) for url in ext_options.get('source_urls', [])]
                        force_download = build_option('force_download') in [FORCE_DOWNLOAD_ALL, FORCE_DOWNLOAD_SOURCES]
                        src_fn = self.obtain_file(fn, extension=True, urls=source_urls, force_download=force_download)

                        if src_fn:
                            ext_src.update({'src': src_fn})

                            if not skip_checksums:
                                # report both MD5 and SHA256 checksums, since both are valid default checksum types
                                for checksum_type in (CHECKSUM_TYPE_MD5, CHECKSUM_TYPE_SHA256):
                                    src_checksum = compute_checksum(src_fn, checksum_type=checksum_type)
                                    self.log.info("%s checksum for %s: %s", checksum_type, src_fn, src_checksum)

                                if checksums:
                                    fn_checksum = self.get_checksum_for(checksums, filename=src_fn, index=0)
                                    if verify_checksum(src_fn, fn_checksum):
                                        self.log.info('Checksum for extension source %s verified', fn)
                                    elif build_option('ignore_checksums'):
                                        print_warning("Ignoring failing checksum verification for %s" % fn)
                                    else:
                                        raise EasyBuildError('Checksum verification for extension source %s failed', fn)

                            ext_patches = self.fetch_patches(patch_specs=ext_options.get('patches', []), extension=True)
                            if ext_patches:
                                self.log.debug('Found patches for extension %s: %s' % (ext_name, ext_patches))
                                ext_src.update({'patches': ext_patches})

                                if not skip_checksums:
                                    for patch in ext_patches:
                                        # report both MD5 and SHA256 checksums,
                                        # since both are valid default checksum types
                                        for checksum_type in (CHECKSUM_TYPE_MD5, CHECKSUM_TYPE_SHA256):
                                            checksum = compute_checksum(patch, checksum_type=checksum_type)
                                            self.log.info("%s checksum for %s: %s", checksum_type, patch, checksum)

                                    if checksums:
                                        self.log.debug('Verifying checksums for extension patches...')
                                        for idx, patch in enumerate(ext_patches):
                                            checksum = self.get_checksum_for(checksums[1:], filename=patch, index=idx)
                                            if verify_checksum(patch, checksum):
                                                self.log.info('Checksum for extension patch %s verified', patch)
                                            elif build_option('ignore_checksums'):
                                                print_warning("Ignoring failing checksum verification for %s" % patch)
                                            else:
                                                raise EasyBuildError('Checksum for extension patch %s failed', patch)
                            else:
                                self.log.debug('No patches found for extension %s.' % ext_name)

                            exts_sources.append(ext_src)

                        else:
                            raise EasyBuildError("Source for extension %s not found.", ext)

            elif isinstance(ext, basestring):
                exts_sources.append({'name': ext})

            else:
                raise EasyBuildError("Extension specified in unknown format (not a string/list/tuple)")

        return exts_sources

    def obtain_file(self, filename, extension=False, urls=None, download_filename=None, force_download=False):
        """
        Locate the file with the given name
        - searches in different subdirectories of source path
        - supports fetching file from the web if path is specified as an url (i.e. starts with "http://:")
        :param filename: filename of source
        :param extension: indicates whether locations for extension sources should also be considered
        :param urls: list of source URLs where this file may be available
        :param download_filename: filename with which the file should be downloaded, and then renamed to <filename>
        :force_download: always try to download file, even if it's already available in source path
        """
        res = None
        srcpaths = source_paths()

        # should we download or just try and find it?
        if re.match(r"^(https?|ftp)://", filename):
            # URL detected, so let's try and download it

            url = filename
            filename = url.split('/')[-1]

            # figure out where to download the file to
            filepath = os.path.join(srcpaths[0], letter_dir_for(self.name), self.name)
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

            except IOError, err:
                raise EasyBuildError("Downloading file %s from url %s to %s failed: %s", filename, url, fullpath, err)

        else:
            # try and find file in various locations
            foundfile = None
            failedpaths = []

            # always look first in the dir of the current eb file
            ebpath = [os.path.dirname(self.cfg.path)]

            # always consider robot + easyconfigs install paths as a fall back (e.g. for patch files, test cases, ...)
            common_filepaths = []
            if self.robot_path:
                common_filepaths.extend(self.robot_path)
            common_filepaths.extend(get_paths_for(subdir=EASYCONFIGS_PKG_SUBDIR, robot_path=self.robot_path))

            for path in ebpath + common_filepaths + srcpaths:
                # create list of candidate filepaths
                namepath = os.path.join(path, self.name)
                letterpath = os.path.join(path, letter_dir_for(self.name), self.name)

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

            if foundfile:
                if self.dry_run:
                    self.dry_run_msg("  * %s found at %s", filename, foundfile)
                return foundfile
            else:
                # try and download source files from specified source URLs
                if urls:
                    source_urls = urls
                else:
                    source_urls = []
                source_urls.extend(self.cfg['source_urls'])

                targetdir = os.path.join(srcpaths[0], self.name.lower()[0], self.name)
                mkdir(targetdir, parents=True)

                for url in source_urls:

                    if extension:
                        targetpath = os.path.join(targetdir, "extensions", filename)
                    else:
                        targetpath = os.path.join(targetdir, filename)

                    url_filename = download_filename or filename

                    if isinstance(url, basestring):
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
                            _log.debug("Using alternate PyPI URL for %s: %s", fullurl, alt_url)
                            fullurl = alt_url
                        else:
                            _log.debug("Failed to derive alternate PyPI URL for %s, so retaining the original", fullurl)

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

                        except IOError, err:
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
                    raise EasyBuildError("Couldn't find file %s anywhere, and downloading it didn't work either... "
                                         "Paths attempted (in order): %s ", filename, ', '.join(failedpaths))

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
            while(os.path.isdir(uniq_builddir)):
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
            self.log.info("Changing build dir to %s" % self.installdir)
            self.builddir = self.installdir

            self.log.info("Overriding 'cleanupoldinstall' (to False), 'cleanupoldbuild' (to True) "
                          "and 'keeppreviousinstall' because we're building in the installation directory.")
            # force cleanup before installation
            if build_option('module_only'):
                self.log.debug("Disabling cleanupoldbuild because we run as module-only")
                self.cfg['cleanupoldbuild'] = False
            else:
                self.cfg['cleanupoldbuild'] = True

            self.cfg['keeppreviousinstall'] = False
            # avoid cleanup after installation
            self.cfg['cleanupoldinstall'] = False

        # always make build dir
        self.make_dir(self.builddir, self.cfg['cleanupoldbuild'])

        trace_msg("build dir: %s" % self.builddir)

    def gen_installdir(self):
        """
        Generate the name of the installation directory.
        """
        basepath = install_path()
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
                self.log.info("Keeping old directory %s (hopefully you know what you are doing)" % dir_name)
                return
            elif clean:
                try:
                    rmtree2(dir_name)
                    self.log.info("Removed old directory %s" % dir_name)
                except OSError, err:
                    raise EasyBuildError("Removal of old directory %s failed: %s", dir_name, err)
            elif build_option('module_only'):
                self.log.info("Not touching existing directory %s in module-only mode...", dir_name)
            else:
                self.log.info("Moving existing directory %s out of the way...", dir_name)
                try:
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    backupdir = "%s.%s" % (dir_name, timestamp)
                    shutil.move(dir_name, backupdir)
                    self.log.info("Moved old directory %s to %s" % (dir_name, backupdir))
                except OSError, err:
                    raise EasyBuildError("Moving old directory to backup %s %s failed: %s", dir_name, backupdir, err)

        if dontcreateinstalldir:
            olddir = dir_name
            dir_name = os.path.dirname(dir_name)
            self.log.info("Cleaning only, no actual creation of %s, only verification/defining of dirname %s" % (olddir, dir_name))
            if os.path.exists(dir_name):
                return
            # if not, create dir as usual

        mkdir(dir_name, parents=True)

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

        # load fake module
        fake_mod_data = self.load_fake_module(purge=True)

        header = self.module_generator.MODULE_SHEBANG
        if header:
            header += '\n'

        load_lines = []
        # capture all the EBDEVEL vars
        # these should be all the dependencies and we should load them
        recursive_unload = self.cfg['recursive_module_unload']
        for key in os.environ:
            # legacy support
            if key.startswith(DEVEL_ENV_VAR_NAME_PREFIX):
                if not key.endswith(convert_name(self.name, upper=True)):
                    path = os.environ[key]
                    if os.path.isfile(path):
                        mod_name = path.rsplit(os.path.sep, 1)[-1]
                        load_statement = self.module_generator.load_module(mod_name, recursive_unload=recursive_unload)
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
            output_dir = os.path.join(self.installdir, log_path())
            mkdir(output_dir, parents=True)

        filename = os.path.join(output_dir, ActiveMNS().det_devel_module_filename(self.cfg))
        self.log.debug("Writing devel module to %s" % filename)

        txt = ''.join([header] + load_lines + env_lines)
        write_file(filename, txt)

        # cleanup: unload fake module, remove fake module dir
        self.clean_up_fake_module(fake_mod_data)

    def make_module_dep(self, unload_info=None):
        """
        Make the dependencies for the module file.

        :param unload_info: dictionary with full module names as keys and module name to unload first as corr. value
        """
        mns = ActiveMNS()
        unload_info = unload_info or {}

        # include toolchain as first dependency to load
        tc_mod = None
        if self.toolchain.name != DUMMY_TOOLCHAIN_NAME:
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
        loads = []
        for dep in deps:
            unload_modules = []
            if dep in unload_info:
                unload_modules.append(unload_info[dep])
            loads.append(self.module_generator.load_module(dep, recursive_unload=self.cfg['recursive_module_unload'],
                                                           unload_modules=unload_modules))

        # Force unloading any other modules
        if self.cfg['moduleforceunload']:
            unloads = [self.module_generator.unload_module(d) for d in deps[::-1]]
            return ''.join(unloads) + ''.join(loads)
        else:
            return ''.join(loads)

    def make_module_description(self):
        """
        Create the module description.
        """
        return self.module_generator.get_description()

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
        devel_path = os.path.join(log_path(), ActiveMNS().det_devel_module_filename(self.cfg))
        devel_path_envvar = DEVEL_ENV_VAR_NAME_PREFIX + env_name
        lines.append(self.module_generator.set_environment(devel_path_envvar, devel_path, relpath=True))

        lines.append('\n')
        for (key, value) in self.cfg['modextravars'].items():
            lines.append(self.module_generator.set_environment(key, value))

        for (key, value) in self.cfg['modextrapaths'].items():
            if isinstance(value, basestring):
                value = [value]
            elif not isinstance(value, (tuple, list)):
                raise EasyBuildError("modextrapaths dict value %s (type: %s) is not a list or tuple",
                                     value, type(value))
            lines.append(self.module_generator.prepend_paths(key, value, allow_abs=self.cfg['allow_prepend_abs_path']))

        if self.cfg['modloadmsg']:
            lines.append(self.module_generator.msg_on_load(self.cfg['modloadmsg']))

        if self.cfg['modtclfooter']:
            if isinstance(self.module_generator, ModuleGeneratorTcl):
                self.log.debug("Including Tcl footer in module: %s", self.cfg['modtclfooter'])
                lines.extend([self.cfg['modtclfooter'], '\n'])
            else:
                self.log.warning("Not including footer in Tcl syntax in non-Tcl module file: %s",
                                 self.cfg['modtclfooter'])

        if self.cfg['modluafooter']:
            if isinstance(self.module_generator, ModuleGeneratorLua):
                self.log.debug("Including Lua footer in module: %s", self.cfg['modluafooter'])
                lines.extend([self.cfg['modluafooter'], '\n'])
            else:
                self.log.warning("Not including footer in Lua syntax in non-Lua module file: %s",
                                 self.cfg['modluafooter'])

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
        exts_list = ','.join(['%s-%s' % (ext[0], ext[1]) for ext in self.cfg['exts_list']])
        env_var_name = convert_name(self.name, upper=True)
        lines.append(self.module_generator.set_environment('EBEXTSLIST%s' % env_var_name, exts_list))

        return ''.join(lines)

    def make_module_footer(self):
        """
        Insert a footer section in the module file, primarily meant for contextual information
        """
        footer = [self.module_generator.comment("Built with EasyBuild version %s" % VERBOSE_VERSION)]

        # add extra stuff for extensions (if any)
        if self.cfg['exts_list']:
            footer.append(self.make_module_extra_extensions())

        # include modules footer if one is specified
        if self.modules_footer is not None:
            self.log.debug("Including specified footer into module: '%s'" % self.modules_footer)
            footer.append(self.modules_footer)

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
                # If a mod_path_suffix is being used, we should respect it
                mod_path_suffix = build_option('suffix_modules_path')
                user_modpath = os.path.join(user_modpath, mod_path_suffix)
                user_modpath_exts = ActiveMNS().det_user_modpath_extensions(self.cfg)
                user_modpath_exts = [os.path.join(user_modpath, e) for e in user_modpath_exts]
                self.log.debug("Including user module path extensions returned by naming scheme: %s", user_modpath_exts)
                txt += self.module_generator.use(user_modpath_exts, prefix=self.module_generator.getenv_cmd('HOME'),
                                                 guarded=True)
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
        Generate the environment-variables to run the module.
        """
        requirements = self.make_module_req_guess()

        lines = ['\n']
        if os.path.isdir(self.installdir):
            change_dir(self.installdir)

            if self.dry_run:
                self.dry_run_msg("List of paths that would be searched and added to module file:\n")
                note = "note: glob patterns are not expanded and existence checks "
                note += "for paths are skipped for the statements below due to dry run"
                lines.append(self.module_generator.comment(note))

            for key in sorted(requirements):
                if self.dry_run:
                    self.dry_run_msg(" $%s: %s" % (key, ', '.join(requirements[key])))
                reqs = requirements[key]
                if isinstance(reqs, basestring):
                    self.log.warning("Hoisting string value %s into a list before iterating over it", reqs)
                    reqs = [reqs]

                for path in reqs:
                    # only use glob if the string is non-empty
                    if path and not self.dry_run:
                        paths = sorted(glob.glob(path))
                    else:
                        # empty string is a valid value here (i.e. to prepend the installation prefix, cfr $CUDA_HOME)
                        paths = [path]

                    lines.append(self.module_generator.prepend_paths(key, paths))
            if self.dry_run:
                self.dry_run_msg('')
            change_dir(self.orig_workdir)

        return ''.join(lines)

    def make_module_req_guess(self):
        """
        A dictionary of possible directories to look for.
        """
        return {
            'PATH': ['bin', 'sbin'],
            'LD_LIBRARY_PATH': ['lib', 'lib32', 'lib64'],
            'LIBRARY_PATH': ['lib', 'lib32', 'lib64'],
            'CPATH': ['include'],
            'MANPATH': ['man', os.path.join('share', 'man')],
            'PKG_CONFIG_PATH': [os.path.join(x, 'pkgconfig') for x in ['lib', 'lib32', 'lib64', 'share']],
            'ACLOCAL_PATH': [os.path.join('share', 'aclocal')],
            'CLASSPATH': ['*.jar'],
        }

    def load_module(self, mod_paths=None, purge=True):
        """
        Load module for this software package/version, after purging all currently loaded modules.
        """
        # self.full_mod_name might not be set (e.g. during unit tests)
        if self.full_mod_name is not None:
            if mod_paths is None:
                mod_paths = []
            all_mod_paths = mod_paths + ActiveMNS().det_init_modulepaths(self.cfg)

            # for flat module naming schemes, we can load the module directly;
            # for non-flat (hierarchical) module naming schemes, we may need to load the toolchain module first
            # to update $MODULEPATH such that the module can be loaded using the short module name
            mods = [self.short_mod_name]
            if self.mod_subdir and self.toolchain.name != DUMMY_TOOLCHAIN_NAME:
                mods.insert(0, self.toolchain.det_short_module_name())

            self.modules_tool.load(mods, mod_paths=all_mod_paths, purge=purge, init_env=self.initial_environ)
        else:
            self.log.warning("Not loading module, since self.full_mod_name is not set.")

    def load_fake_module(self, purge=False):
        """
        Create and load fake module.
        """
        # take a copy of the current environment before loading the fake module, so we can restore it
        env = copy.deepcopy(os.environ)

        # create fake module
        fake_mod_path = self.make_module_step(fake=True)

        # load fake module
        self.modules_tool.prepend_module_path(os.path.join(fake_mod_path, self.mod_subdir))
        self.load_module(purge=purge)

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
                rmtree2(os.path.dirname(fake_mod_path))
            except OSError, err:
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

    def prepare_for_extensions(self):
        """
        Also do this before (eg to set the template)
        """
        pass

    def skip_extensions(self):
        """
        Called when self.skip is True
        - use this to detect existing extensions and to remove them from self.exts
        - based on initial R version
        """
        # disabling templating is required here to support legacy string templates like name/version
        self.cfg.enable_templating = False
        exts_filter = self.cfg['exts_filter']
        self.cfg.enable_templating = True

        if not exts_filter or len(exts_filter) == 0:
            raise EasyBuildError("Skipping of extensions, but no exts_filter set in easyconfig")
        elif isinstance(exts_filter, basestring) or len(exts_filter) != 2:
            raise EasyBuildError('exts_filter should be a list or tuple of ("command","input")')
        cmdtmpl = exts_filter[0]
        cmdinputtmpl = exts_filter[1]

        res = []
        for ext in self.exts:
            name = ext['name']
            if 'options' in ext and 'modulename' in ext['options']:
                modname = ext['options']['modulename']
            else:
                modname = name
            tmpldict = {
                'ext_name': modname,
                'ext_version': ext.get('version'),
                'src': ext.get('source'),
            }

            try:
                cmd = cmdtmpl % tmpldict
            except KeyError, err:
                msg = "KeyError occurred on completing extension filter template: %s; "
                msg += "'name'/'version' keys are no longer supported, should use 'ext_name'/'ext_version' instead"
                self.log.nosupport(msg, '2.0')

            if cmdinputtmpl:
                stdin = cmdinputtmpl % tmpldict
                (cmdstdouterr, ec) = run_cmd(cmd, log_all=False, log_ok=False, simple=False, inp=stdin, regexp=False)
            else:
                (cmdstdouterr, ec) = run_cmd(cmd, log_all=False, log_ok=False, simple=False, regexp=False)
            self.log.info("exts_filter result %s %s", cmdstdouterr, ec)
            if ec:
                self.log.info("Not skipping %s" % name)
                self.log.debug("exit code: %s, stdout/err: %s" % (ec, cmdstdouterr))
                res.append(ext)
            else:
                self.log.info("Skipping %s" % name)
        self.exts = res

    #
    # MISCELLANEOUS UTILITY FUNCTIONS
    #

    @property
    def start_dir(self):
        """Start directory in build directory"""
        return self.cfg['start_dir']

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
        if self.start_dir and not build_option('module_only'):
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

    def handle_iterate_opts(self):
        """Handle options relevant during iterated part of build/install procedure."""

        # disable templating in this function, since we're messing about with values in self.cfg
        self.cfg.enable_templating = False

        # handle configure/build/install options that are specified as lists
        # set first element to be used, keep track of list in self.iter_opts
        # this will only be done during first iteration, since after that the options won't be lists anymore
        for opt in ITERATE_OPTIONS:
            # keep track of list, supply first element as first option to handle
            if isinstance(self.cfg[opt], (list, tuple)):
                self.iter_opts[opt] = self.cfg[opt]  # copy
                self.log.debug("Found list for %s: %s", opt, self.iter_opts[opt])

        if self.iter_opts:
            self.log.info("Current iteration index: %s", self.iter_idx)

        # pop first element from all *_list options as next value to use
        for opt in self.iter_opts:
            if len(self.iter_opts[opt]) > self.iter_idx:
                self.cfg[opt] = self.iter_opts[opt][self.iter_idx]
            else:
                self.cfg[opt] = ''  # empty list => empty option as next value
            self.log.debug("Next value for %s: %s" % (opt, str(self.cfg[opt])))

        # re-enable templating before self.cfg values are used
        self.cfg.enable_templating = True

        # prepare for next iteration (if any)
        self.iter_idx += 1

    def restore_iterate_opts(self):
        """Restore options that were iterated over"""
        # disable templating, since we're messing about with values in self.cfg
        self.cfg.enable_templating = False

        for opt in self.iter_opts:
            self.cfg[opt] = self.iter_opts[opt]
            self.log.debug("Restored value of '%s' that was iterated over: %s", opt, self.cfg[opt])

        # re-enable templating before self.cfg values are used
        self.cfg.enable_templating = True

    def det_iter_cnt(self):
        """Determine iteration count based on configure/build/install options that may be lists."""
        iter_cnt = max([1] + [len(self.cfg[opt]) for opt in ITERATE_OPTIONS
                              if isinstance(self.cfg[opt], (list, tuple))])
        return iter_cnt

    #
    # STEP FUNCTIONS
    #
    def check_readiness_step(self):
        """
        Verify if all is ok to start build.
        """
        # set level of parallelism for build
        par = build_option('parallel')
        if self.cfg['parallel']:
            if par is None:
                par = self.cfg['parallel']
                self.log.debug("Desired parallelism specified via 'parallel' easyconfig parameter: %s", par)
            else:
                par = min(int(par), int(self.cfg['parallel']))
                self.log.debug("Desired parallelism: minimum of 'parallel' build option/easyconfig parameter: %s", par)
        else:
            self.log.debug("Desired parallelism specified via 'parallel' build option: %s", par)

        self.cfg['parallel'] = det_parallelism(par=par, maxpar=self.cfg['maxparallel'])
        self.log.info("Setting parallelism: %s" % self.cfg['parallel'])

        # check whether modules are loaded
        loadedmods = self.modules_tool.loaded_modules()
        if len(loadedmods) > 0:
            self.log.warning("Loaded modules detected: %s" % loadedmods)

        # do all dependencies have a toolchain version?
        self.toolchain.add_dependencies(self.cfg.dependencies())
        if not len(self.cfg.dependencies()) == len(self.toolchain.dependencies):
            self.log.debug("dep %s (%s)" % (len(self.cfg.dependencies()), self.cfg.dependencies()))
            self.log.debug("tc.dep %s (%s)" % (len(self.toolchain.dependencies), self.toolchain.dependencies))
            raise EasyBuildError('Not all dependencies have a matching toolchain version')

        # check if the application is not loaded at the moment
        (root, env_var) = get_software_root(self.name, with_env_var=True)
        if root:
            raise EasyBuildError("Module is already loaded (%s is set), installation cannot continue.", env_var)

        # create backup of existing module file (if requested)
        if os.path.exists(self.mod_filepath) and build_option('backup_modules'):
            # backups of modules in Tcl syntax should be hidden to avoid that they're shown in 'module avail';
            # backups of modules in Lua syntax do not need to be hidden:
            # since they don't end in .lua (but in .lua.bak_*) Lmod will not pick them up anymore,
            # which is better than hiding them (since --show-hidden still reveals them)
            hidden = isinstance(self.module_generator, ModuleGeneratorTcl)
            self.mod_file_backup = back_up_file(self.mod_filepath, hidden=hidden)
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
        elif build_option('force') or build_option('rebuild'):
            if os.path.exists(self.mod_filepath):
                self.log.info("Removing existing module file %s", self.mod_filepath)
                remove_file(self.mod_filepath)

    def fetch_step(self, skip_checksums=False):
        """Fetch source files and patches (incl. extensions)."""

        # check EasyBuild version
        easybuild_version = self.cfg['easybuild_version']
        if not easybuild_version:
            self.log.warn("Easyconfig does not specify an EasyBuild-version (key 'easybuild_version')! "
                          "Assuming the latest version")
        else:
            if LooseVersion(easybuild_version) < VERSION:
                self.log.warn("EasyBuild-version %s is older than the currently running one. Proceed with caution!",
                              easybuild_version)
            elif LooseVersion(easybuild_version) > VERSION:
                raise EasyBuildError("EasyBuild-version %s is newer than the currently running one. Aborting!",
                                     easybuild_version)

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
        else:
            self.log.info('no sources provided')

        if self.dry_run:
            # actual list of patches is printed via _obtain_file_dry_run method
            self.dry_run_msg("\nList of patches:")

        # fetch patches
        if self.cfg['patches']:
            if isinstance(self.cfg['checksums'], (list, tuple)):
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
                # report both MD5 and SHA256 checksums, since both are valid default checksum types
                for checksum_type in [CHECKSUM_TYPE_MD5, CHECKSUM_TYPE_SHA256]:
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
        if self.cfg['exts_list']:
            self.exts = self.fetch_extension_sources(skip_checksums=skip_checksums)

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

        self.log.info("Checking dirs that need to be created: %s" % pardirs)
        for pardir in pardirs:
            mkdir(pardir, parents=True)

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
                    raise EasyBuildError("Checksum verification for %s using %s failed.", fil['path'], fil['checksum'])

    def extract_step(self):
        """
        Unpack the source files.
        """
        for src in self.src:
            self.log.info("Unpacking source %s" % src['name'])
            srcdir = extract_file(src['path'], self.builddir, cmd=src['cmd'], extra_options=self.cfg['unpack_options'])
            if srcdir:
                self.src[self.src.index(src)]['finalpath'] = srcdir
            else:
                raise EasyBuildError("Unpacking source %s failed", src['name'])

    def patch_step(self, beginpath=None):
        """
        Apply the patches
        """
        for patch in self.patches:
            self.log.info("Applying patch %s" % patch['name'])
            trace_msg("applying patch %s" % patch['name'])

            # patch source at specified index (first source if not specified)
            srcind = patch.get('source', 0)
            # if patch level is specified, use that (otherwise let apply_patch derive patch level)
            level = patch.get('level', None)
            # determine suffix of source path to apply patch in (if any)
            srcpathsuffix = patch.get('sourcepath', patch.get('copy', ''))
            # determine whether 'patch' file should be copied rather than applied
            copy_patch = 'copy' in patch and not 'sourcepath' in patch

            self.log.debug("Source index: %s; patch level: %s; source path suffix: %s; copy patch: %s",
                           srcind, level, srcpathsuffix, copy)

            if beginpath is None:
                try:
                    beginpath = self.src[srcind]['finalpath']
                    self.log.debug("Determine begin path for patch %s: %s" % (patch['name'], beginpath))
                except IndexError, err:
                    raise EasyBuildError("Can't apply patch %s to source at index %s of list %s: %s",
                                         patch['name'], srcind, self.src, err)
            else:
                self.log.debug("Using specified begin path for patch %s: %s" % (patch['name'], beginpath))

            # detect partial overlap between paths
            src = os.path.abspath(weld_paths(beginpath, srcpathsuffix))
            self.log.debug("Applying patch %s in path %s", patch, src)

            if not apply_patch(patch['path'], src, copy=copy_patch, level=level):
                raise EasyBuildError("Applying patch %s failed", patch['name'])

    def prepare_step(self, start_dir=True):
        """
        Pre-configure step. Set's up the builddir just before starting configure

        :param start_dir: guess start directory based on unpacked sources
        """
        if self.dry_run:
            self.dry_run_msg("Defining build environment, based on toolchain (options) and specified dependencies...\n")

        # clean environment, undefine any unwanted environment variables that may be harmful
        self.cfg['unwanted_env_vars'] = env.unset_env_vars(self.cfg['unwanted_env_vars'])

        # list of paths to include in RPATH filter;
        # only include builddir if we're not building in installation directory
        self.rpath_filter_dirs.append(tempfile.gettempdir())
        if not self.build_in_installdir:
            self.rpath_filter_dirs.append(self.builddir)

        # always include '<installdir>/lib', '<installdir>/lib64', $ORIGIN, $ORIGIN/../lib and $ORIGIN/../lib64
        # $ORIGIN will be resolved by the loader to be the full path to the executable or shared object
        # see also https://linux.die.net/man/8/ld-linux;
        self.rpath_include_dirs.append(os.path.join(self.installdir, 'lib'))
        self.rpath_include_dirs.append(os.path.join(self.installdir, 'lib64'))
        self.rpath_include_dirs.append('$ORIGIN')
        self.rpath_include_dirs.append('$ORIGIN/../lib')
        self.rpath_include_dirs.append('$ORIGIN/../lib64')

        # prepare toolchain: load toolchain module and dependencies, set up build environment
        self.toolchain.prepare(self.cfg['onlytcmod'], silent=self.silent, rpath_filter_dirs=self.rpath_filter_dirs, 
                               rpath_include_dirs=self.rpath_include_dirs)

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
        if self.cfg['runtest']:

            self.log.debug("Trying to execute %s as a command for running unit tests...")
            (out, _) = run_cmd(self.cfg['runtest'], log_all=True, simple=False)

            return out

    def stage_install_step(self):
        """
        Install in a stage directory before actual installation.
        """
        pass

    def install_step(self):
        """Install built software (abstract method)."""
        raise NotImplementedError

    def extensions_step(self, fetch=False):
        """
        After make install, run this.
        - only if variable len(exts_list) > 0
        - optionally: load module that was just created using temp module file
        - find source for extensions, in 'extensions' (and 'packages' for legacy reasons)
        - run extra_extensions
        """
        if len(self.cfg['exts_list']) == 0:
            self.log.debug("No extensions in exts_list")
            return

        # load fake module
        fake_mod_data = None
        if not self.dry_run:
            fake_mod_data = self.load_fake_module(purge=True)

            # also load modules for build dependencies again, since those are not loaded by the fake module
            self.modules_tool.load(dep['short_mod_name'] for dep in self.cfg['builddependencies'])

        self.prepare_for_extensions()

        if fetch:
            self.exts = self.fetch_extension_sources()

        self.exts_all = self.exts[:]  # retain a copy of all extensions, regardless of filtering/skipping

        if self.skip:
            self.skip_extensions()

        # actually install extensions
        self.log.debug("Installing extensions")
        exts_defaultclass = self.cfg['exts_defaultclass']
        exts_classmap = self.cfg['exts_classmap']

        # we really need a default class
        if not exts_defaultclass and fake_mod_data:
            self.clean_up_fake_module(fake_mod_data)
            raise EasyBuildError("ERROR: No default extension class set for %s", self.name)

        # obtain name and module path for default extention class
        if hasattr(exts_defaultclass, '__iter__'):
            self.log.nosupport("Module path for default class is explicitly defined", '2.0')

        elif isinstance(exts_defaultclass, basestring):
            # proper way: derive module path from specified class name
            default_class = exts_defaultclass
            default_class_modpath = get_module_path(default_class, generic=True)

        else:
            raise EasyBuildError("Improper default extension class specification, should be list/tuple or string.")

        # get class instances for all extensions
        exts_cnt = len(self.exts)
        for idx, ext in enumerate(self.exts):
            self.log.debug("Starting extension %s" % ext['name'])
            tup = (ext['name'], ext.get('version', ''), idx+1, exts_cnt)
            print_msg("installing extension %s %s (%d/%d)..." % tup, silent=self.silent)

            # always go back to original work dir to avoid running stuff from a dir that no longer exists
            change_dir(self.orig_workdir)

            cls, inst = None, None
            class_name = encode_class_name(ext['name'])
            mod_path = get_module_path(class_name)

            # try instantiating extension-specific class
            try:
                # no error when importing class fails, in case we run into an existing easyblock
                # with a similar name (e.g., Perl Extension 'GO' vs 'Go' for which 'EB_Go' is available)
                cls = get_easyblock_class(None, name=ext['name'], error_on_failed_import=False,
                                          error_on_missing_easyblock=False)
                self.log.debug("Obtained class %s for extension %s" % (cls, ext['name']))
                if cls is not None:
                    inst = cls(self, ext)
            except (ImportError, NameError), err:
                self.log.debug("Failed to use extension-specific class for extension %s: %s" % (ext['name'], err))

            # alternative attempt: use class specified in class map (if any)
            if inst is None and ext['name'] in exts_classmap:

                class_name = exts_classmap[ext['name']]
                mod_path = get_module_path(class_name)
                try:
                    cls = get_class_for(mod_path, class_name)
                    inst = cls(self, ext)
                except (ImportError, NameError), err:
                    raise EasyBuildError("Failed to load specified class %s for extension %s: %s",
                                         class_name, ext['name'], err)

            # fallback attempt: use default class
            if inst is None:
                try:
                    cls = get_class_for(default_class_modpath, default_class)
                    self.log.debug("Obtained class %s for installing extension %s" % (cls, ext['name']))
                    inst = cls(self, ext)
                    self.log.debug("Installing extension %s with default class %s (from %s)",
                                   ext['name'], default_class, default_class_modpath)
                except (ImportError, NameError), err:
                    raise EasyBuildError("Also failed to use default class %s from %s for extension %s: %s, giving up",
                                         default_class, default_class_modpath, ext['name'], err)
            else:
                self.log.debug("Installing extension %s with class %s (from %s)" % (ext['name'], class_name, mod_path))

            if self.dry_run:
                tup = (ext['name'], ext.get('version', ''), cls.__name__)
                msg = "\n* installing extension %s %s using '%s' easyblock\n" % tup
                self.dry_run_msg(msg)

            self.log.debug("List of loaded modules: %s", self.modules_tool.list())

            # prepare toolchain build environment, but only when not doing a dry run
            # since in that case the build environment is the same as for the parent
            if self.dry_run:
                self.dry_run_msg("defining build environment based on toolchain (options) and dependencies...")
            else:
                # don't reload modules for toolchain, there is no need since they will be loaded already;
                # the (fake) module for the parent software gets loaded before installing extensions
                inst.toolchain.prepare(onlymod=self.cfg['onlytcmod'], silent=True, loadmod=False,
                                       rpath_filter_dirs=self.rpath_filter_dirs)

            # real work
            inst.prerun()
            txt = inst.run()
            if txt:
                self.module_extra_extensions += txt
            inst.postrun()

            # append so we can make us of it later (in sanity_check_step)
            self.ext_instances.append(inst)

        # cleanup (unload fake module, remove fake module dir)
        if fake_mod_data:
            self.clean_up_fake_module(fake_mod_data)

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

    def post_install_step(self):
        """
        Do some postprocessing
        - run post install commands if any were specified
        """
        if self.cfg['postinstallcmds'] is not None:
            # make sure we have a list of commands
            if not isinstance(self.cfg['postinstallcmds'], (list, tuple)):
                raise EasyBuildError("Invalid value for 'postinstallcmds', should be list or tuple of strings.")
            for cmd in self.cfg['postinstallcmds']:
                if not isinstance(cmd, basestring):
                    raise EasyBuildError("Invalid element in 'postinstallcmds', not a string: %s", cmd)
                run_cmd(cmd, simple=True, log_ok=True, log_all=True)

    def sanity_check_step(self, *args, **kwargs):
        """
        Do a sanity check on the installation
        - if *any* of the files/subdirectories in the installation directory listed
          in sanity_check_paths are non-existent (or empty), the sanity check fails
        """
        if self.dry_run:
            self._sanity_check_step_dry_run(*args, **kwargs)
        else:
            self._sanity_check_step(*args, **kwargs)

    def sanity_check_rpath(self, rpath_dirs=None):
        """Sanity check binaries/libraries w.r.t. RPATH linking."""

        fails = []

        # hard reset $LD_LIBRARY_PATH before running RPATH sanity check
        orig_env = env.unset_env_vars(['LD_LIBRARY_PATH'])

        self.log.debug("$LD_LIBRARY_PATH during RPATH sanity check: %s", os.getenv('LD_LIBRARY_PATH', '(empty)'))
        self.log.debug("List of loaded modules: %s", self.modules_tool.list())

        not_found_regex = re.compile('not found', re.M)
        readelf_rpath_regex = re.compile('(RPATH)', re.M)

        if rpath_dirs is None:
            rpath_dirs = ['bin', 'lib', 'lib64']
            self.log.info("Using default subdirs for binaries/libraries to verify RPATH linking: %s", rpath_dirs)
        else:
            self.log.info("Using specified subdirs for binaries/libraries to verify RPATH linking: %s", rpath_dirs)

        for dirpath in [os.path.join(self.installdir, d) for d in rpath_dirs]:
            if os.path.exists(dirpath):
                self.log.debug("Sanity checking RPATH for files in %s", dirpath)

                for path in [os.path.join(dirpath, x) for x in os.listdir(dirpath)]:
                    self.log.debug("Sanity checking RPATH for %s", path)

                    out, ec = run_cmd("file %s" % path, simple=False)
                    if ec:
                        fails.append("Failed to run 'file %s': %s" % (path, out))

                    # only run ldd/readelf on dynamically linked executables/libraries
                    # example output:
                    # ELF 64-bit LSB executable, x86-64, version 1 (SYSV), dynamically linked (uses shared libs), ...
                    # ELF 64-bit LSB shared object, x86-64, version 1 (SYSV), dynamically linked, not stripped
                    if "dynamically linked" in out:
                        # check whether all required libraries are found via 'ldd'
                        out, ec = run_cmd("ldd %s" % path, simple=False)
                        if ec:
                            fail_msg = "Failed to run 'ldd %s': %s" % (path, out)
                            self.log.warning(fail_msg)
                            fails.append(fail_msg)
                        elif not_found_regex.search(out):
                            fail_msg = "One or more required libraries not found for %s: %s" % (path, out)
                            self.log.warning(fail_msg)
                            fails.append(fail_msg)
                        else:
                            self.log.debug("Output of 'ldd %s' checked, looks OK", path)

                        # check whether RPATH section in 'readelf -d' output is there
                        out, ec = run_cmd("readelf -d %s" % path, simple=False)
                        if ec:
                            fail_msg = "Failed to run 'readelf %s': %s" % (path, out)
                            self.log.warning(fail_msg)
                            fails.append(fail_msg)
                        elif not readelf_rpath_regex.search(out):
                            fail_msg = "No '(RPATH)' found in 'readelf -d' output for %s: %s" % (path, out)
                            self.log.warning(fail_msg)
                            fails.append(fail_msg)
                        else:
                            self.log.debug("Output of 'readelf -d %s' checked, looks OK", path)

                    else:
                        self.log.debug("%s is not dynamically linked, so skipping it in RPATH sanity check", path)
            else:
                self.log.debug("Not sanity checking files in non-existing directory %s", dirpath)

        env.restore_env_vars(orig_env)

        return fails

    def _sanity_check_step_common(self, custom_paths, custom_commands):
        """Determine sanity check paths and commands to use."""

        # supported/required keys in for sanity check paths, along with function used to check the paths
        path_keys_and_check = {
            # files must exist and not be a directory
            'files': ('file', lambda fp: os.path.exists(fp) and not os.path.isdir(fp)),
            # directories must exist and be non-empty
            'dirs': ("(non-empty) directory", lambda dp: os.path.isdir(dp) and os.listdir(dp)),
        }

        # prepare sanity check paths
        paths = self.cfg['sanity_check_paths']
        if not paths:
            if custom_paths:
                paths = custom_paths
                self.log.info("Using customized sanity check paths: %s" % paths)
            else:
                paths = {}
                for key in path_keys_and_check:
                    paths.setdefault(key, [])
                paths.update({'dirs': ['bin', ('lib', 'lib64')]})
                self.log.info("Using default sanity check paths: %s" % paths)
        else:
            self.log.info("Using specified sanity check paths: %s" % paths)

        ks = sorted(paths.keys())
        valnottypes = [not isinstance(x, list) for x in paths.values()]
        lenvals = [len(x) for x in paths.values()]
        req_keys = sorted(path_keys_and_check.keys())
        if not ks == req_keys or sum(valnottypes) > 0 or sum(lenvals) == 0:
            raise EasyBuildError("Incorrect format for sanity_check_paths (should (only) have %s keys, "
                                 "values should be lists (at least one non-empty)).", ','.join(req_keys))

        commands = self.cfg['sanity_check_commands']
        if not commands:
            if custom_commands:
                commands = custom_commands
                self.log.info("Using customised sanity check commands: %s" % commands)
            else:
                commands = []
                self.log.info("Using specified sanity check commands: %s" % commands)

        for i, command in enumerate(commands):
            # set command to default. This allows for config files with
            # non-tuple commands
            if isinstance(command, basestring):
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
        """Dry run version of sanity_check_step method."""
        paths, path_keys_and_check, commands = self._sanity_check_step_common(custom_paths, custom_commands)

        for key, (typ, _) in path_keys_and_check.items():
            self.dry_run_msg("Sanity check paths - %s ['%s']", typ, key)
            if paths[key]:
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

        if self.toolchain.use_rpath:
            self.sanity_check_rpath()
        else:
            self.log.debug("Skiping RPATH sanity check")

    def _sanity_check_step(self, custom_paths=None, custom_commands=None, extension=False):
        """Real version of sanity_check_step method."""
        paths, path_keys_and_check, commands = self._sanity_check_step_common(custom_paths, custom_commands)

        # check sanity check paths
        for key, (typ, check_fn) in path_keys_and_check.items():

            for xs in paths[key]:
                if isinstance(xs, basestring):
                    xs = (xs,)
                elif not isinstance(xs, tuple):
                    raise EasyBuildError("Unsupported type '%s' encountered in %s, not a string or tuple",
                                         key, type(xs))
                found = False
                for name in xs:
                    path = os.path.join(self.installdir, name)
                    if check_fn(path):
                        self.log.debug("Sanity check: found %s %s in %s" % (typ, name, self.installdir))
                        found = True
                        break
                    else:
                        self.log.debug("Could not find %s %s in %s" % (typ, name, self.installdir))
                if not found:
                    self.sanity_check_fail_msgs.append("no %s of %s in %s" % (typ, xs, self.installdir))
                    self.log.warning("Sanity check: %s" % self.sanity_check_fail_msgs[-1])

                cand_paths = ' or '.join(["'%s'" % x for x in xs])
                trace_msg("%s %s found: %s" % (typ, cand_paths, ('FAILED', 'OK')[found]))

        fake_mod_data = None
        # only load fake module for non-extensions, and not during dry run
        if not (extension or self.dry_run):
            try:
                # unload all loaded modules before loading fake module
                # this ensures that loading of dependencies is tested, and avoids conflicts with build dependencies
                fake_mod_data = self.load_fake_module(purge=True)
            except EasyBuildError, err:
                self.sanity_check_fail_msgs.append("loading fake module failed: %s" % err)
                self.log.warning("Sanity check: %s" % self.sanity_check_fail_msgs[-1])

        # chdir to installdir (better environment for running tests)
        if os.path.isdir(self.installdir):
            change_dir(self.installdir)

        # run sanity check commands
        for command in commands:

            out, ec = run_cmd(command, simple=False, log_ok=False, log_all=False, trace=False)
            if ec != 0:
                fail_msg = "sanity check command %s exited with code %s (output: %s)" % (command, ec, out)
                self.sanity_check_fail_msgs.append(fail_msg)
                self.log.warning("Sanity check: %s" % self.sanity_check_fail_msgs[-1])
            else:
                self.log.info("sanity check command %s ran successfully! (output: %s)" % (command, out))

            trace_msg("running command '%s': %s" % (command, ('FAILED', 'OK')[ec == 0]))

        if not extension:
            failed_exts = [ext.name for ext in self.ext_instances if not ext.sanity_check_step()]

            if failed_exts:
                self.sanity_check_fail_msgs.append("sanity checks for %s extensions failed!" % failed_exts)
                self.log.warning("Sanity check: %s" % self.sanity_check_fail_msgs[-1])

        # cleanup
        if fake_mod_data:
            self.clean_up_fake_module(fake_mod_data)

        if self.toolchain.use_rpath:
            rpath_fails = self.sanity_check_rpath()
            if rpath_fails:
                self.log.warning("RPATH sanity check failed!")
                self.sanity_check_fail_msgs.extend(rpath_fails)
        else:
            self.log.debug("Skiping RPATH sanity check")

        # pass or fail
        if self.sanity_check_fail_msgs:
            raise EasyBuildError("Sanity check failed: %s", ', '.join(self.sanity_check_fail_msgs))
        else:
            self.log.debug("Sanity check passed!")

    def _set_module_as_default(self):
        """
        Defining default module Version

        sets the default module version except if we are in dry run.
        """
        version = self.full_mod_name.split('/')[-1]
        if self.dry_run:
            dry_run_msg("Marked %s v%s as default version" % (self.name, version))
        else:
            mod_folderpath = os.path.dirname(self.module_generator.get_module_filepath())
            self.module_generator.set_as_default(mod_folderpath, version)

    def cleanup_step(self):
        """
        Cleanup leftover mess: remove/clean build directory

        except when we're building in the installation directory or
        cleanup_builddir is False, otherwise we remove the installation
        """
        if not self.build_in_installdir and build_option('cleanup_builddir'):

            # make sure we're out of the dir we're removing
            change_dir(self.orig_workdir)
            self.log.info("Cleaning up builddir %s (in %s)", self.builddir, os.getcwd())

            try:
                rmtree2(self.builddir)
                base = os.path.dirname(self.builddir)

                # keep removing empty directories until we either find a non-empty one
                # or we end up in the root builddir
                while len(os.listdir(base)) == 0 and not os.path.samefile(base, build_path()):
                    os.rmdir(base)
                    base = os.path.dirname(base)

            except OSError, err:
                raise EasyBuildError("Cleaning up builddir %s failed: %s", self.builddir, err)

        if not build_option('cleanup_builddir'):
            self.log.info("Keeping builddir %s" % self.builddir)

        self.toolchain.cleanup()

        env.restore_env_vars(self.cfg['unwanted_env_vars'])

        self.restore_iterate_opts()

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

        txt = self.module_generator.MODULE_SHEBANG
        if txt:
            txt += '\n'

        if self.modules_header:
            txt += self.modules_header + '\n'

        txt += self.make_module_description()
        txt += self.make_module_group_check()
        txt += self.make_module_dep()
        txt += self.make_module_extend_modpath()
        txt += self.make_module_req()
        txt += self.make_module_extra()
        txt += self.make_module_footer()

        if self.dry_run:
            # only report generating actual module file during dry run, don't mention temporary module files
            if not fake:
                self.dry_run_msg("Generating module file %s, with contents:\n", mod_filepath)
                for line in txt.split('\n'):
                    self.dry_run_msg(INDENT_4SPACES + line)
        else:
            write_file(mod_filepath, txt)
            self.log.info("Module file %s written: %s", mod_filepath, txt)

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

            # invalidate relevant 'module avail'/'module show' cache entries
            # consider both paths: for short module name, and subdir indicated by long module name
            paths = [modpath]
            if self.mod_subdir:
                paths.append(os.path.join(modpath, self.mod_subdir))

            for path in paths:
                invalidate_module_caches_for(path)

            # only update after generating final module file
            if not fake:
                self.modules_tool.update()

            mod_symlink_paths = ActiveMNS().det_module_symlink_paths(self.cfg)
            self.module_generator.create_symlinks(mod_symlink_paths, fake=fake)

            if ActiveMNS().mns.det_make_devel_module() and not fake:
                self.make_devel_module()
            else:
                self.log.info("Skipping devel module...")


        if build_option('set_default_module'):
            self._set_module_as_default()

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
            except EasyBuildError, err:
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
            self.log.debug("Ensuring read permissions for user/group on install dir (recursively)")
            if self.group is None:
                perms |= stat.S_IROTH
                self.log.debug("Also ensuring read permissions for others on install dir (no group specified)")

            umask = build_option('umask')
            if umask is not None:
                # umask is specified as a string, so interpret it first as integer in octal, then take complement (~)
                perms &= ~int(umask, 8)
                self.log.debug("Taking umask '%s' into account when ensuring read permissions to install dir", umask)

            adjust_permissions(self.installdir, perms, add=True, recursive=True, relative=True, ignore_errors=True)
            self.log.info("Successfully added read permissions '%s' recursively on install dir", oct(perms))

    def test_cases_step(self):
        """
        Run provided test cases.
        """
        for test in self.cfg['tests']:
            change_dir(self.orig_workdir)
            if os.path.isabs(test):
                path = test
            else:
                for source_path in source_paths():
                    path = os.path.join(source_path, self.name, test)
                    if os.path.exists(path):
                        break
                if not os.path.exists(path):
                    raise EasyBuildError("Test specifies invalid path: %s", path)

            try:
                self.log.debug("Running test %s" % path)
                run_cmd(path, log_all=True, simple=True)
            except EasyBuildError, err:
                raise EasyBuildError("Running test %s failed: %s", path, err)

    def update_config_template_run_step(self):
        """Update the the easyconfig template dictionary with easyconfig.TEMPLATE_NAMES_EASYBLOCK_RUN_STEP names"""

        for name in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP:
            self.cfg.template_values[name[0]] = str(getattr(self, name[0], None))
        self.cfg.generate_template_values()

    def _skip_step(self, step, skippable):
        """Dedice whether or not to skip the specified step."""
        module_only = build_option('module_only')
        force = build_option('force') or build_option('rebuild')
        skip = False

        # skip step if specified as individual (skippable) step
        if skippable and (self.skip or step in self.cfg['skipsteps']):
            self.log.info("Skipping %s step (skip: %s, skipsteps: %s)", step, self.skip, self.cfg['skipsteps'])
            skip = True

        # skip step when only generating module file
        # * still run sanity check without use of force
        # * always run ready & prepare step to set up toolchain + deps
        elif module_only and not step in MODULE_ONLY_STEPS:
            self.log.info("Skipping %s step (only generating module)", step)
            skip = True

        # allow skipping sanity check too when only generating module and force is used
        elif module_only and step == SANITYCHECK_STEP and force:
            self.log.info("Skipping %s step because of forced module-only mode", step)
            skip = True

        else:
            self.log.debug("Not skipping %s step (skippable: %s, skip: %s, skipsteps: %s, module_only: %s, force: %s",
                           step, skippable, self.skip, self.cfg['skipsteps'], module_only, force)

        return skip

    def run_step(self, step, step_methods):
        """
        Run step, returns false when execution should be stopped
        """
        self.log.info("Starting %s step", step)
        self.update_config_template_run_step()

        run_hook(step, self.hooks, pre_step_hook=True, args=[self])

        for step_method in step_methods:
            self.log.info("Running method %s part of step %s" % ('_'.join(step_method.func_code.co_names), step))

            if self.dry_run:
                self.dry_run_msg("[%s method]", step_method(self).__name__)

                # if an known possible error occurs, just report it and continue
                try:
                    # step_method is a lambda function that takes an EasyBlock instance as an argument,
                    # and returns the actual method, so use () to execute it
                    step_method(self)()
                except Exception as err:
                    if build_option('extended_dry_run_ignore_errors'):
                        dry_run_warning("ignoring error %s" % err, silent=self.silent)
                        self.ignored_errors = True
                    else:
                        raise
                self.dry_run_msg('')
            else:
                # step_method is a lambda function that takes an EasyBlock instance as an argument,
                # and returns the actual method, so use () to execute it
                step_method(self)()

        run_hook(step, self.hooks, post_step_hook=True, args=[self])

        if self.cfg['stop'] == step:
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
            (True, lambda x: env.reset_changes),
            (True, lambda x: x.handle_iterate_opts),
        ]
        ready_step_spec = lambda initial: get_step(READY_STEP, "creating build dir, resetting environment",
                                                   ready_substeps, False, initial=initial)

        source_substeps = [
            (False, lambda x: x.checksum_step),
            (True, lambda x: x.extract_step),
        ]
        source_step_spec = lambda initial: get_step(SOURCE_STEP, "unpacking", source_substeps, True, initial=initial)

        def prepare_step_spec(initial):
            """Return prepare step specification."""
            if initial:
                substeps = [lambda x: x.prepare_step]
            else:
                substeps = [lambda x: x.guess_start_dir]
            return (PREPARE_STEP, 'preparing', substeps, False)

        install_substeps = [
            (False, lambda x: x.stage_install_step),
            (False, lambda x: x.make_installdir),
            (True, lambda x: x.install_step),
        ]
        install_step_spec = lambda init: get_step(INSTALL_STEP, "installing", install_substeps, True, initial=init)

        # format for step specifications: (stop_name: (description, list of functions, skippable))

        # core steps that are part of the iterated loop
        patch_step_spec = (PATCH_STEP, 'patching', [lambda x: x.patch_step], True)
        configure_step_spec = (CONFIGURE_STEP, 'configuring', [lambda x: x.configure_step], True)
        build_step_spec = (BUILD_STEP, 'building', [lambda x: x.build_step], True)
        test_step_spec = (TEST_STEP, 'testing', [lambda x: x.test_step], True)

        # part 1: pre-iteration + first iteration
        steps_part1 = [
            (FETCH_STEP, 'fetching files', [lambda x: x.fetch_step], False),
            ready_step_spec(True),
            source_step_spec(True),
            patch_step_spec,
            prepare_step_spec(True),
            configure_step_spec,
            build_step_spec,
            test_step_spec,
            install_step_spec(True),
        ]
        # part 2: iterated part, from 2nd iteration onwards
        # repeat core procedure again depending on specified iteration count
        # not all parts of all steps need to be rerun (see e.g., ready, prepare)
        steps_part2 = [
            ready_step_spec(False),
            source_step_spec(False),
            patch_step_spec,
            prepare_step_spec(False),
            configure_step_spec,
            build_step_spec,
            test_step_spec,
            install_step_spec(False),
        ] * (iteration_count - 1)
        # part 3: post-iteration part
        steps_part3 = [
            (EXTENSIONS_STEP, 'taking care of extensions', [lambda x: x.extensions_step], False),
            (POSTPROC_STEP, 'postprocessing', [lambda x: x.post_install_step], True),
            (SANITYCHECK_STEP, 'sanity checking', [lambda x: x.sanity_check_step], False),
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
        if self.cfg['stop'] and self.cfg['stop'] == 'cfg':
            return True

        steps = self.get_steps(run_test_cases=run_test_cases, iteration_count=self.det_iter_cnt())

        print_msg("building and installing %s..." % self.full_mod_name, log=self.log, silent=self.silent)
        trace_msg("installation prefix: %s" % self.installdir)
        try:
            for (step_name, descr, step_methods, skippable) in steps:
                if self._skip_step(step_name, skippable):
                    print_msg("%s [skipped]" % descr, log=self.log, silent=self.silent)
                else:
                    if self.dry_run:
                        self.dry_run_msg("%s... [DRY RUN]\n", descr)
                    else:
                        print_msg("%s..." % descr, log=self.log, silent=self.silent)
                    self.current_step = step_name
                    self.run_step(step_name, step_methods)

        except StopException:
            pass

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


def build_and_install_one(ecdict, init_env, hooks=None):
    """
    Build the software
    :param ecdict: dictionary contaning parsed easyconfig + metadata
    :param init_env: original environment (used to reset environment)
    """
    silent = build_option('silent')

    spec = ecdict['spec']
    rawtxt = ecdict['ec'].rawtxt
    name = ecdict['ec']['name']

    dry_run = build_option('extended_dry_run')

    if dry_run:
        dry_run_msg('', silent=silent)
    print_msg("processing EasyBuild easyconfig %s" % spec, log=_log, silent=silent)

    if dry_run:
        # print note on interpreting dry run output (argument is reference to location of dry run messages)
        print_dry_run_note('below', silent=silent)

    # restore original environment, and then sanitize it
    _log.info("Resetting environment")
    filetools.errors_found_in_log = 0
    restore_env(init_env)
    sanitize_env()

    cwd = os.getcwd()

    # load easyblock
    easyblock = build_option('easyblock')
    if not easyblock:
        easyblock = fetch_parameters_from_easyconfig(rawtxt, ['easyblock'])[0]

    try:
        app_class = get_easyblock_class(easyblock, name=name)

        app = app_class(ecdict['ec'], hooks=hooks)
        _log.info("Obtained application instance of for %s (easyblock: %s)" % (name, easyblock))
    except EasyBuildError, err:
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

    # build easyconfig
    errormsg = '(no error)'
    # timing info
    start_time = time.time()
    try:
        run_test_cases = not build_option('skip_test_cases') and app.cfg['tests']
        result = app.run_all_steps(run_test_cases=run_test_cases)
    except EasyBuildError, err:
        first_n = 300
        errormsg = "build failed (first %d chars): %s" % (first_n, err.msg[:first_n])
        _log.warning(errormsg)
        result = False
    app.close_log()

    ended = 'ended'

    # make sure we're back in original directory before we finish up
    change_dir(cwd)

    application_log = None

    # successful (non-dry-run) build
    if result and not dry_run:

        ec_filename = '%s-%s.eb' % (app.name, det_full_ec_version(app.cfg))

        if app.cfg['stop']:
            ended = 'STOPPED'
            if app.builddir is not None:
                new_log_dir = os.path.join(app.builddir, config.log_path())
            else:
                new_log_dir = os.path.dirname(app.logfile)
        else:
            new_log_dir = os.path.join(app.installdir, config.log_path())
            if build_option('read_only_installdir'):
                # temporarily re-enable write permissions for copying log/easyconfig to install dir
                adjust_permissions(new_log_dir, stat.S_IWUSR, add=True, recursive=False)

            # collect build stats
            _log.info("Collecting build stats...")

            buildstats = get_build_stats(app, start_time, build_option('command_line'))
            _log.info("Build stats: %s" % buildstats)

            if build_option("minimal_toolchains"):
                # for reproducability we dump out the parsed easyconfig since the contents are affected when
                # --minimal-toolchains (and --use-existing-modules) is used
                # TODO --try-toolchain needs to be fixed so this doesn't play havoc with it's usability
                reprod_spec = os.path.join(new_log_dir, 'reprod', ec_filename)
                app.cfg.dump(reprod_spec)
                _log.debug("Dumped easyconfig tweaked via --minimal-toolchains to %s", reprod_spec)

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
            except EasyBuildError, err:
                _log.warn("Unable to commit easyconfig to repository: %s", err)

        # cleanup logs
        log_fn = os.path.basename(get_log_filename(app.name, app.version))
        application_log = os.path.join(new_log_dir, log_fn)
        move_logs(app.logfile, application_log)

        newspec = os.path.join(new_log_dir, ec_filename)
        copy_file(spec, newspec)
        _log.debug("Copied easyconfig file %s to %s", spec, newspec)

        # copy patches
        for patch in app.patches:
            target = os.path.join(new_log_dir, os.path.basename(patch['path']))
            copy_file(patch['path'], target)
            _log.debug("Copied patch %s to %s", patch['path'], target)

        if build_option('read_only_installdir'):
            # take away user write permissions (again)
            adjust_permissions(new_log_dir, stat.S_IWUSR, add=False, recursive=False)

    if result:
        success = True
        summary = 'COMPLETED'
        succ = 'successfully'
    else:
        # build failed
        success = False
        summary = 'FAILED'

        build_dir = ''
        if app.builddir:
            build_dir = " (build directory: %s)" % (app.builddir)
        succ = "unsuccessfully%s: %s" % (build_dir, errormsg)

        # cleanup logs
        app.close_log()
        application_log = app.logfile

    print_msg("%s: Installation %s %s" % (summary, ended, succ), log=_log, silent=silent)

    # check for errors
    if filetools.errors_found_in_log > 0:
        print_msg("WARNING: %d possible error(s) were detected in the "
                  "build logs, please verify the build." % filetools.errors_found_in_log,
                  _log, silent=silent)

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

    del app

    return (success, application_log, errormsg)


def get_easyblock_instance(ecdict):
    """
    Get an instance for this easyconfig
    :param easyconfig: parsed easyconfig (EasyConfig instance)

    returns an instance of EasyBlock (or subclass thereof)
    """
    spec = ecdict['spec']
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

    base_dir = os.getcwd()

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
    """
    StopException class definition.
    """
    pass


def inject_checksums(ecs, checksum_type):
    """
    Inject checksums of given type in specified easyconfig files

    :param ecs: list of EasyConfig instances to inject checksums into corresponding files
    :param checksum_type: type of checksum to use
    """
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
        print_msg("backup of easyconfig file saved to %s..." % ec_backup, log=_log)

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
            for fn, checksum in checksums:
                checksum_lines.append("%s'%s',  # %s" % (INDENT_4SPACES, checksum, fn))
            checksum_lines.append(']\n')

        checksums_txt = '\n'.join(checksum_lines)

        if app.cfg['checksums']:
            regex = re.compile(r'^checksums(?:.|\n)+?\]\s*$', re.M)
            ectxt = regex.sub(checksums_txt, ectxt)

        # it is possible no sources (and hence patches) are listed, e.g. for 'bundle' easyconfigs
        elif app.src:
            placeholder = '# PLACEHOLDER FOR SOURCES/PATCHES WITH CHECKSUMS'

            # grab raw lines for source_urls, sources, patches
            raw = {}
            for key in ['patches', 'source_urls', 'sources']:
                regex = re.compile(r'^(%s(?:.|\n)*?\])\s*$' % key, re.M)
                res = regex.search(ectxt)
                if res:
                    raw[key] = res.group(0).strip() + '\n'
                    ectxt = regex.sub(placeholder, ectxt)

            # inject combination of source_urls/sources/patches/checksums into easyconfig
            # by replacing first occurence of placeholder that was put in place
            sources_raw = raw.get('sources', '')
            source_urls_raw = raw.get('source_urls', '')
            patches_raw = raw.get('patches', '')
            regex = re.compile(placeholder + '\n', re.M)
            ectxt = regex.sub(source_urls_raw + sources_raw + patches_raw + checksums_txt + '\n', ectxt, count=1)

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
                if ext.keys() == ['name']:
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
                        patch_fn = os.path.basename(ext_patch)
                        checksum = compute_checksum(ext_patch, checksum_type)
                        print_msg(" * %s: %s" % (patch_fn, checksum), log=_log)
                        ext_checksums.append((patch_fn, checksum))

                    exts_list_lines.append("%s(%s, %s," % (INDENT_4SPACES, ext_name, ext_version))
                    if ext_options or ext_checksums:
                        exts_list_lines[-1] += ' {'

                    # make sure we grab *raw* dict of default options for extension,
                    # since it may use template values like %(name)s & %(version)s
                    app.cfg.enable_templating = False
                    exts_default_options = app.cfg['exts_default_options']
                    app.cfg.enable_templating = True

                    for key, val in sorted(ext_options.items()):
                        if key != 'checksums' and val != exts_default_options.get(key):
                            val = quote_str(val, prefer_single_quotes=True)
                            exts_list_lines.append("%s'%s': %s," % (INDENT_4SPACES * 2, key, val))

                    # if any checksums were collected, inject them for this extension
                    if ext_checksums:
                        if len(ext_checksums) == 1:
                            exts_list_lines.append("%s'checksums': ['%s']," % (INDENT_4SPACES * 2, checksum))
                        else:
                            exts_list_lines.append("%s'checksums': [" % (INDENT_4SPACES * 2))
                            for fn, checksum in ext_checksums:
                                exts_list_lines.append("%s'%s',  # %s" % (INDENT_4SPACES * 3, checksum, fn))
                            exts_list_lines.append("%s]," % (INDENT_4SPACES * 2))

                    if ext_options or ext_checksums:
                        exts_list_lines.append("%s})," % INDENT_4SPACES)
                    else:
                        exts_list_lines[-1] += '),'

            exts_list_lines.append(']\n')

            regex = re.compile(r'^exts_list(.|\n)*?\n\]\s*$', re.M)
            ectxt = regex.sub('\n'.join(exts_list_lines), ectxt)

        write_file(ec['spec'], ectxt)
