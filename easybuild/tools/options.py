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
import easybuild.tools.filetools as filetools
import os
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig import get_paths_for
from easybuild.tools.config import get_default_configfile
from easybuild.tools.ordereddict import OrderedDict
from vsc.utils.generaloption import GeneralOption


class EasyBuildOptions(GeneralOption):
    def basic_options(self):
        """basic runtime options"""
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        strictness_options = [filetools.IGNORE, filetools.WARN, filetools.ERROR]

        try:
            default_robot_path = get_paths_for(self.log, "easyconfigs", robot_path=None)[0]
        except:
            self.log.warning("basic_options: unable to determine default easyconfig path")
            default_robot_path = False  # False as opposed to None, since None is used for indicating that --robot was not used

        descr = ("Basic options", "Basic runtime options for EasyBuild.")

        opts = OrderedDict({
                            "only-blocks":("Only build blocks blk[,blk2]",
                                           None, "store_true", False, "b", {'metavar':"BLOCKS"}),
                            "force":(("Force to rebuild software even if it's already installed "
                                      "(i.e. if it can be found as module)"),
                                     None, "store_true", False, "f"),
                            "job":("Submit the build as a job", None, "store_true", False),
                            "skip":("Skip existing software (useful for installing additional packages)",
                                    None, "store_true", False, "k"),
                            "robot":("Path to search for easyconfigs for missing dependencies." ,
                                     None, "store_or_None", default_robot_path, "r", {'metavar':"PATH"}),
                            "stop":("Stop the installation after certain step",
                                    "choice", "store_or_None", "unpack", "s", all_stops),
                            "strict":("Set strictness level",
                                      "choice", "store", filetools.ERROR, strictness_options),
                            "logtostdout":("Redirect main log to stdout", None, "store_true", False, "l"),
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
                                          None, 'store', None, {'metavar':'NAME,VERSION'}),
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

        default_config = get_default_configfile()

        opts = {
                "config":("path to EasyBuild config file ",
                          None, 'store', default_config, "C",),
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

    def informative_options(self):
        # informative options
        descr = ("Informative options",
                 "Obtain information about EasyBuild.")

        opts = {
                "avail-easyconfig-params":(("Show all easyconfig parameters (include "
                                            "easyblock-specific ones by using -e)"),
                                            None, "store_true", False, "a",),
                "list-easyblocks":("Show list of available easyblocks",
                                   "choice", "store_or_None", "simple", ["simple", "detailed"]),
                "list-toolchains":("Show list of known toolchains",
                                  None, "store_true", False),
                "search":("Search for module-files in the robot-directory",
                         None, "store", None, {'metavar':"STR"}),
                 "version":("Show version", None, "store_true", None, "v",),
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

        opts = {'x':('x', None, "store", None)}
        self.log.debug("easyconfig_options: descr %s opts %s" % (descr, opts))
        # self.add_group_parser(opts, descr, prefix='easyconfig')

    def easyblock_options(self):
        # easyblock options (to be passed to easyblock instance)
        descr = ("Options for Easyblocks",
                 "Options to be passed to all Easyblocks.")

        opts = {'x':('x', None, "store", None)}
        self.log.debug("easyblock_options: descr %s opts %s" % (descr, opts))
        # self.add_group_parser(opts, descr, prefix='easyblock')



def parse_options(args=None):
    usage = "%prog [options] easyconfig [...]"
    description = ("Builds software based on easyconfig (or parse a directory).\n"
                   "Provide one or more easyconfigs or directories, use -h or --help more information.")

    eb_go = EasyBuildOptions(
                             usage=usage,
                             description=description,
                             prog='eb',
                             envvar_prefix='EASYBUILD',
                             go_args=args,
                             )
    return eb_go.options, eb_go.args, eb_go.parser
