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
Generic EasyBuild support for building and installing software.
The EasyBlock class should serve as a base class for all easyblocks.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
@author: Fotis Georgatos (University of Luxembourg)
"""

import copy
import grp  # @UnresolvedImport
import re
import os
import shutil
import stat
import sys
import time
import traceback
import urllib
from distutils.version import LooseVersion
from vsc import fancylogger
from vsc.utils.missing import nub

import easybuild.tools.environment as env
from easybuild.tools import config, filetools
from easybuild.framework.easyconfig.default import get_easyconfig_parameter_default
from easybuild.framework.easyconfig.easyconfig import EasyConfig, ITERATE_OPTIONS, resolve_template
from easybuild.framework.easyconfig.tools import get_paths_for, resolve_dependencies
from easybuild.framework.easyconfig.templates import TEMPLATE_NAMES_EASYBLOCK_RUN_STEP
from easybuild.tools.build_details import get_build_stats
from easybuild.tools.build_log import EasyBuildError, print_error, print_msg
from easybuild.tools.config import build_path, get_log_filename, get_repository, get_repositorypath, install_path
from easybuild.tools.config import log_path, module_classes, read_only_installdir, source_paths
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import DEFAULT_CHECKSUM
from easybuild.tools.filetools import adjust_permissions, apply_patch, convert_name
from easybuild.tools.filetools import download_file, encode_class_name, extract_file, read_file, rmtree2, run_cmd
from easybuild.tools.filetools import decode_class_name, write_file, compute_checksum, verify_checksum
from easybuild.tools.jenkins import write_to_xml
from easybuild.tools.module_generator import GENERAL_CLASS, ModuleGenerator
from easybuild.tools.module_generator import det_full_module_name, det_devel_module_filename
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.modules import ROOT_ENV_VAR_NAME_PREFIX, VERSION_ENV_VAR_NAME_PREFIX, DEVEL_ENV_VAR_NAME_PREFIX
from easybuild.tools.modules import get_software_root, modules_tool
from easybuild.tools.repository import init_repository
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.systemtools import get_avail_core_count
from easybuild.tools.utilities import remove_unwanted_chars
from easybuild.tools.version import this_is_easybuild, VERBOSE_VERSION, VERSION

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
        if extra == None:
            return []
        else:
            return extra

    #
    # INIT
    #
    def __init__(self, path, build_options=None, build_specs=None):
        """
        Initialize the EasyBlock instance.
        @param path: path to easyconfig file
        @param build_options: dictionary of build options, e.g. robot_path, validate_ec, check_osdeps, ... (default: {})
        @param build_specs: dictionary of build specifications (see EasyConfig class, default: {})
        """
        if build_options is None:
            build_options = {}

        # list of patch/source files, along with checksums
        self.patches = []
        self.src = []
        self.checksums = []

        # build/install directories
        self.builddir = None
        self.installdir = None

        # extensions
        self.exts = None
        self.exts_all = None
        self.ext_instances = []
        self.skip = None
        self.module_extra_extensions = ''  # extra stuff for module file required by extensions

        # modules interface with default MODULEPATH
        self.modules_tool = modules_tool()
        # module generator
        self.moduleGenerator = None

        # modules footer
        self.modules_footer = None
        modules_footer_path = build_options.get('modules_footer', None)
        if modules_footer_path is not None:
            self.modules_footer = read_file(modules_footer_path)

        # recursive unloading in modules
        self.recursive_mod_unload = build_options.get('recursive_mod_unload', False)

        # easyconfig for this application
        all_stops = [x[0] for x in self.get_steps()]
        ec_build_options = copy.deepcopy(build_options)
        ec_build_options.update({
            'valid_module_classes': module_classes(),
            'valid_stops': all_stops,
            'validate': build_options.get('validate_ec', True),
        })
        extra = self.extra_options()
        self.cfg = EasyConfig(path, extra_options=extra, build_options=ec_build_options, build_specs=build_specs)

        # indicates whether build should be performed in installation dir
        self.build_in_installdir = self.cfg['buildininstalldir']

        # logging
        self.log = None
        self.logfile = None
        self.logdebug = build_options.get('debug', False)
        self.postmsg = ''  # allow a post message to be set, which can be shown as last output

        # original environ will be set later
        self.orig_environ = {}

        # list of loaded modules
        self.loaded_modules = []

        # robot path
        self.robot_path = build_options.get('robot_path', None)

        # original module path
        self.orig_modulepath = os.getenv('MODULEPATH')

        # keep track of original environment, so we restore it if needed
        self.orig_environ = copy.deepcopy(os.environ)

        # at the end of __init__, initialise the logging
        self._init_log()

        # iterate configure/build/options
        self.iter_opts = {}

        # sanity check fail error messages to report (if any)
        self.sanity_check_fail_msgs = []

        # should we keep quiet?
        self.silent = build_options.get('silent', False)

        # full module name to generate
        self.mod_name = None

        self.log.info("Init completed for application name %s version %s" % (self.name, self.version))


    # INIT/CLOSE LOG
    def _init_log(self):
        """
        Initialize the logger.
        """
        if not self.log is None:
            return

        self.logfile = get_log_filename(self.name, self.version, add_salt=True)
        fancylogger.logToFile(self.logfile)

        self.log = fancylogger.getLogger(name=self.__class__.__name__, fname=False)

        self.log.info(this_is_easybuild())


    def close_log(self):
        """
        Shutdown the logger.
        """
        self.log.info("Closing log for application name %s version %s" % (self.name, self.version))
        fancylogger.logToFile(self.logfile, enable=False)


    #
    # FETCH UTILITY FUNCTIONS
    #

    def get_checksum_for(self, checksums, filename=None, index=None):
        """
        Obtain checksum for given filename.

        @param checksums: a list or tuple of checksums (or None)
        @param filename: name of the file to obtain checksum for
        @param index: index of file in list
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
            self.log.error("Invalid type for checksums (%s), should be list, tuple or None." % type(checksums))

    def fetch_sources(self, list_of_sources, checksums=None):
        """
        Add a list of source files (can be tarballs, isos, urls).
        All source files will be checked if a file exists (or can be located)
        """

        for index, src_entry in enumerate(list_of_sources):
            if isinstance(src_entry, (list, tuple)):
                cmd = src_entry[1]
                source = src_entry[0]
            elif isinstance(src_entry, basestring):
                cmd = None
                source = src_entry

            # check if the sources can be located
            path = self.obtain_file(source)
            if path:
                self.log.debug('File %s found for source %s' % (path, source))
                self.src.append({
                    'name': source,
                    'path': path,
                    'cmd': cmd,
                    'checksum': self.get_checksum_for(checksums, filename=source, index=index),
                    # always set a finalpath
                    'finalpath': self.builddir,
                })
            else:
                self.log.error('No file found for source %s' % source)

        self.log.info("Added sources: %s" % self.src)

    def fetch_patches(self, list_of_patches, extension=False, checksums=None):
        """
        Add a list of patches.
        All patches will be checked if a file exists (or can be located)
        """

        patches = []
        for index, patch_entry in enumerate(list_of_patches):

            # check if the patches can be located
            copy_file = False
            suff = None
            level = None
            if isinstance(patch_entry, (list, tuple)):
                if not len(patch_entry) == 2:
                    self.log.error("Unknown patch specification '%s', only two-element lists/tuples are supported!" % patch_entry)
                pf = patch_entry[0]

                if isinstance(patch_entry[1], int):
                    level = patch_entry[1]
                elif isinstance(patch_entry[1], basestring):
                    # non-patch files are assumed to be files to copy
                    if not patch_entry[0].endswith('.patch'):
                        copy_file = True
                    suff = patch_entry[1]
                else:
                    self.log.error("Wrong patch specification '%s', only int and string are supported as second element!" % patch_entry)
            else:
                pf = patch_entry

            path = self.obtain_file(pf, extension=extension)
            if path:
                self.log.debug('File %s found for patch %s' % (path, patch_entry))
                patchspec = {
                    'name': pf,
                    'path': path,
                    'checksum': self.get_checksum_for(checksums, filename=pf, index=index),
                }
                if suff:
                    if copy_file:
                        patchspec['copy'] = suff
                    else:
                        patchspec['sourcepath'] = suff
                if level:
                    patchspec['level'] = level

                if extension:
                    patches.append(patchspec)
                else:
                    self.patches.append(patchspec)
            else:
                self.log.error('No file found for patch %s' % patch_entry)

        if extension:
            self.log.info("Fetched extension patches: %s" % patches)
            return [patch['path'] for patch in patches]
        else:
            self.log.info("Added patches: %s" % self.patches)

    def fetch_extension_sources(self):
        """
        Find source file for extensions.
        """
        exts_sources = []
        self.cfg.enable_templating = False
        exts_list = self.cfg['exts_list']
        self.cfg.enable_templating = True
        for ext in exts_list:
            if (isinstance(ext, list) or isinstance(ext, tuple)) and ext:

                # expected format: (name, version, options (dict))

                ext_name = ext[0]
                if len(ext) == 1:
                    exts_sources.append({'name': ext_name})
                else:
                    ext_version = ext[1]
                    ext_options = {}

                    def_src_tmpl = "%(name)s-%(version)s.tar.gz"

                    if len(ext) == 3:
                        ext_options = ext[2]

                        if not isinstance(ext_options, dict):
                            self.log.error("Unexpected type (non-dict) for 3rd element of %s" % ext)
                    elif len(ext) > 3:
                        self.log.error('Extension specified in unknown format (list/tuple too long)')

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
                        src_fn = self.obtain_file(fn, extension=True, urls=source_urls)

                        if src_fn:
                            ext_src.update({'src': src_fn})

                            if checksums:
                                fn_checksum = self.get_checksum_for(checksums, filename=src_fn, index=0)
                                if verify_checksum(src_fn, fn_checksum):
                                    self.log.info('Checksum for ext source %s verified' % fn)
                                else:
                                    self.log.error('Checksum for ext source %s failed' % fn)

                            ext_patches = self.fetch_patches(ext_options.get('patches', []), extension=True)
                            if ext_patches:
                                self.log.debug('Found patches for extension %s: %s' % (ext_name, ext_patches))
                                ext_src.update({'patches': ext_patches})

                                if checksums:
                                    self.log.debug('Verifying checksums for extension patches...')
                                    for index, ext_patch in enumerate(ext_patches):
                                        checksum = self.get_checksum_for(checksums[1:], filename=ext_patch, index=index)
                                        if verify_checksum(ext_patch, checksum):
                                            self.log.info('Checksum for extension patch %s verified' % ext_patch)
                                        else:
                                            self.log.error('Checksum for extension patch %s failed' % ext_patch)
                            else:
                                self.log.debug('No patches found for extension %s.' % ext_name)

                            exts_sources.append(ext_src)

                        else:
                            self.log.error("Source for extension %s not found.")

            elif isinstance(ext, basestring):
                exts_sources.append({'name': ext})

            else:
                self.log.error("Extension specified in unknown format (not a string/list/tuple)")

        return exts_sources

    def obtain_file(self, filename, extension=False, urls=None):
        """
        Locate the file with the given name
        - searches in different subdirectories of source path
        - supports fetching file from the web if path is specified as an url (i.e. starts with "http://:")
        """
        srcpaths = source_paths()

        # should we download or just try and find it?
        if filename.startswith("http://") or filename.startswith("ftp://"):

            # URL detected, so let's try and download it

            url = filename
            filename = url.split('/')[-1]

            # figure out where to download the file to
            for srcpath in srcpaths:
                filepath = os.path.join(srcpath, self.name[0].lower(), self.name)
                if extension:
                    filepath = os.path.join(filepath, "extensions")
                if os.path.isdir(filepath):
                    self.log.info("Going to try and download file to %s" % filepath)
                    break

            # if no path was found, let's just create it in the last source path
            if not os.path.isdir(filepath):
                try:
                    self.log.info("No path found to download file to, so creating it: %s" % filepath)
                    os.makedirs(filepath)
                except OSError, err:
                    self.log.error("Failed to create %s: %s" % (filepath, err))

            try:
                fullpath = os.path.join(filepath, filename)

                # only download when it's not there yet
                if os.path.exists(fullpath):
                    self.log.info("Found file %s at %s, no need to download it." % (filename, filepath))
                    return fullpath

                else:
                    if download_file(filename, url, fullpath):
                        return fullpath

            except IOError, err:
                self.log.exception("Downloading file %s from url %s to %s failed: %s" % (filename, url, fullpath, err))

        else:
            # try and find file in various locations
            foundfile = None
            failedpaths = []

            # always look first in the dir of the current eb file
            ebpath = [os.path.dirname(self.cfg.path)]

            # always consider robot + easyconfigs install paths as a fall back (e.g. for patch files, test cases, ...)
            common_filepaths = []
            if self.robot_path is not None:
                common_filepaths.extend(self.robot_path)
            common_filepaths.extend(get_paths_for("easyconfigs", robot_path=self.robot_path))

            for path in ebpath + common_filepaths + srcpaths:
                # create list of candidate filepaths
                namepath = os.path.join(path, self.name)
                letterpath = os.path.join(path, self.name.lower()[0], self.name)

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
                            self.log.info("Found file %s at %s" % (filename, fp))
                            foundfile = os.path.abspath(fp)
                            break  # no need to try further
                        else:
                            failedpaths.append(fp)

                if foundfile:
                    break  # no need to try other source paths

            if foundfile:
                return foundfile
            else:
                # try and download source files from specified source URLs
                if urls:
                    source_urls = urls
                else:
                    source_urls = []
                source_urls.extend(self.cfg['source_urls'])

                targetdir = os.path.join(srcpaths[0], self.name.lower()[0], self.name)
                if not os.path.isdir(targetdir):
                    try:
                        os.makedirs(targetdir)
                    except OSError, err:
                        self.log.error("Failed to create directory %s to download source file %s into" % (targetdir, filename))

                for url in source_urls:

                    if extension:
                        targetpath = os.path.join(targetdir, "extensions", filename)
                    else:
                        targetpath = os.path.join(targetdir, filename)

                    if isinstance(url, basestring):
                        if url[-1] in ['=', '/']:
                            fullurl = "%s%s" % (url, filename)
                        else:
                            fullurl = "%s/%s" % (url, filename)
                    elif isinstance(url, tuple):
                        # URLs that require a suffix, e.g., SourceForge download links
                        # e.g. http://sourceforge.net/projects/math-atlas/files/Stable/3.8.4/atlas3.8.4.tar.bz2/download
                        fullurl = "%s/%s/%s" % (url[0], filename, url[1])
                    else:
                        self.log.warning("Source URL %s is of unknown type, so ignoring it." % url)
                        continue

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

                self.log.error("Couldn't find file %s anywhere, and downloading it didn't work either...\nPaths attempted (in order): %s " % (filename, ', '.join(failedpaths)))


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

    #
    # DIRECTORY UTILITY FUNCTIONS
    #
    def gen_builddir(self):
        """Generate the (unique) name for the builddir"""
        clean_name = remove_unwanted_chars(self.name)

        # if a toolchain version starts with a -, remove the - so prevent a -- in the path name
        tcversion = self.toolchain.version.lstrip('-')
        lastdir = "%s%s-%s%s" % (self.cfg['versionprefix'], self.toolchain.name, tcversion, self.cfg['versionsuffix'])

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
                self.log.error("self.builddir not set, make sure gen_builddir() is called first!")
            self.log.debug("Creating the build directory %s (cleanup: %s)" % (self.builddir, self.cfg['cleanupoldbuild']))
        else:
            self.log.info("Changing build dir to %s" % self.installdir)
            self.builddir = self.installdir

            self.log.info("Overriding 'cleanupoldinstall' (to False), 'cleanupoldbuild' (to True) " \
                          "and 'keeppreviousinstall' because we're building in the installation directory.")
            # force cleanup before installation
            self.cfg['cleanupoldbuild'] = True
            self.cfg['keeppreviousinstall'] = False
            # avoid cleanup after installation
            self.cfg['cleanupoldinstall'] = False

        # always make build dir
        self.make_dir(self.builddir, self.cfg['cleanupoldbuild'])

    def gen_installdir(self):
        """
        Generate the name of the installation directory.
        """
        basepath = install_path()

        if basepath:
            installdir = os.path.join(basepath, self.mod_name)
            self.installdir = os.path.abspath(installdir)
        else:
            self.log.error("Can't set installation directory")

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

    def make_dir(self, dirName, clean, dontcreateinstalldir=False):
        """
        Create the directory.
        """
        if os.path.exists(dirName):
            self.log.info("Found old directory %s" % dirName)
            if self.cfg['keeppreviousinstall']:
                self.log.info("Keeping old directory %s (hopefully you know what you are doing)" % dirName)
                return
            elif clean:
                try:
                    rmtree2(dirName)
                    self.log.info("Removed old directory %s" % dirName)
                except OSError, err:
                    self.log.exception("Removal of old directory %s failed: %s" % (dirName, err))
            else:
                try:
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    backupdir = "%s.%s" % (dirName, timestamp)
                    shutil.move(dirName, backupdir)
                    self.log.info("Moved old directory %s to %s" % (dirName, backupdir))
                except OSError, err:
                    self.log.exception("Moving old directory to backup %s %s failed: %s" % (dirName, backupdir, err))

        if dontcreateinstalldir:
            olddir = dirName
            dirName = os.path.dirname(dirName)
            self.log.info("Cleaning only, no actual creation of %s, only verification/creation of dirname %s" % (olddir, dirName))
            if os.path.exists(dirName):
                return
            # if not, create dir as usual

        try:
            os.makedirs(dirName)
        except OSError, err:
            self.log.exception("Can't create directory %s: %s" % (dirName, err))

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

        mod_gen = ModuleGenerator(self)
        header = "#%Module\n"

        env_txt = ""
        for (key, val) in env.changes.items():
            # check if non-empty string
            # TODO: add unset for empty vars?
            if val.strip():
                env_txt += mod_gen.set_environment(key, val)

        load_txt = ""
        # capture all the EBDEVEL vars
        # these should be all the dependencies and we should load them
        for key in os.environ:
            # legacy support
            if key.startswith(DEVEL_ENV_VAR_NAME_PREFIX) or key.startswith("SOFTDEVEL"):
                if key.startswith("SOFTDEVEL"):
                    self.log.deprecated("Environment variable SOFTDEVEL* being relied on", "2.0")
                if not key.endswith(convert_name(self.name, upper=True)):
                    path = os.environ[key]
                    if os.path.isfile(path):
                        mod_name = path.rsplit(os.path.sep, 1)[-1]
                        load_txt += mod_gen.load_module(mod_name, recursive_unload=self.recursive_mod_unload)

        if create_in_builddir:
            output_dir = self.builddir
        else:
            output_dir = os.path.join(self.installdir, log_path())
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

        filename = os.path.join(output_dir, det_devel_module_filename(self.cfg))
        self.log.debug("Writing devel module to %s" % filename)

        write_file(filename, header + load_txt + env_txt)

        # cleanup: unload fake module, remove fake module dir
        self.clean_up_fake_module(fake_mod_data)

    def make_module_dep(self):
        """
        Make the dependencies for the module file.
        """
        load = unload = ''

        # Load toolchain
        if self.toolchain.name != DUMMY_TOOLCHAIN_NAME:
            tc_mod_name = self.toolchain.det_module_name()
            load += self.moduleGenerator.load_module(tc_mod_name, recursive_unload=self.recursive_mod_unload)
            unload += self.moduleGenerator.unload_module(tc_mod_name)

        # Load dependencies
        builddeps = self.cfg.builddependencies()
        for dep in self.toolchain.dependencies:
            if not dep in builddeps:
                dep_mod_name = det_full_module_name(dep)
                self.log.debug("Adding %s as a module dependency" % dep_mod_name)
                load += self.moduleGenerator.load_module(dep_mod_name, recursive_unload=self.recursive_mod_unload)
                unload += self.moduleGenerator.unload_module(dep_mod_name)
            else:
                self.log.debug("Skipping build dependency %s" % str(dep))

        # Force unloading any other modules
        if self.cfg['moduleforceunload']:
            return unload + load
        else:
            return load

    def make_module_description(self):
        """
        Create the module description.
        """
        return self.moduleGenerator.get_description()

    def make_module_extra(self):
        """
        Sets optional variables (EBROOT, MPI tuning variables).
        """
        txt = "\n"

        # EBROOT + EBVERSION + EBDEVEL
        environment_name = convert_name(self.name, upper=True)
        txt += self.moduleGenerator.set_environment(ROOT_ENV_VAR_NAME_PREFIX + environment_name, "$root")
        txt += self.moduleGenerator.set_environment(VERSION_ENV_VAR_NAME_PREFIX + environment_name, self.version)
        devel_path = os.path.join("$root", log_path(), det_devel_module_filename(self.cfg))
        txt += self.moduleGenerator.set_environment(DEVEL_ENV_VAR_NAME_PREFIX + environment_name, devel_path)

        txt += "\n"
        for (key, value) in self.cfg['modextravars'].items():
            txt += self.moduleGenerator.set_environment(key, value)
        for (key, value) in self.cfg['modextrapaths'].items():
            if isinstance(value, basestring):
                value = [value]
            elif not isinstance(value, (tuple, list)):
                self.log.error("modextrapaths dict value %s (type: %s) is not a list or tuple" % (value, type(value)))
            txt += self.moduleGenerator.prepend_paths(key, value)

        self.log.debug("make_module_extra added this: %s" % txt)

        return txt

    def make_module_extra_extensions(self):
        """
        Sets optional variables for extensions.
        """
        # add stuff specific to individual extensions
        txt = self.module_extra_extensions

        # set environment variable that specifies list of extensions
        if self.exts_all:
            exts_list = ','.join(['%s-%s' % (ext['name'], ext.get('version', '')) for ext in self.exts_all])
            txt += self.moduleGenerator.set_environment('EBEXTSLIST%s' % self.name.upper(), exts_list)

        return txt

    def make_module_footer(self):
        """
        Insert a footer section in the modulefile, primarily meant for contextual information
        """
        txt = '\n# Built with EasyBuild version %s\n' % VERBOSE_VERSION

        # add extra stuff for extensions (if any)
        if self.cfg['exts_list']:
            txt += self.make_module_extra_extensions()

        # include modules footer if one is specified
        if self.modules_footer is not None:
            self.log.debug("Including specified footer into module: '%s'" % self.modules_footer)
            txt += self.modules_footer

        return txt

    def make_module_req(self):
        """
        Generate the environment-variables to run the module.
        """
        requirements = self.make_module_req_guess()

        txt = "\n"
        for key in sorted(requirements):
            for path in requirements[key]:
                if os.path.exists(os.path.join(self.installdir, path)):
                    txt += self.moduleGenerator.prepend_paths(key, [path])
        return txt

    def make_module_req_guess(self):
        """
        A dictionary of possible directories to look for.
        """
        return {
            'PATH': ['bin', 'sbin'],
            'LD_LIBRARY_PATH': ['lib', 'lib64'],
            'LIBRARY_PATH': ['lib', 'lib64'],
            'CPATH':['include'],
            'MANPATH': ['man', 'share/man'],
            'PKG_CONFIG_PATH' : ['lib/pkgconfig', 'share/pkgconfig'],
            'ACLOCAL_PATH' : ['share/aclocal'],
        }

    def load_module(self, mod_paths=None, purge=True):
        """
        Load module for this software package/version, after purging all currently loaded modules.
        """
        # self.mod_name might not be set (e.g. during unit tests)
        if self.mod_name is not None:
            m = modules_tool(mod_paths)
            # purge all loaded modules if desired
            if purge:
                m.purge()
                # restore original environment
                modify_env(os.environ, self.orig_environ)
            m.check_module_path()  # make sure MODULEPATH is set correctly after purging
            m.load([self.mod_name])
        else:
            self.log.warning("Not loading module, since self.mod_name is not set.")

    def load_fake_module(self, purge=False):
        """
        Create and load fake module.
        """

        # take a copy of the environment before loading the fake module, so we can restore it
        orig_env = copy.deepcopy(os.environ)

        # create fake module
        fake_mod_path = self.make_module_step(True)

        # load fake module
        mod_paths = [fake_mod_path]
        mod_paths.extend(self.orig_modulepath.split(':'))
        self.log.debug("mod_paths: %s" % mod_paths)

        self.load_module(mod_paths=mod_paths, purge=purge)

        return (fake_mod_path, orig_env)

    def clean_up_fake_module(self, fake_mod_data):
        """
        Clean up fake module.
        """

        fake_mod_path, orig_env = fake_mod_data

        # unload module and remove temporary module directory
        if fake_mod_path:
            try:
                mod_paths = [fake_mod_path]
                mod_paths.extend(self.modules_tool.mod_paths)
                m = modules_tool(mod_paths)
                # self.mod_name might not be set (e.g. during unit tests)
                if self.mod_name is not None:
                    m.unload([self.mod_name])
                else:
                    self.log.warning("Not unloading module, since self.mod_name is not set.")
                rmtree2(os.path.dirname(fake_mod_path))
            except OSError, err:
                self.log.error("Failed to clean up fake module dir: %s" % err)

        # restore original environment
        modify_env(os.environ, orig_env)

    def load_dependency_modules(self):
        """Load dependency modules."""
        self.modules_tool.load([det_full_module_name(dep) for dep in self.cfg.dependencies()])

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
            self.log.error("Skipping of extensions, but no exts_filter set in easyconfig")
        elif isinstance(exts_filter, basestring) or len(exts_filter) != 2:
            self.log.error('exts_filter should be a list or tuple of ("command","input")')
        cmdtmpl = exts_filter[0]
        cmdinputtmpl = exts_filter[1]
        if not self.exts:
            self.exts = []

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
                        # the ones below are only there for legacy purposes
                        # TODO deprecated, remove in v2.0
                        # TODO same dict is used in extension.py sanity_check_step, resolve this
                        'name': modname,
                        'version': ext.get('version'),
                       }
            cmd = cmdtmpl % tmpldict
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

    def det_installsize(self):
        """Determine size of installation."""
        installsize = 0
        try:
            # change to home dir, to avoid that cwd no longer exists
            os.chdir(os.getenv('HOME'))

            # walk install dir to determine total size
            for (dirpath, _, filenames) in os.walk(self.installdir):
                for filename in filenames:
                    fullpath = os.path.join(dirpath, filename)
                    if os.path.exists(fullpath):
                        installsize += os.path.getsize(fullpath)
        except OSError, err:
            self.log.warn("Could not determine install size: %s" % err)

        return installsize

    def guess_start_dir(self):
        """
        Return the directory where to start the whole configure/make/make install cycle from
        - typically self.src[0]['finalpath']
        - start_dir option
        -- if abspath: use that
        -- else, treat it as subdir for regular procedure
        """
        tmpdir = ''
        if self.cfg['start_dir']:
            tmpdir = self.cfg['start_dir']

        if not os.path.isabs(tmpdir):
            if len(self.src) > 0 and not self.skip:
                self.cfg['start_dir'] = os.path.join(self.src[0]['finalpath'], tmpdir)
            else:
                self.cfg['start_dir'] = os.path.join(self.builddir, tmpdir)

        try:
            os.chdir(self.cfg['start_dir'])
            self.log.debug("Changed to real build directory %s" % (self.cfg['start_dir']))
        except OSError, err:
            self.log.exception("Can't change to real build directory %s: %s" % (self.cfg['start_dir'], err))

    def handle_iterate_opts(self):
        """Handle options relevant during iterated part of build/install procedure."""

        # disable templating in this function, since we're messing about with values in self.cfg
        self.cfg.enable_templating = False

        # handle configure/build/install options that are specified as lists
        # set first element to be used, keep track of list in *_list options dictionary
        # this will only be done during first iteration, since after that the options won't be lists anymore
        suffix = "_list"
        sufflen = len(suffix)
        for opt in ITERATE_OPTIONS:
            # keep track of list, supply first element as first option to handle
            if isinstance(self.cfg[opt], (list, tuple)):
                self.iter_opts[opt + suffix] = self.cfg[opt]  # copy
                self.log.debug("Found list for %s: %s" % (opt, self.iter_opts[opt + suffix]))

        # pop first element from all *_list options as next value to use
        for (lsname, ls) in self.iter_opts.items():
            opt = lsname[:-sufflen]  # drop '_list' part from name to get option name
            if len(self.iter_opts[lsname]) > 0:
                self.cfg[opt] = self.iter_opts[lsname].pop(0)  # first element will be used next
            else:
                self.cfg[opt] = ''  # empty list => empty option as next value
            self.log.debug("Next value for %s: %s" % (opt, str(self.cfg[opt])))

        # re-enable templating before self.cfg values are used
        self.cfg.enable_templating = True

    def det_iter_cnt(self):
        """Determine iteration count based on configure/build/install options that may be lists."""
        iter_cnt = max([1] + [len(self.cfg[opt]) for opt in ITERATE_OPTIONS
                              if isinstance(self.cfg[opt], (list, tuple))])
        return iter_cnt

    def print_environ(self):
        """
        Prints the environment changes and loaded modules to the debug log
        - pretty prints the environment for easy copy-pasting
        """
        mods = [(mod['name'], mod['version']) for mod in self.modules_tool.loaded_modules()]
        mods_text = "\n".join(["module load %s/%s" % m for m in mods if m not in self.loaded_modules])
        self.loaded_modules = mods

        env = copy.deepcopy(os.environ)

        changed = [(k, env[k]) for k in env if k not in self.orig_environ]
        for k in env:
            if k in self.orig_environ and env[k] != self.orig_environ[k]:
                changed.append((k, env[k]))

        unset = [key for key in self.orig_environ if key not in env]

        text = "\n".join(['export %s="%s"' % change for change in changed])
        unset_text = "\n".join(['unset %s' % key for key in unset])

        if mods:
            self.log.debug("Loaded modules:\n%s" % mods_text)
        if changed:
            self.log.debug("Added to environment:\n%s" % text)
        if unset:
            self.log.debug("Removed from environment:\n%s" % unset_text)

        self.orig_environ = env

    def set_parallelism(self, nr=None):
        """
        Determines how many processes should be used (default: nr of procs - 1).
        """
        if not nr and self.cfg['parallel']:
            nr = self.cfg['parallel']

        if nr:
            try:
                nr = int(nr)
            except ValueError, err:
                self.log.error("Parallelism %s not integer: %s" % (nr, err))
        else:
            nr = get_avail_core_count()
            # check ulimit -u
            out, ec = run_cmd('ulimit -u')
            try:
                if out.startswith("unlimited"):
                    out = 2 ** 32 - 1
                maxuserproc = int(out)
                # assume 6 processes per build thread + 15 overhead
                maxnr = int((maxuserproc - 15) / 6)
                if maxnr < nr:
                    nr = maxnr
                    self.log.info("Limit parallel builds to %s because max user processes is %s" % (nr, out))
            except ValueError, err:
                self.log.exception("Failed to determine max user processes (%s,%s): %s" % (ec, out, err))

        maxpar = self.cfg['maxparallel']
        if maxpar and maxpar < nr:
            self.log.info("Limiting parallellism from %s to %s" % (nr, maxpar))
            nr = min(nr, maxpar)

        self.cfg['parallel'] = nr
        self.log.info("Setting parallelism: %s" % nr)

    def verify_homepage(self):
        """
        Download homepage, verify if the name of the software is mentioned
        """
        homepage = self.cfg["homepage"]

        try:
            page = urllib.urlopen(homepage)
        except IOError:
            self.log.error("Homepage (%s) is unavailable." % homepage)
            return False

        regex = re.compile(self.name, re.I)

        # if url contains software name and is available we are satisfied
        if regex.search(homepage):
            return True

        # Perform a lowercase compare against the entire contents of the html page
        # (does not care about html)
        for line in page:
            if regex.search(line):
                return True
        return False


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

        # do all dependencies have a toolchain version?
        self.toolchain.add_dependencies(self.cfg.dependencies())
        if not len(self.cfg.dependencies()) == len(self.toolchain.dependencies):
            self.log.debug("dep %s (%s)" % (len(self.cfg.dependencies()), self.cfg.dependencies()))
            self.log.debug("tc.dep %s (%s)" % (len(self.toolchain.dependencies), self.toolchain.dependencies))
            self.log.error('Not all dependencies have a matching toolchain version')

        # check if the application is not loaded at the moment
        (root, env_var) = get_software_root(self.name, with_env_var=True)
        if root:
            self.log.error("Module is already loaded (%s is set), installation cannot continue." % env_var)

        # check if main install needs to be skipped
        # - if a current module can be found, skip is ok
        # -- this is potentially very dangerous
        if self.cfg['skip']:
            if self.modules_tool.exists(self.mod_name):
                self.skip = True
                self.log.info("Module %s found." % self.mod_name)
                self.log.info("Going to skip actual main build and potential existing extensions. Expert only.")
            else:
                self.log.info("No module %s found. Not skipping anything." % self.mod_name)

        # Set group id, if a group was specified
        if self.cfg['group']:
            gid = grp.getgrnam(self.cfg['group'])[2]
            os.setgid(gid)
            self.log.debug("Changing group to %s (gid: %s)" % (self.cfg['group'], gid))

    def fetch_step(self, skip_checksums=False):
        """
        prepare for building
        """
        # check EasyBuild version
        easybuild_version = self.cfg['easybuild_version']
        if not easybuild_version:
            self.log.warn("Easyconfig does not specify an EasyBuild-version (key 'easybuild_version')! Assuming the latest version")
        else:
            if LooseVersion(easybuild_version) < VERSION:
                self.log.warn("EasyBuild-version %s is older than the currently running one. Proceed with caution!" % easybuild_version)
            elif LooseVersion(easybuild_version) > VERSION:
                self.log.error("EasyBuild-version %s is newer than the currently running one. Aborting!" % easybuild_version)

        # fetch sources
        if self.cfg['sources']:
            self.fetch_sources(self.cfg['sources'], checksums=self.cfg['checksums'])
        else:
            self.log.info('no sources provided')

        # fetch patches
        if self.cfg['patches']:
            if isinstance(self.cfg['checksums'], (list, tuple)):
                # if checksums are provided as a list, first entries are assumed to be for sources
                patches_checksums = self.cfg['checksums'][len(self.cfg['sources']):]
            else:
                patches_checksums = self.cfg['checksums']
            self.fetch_patches(self.cfg['patches'], checksums=patches_checksums)
        else:
            self.log.info('no patches provided')

        # compute checksums for all source and patch files
        if not skip_checksums:
            for fil in self.src + self.patches:
                check_sum = compute_checksum(fil['path'], checksum_type=DEFAULT_CHECKSUM)
                fil[DEFAULT_CHECKSUM] = check_sum
                self.log.info("%s checksum for %s: %s" % (DEFAULT_CHECKSUM, fil['path'], fil[DEFAULT_CHECKSUM]))

        # set level of parallelism for build
        self.set_parallelism()

        # create parent dirs in install and modules path already
        # this is required when building in parallel
        pardirs = [os.path.join(install_path(), self.name),
                   os.path.join(install_path('mod'), GENERAL_CLASS, self.name),
                   os.path.join(install_path('mod'), self.cfg['moduleclass'], self.name)]
        self.log.info("Checking dirs that need to be created: %s" % pardirs)
        try:
            for pardir in pardirs:
                if not os.path.exists(pardir):
                    os.makedirs(pardir)
                    self.log.debug("Created directory %s" % pardir)
                else:
                    self.log.debug("Not creating %s, it already exists." % pardir)
        except OSError, err:
            self.log.error("Failed to create parent dirs in install and modules path: %s" % err)

    def checksum_step(self):
        """Verify checksum of sources and patches, if a checksum is available."""
        for fil in self.src + self.patches:
            ok = verify_checksum(fil['path'], fil['checksum'])
            if not ok:
                self.log.error("Checksum verification for %s using %s failed." % (fil['path'], fil['checksum']))
            else:
                self.log.info("Checksum verification for %s using %s passed." % (fil['path'], fil['checksum']))

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
                self.log.error("Unpacking source %s failed" % src['name'])

    def patch_step(self, beginpath=None):
        """
        Apply the patches
        """
        for patch in self.patches:
            self.log.info("Applying patch %s" % patch['name'])

            copy = False
            # default: patch first source
            srcind = 0
            if 'source' in patch:
                srcind = patch['source']
            srcpathsuffix = ''
            if 'sourcepath' in patch:
                srcpathsuffix = patch['sourcepath']
            elif 'copy' in patch:
                srcpathsuffix = patch['copy']
                copy = True

            if not beginpath:
                beginpath = self.src[srcind]['finalpath']

            src = os.path.abspath("%s/%s" % (beginpath, srcpathsuffix))

            level = None
            if 'level' in patch:
                level = patch['level']

            if not apply_patch(patch['path'], src, copy=copy, level=level):
                self.log.error("Applying patch %s failed" % patch['name'])

    def prepare_step(self):
        """
        Pre-configure step. Set's up the builddir just before starting configure
        """
        self.cfg['unwanted_env_vars'] = env.unset_env_vars(self.cfg['unwanted_env_vars'])
        self.toolchain.prepare(self.cfg['onlytcmod'])
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

    def extensions_step(self):
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
        fake_mod_data = self.load_fake_module(purge=True)

        self.prepare_for_extensions()

        self.exts = self.fetch_extension_sources()
        self.exts_all = self.exts[:]  # retain a copy of all extensions, regardless of filtering/skipping

        if self.skip:
            self.skip_extensions()

        # actually install extensions
        self.log.debug("Installing extensions")
        exts_defaultclass = self.cfg['exts_defaultclass']
        exts_classmap = self.cfg['exts_classmap']

        # we really need a default class
        if not exts_defaultclass:
            self.clean_up_fake_module(fake_mod_data)
            self.log.error("ERROR: No default extension class set for %s" % self.name)

        # obtain name and module path for default extention class
        legacy = False
        if hasattr(exts_defaultclass, '__iter__'):
            # LEGACY: module path is explicitely specified
            self.log.warning("LEGACY: using specified module path for default class (will be deprecated soon)")
            default_class_modpath = exts_defaultclass[0]
            default_class = exts_defaultclass[1]
            derived_mod_path = get_module_path(default_class, generic=True)
            if not default_class_modpath == derived_mod_path:
                msg = "Specified module path for default class %s " % default_class_modpath
                msg += "doesn't match derived path %s" % derived_mod_path
                self.log.warning(msg)
            legacy = True

        elif isinstance(exts_defaultclass, basestring):
            # proper way: derive module path from specified class name
            default_class = exts_defaultclass
            default_class_modpath = get_module_path(default_class, generic=True)

        else:
            self.log.error("Improper default extension class specification, should be list/tuple or string.")

        # get class instances for all extensions
        for ext in self.exts:
            self.log.debug("Starting extension %s" % ext['name'])

            # always go back to build dir to avoid running stuff from a dir that no longer exists
            os.chdir(self.builddir)

            inst = None

            # try instantiating extension-specific class
            class_name = encode_class_name(ext['name'])  # use the same encoding as get_class
            mod_path = get_module_path(class_name)
            if not os.path.exists("%s.py" % mod_path):
                self.log.deprecated("Determine module path based on software name", "2.0")
                mod_path = get_module_path(ext['name'], decode=False)

            try:
                cls = get_class_for(mod_path, class_name)
                inst = cls(self, ext)
            except (ImportError, NameError), err:
                self.log.debug("Failed to use class %s from %s for extension %s: %s" % (class_name,
                                                                                        mod_path,
                                                                                        ext['name'],
                                                                                        err))

            # LEGACY: try and use default module path for getting extension class instance
            if inst is None and legacy:
                try:
                    msg = "Failed to use derived module path for %s, " % class_name
                    msg += "considering specified module path as (legacy) fallback."
                    self.log.debug(msg)
                    mod_path = default_class_modpath
                    cls = get_class_for(mod_path, class_name)
                    inst = cls(self, ext)
                except (ImportError, NameError), err:
                    self.log.debug("Failed to use class %s from %s for extension %s: %s" % (class_name,
                                                                                            mod_path,
                                                                                            ext['name'],
                                                                                            err))

            # alternative attempt: use class specified in class map (if any)
            if inst is None and ext['name'] in exts_classmap:

                class_name = exts_classmap[ext['name']]
                mod_path = get_module_path(class_name)
                try:
                    cls = get_class_for(mod_path, class_name)
                    inst = cls(self, ext)
                except (ImportError, NameError), err:
                    self.log.error("Failed to load specified class %s for extension %s: %s" % (class_name,
                                                                                               ext['name'],
                                                                                               err))

            # fallback attempt: use default class
            if not inst is None:
                self.log.debug("Installing extension %s with class %s (from %s)" % (ext['name'], class_name, mod_path))
            else:
                try:
                    cls = get_class_for(default_class_modpath, default_class)
                    self.log.debug("Obtained class %s for installing extension %s" % (cls, ext['name']))
                    inst = cls(self, ext)
                    self.log.debug("Installing extension %s with default class %s" % (ext['name'], default_class))
                except (ImportError, NameError), err:
                    msg = "Also failed to use default class %s from %s for extension %s: %s, giving up" % \
                        (default_class, default_class_modpath, ext['name'], err)
                    self.log.error(msg)

            # real work
            inst.prerun()
            txt = inst.run()
            if txt:
                self.module_extra_extensions += txt
            inst.postrun()

            # append so we can make us of it later (in sanity_check_step)
            self.ext_instances.append(inst)

        # cleanup (unload fake module, remove fake module dir)
        self.clean_up_fake_module(fake_mod_data)

    def package_step(self):
        """Package software (e.g. into an RPM)."""
        pass

    def post_install_step(self):
        """
        Do some postprocessing
        - set file permissions ....
        Installing user must be member of the group that it is changed to
        """
        if self.cfg['group']:

            gid = grp.getgrnam(self.cfg['group'])[2]
            # rwx for owner, r-x for group, --- for other
            try:
                adjust_permissions(self.installdir, 0750, recursive=True, group_id=gid, relative=False,
                                   ignore_errors=True)
            except EasyBuildError, err:
                self.log.error("Unable to change group permissions of file(s). " \
                               "Are you a member of this group?\n%s" % err)
            self.log.info("Successfully made software only available for group %s" % self.cfg['group'])

        else:
            # remove write permissions for group and other
            perms = stat.S_IWGRP | stat.S_IWOTH
            adjust_permissions(self.installdir, perms, add=False, recursive=True, relative=True, ignore_errors=True)
            self.log.info("Successfully removed write permissions recursively for group/other on install dir.")

        if read_only_installdir():
            # remove write permissions for everyone
            perms = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
            adjust_permissions(self.installdir, perms, add=False, recursive=True, relative=True, ignore_errors=True)
            self.log.info("Successfully removed write permissions recursively for *EVERYONE* on install dir.")

    def sanity_check_step(self, custom_paths=None, custom_commands=None, extension=False):
        """
        Do a sanity check on the installation
        - if *any* of the files/subdirectories in the installation directory listed
          in sanity_check_paths are non-existent (or empty), the sanity check fails
        """
        # supported/required keys in for sanity check paths, along with function used to check the paths
        path_keys_and_check = {
            'files': lambda fp: os.path.exists(fp),  # files must exist
            'dirs': lambda dp: os.path.isdir(dp) and os.listdir(dp),  # directories must exist and be non-empty
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
                paths.update({'dirs': ["bin", "lib"]})
                self.log.info("Using default sanity check paths: %s" % paths)
        else:
            self.log.info("Using specified sanity check paths: %s" % paths)

        # check sanity check paths
        ks = sorted(paths.keys())
        valnottypes = [not isinstance(x, list) for x in paths.values()]
        lenvals = [len(x) for x in paths.values()]
        req_keys = sorted(path_keys_and_check.keys())
        if not ks == req_keys or sum(valnottypes) > 0 or sum(lenvals) == 0:
            self.log.error("Incorrect format for sanity_check_paths (should have %s keys, " \
                           "values should be lists (at least one non-empty))." % '/'.join(req_keys))

        for key, check_fn in path_keys_and_check.items():
            for xs in paths[key]:
                if isinstance(xs, basestring):
                    xs = (xs,)
                elif not isinstance(xs, tuple):
                    self.log.error("Unsupported type '%s' encountered in %s, not a string or tuple" % (key, type(xs)))
                found = False
                for name in xs:
                    path = os.path.join(self.installdir, name)
                    if os.path.exists(path):
                        self.log.debug("Sanity check: found %s %s in %s" % (key[:-1], name, self.installdir))
                        found = True
                        break
                    else:
                        self.log.debug("Could not find %s %s in %s" % (key[:-1], name, self.installdir))
                if not found:
                    self.sanity_check_fail_msgs.append("no %s of %s in %s" % (key[:-1], xs, self.installdir))
                    self.log.warning("Sanity check: %s" % self.sanity_check_fail_msgs[-1])

        fake_mod_data = None
        if not extension:
            try:
                # unload all loaded modules before loading fake module
                # this ensures that loading of dependencies is tested, and avoids conflicts with build dependencies
                fake_mod_data = self.load_fake_module(purge=True)
            except EasyBuildError, err:
                self.sanity_check_fail_msgs.append("loading fake module failed: %s" % err)
                self.log.warning("Sanity check: %s" % self.sanity_check_fail_msgs[-1])

        # chdir to installdir (better environment for running tests)
        os.chdir(self.installdir)

        # run sanity check commands
        commands = self.cfg['sanity_check_commands']
        if not commands:
            if custom_commands:
                commands = custom_commands
                self.log.info("Using customised sanity check commands: %s" % commands)
            else:
                commands = []
                self.log.info("Using specified sanity check commands: %s" % commands)

        for command in commands:
            # set command to default. This allows for config files with
            # non-tuple commands
            if not isinstance(command, tuple):
                self.log.debug("Setting sanity check command to default")
                command = (None, None)

            # Build substition dictionary
            check_cmd = { 'name': self.name.lower(), 'options': '-h' }

            if command[0] != None:
                check_cmd['name'] = command[0]

            if command[1] != None:
                check_cmd['options'] = command[1]

            cmd = "%(name)s %(options)s" % check_cmd

            out, ec = run_cmd(cmd, simple=False, log_ok=False, log_all=False)
            if ec != 0:
                self.sanity_check_fail_msgs.append("sanity check command %s exited with code %s (output: %s)" % (cmd, ec, out))
                self.log.warning("Sanity check: %s" % self.sanity_check_fail_msgs[-1])
            else:
                self.log.debug("sanity check command %s ran successfully! (output: %s)" % (cmd, out))

        if not extension:
            failed_exts = [ext.name for ext in self.ext_instances if not ext.sanity_check_step()]

            if failed_exts:
                self.sanity_check_fail_msgs.append("sanity checks for %s extensions failed!" % failed_exts)
                self.log.warning("Sanity check: %s" % self.sanity_check_fail_msgs[-1])

        # cleanup
        if fake_mod_data:
            self.clean_up_fake_module(fake_mod_data)

        # pass or fail
        if self.sanity_check_fail_msgs:
            self.log.error("Sanity check failed: %s" % ', '.join(self.sanity_check_fail_msgs))
        else:
            self.log.debug("Sanity check passed!")

    def cleanup_step(self):
        """
        Cleanup leftover mess: remove/clean build directory

        except when we're building in the installation directory,
        otherwise we remove the installation
        """
        if not self.build_in_installdir:
            try:
                os.chdir(build_path())  # make sure we're out of the dir we're removing

                self.log.info("Cleaning up builddir %s (in %s)" % (self.builddir, os.getcwd()))

                rmtree2(self.builddir)
                base = os.path.dirname(self.builddir)

                # keep removing empty directories until we either find a non-empty one
                # or we end up in the root builddir
                while len(os.listdir(base)) == 0 and not os.path.samefile(base, build_path()):
                    os.rmdir(base)
                    base = os.path.dirname(base)

            except OSError, err:
                self.log.exception("Cleaning up builddir %s failed: %s" % (self.builddir, err))

        env.restore_env_vars(self.cfg['unwanted_env_vars'])

    def make_module_step(self, fake=False):
        """
        Generate a module file.
        """
        self.moduleGenerator = ModuleGenerator(self, fake)
        modpath = self.moduleGenerator.create_files()

        txt = ''
        txt += self.make_module_description()
        txt += self.make_module_dep()
        txt += self.make_module_req()
        txt += self.make_module_extra()
        txt += self.make_module_footer()

        write_file(self.moduleGenerator.filename, txt)

        self.log.info("Added modulefile: %s" % (self.moduleGenerator.filename))

        if not fake:
            self.make_devel_module()

        self.modules_tool.update()

        return modpath

    def test_cases_step(self):
        """
        Run provided test cases.
        """
        for test in self.cfg['tests']:
            # Current working dir no longer exists
            os.chdir(self.installdir)
            if os.path.isabs(test):
                path = test
            else:
                for source_path in source_paths():
                    path = os.path.join(source_path, self.name, test)
                    if os.path.exists(path):
                        break
                if not os.path.exists(path):
                    self.log.error("Test specifies invalid path: %s" % path)

            try:
                self.log.debug("Running test %s" % path)
                run_cmd(path, log_all=True, simple=True)
            except EasyBuildError, err:
                self.log.exception("Running test %s failed: %s" % (path, err))

    def update_config_template_run_step(self):
        """Update the the easyconfig template dictionary with easyconfig.TEMPLATE_NAMES_EASYBLOCK_RUN_STEP names"""

        for name in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP:
            self.cfg.template_values[name[0]] = str(getattr(self, name[0], None))
        self.cfg.generate_template_values()

    def run_step(self, step, methods, skippable=False):
        """
        Run step, returns false when execution should be stopped
        """
        if skippable and (self.skip or step in self.cfg['skipsteps']):
            self.log.info("Skipping %s step" % step)
        else:
            self.log.info("Starting %s step" % step)
            # update the config templates
            self.update_config_template_run_step()

            for m in methods:
                self.log.info("Running method %s part of step %s" % ('_'.join(m.func_code.co_names), step))
                m(self)

        if self.cfg['stop'] == step:
            self.log.info("Stopping after %s step." % step)
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
            (False, lambda x: x.check_readiness_step()),
            (False, lambda x: x.gen_builddir()),
            (False, lambda x: x.gen_installdir()),
            (True, lambda x: x.make_builddir()),
            (True, lambda x: env.reset_changes()),
            (True, lambda x: x.handle_iterate_opts()),
        ]
        ready_step_spec = lambda initial: get_step('ready', "creating build dir, resetting environment",
                                                   ready_substeps, False, initial=initial)

        source_substeps = [
            (False, lambda x: x.checksum_step()),
            (True, lambda x: x.extract_step()),
        ]
        source_step_spec = lambda initial: get_step('source', "unpacking", source_substeps, True, initial=initial)

        def prepare_step_spec(initial):
            """Return prepare step specification."""
            if initial:
                substeps = [lambda x: x.prepare_step()]
            else:
                substeps = [lambda x: x.guess_start_dir()]
            return ('prepare', 'preparing', substeps, False)

        install_substeps = [
            (False, lambda x: x.stage_install_step()),
            (False, lambda x: x.make_installdir()),
            (True, lambda x: x.install_step()),
        ]
        install_step_spec = lambda initial: get_step('install', "installing", install_substeps, True, initial=initial)

        # format for step specifications: (stop_name: (description, list of functions, skippable))

        # core steps that are part of the iterated loop
        patch_step_spec = ('patch', 'patching', [lambda x: x.patch_step()], True)
        configure_step_spec = ('configure', 'configuring', [lambda x: x.configure_step()], True)
        build_step_spec = ('build', 'building', [lambda x: x.build_step()], True)
        test_step_spec = ('test', 'testing', [lambda x: x.test_step()], True)

        # part 1: pre-iteration + first iteration
        steps_part1 = [
            ('fetch', 'fetching files', [lambda x: x.fetch_step()], False),
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
            ('extensions', 'taking care of extensions', [lambda x: x.extensions_step()], False),
            ('package', 'packaging', [lambda x: x.package_step()], True),
            ('postproc', 'postprocessing', [lambda x: x.post_install_step()], True),
            ('sanitycheck', 'sanity checking', [lambda x: x.sanity_check_step()], False),
            ('cleanup', 'cleaning up', [lambda x: x.cleanup_step()], False),
            ('module', 'creating module', [lambda x: x.make_module_step()], False),
        ]

        # full list of steps, included iterated steps
        steps = steps_part1 + steps_part2 + steps_part3

        if run_test_cases:
            steps.append(('testcases', 'running test cases', [
                                                              lambda x: x.load_module(),
                                                              lambda x: x.test_cases_step(),
                                                             ], False))

        return steps

    def run_all_steps(self, run_test_cases, regtest_online):
        """
        Build and install this software.
        run_test_cases (bool): run tests after building (e.g.: make test)
        regtest_online (bool): do an online regtest, this means check the websites and try to download sources"
        """
        if self.cfg['stop'] and self.cfg['stop'] == 'cfg':
            return True

        steps = self.get_steps(run_test_cases=run_test_cases, iteration_count=self.det_iter_cnt())

        self.mod_name = det_full_module_name(self.cfg)
        print_msg("building and installing %s..." % self.mod_name, self.log, silent=self.silent)
        try:
            for (stop_name, descr, step_methods, skippable) in steps:
                print_msg("%s..." % descr, self.log, silent=self.silent)
                self.run_step(stop_name, step_methods, skippable=skippable)

        except StopException:
            pass

        # return True for successfull build (or stopped build)
        return True


def get_class_for(modulepath, class_name):
    """
    Get class for a given class name and easyblock module path.
    """
    # >>> import pkgutil
    # >>> loader = pkgutil.find_loader('easybuild.apps.Base')
    # >>> d = loader.load_module('Base')
    # >>> c = getattr(d,'Likwid')
    # >>> c()
    m = __import__(modulepath, globals(), locals(), [''])
    try:
        c = getattr(m, class_name)
    except AttributeError:
        raise ImportError
    return c


def get_module_path(name, generic=False, decode=True):
    """
    Determine the module path for a given easyblock or software name,
    based on the encoded class name.
    """
    if not name:
        return None

    # example: 'EB_VSC_minus_tools' should result in 'vsc_tools'
    if decode:
        name = decode_class_name(name)
    module_name = remove_unwanted_chars(name.replace('-', '_')).lower()

    if generic:
        modpath = '.'.join(["easybuild", "easyblocks", "generic"])
    else:
        modpath = '.'.join(["easybuild", "easyblocks"])

    return '.'.join([modpath, module_name])


def get_class(easyblock, name=None):
    """
    Get class for a particular easyblock (or use default)
    """

    def_class = get_easyconfig_parameter_default('easyblock')
    def_mod_path = get_module_path(def_class, generic=True)

    try:
        # if no easyblock specified, try to find if one exists
        if not easyblock:
            if not name:
                name = "UNKNOWN"
            # The following is a generic way to calculate unique class names for any funny software title
            class_name = encode_class_name(name)
            # modulepath will be the namespace + encoded modulename (from the classname)
            modulepath = get_module_path(class_name)
            if not os.path.exists("%s.py" % modulepath):
                _log.deprecated("Determine module path based on software name", "2.0")
                modulepath = get_module_path(name, decode=False)

            # try and find easyblock
            try:
                _log.debug("getting class for %s.%s" % (modulepath, class_name))
                cls = get_class_for(modulepath, class_name)
                _log.info("Successfully obtained %s class instance from %s" % (class_name, modulepath))
                return cls
            except ImportError, err:

                # when an ImportError occurs, make sure that it's caused by not finding the easyblock module,
                # and not because of a broken import statement in the easyblock module
                error_re = re.compile(r"No module named %s" % modulepath.replace("easybuild.easyblocks.", ''))
                _log.debug("error regexp: %s" % error_re.pattern)
                if not error_re.match(str(err)):
                    _log.error("Failed to import easyblock for %s because of module issue: %s" % (class_name, err))

                else:
                    # no easyblock could be found, so fall back to default class.
                    _log.warning("Failed to import easyblock for %s, falling back to default class %s: error: %s" % \
                                (class_name, (def_mod_path, def_class), err))
                    cls = get_class_for(def_mod_path, def_class)

        # something was specified, lets parse it
        else:
            class_name = easyblock.split('.')[-1]
            # figure out if full path was specified or not
            if len(easyblock.split('.')) > 1:
                _log.info("Assuming that full easyblock module path was specified.")
                modulepath = '.'.join(easyblock.split('.')[:-1])
                cls = get_class_for(modulepath, class_name)
            else:
                # if we only get the class name, most likely we're dealing with a generic easyblock
                try:
                    modulepath = get_module_path(easyblock, generic=True)
                    cls = get_class_for(modulepath, class_name)
                except ImportError, err:
                    # we might be dealing with a non-generic easyblock, e.g. with --easyblock is used
                    modulepath = get_module_path(easyblock)
                    cls = get_class_for(modulepath, class_name)
                _log.info("Derived full easyblock module path for %s: %s" % (class_name, modulepath))

        _log.info("Successfully obtained %s class instance from %s" % (class_name, modulepath))
        return cls

    except Exception, err:
        _log.error("Failed to obtain class for %s easyblock (not available?): %s" % (easyblock, err))


def build_and_install_software(module, orig_environ, build_options=None, build_specs=None):
    """
    Build the software
    @param module: dictionary contaning parsed easyconfig + metadata
    @param orig_environ: original environment (used to reset environment)
    @param build_options: dictionary specifying build options (e.g. robot_path, check_osdeps, ...)
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    """
    silent = build_options.get('silent', False)

    spec = module['spec']

    print_msg("processing EasyBuild easyconfig %s" % spec, log=_log, silent=silent)

    # restore original environment
    _log.info("Resetting environment")
    filetools.errors_found_in_log = 0
    modify_env(os.environ, orig_environ)

    cwd = os.getcwd()

    # load easyblock
    easyblock = build_options.get('easyblock', None)
    if not easyblock:
        # try to look in .eb file
        reg = re.compile(r"^\s*easyblock\s*=(.*)$")
        txt = read_file(spec)
        for line in txt.split('\n'):
            match = reg.search(line)
            if match:
                easyblock = eval(match.group(1))
                break

    name = module['ec']['name']
    try:
        app_class = get_class(easyblock, name=name)
        app = app_class(spec, build_options=build_options, build_specs=build_specs)
        _log.info("Obtained application instance of for %s (easyblock: %s)" % (name, easyblock))
    except EasyBuildError, err:
        tup = (name, easyblock, err.msg)
        print_error("Failed to get application instance for %s (easyblock: %s): %s" % tup, silent=silent)

    # application settings
    stop = build_options.get('stop', None)
    if stop is not None:
        _log.debug("Stop set to %s" % stop)
        app.cfg['stop'] = stop

    skip = build_options.get('skip', None)
    if skip is not None:
        _log.debug("Skip set to %s" % skip)
        app.cfg['skip'] = skip

    # build easyconfig
    errormsg = '(no error)'
    # timing info
    start_time = time.time()
    try:
        run_test_cases = not build_options.get('skip_test_cases', False) and app.cfg['tests']
        regtest_online = build_options.get('regtest_online', False)
        result = app.run_all_steps(run_test_cases=run_test_cases, regtest_online=regtest_online)
    except EasyBuildError, err:
        lastn = 300
        errormsg = "autoBuild Failed (last %d chars): %s" % (lastn, err.msg[-lastn:])
        _log.exception(errormsg)
        result = False

    ended = "ended"

    # successful build
    if result:

        if app.cfg['stop']:
            ended = "STOPPED"
            if app.builddir is not None:
                new_log_dir = os.path.join(app.builddir, config.log_path())
            else:
                new_log_dir = os.path.dirname(app.logfile)
        else:
            new_log_dir = os.path.join(app.installdir, config.log_path())

            # collect build stats
            _log.info("Collecting build stats...")

            buildstats = get_build_stats(app, start_time, build_options.get('command_line', None))
            _log.info("Build stats: %s" % buildstats)

            try:
                # upload spec to central repository
                currentbuildstats = app.cfg['buildstats']
                repo = init_repository(get_repository(), get_repositorypath())
                if 'originalSpec' in module:
                    block = det_full_ec_version(app.cfg) + ".block"
                    repo.add_easyconfig(module['originalSpec'], app.name, block, buildstats, currentbuildstats)
                repo.add_easyconfig(spec, app.name, det_full_ec_version(app.cfg), buildstats, currentbuildstats)
                repo.commit("Built %s" % det_full_module_name(app.cfg))
                del repo
            except EasyBuildError, err:
                _log.warn("Unable to commit easyconfig to repository: %s", err)

        exit_code = 0
        succ = "successfully"
        summary = "COMPLETED"

        # cleanup logs
        app.close_log()
        try:
            if not os.path.isdir(new_log_dir):
                os.makedirs(new_log_dir)
            log_fn = os.path.basename(get_log_filename(app.name, app.version))
            application_log = os.path.join(new_log_dir, log_fn)
            shutil.move(app.logfile, application_log)
            _log.debug("Moved log file %s to %s" % (app.logfile, application_log))
        except (IOError, OSError), err:
            print_error("Failed to move log file %s to new log file %s: %s" % (app.logfile, application_log, err))

        try:
            newspec = os.path.join(new_log_dir, "%s-%s.eb" % (app.name, det_full_ec_version(app.cfg)))
            shutil.copy(spec, newspec)
            _log.debug("Copied easyconfig file %s to %s" % (spec, newspec))
        except (IOError, OSError), err:
            print_error("Failed to move easyconfig %s to log dir %s: %s" % (spec, new_log_dir, err))

    # build failed
    else:
        exit_code = 1
        summary = "FAILED"

        build_dir = ''
        if app.builddir:
            build_dir = " (build directory: %s)" % (app.builddir)
        succ = "unsuccessfully%s:\n%s" % (build_dir, errormsg)

        # cleanup logs
        app.close_log()
        application_log = app.logfile

    print_msg("%s: Installation %s %s" % (summary, ended, succ), log=_log, silent=silent)

    # check for errors
    if exit_code != 0 or filetools.errors_found_in_log > 0:
        print_msg("\nWARNING: Build exited with non-zero exit code %d. %d possible error(s) were detected in the "
                  "build logs, please verify the build.\n" % (exit_code, filetools.errors_found_in_log),
                  _log, silent=silent)

    if app.postmsg:
        print_msg("\nWARNING: %s\n" % app.postmsg, _log, silent=silent)

    print_msg("Results of the build can be found in the log file %s" % application_log, _log, silent=silent)

    del app
    os.chdir(cwd)

    return (exit_code == 0, application_log)


def get_easyblock_instance(easyconfig, build_options=None, build_specs=None):
    """
    Get an instance for this easyconfig
    @param easyconfig: parsed easyconfig
    @param build_options: dictionary specifying build options (e.g. robot_path, check_osdeps, ...)
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)

    returns an instance of EasyBlock (or subclass thereof)
    """
    spec = easyconfig['spec']
    name = easyconfig['ec']['name']

    # handle easyconfigs with custom easyblocks
    easyblock = None
    reg = re.compile(r"^\s*easyblock\s*=(.*)$")
    txt = read_file(spec)
    for line in txt.split('\n'):
        match = reg.search(line)
        if match:
            easyblock = eval(match.group(1))
            break

    app_class = get_class(easyblock, name=name)
    return app_class(spec, build_options=build_options, build_specs=build_specs)


def build_easyconfigs(easyconfigs, output_dir, test_results, build_options=None):
    """Build the list of easyconfigs."""

    build_stopped = {}
    apploginfo = lambda x, y: x.log.info(y)

    def perform_step(step, obj, method, logfile):
        """Perform method on object if it can be built."""
        if (isinstance(obj, dict) and obj['spec'] not in build_stopped) or obj not in build_stopped:

            # update templates before every step (except for initialization)
            if isinstance(obj, EasyBlock):
                obj.update_config_template_run_step()

            try:
                if step == 'initialization':
                    _log.info("Running %s step" % step)
                    return get_easyblock_instance(obj, build_options=build_options)
                else:
                    apploginfo(obj, "Running %s step" % step)
                    method(obj)
            except Exception, err:  # catch all possible errors, also crashes in EasyBuild code itself
                fullerr = str(err)
                if not isinstance(err, EasyBuildError):
                    tb = traceback.format_exc()
                    fullerr = '\n'.join([tb, str(err)])
                # we cannot continue building it
                if step == 'initialization':
                    obj = obj['spec']
                test_results.append((obj, step, fullerr, logfile))
                # keep a dict of so we can check in O(1) if objects can still be build
                build_stopped[obj] = step

    # initialize all instances
    apps = []
    for ec in easyconfigs:
        instance = perform_step('initialization', ec, None, _log)
        instance.mod_name = det_full_module_name(instance.cfg)
        apps.append(instance)

    base_dir = os.getcwd()
    base_env = copy.deepcopy(os.environ)
    succes = []

    for app in apps:

        # if initialisation step failed, app will be None
        if app:

            applog = os.path.join(output_dir, "%s-%s.log" % (app.name, det_full_ec_version(app.cfg)))

            start_time = time.time()

            # start with a clean slate
            os.chdir(base_dir)
            modify_env(os.environ, base_env)

            steps = EasyBlock.get_steps(iteration_count=app.det_iter_cnt())

            for (step_name, _, step_methods, skippable) in steps:
                if skippable and step_name in app.cfg['skipsteps']:
                    _log.info("Skipping step %s" % step_name)
                else:
                    for step_method in step_methods:
                        method_name = '_'.join(step_method.func_code.co_names)
                        perform_step('_'.join([step_name, method_name]), app, step_method, applog)

            # close log and move it
            app.close_log()
            try:
                # retain old logs
                if os.path.exists(applog):
                    i = 0
                    old_applog = "%s.%d" % (applog, i)
                    while os.path.exists(old_applog):
                        i += 1
                        old_applog = "%s.%d" % (applog, i)
                    shutil.move(applog, old_applog)
                    _log.info("Moved existing log file %s to %s" % (applog, old_applog))

                shutil.move(app.logfile, applog)
                _log.info("Log file moved to %s" % applog)
            except IOError, err:
                print_error("Failed to move log file %s to new log file %s: %s" % (app.logfile, applog, err))

            if app not in build_stopped:
                # gather build stats
                buildstats = get_build_stats(app, start_time, build_options.get('command_line', None))
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
