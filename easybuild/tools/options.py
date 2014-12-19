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
Command line options for eb

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import os
import re
import sys
from distutils.version import LooseVersion
from vsc.utils.missing import nub

from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig import EASYCONFIGS_PKG_SUBDIR
from easybuild.framework.easyconfig.constants import constant_documentation
from easybuild.framework.easyconfig.default import convert_to_help
from easybuild.framework.easyconfig.easyconfig import get_easyblock_class
from easybuild.framework.easyconfig.format.pyheaderconfigobj import build_easyconfig_constants_dict
from easybuild.framework.easyconfig.licenses import license_documentation
from easybuild.framework.easyconfig.templates import template_documentation
from easybuild.framework.easyconfig.tools import get_paths_for
from easybuild.framework.extension import Extension
from easybuild.tools import build_log, config, run  # @UnusedImport make sure config is always initialized!
from easybuild.tools.config import DEFAULT_LOGFILE_FORMAT, DEFAULT_MNS, DEFAULT_MODULES_TOOL, DEFAULT_MODULECLASSES
from easybuild.tools.config import DEFAULT_PATH_SUBDIRS, DEFAULT_PREFIX, DEFAULT_REPOSITORY, DEFAULT_TMP_LOGDIR
from easybuild.tools.config import get_default_configfiles, get_pretend_installpath
from easybuild.tools.config import get_default_oldstyle_configfile, mk_full_default_path
from easybuild.tools.github import HAVE_GITHUB_API, HAVE_KEYRING, fetch_github_token
from easybuild.tools.modules import avail_modules_tools
from easybuild.tools.module_naming_scheme import GENERAL_CLASS
from easybuild.tools.module_naming_scheme.utilities import avail_module_naming_schemes
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.repository.repository import avail_repositories
from easybuild.tools.version import this_is_easybuild
from vsc.utils import fancylogger
from vsc.utils.generaloption import GeneralOption
from vsc.utils.missing import any


class EasyBuildOptions(GeneralOption):
    """Easybuild generaloption class"""
    VERSION = this_is_easybuild()

    DEFAULT_LOGLEVEL = 'INFO'
    DEFAULT_CONFIGFILES = get_default_configfiles()

    ALLOPTSMANDATORY = False  # allow more than one argument

    def __init__(self, *args, **kwargs):
        """Constructor."""

        self.default_robot_paths = get_paths_for(subdir=EASYCONFIGS_PKG_SUBDIR, robot_path=None) or []

        # set up constants to seed into config files parser, by section
        self.go_cfg_constants = {
            self.DEFAULTSECT: {
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
            'force': ("Force to rebuild software even if it's already installed (i.e. if it can be found as module)",
                      None, 'store_true', False, 'f'),
            'job': ("Submit the build as a job", None, 'store_true', False),
            'logtostdout': ("Redirect main log to stdout", None, 'store_true', False, 'l'),
            'only-blocks': ("Only build listed blocks", None, 'extend', None, 'b', {'metavar': 'BLOCKS'}),
            'robot': ("Enable dependency resolution, using easyconfigs in specified paths",
                      'pathlist', 'store_or_None', [], 'r', {'metavar': 'PATH[%sPATH]' % os.pathsep}),
            'robot-paths': ("Additional paths to consider by robot for easyconfigs (--robot paths get priority)",
                            'pathlist', 'store', self.default_robot_paths, {'metavar': 'PATH[%sPATH]' % os.pathsep}),
            'skip': ("Skip existing software (useful for installing additional packages)",
                     None, 'store_true', False, 'k'),
            'stop': ("Stop the installation after certain step", 'choice', 'store_or_None', 'source', 's', all_stops),
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
            'amend':(("Specify additional search and build parameters (can be used multiple times); "
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
            'allow-modules-tool-mismatch': ("Allow mismatch of modules tool and definition of 'module' function",
                                            None, 'store_true', False),
            'cleanup-builddir': ("Cleanup build dir after successful installation.", None, 'store_true', True),
            'deprecated': ("Run pretending to be (future) version, to test removal of deprecated code.",
                           None, 'store', None),
            'easyblock': ("easyblock to use for processing the spec file or dumping the options",
                          None, 'store', None, 'e', {'metavar': 'CLASS'}),
            'experimental': ("Allow experimental code (with behaviour that can be changed or removed at any given time).",
                             None, 'store_true', False),
            'group': ("Group to be used for software installations (only verified, not set)", None, 'store', None),
            'hidden': ("Install 'hidden' module file(s) by prefixing their name with '.'", None, 'store_true', False),
            'ignore-osdeps': ("Ignore any listed OS dependencies", None, 'store_true', False),
            'filter-deps': ("Comma separated list of dependencies that you DON'T want to install with EasyBuild, "
                            "because equivalent OS packages are installed. (e.g. --filter-deps=zlib,ncurses)",
                            str, 'extend', None),
            'oldstyleconfig':   ("Look for and use the oldstyle configuration file.",
                                 None, 'store_true', True),
            'pretend': (("Does the build/installation in a test directory located in $HOME/easybuildinstall"),
                         None, 'store_true', False, 'p'),
            'set-gid-bit': ("Set group ID bit on newly created directories", None, 'store_true', False),
            'sticky-bit': ("Set sticky bit on newly created directories", None, 'store_true', False),
            'skip-test-cases': ("Skip running test cases", None, 'store_true', False, 't'),
            'umask': ("umask to use (e.g. '022'); non-user write permissions on install directories are removed",
                      None, 'store', None),
            'optarch': ("Set architecture optimization, overriding native architecture optimizations",
                        None, 'store', None),
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
            'ignore-dirs': ("Directory names to ignore when searching for files/dirs",
                            'strlist', 'store', ['.git', '.svn']),
            'installpath': ("Install path for software and modules", None, 'store', mk_full_default_path('installpath')),
            'config': ("Path to EasyBuild config file (DEPRECATED, use --configfiles instead!)",
                       None, 'store', get_default_oldstyle_configfile(), 'C'),
            # purposely take a copy for the default logfile format
            'logfile-format': ("Directory name and format of the log file",
                               'strtuple', 'store', DEFAULT_LOGFILE_FORMAT[:], {'metavar': 'DIR,FORMAT'}),
            'module-naming-scheme': ("Module naming scheme",
                                     'choice', 'store', DEFAULT_MNS, sorted(avail_module_naming_schemes().keys())),
            'moduleclasses': (("Extend supported module classes "
                               "(For more info on the default classes, use --show-default-moduleclasses)"),
                               None, 'extend', [x[0] for x in DEFAULT_MODULECLASSES]),
            'modules-footer': ("Path to file containing footer to be added to all generated module files",
                               None, 'store_or_None', None, {'metavar': "PATH"}),
            'modules-tool': ("Modules tool to use",
                             'choice', 'store', DEFAULT_MODULES_TOOL, sorted(avail_modules_tools().keys())),
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
                                'strlist', 'store',
                                [mk_full_default_path('repositorypath')]),
            'show-default-moduleclasses': ("Show default module classes with description",
                                           None, 'store_true', False),
            'sourcepath': ("Path(s) to where sources should be downloaded (string, colon-separated)",
                           None, 'store', mk_full_default_path('sourcepath')),
            'subdir-modules': ("Installpath subdir for modules", None, 'store', DEFAULT_PATH_SUBDIRS['subdir_modules']),
            'subdir-software': ("Installpath subdir for software", None, 'store', DEFAULT_PATH_SUBDIRS['subdir_software']),
            'suffix-modules-path': ("Suffix for module files install path", None, 'store', GENERAL_CLASS),
            # this one is sort of an exception, it's something jobscripts can set,
            # has no real meaning for regular eb usage
            'testoutput': ("Path to where a job should place the output (to be set within jobscript)",
                            None, 'store', None),
            'tmp-logdir': ("Log directory where temporary log files are stored",
                           None, 'store', DEFAULT_TMP_LOGDIR),
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
                                         None, "store_true", False, 'a'),
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
            'sequential': ("Specify this option if you want to prevent parallel build",
                           None, 'store_true', False),
            'upload-test-report': ("Upload full test report as a gist on GitHub", None, 'store_true', None),
            'test-report-env-filter': ("Regex used to filter out variables in environment dump of test report",
                                       None, 'regex', None),
        })

        self.log.debug("regtest_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def easyconfig_options(self):
        # easyconfig options (to be passed to easyconfig instance)
        descr = ("Options for Easyconfigs", "Options to be passed to all Easyconfig.")

        opts = None
        self.log.debug("easyconfig_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr, prefix='easyconfig')

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
        error_cnt = 0

        for opt in ['software', 'try-software', 'toolchain', 'try-toolchain']:
            val = getattr(self.options, opt.replace('-', '_'))
            if val and len(val) != 2:
                self.log.warning('--%s requires NAME,VERSION (given %s)' % (opt, ','.join(val)))
                error_cnt += 1

        if self.options.umask:
            umask_regex = re.compile('^[0-7]{3}$')
            if not umask_regex.match(self.options.umask):
                self.log.warning("--umask value should be 3 digits (0-7) (regex pattern '%s')" % umask_regex.pattern)
                error_cnt += 1

        if error_cnt > 0:
            self.log.error("Found %s problems validating the options, treating warnings above as fatal." % error_cnt)

    def postprocess(self):
        """Do some postprocessing, in particular print stuff"""
        build_log.EXPERIMENTAL = self.options.experimental
        config.SUPPORT_OLDSTYLE = self.options.oldstyleconfig

        # set strictness of run module
        if self.options.strict:
            run.strictness = self.options.strict

        # override current version of EasyBuild with version specified to --deprecated
        if self.options.deprecated:
            build_log.CURRENT_VERSION = LooseVersion(self.options.deprecated)

        # log to specified value of --unittest-file
        if self.options.unittest_file:
            fancylogger.logToFile(self.options.unittest_file)

        # prepare for --list/--avail
        if any([self.options.avail_easyconfig_params, self.options.avail_easyconfig_templates,
                self.options.list_easyblocks, self.options.list_toolchains, self.options.avail_cfgfile_constants,
                self.options.avail_easyconfig_constants, self.options.avail_easyconfig_licenses,
                self.options.avail_repositories, self.options.show_default_moduleclasses,
                self.options.avail_modules_tools, self.options.avail_module_naming_schemes,
               ]):
            build_easyconfig_constants_dict()  # runs the easyconfig constants sanity check
            self._postprocess_list_avail()

        # fail early if required dependencies for functionality requiring using GitHub API are not available:
        if self.options.from_pr or self.options.upload_test_report:
            if not HAVE_GITHUB_API:
                self.log.error("Required support for using GitHub API is not available (see warnings).")

        # make sure a GitHub token is available when it's required
        if self.options.upload_test_report:
            if not HAVE_KEYRING:
                self.log.error("Python 'keyring' module required for obtaining GitHub token is not available.")
            if self.options.github_user is None:
                self.log.error("No GitHub user name provided, required for fetching GitHub token.")
            token = fetch_github_token(self.options.github_user)
            if token is None:
                self.log.error("Failed to obtain required GitHub token for user '%s'" % self.options.github_user)

        self._postprocess_config()

    def _postprocess_config(self):
        """Postprocessing of configuration options"""
        if self.options.prefix is not None:
            # prefix applies to all paths, and repository has to be reinitialised to take new repositorypath into account
            # in the legacy-style configuration, repository is initialised in configuration file itself
            for dest in ['installpath', 'buildpath', 'sourcepath', 'repository', 'repositorypath']:
                if not self.options._action_taken.get(dest, False):
                    if dest == 'repository':
                        setattr(self.options, dest, DEFAULT_REPOSITORY)
                    elif dest == 'repositorypath':
                        setattr(self.options, dest, [mk_full_default_path(dest, prefix=self.options.prefix)])
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
            msg += self.avail_easyconfig_params()

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

        # dump default moduleclasses with description
        if self.options.show_default_moduleclasses:
            msg += self.show_default_moduleclasses()

        if self.options.unittest_file:
            self.log.info(msg)
        else:
            print msg
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

    def avail_easyconfig_params(self):
        """
        Print the available easyconfig parameters, for the given easyblock.
        """
        extra = []
        app = get_easyblock_class(self.options.easyblock, default_fallback=False)
        if app is not None:
            extra = app.extra_options()
        mapping = convert_to_help(extra, has_default=False)
        if extra:
            ebb_msg = " (* indicates specific for the %s EasyBlock)" % app.__name__
            extra_names = [x[0] for x in extra]
        else:
            ebb_msg = ''
            extra_names = []
        txt = ["Available easyconfig parameters%s" % ebb_msg]
        params = [(k, v) for (k, v) in mapping.items() if k.upper() not in ['HIDDEN']]
        for key, values in params:
            txt.append("%s" % key.upper())
            txt.append('-' * len(key))
            for name, value in values:
                tabs = "\t" * (3 - (len(name) + 1) / 8)
                if name in extra_names:
                    starred = '(*)'
                else:
                    starred = ''
                txt.append("%s%s:%s%s" % (name, starred, tabs, value))
            txt.append('')

        return "\n".join(txt)

    def avail_classes_tree(self, classes, classNames, detailed, depth=0):
        """Print list of classes as a tree."""
        txt = []
        for className in classNames:
            classInfo = classes[className]
            if detailed:
                txt.append("%s|-- %s (%s)" % ("|   " * depth, className, classInfo['module']))
            else:
                txt.append("%s|-- %s" % ("|   " * depth, className))
            if 'children' in classInfo:
                txt.extend(self.avail_classes_tree(classes, classInfo['children'], detailed, depth + 1))
        return txt

    def avail_easyblocks(self):
        """Get a class tree for easyblocks."""
        detailed = self.options.list_easyblocks == "detailed"
        module_regexp = re.compile(r"^([^_].*)\.py$")

        # finish initialisation of the toolchain module (ie set the TC_CONSTANT constants)
        search_toolchain('')

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
                            __import__("%s.%s" % (package, res.group(1)))

        def add_class(classes, cls):
            """Add a new class, and all of its subclasses."""
            children = cls.__subclasses__()
            classes.update({cls.__name__: {
                                           'module': cls.__module__,
                                           'children': [x.__name__ for x in children]
                                           }
                            })
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
                txt.append("%s (%s)" % (root, classes[root]['module']))
            else:
                txt.append("%s" % root)
            if 'children' in classes[root]:
                txt.extend(self.avail_classes_tree(classes, classes[root]['children'], detailed))
                txt.append("")

        return "\n".join(txt)

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
        repopath_defaults = mk_full_default_path('repositorypath')
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

    def show_default_moduleclasses(self):
        """Show list of default moduleclasses and description."""
        txt = ["Default available moduleclasses"]
        indent = " " * 2
        maxlen = max([len(x[0]) for x in DEFAULT_MODULECLASSES]) + 1  # at least 1 space
        for name, descr in DEFAULT_MODULECLASSES:
            txt.append("%s%s:%s%s" % (indent, name, (" " * (maxlen - len(name))), descr))
        return "\n".join(txt)


def parse_options(args=None):
    """wrapper function for option parsing"""
    if os.environ.get('DEBUG_EASYBUILD_OPTIONS', '0').lower() in ('1', 'true', 'yes', 'y'):
        # very early debug, to debug the generaloption itself
        fancylogger.logToScreen(enable=True)
        fancylogger.setLogLevel('DEBUG')

    usage = "%prog [options] easyconfig [...]"
    description = ("Builds software based on easyconfig (or parse a directory).\n"
                   "Provide one or more easyconfigs or directories, use -H or --help more information.")

    eb_go = EasyBuildOptions(usage=usage, description=description, prog='eb', envvar_prefix='EASYBUILD', go_args=args)
    return eb_go


def process_software_build_specs(options):
    """
    Create a dictionary with specified software build options.
    The options arguments should be a parsed option list (as delivered by parse_options(args).options)
    """

    try_to_generate = False
    build_specs = {}

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
                self.log.warning("Ignoring --try-%(opt)s, only using --%(opt)s specification" % {'opt': opt})
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
                self.log.warning("Ignoring options passed via --try-amend, only using those passed via --amend.")
        if options.try_amend:
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
