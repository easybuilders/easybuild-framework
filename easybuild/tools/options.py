##
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
##
"""
Command line options for eb

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import glob
import os
import re
import shutil
import sys
import tempfile
from distutils.version import LooseVersion
from vsc.utils.missing import nub

import easybuild.tools.environment as env
from easybuild.framework.easyblock import MODULE_ONLY_STEPS, SOURCE_STEP, EasyBlock
from easybuild.framework.easyconfig import EASYCONFIGS_PKG_SUBDIR
from easybuild.framework.easyconfig.constants import constant_documentation
from easybuild.framework.easyconfig.easyconfig import HAVE_AUTOPEP8
from easybuild.framework.easyconfig.format.pyheaderconfigobj import build_easyconfig_constants_dict
from easybuild.framework.easyconfig.licenses import license_documentation
from easybuild.framework.easyconfig.templates import template_documentation
from easybuild.framework.easyconfig.tools import get_paths_for
from easybuild.framework.extension import Extension
from easybuild.tools import build_log, run  # build_log should always stay there, to ensure EasyBuildLog
from easybuild.tools.build_log import EasyBuildError, raise_easybuilderror
from easybuild.tools.config import DEFAULT_JOB_BACKEND, DEFAULT_LOGFILE_FORMAT, DEFAULT_MNS, DEFAULT_MODULE_SYNTAX
from easybuild.tools.config import DEFAULT_MODULES_TOOL, DEFAULT_MODULECLASSES, DEFAULT_PATH_SUBDIRS
from easybuild.tools.config import DEFAULT_PKG_RELEASE, DEFAULT_PKG_TOOL, DEFAULT_PKG_TYPE, DEFAULT_PNS, DEFAULT_PREFIX
from easybuild.tools.config import DEFAULT_REPOSITORY
from easybuild.tools.config import get_pretend_installpath, mk_full_default_path
from easybuild.tools.configobj import ConfigObj, ConfigObjError
from easybuild.tools.docs import FORMAT_RST, FORMAT_TXT, avail_easyconfig_params
from easybuild.tools.github import HAVE_GITHUB_API, HAVE_KEYRING, fetch_github_token
from easybuild.tools.include import include_easyblocks, include_module_naming_schemes, include_toolchains
from easybuild.tools.job.backend import avail_job_backends
from easybuild.tools.modules import avail_modules_tools
from easybuild.tools.module_generator import ModuleGeneratorLua, avail_module_generators
from easybuild.tools.module_naming_scheme import GENERAL_CLASS
from easybuild.tools.module_naming_scheme.utilities import avail_module_naming_schemes
from easybuild.tools.modules import Lmod
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.run import run_cmd
from easybuild.tools.package.utilities import avail_package_naming_schemes
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.repository.repository import avail_repositories
from easybuild.tools.version import this_is_easybuild
from vsc.utils import fancylogger
from vsc.utils.generaloption import GeneralOption


CONFIG_ENV_VAR_PREFIX = 'EASYBUILD'

XDG_CONFIG_HOME = os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), ".config"))
XDG_CONFIG_DIRS = os.environ.get('XDG_CONFIG_DIRS', '/etc').split(os.pathsep)
DEFAULT_SYS_CFGFILES = [f for d in XDG_CONFIG_DIRS for f in sorted(glob.glob(os.path.join(d, 'easybuild.d', '*.cfg')))]
DEFAULT_USER_CFGFILE = os.path.join(XDG_CONFIG_HOME, 'easybuild', 'config.cfg')


_log = fancylogger.getLogger('options', fname=False)


class EasyBuildOptions(GeneralOption):
    """Easybuild generaloption class"""
    VERSION = this_is_easybuild()

    DEFAULT_LOGLEVEL = 'INFO'
    DEFAULT_CONFIGFILES = DEFAULT_SYS_CFGFILES[:]
    if os.path.exists(DEFAULT_USER_CFGFILE):
        DEFAULT_CONFIGFILES.append(DEFAULT_USER_CFGFILE)

    ALLOPTSMANDATORY = False  # allow more than one argument
    CONFIGFILES_RAISE_MISSING = True  # don't allow non-existing config files to be specified

    def __init__(self, *args, **kwargs):
        """Constructor."""

        self.default_repositorypath = [mk_full_default_path('repositorypath')]
        self.default_robot_paths = get_paths_for(subdir=EASYCONFIGS_PKG_SUBDIR, robot_path=None) or []

        # set up constants to seed into config files parser, by section
        self.go_cfg_constants = {
            self.DEFAULTSECT: {
                'DEFAULT_REPOSITORYPATH': (self.default_repositorypath[0], "Default easyconfigs repository path"),
                'DEFAULT_ROBOT_PATHS': (os.pathsep.join(self.default_robot_paths),
                                        "List of default robot paths ('%s'-separated)" % os.pathsep),
            }
        }

        # update or define go_configfiles_initenv in named arguments to pass to parent constructor
        go_cfg_initenv = kwargs.setdefault('go_configfiles_initenv', {})
        for section, constants in self.go_cfg_constants.items():
            constants = dict([(name, value) for (name, (value, _)) in constants.items()])
            go_cfg_initenv.setdefault(section, {}).update(constants)

        super(EasyBuildOptions, self).__init__(*args, **kwargs)

    def basic_options(self):
        """basic runtime options"""
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        strictness_options = [run.IGNORE, run.WARN, run.ERROR]

        descr = ("Basic options", "Basic runtime options for EasyBuild.")

        opts = OrderedDict({
            'dry-run': ("Print build overview incl. dependencies (full paths)", None, 'store_true', False),
            'dry-run-short': ("Print build overview incl. dependencies (short paths)", None, 'store_true', False, 'D'),
            'extended-dry-run': ("Print build environment and (expected) build procedure that will be performed",
                                 None, 'store_true', False, 'x'),
            'extended-dry-run-ignore-errors': ("Ignore errors that occur during dry run", None, 'store_true', True),
            'force': ("Force to rebuild software even if it's already installed (i.e. if it can be found as module), "
                      "and skipping check for OS dependencies", None, 'store_true', False, 'f'),
            'job': ("Submit the build as a job", None, 'store_true', False),
            'logtostdout': ("Redirect main log to stdout", None, 'store_true', False, 'l'),
            'only-blocks': ("Only build listed blocks", None, 'extend', None, 'b', {'metavar': 'BLOCKS'}),
            'rebuild': ("Rebuild software, even if module already exists (don't skip OS dependencies checks)",
                        None, 'store_true', False),
            'robot': ("Enable dependency resolution, using easyconfigs in specified paths",
                      'pathlist', 'store_or_None', [], 'r', {'metavar': 'PATH[%sPATH]' % os.pathsep}),
            'robot-paths': ("Additional paths to consider by robot for easyconfigs (--robot paths get priority)",
                            'pathlist', 'add_flex', self.default_robot_paths, {'metavar': 'PATH[%sPATH]' % os.pathsep}),
            'skip': ("Skip existing software (useful for installing additional packages)",
                     None, 'store_true', False, 'k'),
            'stop': ("Stop the installation after certain step",
                     'choice', 'store_or_None', SOURCE_STEP, 's', all_stops),
            'strict': ("Set strictness level", 'choice', 'store', run.WARN, strictness_options),
        })

        self.log.debug("basic_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def software_options(self):
        # software build options
        descr = ("Software search and build options",
                 ("Specify software search and build options: EasyBuild will search for a "
                  "matching easyconfig and build it. When called with the try prefix "
                  "(i.e. --try-X ), EasyBuild will search for a matching easyconfig "
                  "and if none are found, try to generate one based on a close matching one "
                  "(NOTE: --try-X is best effort, it might produce wrong builds!)")
                 )

        opts = OrderedDict({
            'amend': (("Specify additional search and build parameters (can be used multiple times); "
                       "for example: versionprefix=foo or patches=one.patch,two.patch)"),
                      None, 'append', None, {'metavar': 'VAR=VALUE[,VALUE]'}),
            'software': ("Search and build software with given name and version",
                         None, 'extend', None, {'metavar': 'NAME,VERSION'}),
            'software-name': ("Search and build software with given name",
                              None, 'store', None, {'metavar': 'NAME'}),
            'software-version': ("Search and build software with given version",
                                 None, 'store', None, {'metavar': 'VERSION'}),
            'toolchain': ("Search and build with given toolchain (name and version)",
                          None, 'extend', None, {'metavar': 'NAME,VERSION'}),
            'toolchain-name': ("Search and build with given toolchain name",
                               None, 'store', None, {'metavar': 'NAME'}),
            'toolchain-version': ("Search and build with given toolchain version",
                                  None, 'store', None, {'metavar': 'VERSION'}),
        })

        longopts = opts.keys()
        for longopt in longopts:
            hlp = opts[longopt][0]
            hlp = "Try to %s (USE WITH CARE!)" % (hlp[0].lower() + hlp[1:])
            opts["try-%s" % longopt] = (hlp,) + opts[longopt][1:]

        # additional options that don't need a --try equivalent
        opts.update({
            'from-pr': ("Obtain easyconfigs from specified PR", int, 'store', None, {'metavar': 'PR#'}),
        })

        self.log.debug("software_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def override_options(self):
        # override options
        descr = ("Override options", "Override default EasyBuild behavior.")

        opts = OrderedDict({
            'add-dummy-to-minimal-toolchains': ("Include dummy in minimal toolchain searches", None, 'store_true', False),
            'allow-modules-tool-mismatch': ("Allow mismatch of modules tool and definition of 'module' function",
                                            None, 'store_true', False),
            'cleanup-builddir': ("Cleanup build dir after successful installation.", None, 'store_true', True),
            'cleanup-tmpdir': ("Cleanup tmp dir after successful run.", None, 'store_true', True),
            'color': ("Allow color output", None, 'store_true', True),
            'deprecated': ("Run pretending to be (future) version, to test removal of deprecated code.",
                           None, 'store', None),
            'download-timeout': ("Timeout for initiating downloads (in seconds)", float, 'store', None),
            'dump-autopep8': ("Reformat easyconfigs using autopep8 when dumping them", None, 'store_true', False),
            'easyblock': ("easyblock to use for processing the spec file or dumping the options",
                          None, 'store', None, 'e', {'metavar': 'CLASS'}),
            'experimental': ("Allow experimental code (with behaviour that can be changed/removed at any given time).",
                             None, 'store_true', False),
            'group': ("Group to be used for software installations (only verified, not set)", None, 'store', None),
            'group-writable-installdir': ("Enable group write permissions on installation directory after installation",
                                          None, 'store_true', False),
            'hidden': ("Install 'hidden' module file(s) by prefixing their name with '.'", None, 'store_true', False),
            'ignore-osdeps': ("Ignore any listed OS dependencies", None, 'store_true', False),
            'filter-deps': ("Comma separated list of dependencies that you DON'T want to install with EasyBuild, "
                            "because equivalent OS packages are installed. (e.g. --filter-deps=zlib,ncurses)",
                            'strlist', 'extend', None),
            'hide-deps': ("Comma separated list of dependencies that you want automatically hidden, "
                          "(e.g. --hide-deps=zlib,ncurses)", 'strlist', 'extend', None),
            'minimal-toolchains': ("Use minimal toolchain when resolving dependencies", None, 'store_true', False),
            'module-only': ("Only generate module file(s); skip all steps except for %s" % ', '.join(MODULE_ONLY_STEPS),
                            None, 'store_true', False),
            'optarch': ("Set architecture optimization, overriding native architecture optimizations",
                        None, 'store', None),
            'parallel': ("Specify (maximum) level of parallellism used during build procedure",
                         'int', 'store', None),
            'pretend': (("Does the build/installation in a test directory located in $HOME/easybuildinstall"),
                        None, 'store_true', False, 'p'),
            'read-only-installdir': ("Set read-only permissions on installation directory after installation",
                                     None, 'store_true', False),
            'set-gid-bit': ("Set group ID bit on newly created directories", None, 'store_true', False),
            'sticky-bit': ("Set sticky bit on newly created directories", None, 'store_true', False),
            'skip-test-cases': ("Skip running test cases", None, 'store_true', False, 't'),
            'umask': ("umask to use (e.g. '022'); non-user write permissions on install directories are removed",
                      None, 'store', None),
            'update-modules-tool-cache': ("Update modules tool cache file(s) after generating module file",
                                          None, 'store_true', False),
            'use-existing-modules': ("Use existing modules when resolving dependencies with minimal toolchains",
                                     None, 'store_true', False),
        })

        self.log.debug("override_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def config_options(self):
        # config options
        descr = ("Configuration options", "Configure EasyBuild behavior.")

        opts = OrderedDict({
            'avail-module-naming-schemes': ("Show all supported module naming schemes",
                                            None, 'store_true', False,),
            'avail-modules-tools': ("Show all supported module tools",
                                    None, "store_true", False,),
            'avail-repositories': ("Show all repository types (incl. non-usable)",
                                   None, "store_true", False,),
            'buildpath': ("Temporary build path", None, 'store', mk_full_default_path('buildpath')),
            'external-modules-metadata': ("List of files specifying metadata for external modules (INI format)",
                                          'strlist', 'store', []),
            'ignore-dirs': ("Directory names to ignore when searching for files/dirs",
                            'strlist', 'store', ['.git', '.svn']),
            'include-easyblocks': ("Location(s) of extra or customized easyblocks", 'strlist', 'store', []),
            'include-module-naming-schemes': ("Location(s) of extra or customized module naming schemes",
                                              'strlist', 'store', []),
            'include-toolchains': ("Location(s) of extra or customized toolchains or toolchain components",
                                   'strlist', 'store', []),
            'installpath': ("Install path for software and modules",
                            None, 'store', mk_full_default_path('installpath')),
            'installpath-modules': ("Install path for modules (if None, combine --installpath and --subdir-modules)",
                                    None, 'store', None),
            'installpath-software': ("Install path for software (if None, combine --installpath and --subdir-software)",
                                     None, 'store', None),
            'job-backend': ("Backend to use for submitting jobs", 'choice', 'store',
                            DEFAULT_JOB_BACKEND, sorted(avail_job_backends().keys())),
            # purposely take a copy for the default logfile format
            'logfile-format': ("Directory name and format of the log file",
                               'strtuple', 'store', DEFAULT_LOGFILE_FORMAT[:], {'metavar': 'DIR,FORMAT'}),
            'module-naming-scheme': ("Module naming scheme to use", None, 'store', DEFAULT_MNS),
            'module-syntax': ("Syntax to be used for module files", 'choice', 'store', DEFAULT_MODULE_SYNTAX,
                              sorted(avail_module_generators().keys())),
            'moduleclasses': (("Extend supported module classes "
                               "(For more info on the default classes, use --show-default-moduleclasses)"),
                              None, 'extend', [x[0] for x in DEFAULT_MODULECLASSES]),
            'modules-footer': ("Path to file containing footer to be added to all generated module files",
                               None, 'store_or_None', None, {'metavar': "PATH"}),
            'modules-tool': ("Modules tool to use",
                             'choice', 'store', DEFAULT_MODULES_TOOL, sorted(avail_modules_tools().keys())),
            'packagepath': ("The destination path for the packages built by package-tool",
                             None, 'store', mk_full_default_path('packagepath')),
            'package-naming-scheme': ("Packaging naming scheme choice",
                                      'choice', 'store', DEFAULT_PNS, sorted(avail_package_naming_schemes().keys())),
            'prefix': (("Change prefix for buildpath, installpath, sourcepath and repositorypath "
                        "(used prefix for defaults %s)" % DEFAULT_PREFIX),
                       None, 'store', None),
            'recursive-module-unload': ("Enable generating of modules that unload recursively.",
                                        None, 'store_true', False),
            'repository': ("Repository type, using repositorypath",
                           'choice', 'store', DEFAULT_REPOSITORY, sorted(avail_repositories().keys())),
            'repositorypath': (("Repository path, used by repository "
                                "(is passed as list of arguments to create the repository instance). "
                                "For more info, use --avail-repositories."),
                               'strlist', 'store', self.default_repositorypath),
            'sourcepath': ("Path(s) to where sources should be downloaded (string, colon-separated)",
                           None, 'store', mk_full_default_path('sourcepath')),
            'subdir-modules': ("Installpath subdir for modules", None, 'store', DEFAULT_PATH_SUBDIRS['subdir_modules']),
            'subdir-software': ("Installpath subdir for software",
                                None, 'store', DEFAULT_PATH_SUBDIRS['subdir_software']),
            'suffix-modules-path': ("Suffix for module files install path", None, 'store', GENERAL_CLASS),
            # this one is sort of an exception, it's something jobscripts can set,
            # has no real meaning for regular eb usage
            'testoutput': ("Path to where a job should place the output (to be set within jobscript)",
                           None, 'store', None),
            'tmp-logdir': ("Log directory where temporary log files are stored", None, 'store', None),
            'tmpdir': ('Directory to use for temporary storage', None, 'store', None),
        })

        self.log.debug("config_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def informative_options(self):
        # informative options
        descr = ("Informative options", "Obtain information about EasyBuild.")

        opts = OrderedDict({
            'avail-cfgfile-constants': ("Show all constants that can be used in configuration files",
                                        None, 'store_true', False),
            'avail-easyconfig-constants': ("Show all constants that can be used in easyconfigs",
                                           None, 'store_true', False),
            'avail-easyconfig-licenses': ("Show all license constants that can be used in easyconfigs",
                                          None, 'store_true', False),
            'avail-easyconfig-params': (("Show all easyconfig parameters (include "
                                         "easyblock-specific ones by using -e)"),
                                        'choice', 'store_or_None', FORMAT_TXT, [FORMAT_RST, FORMAT_TXT], 'a'),
            'avail-easyconfig-templates': (("Show all template names and template constants "
                                            "that can be used in easyconfigs"),
                                           None, 'store_true', False),
            'dep-graph': ("Create dependency graph",
                          None, "store", None, {'metavar': 'depgraph.<ext>'}),
            'list-easyblocks': ("Show list of available easyblocks",
                                'choice', 'store_or_None', 'simple', ['simple', 'detailed']),
            'list-toolchains': ("Show list of known toolchains",
                                None, 'store_true', False),
            'search': ("Search for easyconfig files in the robot directory, print full paths",
                       None, 'store', None, {'metavar': 'STR'}),
            'search-short': ("Search for easyconfig files in the robot directory, print short paths",
                             None, 'store', None, 'S', {'metavar': 'STR'}),
            'show-default-configfiles': ("Show list of default config files", None, 'store_true', False),
            'show-default-moduleclasses': ("Show default module classes with description",
                                           None, 'store_true', False),
        })

        self.log.debug("informative_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def regtest_options(self):
        # regression test options
        descr = ("Regression test options", "Run and control an EasyBuild regression test.")

        opts = OrderedDict({
            'aggregate-regtest': ("Collect all the xmls inside the given directory and generate a single file",
                                  None, 'store', None, {'metavar': 'DIR'}),
            'dump-test-report': ("Dump test report to specified path", None, 'store_or_None', 'test_report.md'),
            'github-user': ("GitHub username", None, 'store', None),
            'regtest': ("Enable regression test mode",
                        None, 'store_true', False),
            'regtest-output-dir': ("Set output directory for test-run",
                                   None, 'store', None, {'metavar': 'DIR'}),
            'review-pr': ("Review specified pull request", int, 'store', None, {'metavar': 'PR#'}),
            'sequential': ("Specify this option if you want to prevent parallel build",
                           None, 'store_true', False),
            'upload-test-report': ("Upload full test report as a gist on GitHub", None, 'store_true', False),
            'test-report-env-filter': ("Regex used to filter out variables in environment dump of test report",
                                       None, 'regex', None),
        })

        self.log.debug("regtest_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def package_options(self):
        # package-related options
        descr = ("Package options", "Control packaging performed by EasyBuild.")

        opts = OrderedDict({
            'package': ("Enabling packaging", None, 'store_true', False),
            'package-tool': ("Packaging tool to use", None, 'store', DEFAULT_PKG_TOOL),
            'package-type': ("Type of package to generate", None, 'store', DEFAULT_PKG_TYPE),
            'package-release': ("Package release iteration number", None, 'store', DEFAULT_PKG_RELEASE),
        })

        self.log.debug("package_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def easyconfig_options(self):
        # easyconfig options (to be passed to easyconfig instance)
        descr = ("Options for Easyconfigs", "Options to be passed to all Easyconfig.")

        opts = None
        self.log.debug("easyconfig_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr, prefix='easyconfig')

    def job_options(self):
        """Option related to --job."""
        descr = ("Options for job backend", "Options for job backend (only relevant when --job is used)")

        opts = OrderedDict({
            'backend-config': ("Configuration file for job backend", None, 'store', None),
            'cores': ("Number of cores to request per job", 'int', 'store', None),
            'max-walltime': ("Maximum walltime for jobs (in hours)", 'int', 'store', 24),
            'output-dir': ("Output directory for jobs (default: current directory)", None, 'store', os.getcwd()),
            'polling-interval': ("Interval between polls for status of jobs (in seconds)", float, 'store', 30.0),
            'target-resource': ("Target resource for jobs", None, 'store', None),
        })

        self.log.debug("job_options: descr %s opts %s", descr, opts)
        self.add_group_parser(opts, descr, prefix='job')

    def easyblock_options(self):
        # easyblock options (to be passed to easyblock instance)
        descr = ("Options for Easyblocks", "Options to be passed to all Easyblocks.")

        opts = None
        self.log.debug("easyblock_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr, prefix='easyblock')

    def unittest_options(self):
        # unittest options
        descr = ("Unittest options", "Options dedicated to unittesting (experts only).")

        opts = OrderedDict({
            'file': ("Log to this file in unittest mode", None, 'store', None),
        })

        self.log.debug("unittest_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr, prefix='unittest')

    def validate(self):
        """Additional validation of options"""
        error_msgs = []

        for opt in ['software', 'try-software', 'toolchain', 'try-toolchain']:
            val = getattr(self.options, opt.replace('-', '_'))
            if val and len(val) != 2:
                msg = "--%s requires NAME,VERSION (given %s)" % (opt, ','.join(val))
                error_msgs.append(msg)

        if self.options.umask:
            umask_regex = re.compile('^[0-7]{3}$')
            if not umask_regex.match(self.options.umask):
                msg = "--umask value should be 3 digits (0-7) (regex pattern '%s')" % umask_regex.pattern
                error_msgs.append(msg)

        # subdir options must be relative
        for typ in ['modules', 'software']:
            subdir_opt = 'subdir_%s' % typ
            val = getattr(self.options, subdir_opt)
            if os.path.isabs(getattr(self.options, subdir_opt)):
                msg = "Configuration option '%s' must specify a *relative* path (use 'installpath-%s' instead?): '%s'"
                msg = msg % (subdir_opt, typ, val)
                error_msgs.append(msg)

        # specified module naming scheme must be a known one
        avail_mnss = avail_module_naming_schemes()
        if self.options.module_naming_scheme and self.options.module_naming_scheme not in avail_mnss:
            msg = "Selected module naming scheme '%s' is unknown: %s" % (self.options.module_naming_scheme, avail_mnss)
            error_msgs.append(msg)

        if error_msgs:
            raise EasyBuildError("Found problems validating the options: %s", '\n'.join(error_msgs))

    def postprocess(self):
        """Do some postprocessing, in particular print stuff"""
        build_log.EXPERIMENTAL = self.options.experimental

        # set strictness of run module
        if self.options.strict:
            run.strictness = self.options.strict

        # override current version of EasyBuild with version specified to --deprecated
        if self.options.deprecated:
            build_log.CURRENT_VERSION = LooseVersion(self.options.deprecated)

        # log to specified value of --unittest-file
        if self.options.unittest_file:
            fancylogger.logToFile(self.options.unittest_file)

        # set tmpdir
        self.tmpdir = set_tmpdir(self.options.tmpdir)

        # take --include options into account
        self._postprocess_include()

        # prepare for --list/--avail
        if any([self.options.avail_easyconfig_params, self.options.avail_easyconfig_templates,
                self.options.list_easyblocks, self.options.list_toolchains, self.options.avail_cfgfile_constants,
                self.options.avail_easyconfig_constants, self.options.avail_easyconfig_licenses,
                self.options.avail_repositories, self.options.show_default_moduleclasses,
                self.options.avail_modules_tools, self.options.avail_module_naming_schemes,
                self.options.show_default_configfiles,
                ]):
            build_easyconfig_constants_dict()  # runs the easyconfig constants sanity check
            self._postprocess_list_avail()

        # fail early if required dependencies for functionality requiring using GitHub API are not available:
        if self.options.from_pr or self.options.upload_test_report:
            if not HAVE_GITHUB_API:
                raise EasyBuildError("Required support for using GitHub API is not available (see warnings).")

        if self.options.module_syntax == ModuleGeneratorLua.SYNTAX and self.options.modules_tool != Lmod.__name__:
            raise EasyBuildError("Generating Lua module files requires Lmod as modules tool.")

        # make sure a GitHub token is available when it's required
        if self.options.upload_test_report:
            if not HAVE_KEYRING:
                raise EasyBuildError("Python 'keyring' module required for obtaining GitHub token is not available.")
            if self.options.github_user is None:
                raise EasyBuildError("No GitHub user name provided, required for fetching GitHub token.")
            token = fetch_github_token(self.options.github_user)
            if token is None:
                raise EasyBuildError("Failed to obtain required GitHub token for user '%s'", self.options.github_user)

        # make sure autopep8 is available when it needs to be
        if self.options.dump_autopep8:
            if not HAVE_AUTOPEP8:
                raise EasyBuildError("Python 'autopep8' module required to reformat dumped easyconfigs as requested")

        self._postprocess_external_modules_metadata()

        self._postprocess_config()

    def _postprocess_external_modules_metadata(self):
        """Parse file(s) specifying metadata for external modules."""
        # leave external_modules_metadata untouched if no files are provided
        if not self.options.external_modules_metadata:
            self.log.debug("No metadata provided for external modules.")
            return

        parsed_external_modules_metadata = ConfigObj()
        for path in self.options.external_modules_metadata:
            if os.path.exists(path):
                self.log.debug("Parsing %s with external modules metadata", path)
                try:
                    parsed_external_modules_metadata.merge(ConfigObj(path))
                except ConfigObjError, err:
                    raise EasyBuildError("Failed to parse %s with external modules metadata: %s", path, err)
            else:
                raise EasyBuildError("Specified path for file with external modules metadata does not exist: %s", path)

        # make sure name/version values are always lists, make sure they're equal length
        for mod, entry in parsed_external_modules_metadata.items():
            for key in ['name', 'version']:
                if isinstance(entry.get(key), basestring):
                    entry[key] = [entry[key]]
                    self.log.debug("Transformed external module metadata value %s for %s into a single-value list: %s",
                                   key, mod, entry[key])

            # if both names and versions are available, lists must be of same length
            names, versions = entry.get('name'), entry.get('version')
            if names is not None and versions is not None and len(names) != len(versions):
                raise EasyBuildError("Different length for lists of names/versions in metadata for external module %s: "
                                     "names: %s; versions: %s", mod, names, versions)

        self.options.external_modules_metadata = parsed_external_modules_metadata
        self.log.debug("External modules metadata: %s", self.options.external_modules_metadata)

    def _postprocess_include(self):
        """Postprocess --include options."""
        # set up included easyblocks, module naming schemes and toolchains/toolchain components
        if self.options.include_easyblocks:
            include_easyblocks(self.tmpdir, self.options.include_easyblocks)

        if self.options.include_module_naming_schemes:
            include_module_naming_schemes(self.tmpdir, self.options.include_module_naming_schemes)

        if self.options.include_toolchains:
            include_toolchains(self.tmpdir, self.options.include_toolchains)

    def _postprocess_config(self):
        """Postprocessing of configuration options"""
        if self.options.prefix is not None:
            # prefix applies to all paths, and repository has to be reinitialised to take new repositorypath in account
            # in the legacy-style configuration, repository is initialised in configuration file itself
            for dest in ['installpath', 'buildpath', 'sourcepath', 'repository', 'repositorypath', 'packagepath']:
                if not self.options._action_taken.get(dest, False):
                    if dest == 'repository':
                        setattr(self.options, dest, DEFAULT_REPOSITORY)
                    elif dest == 'repositorypath':
                        repositorypath = [mk_full_default_path(dest, prefix=self.options.prefix)]
                        setattr(self.options, dest, repositorypath)
                        self.go_cfg_constants[self.DEFAULTSECT]['DEFAULT_REPOSITORYPATH'] = repositorypath
                    else:
                        setattr(self.options, dest, mk_full_default_path(dest, prefix=self.options.prefix))
                    # LEGACY this line is here for oldstyle config reasons
                    self.options._action_taken[dest] = True

        if self.options.pretend:
            self.options.installpath = get_pretend_installpath()

        if self.options.robot is not None:
            # paths specified to --robot have preference over --robot-paths
            # keep both values in sync if robot is enabled, which implies enabling dependency resolver
            self.options.robot_paths = self.options.robot + self.options.robot_paths
            self.options.robot = self.options.robot_paths

    def _postprocess_list_avail(self):
        """Create all the additional info that can be requested (exit at the end)"""
        msg = ''

        # dump supported configuration file constants
        if self.options.avail_cfgfile_constants:
            msg += self.avail_cfgfile_constants()

        # dump possible easyconfig params
        if self.options.avail_easyconfig_params:
            msg += avail_easyconfig_params(self.options.easyblock, self.options.avail_easyconfig_params)

        # dump easyconfig template options
        if self.options.avail_easyconfig_templates:
            msg += template_documentation()

        # dump easyconfig constant options
        if self.options.avail_easyconfig_constants:
            msg += constant_documentation()

        # dump easyconfig license options
        if self.options.avail_easyconfig_licenses:
            msg += license_documentation()

        # dump available easyblocks
        if self.options.list_easyblocks:
            msg += self.avail_easyblocks()

        # dump known toolchains
        if self.options.list_toolchains:
            msg += self.avail_toolchains()

        # dump known repository types
        if self.options.avail_repositories:
            msg += self.avail_repositories()

        # dump supported modules tools
        if self.options.avail_modules_tools:
            msg += self.avail_list('modules tools', avail_modules_tools())

        # dump supported module naming schemes
        if self.options.avail_module_naming_schemes:
            msg += self.avail_list('module naming schemes', avail_module_naming_schemes())

        # dump default list of config files that are considered
        if self.options.show_default_configfiles:
            msg += self.show_default_configfiles()

        # dump default moduleclasses with description
        if self.options.show_default_moduleclasses:
            msg += self.show_default_moduleclasses()

        if self.options.unittest_file:
            self.log.info(msg)
        else:
            print msg

        # cleanup tmpdir
        try:
            shutil.rmtree(self.tmpdir)
        except OSError as err:
            raise EasyBuildError("Failed to clean up temporary directory %s: %s", self.tmpdir, err)

        sys.exit(0)

    def avail_cfgfile_constants(self):
        """
        Return overview of constants supported in configuration files.
        """
        lines = [
            "Constants available (only) in configuration files:",
            "syntax: %(CONSTANT_NAME)s",
        ]
        for section in self.go_cfg_constants:
            lines.append('')
            if section != self.DEFAULTSECT:
                section_title = "only in '%s' section:" % section
                lines.append(section_title)
            for cst_name, (cst_value, cst_help) in sorted(self.go_cfg_constants[section].items()):
                lines.append("* %s: %s [value: %s]" % (cst_name, cst_help, cst_value))
        return '\n'.join(lines)

    def avail_classes_tree(self, classes, class_names, locations, detailed, depth=0):
        """Print list of classes as a tree."""
        txt = []
        for class_name in class_names:
            class_info = classes[class_name]
            if detailed:
                mod = class_info['module']
                loc = ''
                if mod in locations:
                    loc = '@ %s' % locations[mod]
                txt.append("%s|-- %s (%s %s)" % ("|   " * depth, class_name, mod, loc))
            else:
                txt.append("%s|-- %s" % ("|   " * depth, class_name))
            if 'children' in class_info:
                txt.extend(self.avail_classes_tree(classes, class_info['children'], locations, detailed, depth + 1))
        return txt

    def avail_easyblocks(self):
        """Get a class tree for easyblocks."""
        detailed = self.options.list_easyblocks == "detailed"
        module_regexp = re.compile(r"^([^_].*)\.py$")

        # finish initialisation of the toolchain module (ie set the TC_CONSTANT constants)
        search_toolchain('')

        locations = {}
        for package in ["easybuild.easyblocks", "easybuild.easyblocks.generic"]:
            __import__(package)

            # determine paths for this package
            paths = sys.modules[package].__path__

            # import all modules in these paths
            for path in paths:
                if os.path.exists(path):
                    for f in os.listdir(path):
                        res = module_regexp.match(f)
                        if res:
                            easyblock = '%s.%s' % (package, res.group(1))
                            if easyblock not in locations:
                                __import__(easyblock)
                                locations.update({easyblock: os.path.join(path, f)})
                            else:
                                self.log.debug("%s already imported from %s, ignoring %s",
                                               easyblock, locations[easyblock], path)

        def add_class(classes, cls):
            """Add a new class, and all of its subclasses."""
            children = cls.__subclasses__()
            classes.update({cls.__name__: {
                'module': cls.__module__,
                'children': [x.__name__ for x in children]
            }})
            for child in children:
                add_class(classes, child)

        roots = [EasyBlock, Extension]

        classes = {}
        for root in roots:
            add_class(classes, root)

        # Print the tree, start with the roots
        txt = []
        for root in roots:
            root = root.__name__
            if detailed:
                mod = classes[root]['module']
                loc = ''
                if mod in locations:
                    loc = ' @ %s' % locations[mod]
                txt.append("%s (%s%s)" % (root, mod, loc))
            else:
                txt.append("%s" % root)
            if 'children' in classes[root]:
                txt.extend(self.avail_classes_tree(classes, classes[root]['children'], locations, detailed))
                txt.append("")

        return '\n'.join(txt)

    def avail_toolchains(self):
        """Show list of known toolchains."""
        _, all_tcs = search_toolchain('')
        all_tcs_names = [x.NAME for x in all_tcs]
        tclist = sorted(zip(all_tcs_names, all_tcs))

        txt = ["List of known toolchains (toolchainname: module[,module...]):"]

        for (tcname, tcc) in tclist:
            tc = tcc(version='1.2.3')  # version doesn't matter here, but something needs to be there
            tc_elems = nub(sorted([e for es in tc.definition().values() for e in es]))
            txt.append("\t%s: %s" % (tcname, ', '.join(tc_elems)))

        return '\n'.join(txt)

    def avail_repositories(self):
        """Show list of known repository types."""
        repopath_defaults = self.default_repositorypath
        all_repos = avail_repositories(check_useable=False)
        usable_repos = avail_repositories(check_useable=True).keys()

        indent = ' ' * 2
        txt = ['All avaliable repository types']
        repos = sorted(all_repos.keys())
        for repo in repos:
            if repo in usable_repos:
                missing = ''
            else:
                missing = ' (*not usable*, something is missing (e.g. a required Python module))'
            if repo in repopath_defaults:
                default = ' (default arguments: %s)' % ', '.join(repopath_defaults[repo])
            else:
                default = ' (no default arguments)'

            txt.append("%s* %s%s%s" % (indent, repo, default, missing))
            txt.append("%s%s" % (indent * 3, all_repos[repo].DESCRIPTION))

        return "\n".join(txt)

    def avail_list(self, name, items):
        """Show list of available values passed by argument."""
        return "List of supported %s:\n\t%s" % (name, '\n\t'.join(items))

    def show_default_configfiles(self):
        """Show list of default config files."""
        xdg_config_home = os.environ.get('XDG_CONFIG_HOME', '(not set)')
        xdg_config_dirs = os.environ.get('XDG_CONFIG_DIRS', '(not set)')
        system_cfg_glob_paths = os.path.join('{' + ', '.join(XDG_CONFIG_DIRS) + '}', 'easybuild.d', '*.cfg')
        found_cfgfile_cnt = len(self.DEFAULT_CONFIGFILES)
        found_cfgfile_list = ', '.join(self.DEFAULT_CONFIGFILES) or '(none)'
        lines = [
            "Default list of configuration files:",
            '',
            "[with $XDG_CONFIG_HOME: %s, $XDG_CONFIG_DIRS: %s]" % (xdg_config_home, xdg_config_dirs),
            '',
            "* user-level: %s" % os.path.join('${XDG_CONFIG_HOME:-$HOME/.config}', 'easybuild', 'config.cfg'),
            "  -> %s => %s" % (DEFAULT_USER_CFGFILE, ('not found', 'found')[os.path.exists(DEFAULT_USER_CFGFILE)]),
            "* system-level: %s" % os.path.join('${XDG_CONFIG_DIRS:-/etc}', 'easybuild.d', '*.cfg'),
            "  -> %s => %s" % (system_cfg_glob_paths, ', '.join(DEFAULT_SYS_CFGFILES) or "(no matches)"),
            '',
            "Default list of existing configuration files (%d): %s" % (found_cfgfile_cnt, found_cfgfile_list),
        ]
        return '\n'.join(lines)

    def show_default_moduleclasses(self):
        """Show list of default moduleclasses and description."""
        lines = ["Default available module classes:", '']
        maxlen = max([len(x[0]) for x in DEFAULT_MODULECLASSES]) + 1  # at least 1 space
        for name, descr in DEFAULT_MODULECLASSES:
            lines.append("\t%s:%s%s" % (name, (" " * (maxlen - len(name))), descr))
        return '\n'.join(lines)


def parse_options(args=None):
    """wrapper function for option parsing"""
    if os.environ.get('DEBUG_EASYBUILD_OPTIONS', '0').lower() in ('1', 'true', 'yes', 'y'):
        # very early debug, to debug the generaloption itself
        fancylogger.logToScreen(enable=True)
        fancylogger.setLogLevel('DEBUG')

    usage = "%prog [options] easyconfig [...]"
    description = ("Builds software based on easyconfig (or parse a directory).\n"
                   "Provide one or more easyconfigs or directories, use -H or --help more information.")

    try:
        eb_go = EasyBuildOptions(usage=usage, description=description, prog='eb', envvar_prefix=CONFIG_ENV_VAR_PREFIX,
                                 go_args=args, error_env_options=True, error_env_option_method=raise_easybuilderror)
    except Exception as err:
        raise EasyBuildError("Failed to parse configuration options: %s" % err)

    return eb_go


def process_software_build_specs(options):
    """
    Create a dictionary with specified software build options.
    The options arguments should be a parsed option list (as delivered by parse_options(args).options)
    """

    try_to_generate = False
    build_specs = {}
    logger = fancylogger.getLogger()

    # regular options: don't try to generate easyconfig, and search
    opts_map = {
        'name': options.software_name,
        'version': options.software_version,
        'toolchain_name': options.toolchain_name,
        'toolchain_version': options.toolchain_version,
    }

    # try options: enable optional generation of easyconfig
    try_opts_map = {
        'name': options.try_software_name,
        'version': options.try_software_version,
        'toolchain_name': options.try_toolchain_name,
        'toolchain_version': options.try_toolchain_version,
    }

    # process easy options
    for (key, opt) in opts_map.items():
        if opt:
            build_specs[key] = opt
            # remove this key from the dict of try-options (overruled)
            try_opts_map.pop(key)

    for (key, opt) in try_opts_map.items():
        if opt:
            build_specs[key] = opt
            # only when a try option is set do we enable generating easyconfigs
            try_to_generate = True

    # process --(try-)software/toolchain
    for opt in ['software', 'toolchain']:
        val = getattr(options, opt)
        tryval = getattr(options, 'try_%s' % opt)
        if val or tryval:
            if val and tryval:
                logger.warning("Ignoring --try-%(opt)s, only using --%(opt)s specification" % {'opt': opt})
            elif tryval:
                try_to_generate = True
            val = val or tryval  # --try-X value is overridden by --X
            key_prefix = ''
            if opt == 'toolchain':
                key_prefix = 'toolchain_'
            build_specs.update({
                '%sname' % key_prefix: val[0],
                '%sversion' % key_prefix: val[1],
            })

    # provide both toolchain and toolchain_name/toolchain_version keys
    if 'toolchain_name' in build_specs:
        build_specs['toolchain'] = {
            'name': build_specs['toolchain_name'],
            'version': build_specs.get('toolchain_version', None),
        }

    # process --amend and --try-amend
    if options.amend or options.try_amend:

        amends = []
        if options.amend:
            amends += options.amend
            if options.try_amend:
                logger.warning("Ignoring options passed via --try-amend, only using those passed via --amend.")
        elif options.try_amend:
            amends += options.try_amend
            try_to_generate = True

        for amend_spec in amends:
            # e.g., 'foo=bar=baz' => foo = 'bar=baz'
            param = amend_spec.split('=')[0]
            value = '='.join(amend_spec.split('=')[1:])
            # support list values by splitting on ',' if its there
            # e.g., 'foo=bar,baz' => foo = ['bar', 'baz']
            if ',' in value:
                value = value.split(',')
            build_specs.update({param: value})

    return (try_to_generate, build_specs)


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
        raise EasyBuildError("Failed to create temporary directory (tmpdir: %s): %s", tmpdir, err)

    _log.info("Temporary directory used in this EasyBuild run: %s" % current_tmpdir)

    for var in ['TMPDIR', 'TEMP', 'TMP']:
        env.setvar(var, current_tmpdir, verbose=False)

    # reset to make sure tempfile picks up new temporary directory to use
    tempfile.tempdir = None

    # test if temporary directory allows to execute files, warn if it doesn't
    try:
        fd, tmptest_file = tempfile.mkstemp()
        os.close(fd)
        os.chmod(tmptest_file, 0700)
        if not run_cmd(tmptest_file, simple=True, log_ok=False, regexp=False, force_in_dry_run=True):
            msg = "The temporary directory (%s) does not allow to execute files. " % tempfile.gettempdir()
            msg += "This can cause problems in the build process, consider using --tmpdir."
            if raise_error:
                raise EasyBuildError(msg)
            else:
                _log.warning(msg)
        else:
            _log.debug("Temporary directory %s allows to execute files, good!" % tempfile.gettempdir())
        os.remove(tmptest_file)

    except OSError, err:
        raise EasyBuildError("Failed to test whether temporary directory allows to execute files: %s", err)

    return current_tmpdir
