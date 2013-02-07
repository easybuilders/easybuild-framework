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
from optparse import OptionParser, OptionGroup

# see http://stackoverflow.com/questions/1229146/parsing-empty-options-in-python
def optional_arg(default_value):
    """Callback for supporting options with optional values."""

    def func(option, opt_str, value, parser):
        if parser.rargs and not parser.rargs[0].startswith('-'):
            val = parser.rargs[0]
            parser.rargs.pop(0)
        else:
            val = default_value

        setattr(parser.values, option.dest, val)

    return func

def add_cmdline_options(parser):
    """
    Add build options to options parser
    """

    all_stops = [x[0] for x in EasyBlock.get_steps()]

    # runtime options
    basic_options = OptionGroup(parser, "Basic options", "Basic runtime options for EasyBuild.")

    basic_options.add_option("-b", "--only-blocks", metavar="BLOCKS", help="Only build blocks blk[,blk2]")
    basic_options.add_option("-d", "--debug" , action="store_true", help="log debug messages")
    basic_options.add_option("-f", "--force", action="store_true", dest="force",
                        help="force to rebuild software even if it's already installed (i.e. can be found as module)")
    basic_options.add_option("--job", action="store_true", help="will submit the build as a job")
    basic_options.add_option("-k", "--skip", action="store_true",
                        help="skip existing software (useful for installing additional packages)")
    basic_options.add_option("-l", action="store_true", dest="stdoutLog", help="log to stdout")
    basic_options.add_option("-r", "--robot", metavar="PATH", action='callback', callback=optional_arg(True), dest='robot',
                        help="path to search for easyconfigs for missing dependencies " \
                             "(default: easybuild-easyconfigs install path)")
    basic_options.add_option("-s", "--stop", type="choice", choices=all_stops,
                        help="stop the installation after certain step (valid: %s)" % ', '.join(all_stops))
    strictness_options = [filetools.IGNORE, filetools.WARN, filetools.ERROR]
    basic_options.add_option("--strict", type="choice", choices=strictness_options, help="set strictness " + \
                               "level (possible levels: %s)" % ', '.join(strictness_options))

    parser.add_option_group(basic_options)

    # software build options
    software_build_options = OptionGroup(parser, "Software build options",
                                     "Specify software build options; the regular versions of these " \
                                     "options will only search for matching easyconfigs, while the " \
                                     "--try-X versions will cause EasyBuild to try and generate a " \
                                     "matching easyconfig based on available ones if no matching " \
                                     "easyconfig is found (NOTE: best effort, might produce wrong builds!)")

    list_of_software_build_options = [
                                      ('software-name', 'NAME', 'store',
                                       "build software with name"),
                                      ('software-version', 'VERSION', 'store',
                                       "build software with version"),
                                      ('toolchain', 'NAME,VERSION', 'store',
                                       "build with toolchain (name and version)"),
                                      ('toolchain-name', 'NAME', 'store',
                                       "build with toolchain name"),
                                      ('toolchain-version', 'VERSION', 'store',
                                       "build with toolchain version"),
                                      ('amend', 'VAR=VALUE[,VALUE]', 'append',
                                       "specify additional build parameters (can be used multiple times); " \
                                       "for example: versionprefix=foo or patches=one.patch,two.patch)")
                                      ]

    for (opt_name, opt_metavar, opt_action, opt_help) in list_of_software_build_options:
        software_build_options.add_option("--%s" % opt_name,
                                          metavar=opt_metavar,
                                          action=opt_action,
                                          help=opt_help)

    for (opt_name, opt_metavar, opt_action, opt_help) in list_of_software_build_options:
        software_build_options.add_option("--try-%s" % opt_name,
                                          metavar=opt_metavar,
                                          action=opt_action,
                                          help="try to %s (USE WITH CARE!)" % opt_help)

    parser.add_option_group(software_build_options)

    # override options
    override_options = OptionGroup(parser, "Override options", "Override default EasyBuild behavior.")

    override_options.add_option("-C", "--config", help="path to EasyBuild config file " \
                                                         "[default: $EASYBUILDCONFIG or easybuild/easybuild_config.py]")
    override_options.add_option("-e", "--easyblock", metavar="CLASS",
                        help="easyblock to use for processing the spec file or dumping the options")
    override_options.add_option("-p", "--pretend", action="store_true", help="does the build/installation in " \
                                "a test directory located in $HOME/easybuildinstall [default: $EASYBUILDINSTALLPATH " \
                                "or install_path in EasyBuild config file]")
    override_options.add_option("-t", "--skip-test-cases", action="store_true", help="skip running test cases")

    parser.add_option_group(override_options)

    # informative options
    informative_options = OptionGroup(parser, "Informative options",
                                      "Obtain information about EasyBuild.")

    informative_options.add_option("-a", "--avail-easyconfig-params", action="store_true",
                                   help="show all easyconfig parameters (include easyblock-specific ones by using -e)")
    # TODO: figure out a way to set a default choice for --list-easyblocks
    # adding default="simple" doesn't work, it always enables --list-easyblocks
    # see https://github.com/hpcugent/VSC-tools/issues/8
    informative_options.add_option("--list-easyblocks", type="choice", choices=["simple", "detailed"], default=None,
                                   help="show list of available easyblocks ('simple' or 'detailed')")
    informative_options.add_option("--list-toolchains", action="store_true", help="show list of known toolchains")
    informative_options.add_option("--search", metavar="STR", help="search for module-files in the robot-directory")
    informative_options.add_option("-v", "--version", action="store_true", help="show version")
    informative_options.add_option("--dep-graph", metavar="depgraph.<ext>", help="create dependency graph")

    parser.add_option_group(informative_options)

    # regression test options
    regtest_options = OptionGroup(parser, "Regression test options",
                                  "Run and control an EasyBuild regression test.")\

    regtest_options.add_option("--regtest", action="store_true", help="enable regression test mode")
    regtest_options.add_option("--regtest-online", action="store_true",
                               help="enable online regression test mode")
    regtest_options.add_option("--sequential", action="store_true", default=False,
                               help="specify this option if you want to prevent parallel build")
    regtest_options.add_option("--regtest-output-dir", metavar="DIR", help="set output directory for test-run")
    regtest_options.add_option("--aggregate-regtest", metavar="DIR",
                               help="collect all the xmls inside the given directory and generate a single file")

    parser.add_option_group(regtest_options)

def parse_options():

    # options parser
    parser = OptionParser()

    parser.usage = "%prog [options] easyconfig [..]"
    parser.description = "Builds software based on easyconfig (or parse a directory)\n" \
                         "Provide one or more easyconfigs or directories, use -h or --help more information."

    add_cmdline_options(parser)

    (options, paths) = parser.parse_args()

    return options, paths
