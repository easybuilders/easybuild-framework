# #
# Copyright 2009-2012 Ghent University
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
@author: Stijn De Weirdt (Ghent University)
Options for eb main
"""
import easybuild.tools.filetools as filetools
from easybuild.framework.easyblock import EasyBlock
from easybuild.tools.ordereddict import OrderedDict
from vsc.utils.generaloption import GeneralOption


class EasyBuildOptions(GeneralOption):
    def basic_options(self):
        """basic runtime options"""
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        strictness_options = [filetools.IGNORE, filetools.WARN, filetools.ERROR]

        # robot : "(default: easybuild-easyconfigs install path)"
        default_robot_path = '/fix/default/robot/path'  # TODO

        descr = ("Basic options", "Basic runtime options for EasyBuild.")

        opts = OrderedDict({
                            "only-blocks":("Only build blocks blk[,blk2]",
                                           None, "store_true", False, "b", {'metavar':"BLOCKS"}),
                            "force":(("Force to rebuild software even if it's already installed "
                                      "(i.e. can be found as module)"),
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
                                                 None, 'store', {'metavar':'VERSION'}),
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

        # TODO "[default: $EASYBUILDCONFIG or easybuild/easybuild_config.py]"
        default_config = ''

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


def parse_options():
    usage = "%prog [options] easyconfig [..]"
    description = ("Builds software based on easyconfig (or parse a directory)\n"
                   "Provide one or more easyconfigs or directories, use -h or --help more information.")

    eb_go = EasyBuildOptions(usage=usage,
                           description=description,
                           )

    return eb_go.options, eb_go.args
