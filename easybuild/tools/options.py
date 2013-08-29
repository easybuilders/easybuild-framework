# #
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
# #
"""
Command line options for eb

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
"""
import os
import re
import sys
from easybuild.framework.easyblock import EasyBlock, get_class
from easybuild.framework.easyconfig.constants import constant_documentation
from easybuild.framework.easyconfig.default import convert_to_help
from easybuild.framework.easyconfig.easyconfig import EasyConfig, build_easyconfig_constants_dict
from easybuild.framework.easyconfig.licenses import license_documentation
from easybuild.framework.easyconfig.templates import template_documentation
from easybuild.framework.easyconfig.tools import get_paths_for
from easybuild.framework.extension import Extension
from easybuild.tools import config, filetools  # @UnusedImport make sure config is always initialized!
from easybuild.tools.config import get_default_configfiles, get_pretend_installpath
from easybuild.tools.config import get_default_oldstyle_configfile_defaults, DEFAULT_MODULECLASSES
from easybuild.tools.modules import avail_modules_tools
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.repository import avail_repositories
from easybuild.tools.version import this_is_easybuild
from vsc import fancylogger
from vsc.utils.generaloption import GeneralOption
from vsc.utils.missing import any


class EasyBuildOptions(GeneralOption):
    """Easybuild generaloption class"""
    VERSION = this_is_easybuild()

    DEFAULT_LOGLEVEL = 'INFO'
    DEFAULT_CONFIGFILES = get_default_configfiles()

    ALLOPTSMANDATORY = False  # allow more than one argument

    def basic_options(self):
        """basic runtime options"""
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        strictness_options = [filetools.IGNORE, filetools.WARN, filetools.ERROR]

        try:
            default_robot_path = get_paths_for("easyconfigs", robot_path=None)[0]
        except:
            self.log.warning("basic_options: unable to determine default easyconfig path")
            default_robot_path = False  # False as opposed to None, since None is used for indicating that --robot was not used

        descr = ("Basic options", "Basic runtime options for EasyBuild.")

        opts = OrderedDict({
                            "only-blocks":("Only build listed blocks",
                                           None, "extend", None, "b", {'metavar':"BLOCKS"}),
                            "force":(("Force to rebuild software even if it's already installed "
                                      "(i.e. if it can be found as module)"),
                                     None, "store_true", False, "f"),
                            "job":("Submit the build as a job", None, "store_true", False),
                            "skip":("Skip existing software (useful for installing additional packages)",
                                    None, "store_true", False, "k"),
                            "robot":("Path to search for easyconfigs for missing dependencies." ,
                                     None, "store_or_None", default_robot_path, "r", {'metavar':"PATH"}),
                            "stop":("Stop the installation after certain step",
                                    "choice", "store_or_None", "source", "s", all_stops),
                            "strict":("Set strictness level",
                                      "choice", "store", filetools.WARN, strictness_options),
                            "logtostdout":("Redirect main log to stdout", None, "store_true", False, "l"),
                            "dry-run":("Resolve dependencies and print build list, then stop", 
                                      None, "store_true", False),
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
                             'software-name':("Search and build software with name",
                                              None, 'store', None, {'metavar':'NAME'}),
                             'software-version':("Search and build software with version",
                                                 None, 'store', None, {'metavar':'VERSION'}),
                             'toolchain':("Search and build with toolchain (name and version)",
                                          None, 'extend', None, {'metavar':'NAME,VERSION'}),
                             'toolchain-name':("Search and build with toolchain name",
                                               None, 'store', None, {'metavar':'NAME'}),
                             'toolchain-version':("Search and build with toolchain version",
                                                  None, 'store', None, {'metavar':'VERSION'}),
                             'amend':(("Specify additional search and build parameters (can be used multiple times); "
                                       "for example: versionprefix=foo or patches=one.patch,two.patch)"),
                                      None, 'append', None, {'metavar':'VAR=VALUE[,VALUE]'}),
                             })

        longopts = opts.keys()
        for longopt in longopts:
            hlp = opts[longopt][0]
            hlp = "Try to %s (USE WITH CARE!)" % (hlp[0].lower() + hlp[1:])
            opts["try-%s" % longopt] = (hlp,) + opts[longopt][1:]

        self.log.debug("software_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def override_options(self):
        # override options
        descr = ("Override options", "Override default EasyBuild behavior.")

        opts = {
                "easyblock":("easyblock to use for processing the spec file or dumping the options",
                             None, "store", None, "e", {'metavar':"CLASS"},),
                "pretend":(("Does the build/installation in "
                            "a test directory located in $HOME/easybuildinstall "),
                           None, "store_true", False, "p",),
                "skip-test-cases":("Skip running test cases",
                                   None, "store_true", False, "t",),
                }

        self.log.debug("override_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def config_options(self):
        # config options
        descr = ("Configuration options", "Configure EasyBuild behavior.")

        oldstyle_defaults = get_default_oldstyle_configfile_defaults()

        opts = {
                "config":("Path to EasyBuild config file",
                          None, 'store', oldstyle_defaults['config'], "C",),
                'prefix': (('Change prefix for buildpath, installpath, sourcepath and repositorypath '
                            '(repositorypath prefix is only relevant in case of FileRepository repository)'
                            '(used prefix for defaults %s)' % oldstyle_defaults['prefix']),
                               None, 'store', None),
                'buildpath': ('Temporary build path',
                               None, 'store', oldstyle_defaults['buildpath']),
                'installpath':  ('Final install path',
                                  None, 'store', oldstyle_defaults['installpath']),
                'subdir-modules': ('Subdir in installpath for modules',
                                           None, 'store', oldstyle_defaults['subdir_modules']),
                'subdir-software': ('Subdir in installpath for software',
                                            None, 'store', oldstyle_defaults['subdir_software']),
                'repository': ('Repository type, using repositorypath',
                                'choice', 'store', oldstyle_defaults['repository'],
                                sorted(avail_repositories().keys())),
                'repositorypath': (('Repository path, used by repository '
                                    '(is passed as list of arguments to create the repository instance). '
                                    'For more info, use --avail-repositories.'),
                                    'strlist', 'store',
                                    oldstyle_defaults['repositorypath'][oldstyle_defaults['repository']]),
                "avail-repositories":(("Show all repository types (incl. non-usable)"),
                                      None, "store_true", False,),
                'logfile-format': ('Directory name and format of the log file ',
                              'strtuple', 'store', oldstyle_defaults['logfile_format'], {'metavar': 'DIR,FORMAT'}),
                'tmp-logdir': ('Log directory where temporary log files are stored',
                            None, 'store', oldstyle_defaults['tmp_logdir']),
                'sourcepath': ('Path to where sources should be downloaded',
                               None, 'store', oldstyle_defaults['sourcepath']),
                'moduleclasses': (('Extend supported module classes'
                                   ' (For more info on the default classes, use --show-default-moduleclasses)'),
                                  None, 'extend', oldstyle_defaults['moduleclasses']),
                'show-default-moduleclasses': ('Show default module classes with description',
                                               None, 'store_true', False),
                'modules-tool': ('Modules tool to use',
                                 'choice', 'store', oldstyle_defaults['modules_tool'],
                                 sorted(avail_modules_tools().keys())),
                # this one is sort of an exception, it's something jobscripts can set,
                #  has no real meaning for regular eb usage
                "testoutput": ("Path to where a job should place the output (to be set within jobscript)",
                               None, "store", None),
                }

        self.log.debug("config_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def informative_options(self):
        # informative options
        descr = ("Informative options",
                 "Obtain information about EasyBuild.")

        opts = {
                "avail-easyconfig-params":(("Show all easyconfig parameters (include "
                                            "easyblock-specific ones by using -e)"),
                                            None, "store_true", False, "a",),
                "avail-easyconfig-templates":(("Show all template names and template constants "
                                               "that can be used in easyconfigs."),
                                              None, "store_true", False),
                "avail-easyconfig-constants":(("Show all constants that can be used in easyconfigs."),
                                              None, "store_true", False),
                "avail-easyconfig-licenses":(("Show all license constants that can be used in easyconfigs."),
                                              None, "store_true", False),
                "list-easyblocks":("Show list of available easyblocks",
                                   "choice", "store_or_None", "simple", ["simple", "detailed"]),
                "list-toolchains":("Show list of known toolchains",
                                   None, "store_true", False),
                "search":("Search for easyconfig files in the robot directory",
                          None, "store", None, {'metavar':"STR"}),
                "dep-graph":("Create dependency graph",
                             None, "store", None, {'metavar':"depgraph.<ext>"},),
                }

        self.log.debug("informative_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def regtest_options(self):
        # regression test options
        descr = ("Regression test options",
                 "Run and control an EasyBuild regression test.")

        opts = {
                "regtest":("Enable regression test mode",
                           None, "store_true", False),
                "regtest-online":("Enable online regression test mode",
                                  None, "store_true", False,),
                "sequential":("Specify this option if you want to prevent parallel build",
                              None, "store_true", False,),
                "regtest-output-dir":("Set output directory for test-run",
                                      None, "store", None, {'metavar':"DIR"},),
                "aggregate-regtest":("Collect all the xmls inside the given directory and generate a single file",
                                     None, "store", None, {'metavar':"DIR"},),
                }

        self.log.debug("regtest_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def easyconfig_options(self):
        # easyconfig options (to be passed to easyconfig instance)
        descr = ("Options for Easyconfigs",
                 "Options to be passed to all Easyconfig.")

        opts = None
        self.log.debug("easyconfig_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr, prefix='easyconfig')

    def easyblock_options(self):
        # easyblock options (to be passed to easyblock instance)
        descr = ("Options for Easyblocks",
                 "Options to be passed to all Easyblocks.")

        opts = None
        self.log.debug("easyblock_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr, prefix='easyblock')

    def unittest_options(self):
        # unittest options
        descr = ("Unittest options",
                 "Options dedicated to unittesting (experts only).")

        opts = {
                "file":("Log to this file in unittest mode", None, "store", None),
                }

        self.log.debug("unittest_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr, prefix='unittest')

    def validate(self):
        """Additional validation of options"""
        stop_msg = []

        if self.options.toolchain and not len(self.options.toolchain) == 2:
            stop_msg.append('--toolchain requires NAME,VERSION (given %s)' %
                            (','.join(self.options.toolchain)))
        if self.options.try_toolchain and not len(self.options.try_toolchain) == 2:
            stop_msg.append('--try-toolchain requires NAME,VERSION (given %s)' %
                            (','.join(self.options.try_toolchain)))

        if len(stop_msg) > 0:
            indent = " "*2
            stop_msg = ['%s%s' % (indent, x) for x in stop_msg]
            stop_msg.insert(0, 'ERROR: Found %s problems validating the options:' % len(stop_msg))
            print "\n".join(stop_msg)
            sys.exit(1)

    def postprocess(self):
        """Do some postprocessing, in particular print stuff"""
        if self.options.unittest_file:
            fancylogger.logToFile(self.options.unittest_file)

        if any([self.options.avail_easyconfig_params, self.options.avail_easyconfig_templates,
                self.options.list_easyblocks, self.options.list_toolchains,
                self.options.avail_easyconfig_constants, self.options.avail_easyconfig_licenses,
                self.options.avail_repositories, self.options.show_default_moduleclasses,
                ]):
            build_easyconfig_constants_dict()  # runs the easyconfig constants sanity check
            self._postprocess_list_avail()

        self._postprocess_config()

    def _postprocess_config(self):
        """Postprocessing of configuration options"""
        if self.options.prefix is not None:
            changed_defaults = get_default_oldstyle_configfile_defaults(self.options.prefix)
            for dest in ['installpath', 'buildpath', 'sourcepath', 'repositorypath']:
                if not self.options._action_taken.get(dest, False):
                    new_def = changed_defaults[dest]
                    if dest == 'repositorypath':
                        setattr(self.options, dest, new_def[changed_defaults['repository']])
                    else:
                        setattr(self.options, dest, new_def)
                    # LEGACY this line is here for oldstyle reasons
                    self.log.deprecated('Fake action taken to distinguish from default', '2.0')
                    self.options._action_taken[dest] = True

        if self.options.pretend:
            self.options.installpath = get_pretend_installpath()

    def _postprocess_list_avail(self):
        """Create all the additional info that can be requested (exit at the end)"""
        msg = ''
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

        # dump default moduleclasses with description
        if self.options.show_default_moduleclasses:
            msg += self.show_default_moduleclasses()

        if self.options.unittest_file:
            self.log.info(msg)
        else:
            print msg
        sys.exit(0)

    def avail_easyconfig_params(self):
        """
        Print the available easyconfig parameters, for the given easyblock.
        """
        app = get_class(self.options.easyblock)
        extra = app.extra_options()
        mapping = convert_to_help(extra, has_default=False)
        if len(extra) > 0:
            ebb_msg = " (* indicates specific for the %s EasyBlock)" % app.__name__
            extra_names = [x[0] for x in extra]
        else:
            ebb_msg = ''
            extra_names = []
        txt = ["Available easyconfig parameters%s" % ebb_msg]
        for key, values in mapping.items():
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
            tc_elems = set([y for x in dir(tc) if x.endswith('_MODULE_NAME') for y in eval("tc.%s" % x)])

            txt.append("\t%s: %s" % (tcname, ', '.join(sorted(tc_elems))))

        return '\n'.join(txt)

    def avail_repositories(self):
        """Show list of known repository types."""
        repopath_defaults = get_default_oldstyle_configfile_defaults()['repositorypath']
        all_repos = avail_repositories(check_useable=False)
        usable_repos = avail_repositories(check_useable=True).keys()

        indent = ' ' * 2
        txt = ['All avaialble repository types']
        repos = sorted(all_repos.keys())
        for repo in repos:
            if repo in usable_repos:
                missing = ''
            else:
                missing = ' (*Not usable*, something is missing (eg a specific module))'
            if repo in repopath_defaults:
                default = ' (Default arguments: %s)' % (repopath_defaults[repo])
            else:
                default = ' (No default arguments)'

            txt.append("%s%s%s%s" % (indent, repo, default, missing))
            txt.append("%s%s" % (indent * 2, all_repos[repo].DESCRIPTION))

        return "\n".join(txt)

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

    eb_go = EasyBuildOptions(
                             usage=usage,
                             description=description,
                             prog='eb',
                             envvar_prefix='EASYBUILD',
                             go_args=args,
                             )
    return eb_go
