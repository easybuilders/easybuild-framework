#!/usr/bin/env python
##
# Copyright 2009-2012 Ghent University
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
# Copyright 2012 Toon Willems
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
Main entry point for EasyBuild: build software from .eb input file
"""

import copy
import glob
import platform
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
import xml.dom.minidom as xml
from datetime import datetime
from optparse import OptionParser, OptionGroup

# optional Python packages, these might be missing
# failing imports are just ignored
# a NameError should be catched where these are used

# PyGraph (used for generating dependency graphs)
graph_errors = []
try:
    from pygraph.classes.digraph import digraph
except ImportError, err:
    graph_errors.append("Failed to import pygraph-core: try easy_install python-graph-core")

try:
    import  pygraph.readwrite.dot as dot
except ImportError, err:
    graph_errors.append("Failed to import pygraph-dot: try easy_install python-graph-dot")

# graphviz (used for creating dependency graph images)
try:
    sys.path.append('..')
    sys.path.append('/usr/lib/graphviz/python/')
    sys.path.append('/usr/lib64/graphviz/python/')
    import gv
except ImportError, err:
    graph_errors.append("Failed to import graphviz: try yum install graphviz-python, or apt-get install python-pygraphviz")

import easybuild.framework.easyconfig as easyconfig
import easybuild.tools.config as config
import easybuild.tools.filetools as filetools
import easybuild.tools.parallelbuild as parbuild
from easybuild.framework.easyblock import EasyBlock, get_class
from easybuild.framework.easyconfig import EasyConfig, get_paths_for
from easybuild.tools import systemtools
from easybuild.tools.build_log import EasyBuildError, init_logger
from easybuild.tools.build_log import remove_log_handler, print_msg
from easybuild.tools.config import get_repository, module_classes
from easybuild.tools.filetools import modify_env, run_cmd
from easybuild.tools.modules import Modules, search_module
from easybuild.tools.modules import curr_module_paths, mk_module_path
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.version import VERBOSE_VERSION as FRAMEWORK_VERSION
EASYBLOCKS_VERSION = 'UNKNOWN'
try:
    from easybuild.easyblocks import VERBOSE_VERSION as EASYBLOCKS_VERSION
except:
    pass


# applications use their own logger, we need to tell them to debug or not
# so this global variable is used.
LOGDEBUG = False

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
    
    override_options.add_option("-C", "--config", help = "path to EasyBuild config file " \
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

    # mkstemp returns (fd,filename), fd is from os.open, not regular open!
    fd, logfile = tempfile.mkstemp(suffix='.log', prefix='easybuild-')
    os.close(fd)

    if options.stdoutLog:
        os.remove(logfile)
        logfile = None

    global LOGDEBUG
    LOGDEBUG = options.debug

    # initialize logger
    logfile, log, hn = init_logger(filename=logfile, debug=options.debug, typ="main")

    return options, paths, log, logfile, hn, parser

def main(options, orig_paths, log, logfile, hn, parser):
    """
    Main function:
    @arg options: a tuple: (options, paths, logger, logfile, hn) as defined in parse_options
    This function will:
    - read easyconfig
    - build software
    """

    # set strictness of filetools module
    if options.strict:
        filetools.strictness = options.strict

    # disallow running EasyBuild as root
    if os.getuid() == 0:
        sys.stderr.write("ERROR: You seem to be running EasyBuild with root privileges.\n" \
                        "That's not wise, so let's end this here.\n" \
                        "Exiting.\n")
        sys.exit(1)

    # show version
    if options.version:
        top_version = max(FRAMEWORK_VERSION, EASYBLOCKS_VERSION)
        print_msg("This is EasyBuild %s (framework: %s, easyblocks: %s)" % (top_version,
                                                                            FRAMEWORK_VERSION,
                                                                            EASYBLOCKS_VERSION), log)

    # determine easybuild-easyconfigs package install path
    easyconfigs_paths = get_paths_for(log, "easyconfigs", robot_path=options.robot)
    easyconfigs_pkg_full_path = None

    if easyconfigs_paths:
        easyconfigs_pkg_full_path = easyconfigs_paths[0]
    else:
        log.info("Failed to determine install path for easybuild-easyconfigs package.")

    if options.robot and type(options.robot) == bool:
        if not easyconfigs_pkg_full_path is None:
            options.robot = easyconfigs_pkg_full_path
            log.info("Using default robot path (easyconfigs install dir): %s" % options.robot)
        else:
            log.error("No robot path specified, and unable to determine easybuild-easyconfigs install path.")

    configOptions = {}
    if options.pretend:
        configOptions['install_path'] = os.path.join(os.environ['HOME'], 'easybuildinstall')

    if options.only_blocks:
        blocks = options.only_blocks.split(',')
    else:
        blocks = None

    # initialize configuration
    # - check command line option -C/--config
    # - then, check environment variable EASYBUILDCONFIG
    # - next, check for an EasyBuild config in $HOME/.easybuild/config.py
    # - last, use default config file easybuild_config.py in main.py directory
    config_file = options.config
    if not config_file:
        log.debug("No config file specified on command line, trying other options.")

        config_env_var = config.environmentVariables['config_file']
        home_config_file = os.path.join(os.getenv('HOME'), ".easybuild", "config.py")
        if os.getenv(config_env_var):
            log.debug("Environment variable %s, so using that as config file." % config_env_var)
            config_file = os.getenv(config_env_var)
        elif os.path.exists(home_config_file):
            config_file = home_config_file
            log.debug("Found EasyBuild configuration file at %s." % config_file)
        else:
            appPath = os.path.dirname(os.path.realpath(sys.argv[0]))
            config_file = os.path.join(appPath, "easybuild_config.py")
            log.debug("Falling back to default config: %s" % config_file)

    config.init(config_file, **configOptions)

    # dump possible options
    if options.avail_easyconfig_params:
        print_avail_params(options.easyblock, log)

    # dump available easyblocks
    if options.list_easyblocks:
        list_easyblocks(detailed=options.list_easyblocks=="detailed")

    # dump known toolchains
    if options.list_toolchains:
        list_toolchains()

    # search for modules
    if options.search:
        if not options.robot:
            error("Please provide a search-path to --robot when using --search")
        search_module(options.robot, options.search)
    
    # process software build specifications (if any), i.e.
    # software name/version, toolchain name/version, extra patches, ...
    (try_to_generate, software_build_specs) = process_software_build_specs(options)

    paths = []
    if len(orig_paths) == 0:
        if software_build_specs.has_key('name'):
            paths = [obtain_path(software_build_specs, options.robot, log, try_to_generate)]
        elif not any([options.aggregate_regtest, options.avail_easyconfig_params, options.list_easyblocks,
                      options.list_toolchains, options.search, options.regtest, options.version]):
            error("Please provide one or multiple easyconfig files, or use software build " \
                  "options to make EasyBuild search for easyconfigs", optparser=parser)

    else:
        # look for easyconfigs with relative paths in easybuild-easyconfigs package,
        # unless they we found at the given relative paths

        if easyconfigs_pkg_full_path:
            # create a mapping from filename to path in easybuild-easyconfigs package install path
            easyconfigs_map = {}
            for (subpath, _, filenames) in os.walk(easyconfigs_pkg_full_path):
                for filename in filenames:
                    easyconfigs_map.update({filename: os.path.join(subpath, filename)})

            # try and find non-existing non-absolute eaysconfig paths in easybuild-easyconfigs package install path
            for i in range(len(orig_paths)):
                if not os.path.isabs(orig_paths[i]) and not os.path.exists(orig_paths[i]):
                    if orig_paths[i] in easyconfigs_map:
                        log.info("Found %s in %s: %s" % (orig_paths[i], easyconfigs_pkg_full_path, easyconfigs_map[orig_paths[i]]))
                        orig_paths[i] = easyconfigs_map[orig_paths[i]]

        # indicate that specified paths do not contain generated easyconfig files
        paths = [(path, False) for path in orig_paths]

    log.debug("Paths: %s" % paths)

    # run regtest
    if options.regtest or options.aggregate_regtest:
        log.info("Running regression test")
        if paths:
            regtest_ok = regtest(options, log, [path[0] for path in paths])
        else:  # fallback: easybuild-easyconfigs install path
            regtest_ok = regtest(options, log, [easyconfigs_pkg_full_path])

        if not regtest_ok:
            log.info("Regression test failed (partially)!")
            sys.exit(31)  # exit -> 3x1t -> 31

    if any([options.avail_easyconfig_params, options.list_easyblocks, options.list_toolchains, options.search,
             options.version, options.regtest]):
        if logfile:
            os.remove(logfile)
        sys.exit(0)

    # building a dependency graph implies force, so that all dependencies are retained
    # and also skips validation of easyconfigs (e.g. checking os dependencies)
    validate_easyconfigs = True
    retain_all_deps = False
    if options.dep_graph:
        log.info("Enabling force to generate dependency graph.")
        options.force = True
        validate_easyconfigs = False
        retain_all_deps = True

    # read easyconfig files
    easyconfigs = []
    for (path, generated) in paths:
        path = os.path.abspath(path)
        if not (os.path.exists(path)):
            error("Can't find path %s" % path)

        try:
            files = find_easyconfigs(path, log)
            for f in files:
                if not generated and try_to_generate and software_build_specs:
                    ec_file = easyconfig.tweak(f, None, software_build_specs, log)
                else:
                    ec_file = f
                easyconfigs.extend(process_easyconfig(ec_file, log, blocks, validate=validate_easyconfigs))
        except IOError, err:
            log.error("Processing easyconfigs in path %s failed: %s" % (path, err))

    # before building starts, take snapshot of environment (watch out -t option!)
    origEnviron = copy.deepcopy(os.environ)
    os.chdir(os.environ['PWD'])

    # skip modules that are already installed unless forced
    if not options.force:
        m = Modules()
        easyconfigs, check_easyconfigs = [], easyconfigs
        for ec in check_easyconfigs:
            module = ec['module']
            mod = "%s (version %s)" % (module[0], module[1])
            modspath = mk_module_path(curr_module_paths() + [os.path.join(config.install_path("mod"), 'all')])
            if m.exists(module[0], module[1], modspath):
                msg = "%s is already installed (module found in %s), skipping " % (mod, modspath)
                print_msg(msg, log)
                log.info(msg)
            else:
                log.debug("%s is not installed yet, so retaining it" % mod)
                easyconfigs.append(ec)

    # determine an order that will allow all specs in the set to build
    if len(easyconfigs) > 0:
        print_msg("resolving dependencies ...", log)
        # force all dependencies to be retained and validation to be skipped for building dep graph
        force = retain_all_deps and not validate_easyconfigs
        orderedSpecs = resolve_dependencies(easyconfigs, options.robot, log, force=force)
    else:
        print_msg("No easyconfigs left to be built.", log)
        orderedSpecs = []

    # create dependency graph and exit
    if options.dep_graph:
        log.info("Creating dependency graph %s" % options.dep_graph)
        try:
            dep_graph(options.dep_graph, orderedSpecs, log)
        except NameError, err:
            log.error("An optional Python packages required to " \
                      "generate dependency graphs is missing: %s" % "\n".join(graph_errors))
        sys.exit(0)

    # submit build as job(s) and exit
    if options.job:
        curdir = os.getcwd()

        # Reverse option parser -> string

        # the options to ignore
        ignore = map(parser.get_option, ['--robot', '--help', '--job'])

        def flatten(lst):
            """Flatten a list of lists."""
            res = []
            for x in lst:
                res.extend(x)
            return res

        # loop over all the different options.
        result_opts = []
        all_options = parser.option_list + flatten([g.option_list for g in parser.option_groups])
        relevant_opts = [o for o in all_options if o not in ignore]
        for opt in relevant_opts:
            value = getattr(options, opt.dest)
            # explicit check for None (some option are store_false)
            if value != None:
                # get_opt_string is not documented (but is a public method)
                name = opt.get_opt_string()
                if opt.action == 'store':
                    result_opts.append("%s %s" % (name, value))
                else:
                    result_opts.append(name)

        opts = ' '.join(result_opts)

        command = "unset TMPDIR && cd %s && eb %%(spec)s %s" % (curdir, opts)
        log.debug("Command template for jobs: %s" % command)
        jobs = parbuild.build_easyconfigs_in_parallel(command, orderedSpecs, "easybuild-build", log,
                                                      robot_path=options.robot)
        print "List of submitted jobs:"
        for job in jobs:
            print "%s: %s" % (job.name, job.jobid)
        print "(%d jobs submitted)" % len(jobs)

        log.info("Submitted parallel build jobs, exiting now")
        sys.exit(0)

    # build software, will exit when errors occurs (except when regtesting)
    correct_built_cnt = 0
    all_built_cnt = 0
    for spec in orderedSpecs:
        (success, _) = build_and_install_software(spec, options, log, origEnviron)
        if success:
            correct_built_cnt += 1
        all_built_cnt += 1

    print_msg("Build succeeded for %s out of %s" % (correct_built_cnt, all_built_cnt), log)

    get_repository().cleanup()
    # cleanup tmp log file (all is well, all modules have their own log file)
    try:
        remove_log_handler(hn)
        hn.close()
        if logfile:
            os.remove(logfile)

        for ec in easyconfigs:
            if 'originalSpec' in ec:
                os.remove(ec['spec'])

    except IOError, err:
        error("Something went wrong closing and removing the log %s : %s" % (logfile, err))

def error(message, exitCode=1, optparser=None):
    """
    Print error message and exit EasyBuild
    """
    print_msg("ERROR: %s\n" % message)
    if optparser:
        optparser.print_help()
        print_msg("ERROR: %s\n" % message)
    sys.exit(exitCode)

def warning(message):
    """
    Print warning message.
    """
    print_msg("WARNING: %s\n" % message)

def find_easyconfigs(path, log):
    """
    Find .eb easyconfig files in path
    """
    if os.path.isfile(path):
        return [path]

    # walk through the start directory, retain all files that end in .eb
    files = []
    path = os.path.abspath(path)
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            if not f.endswith('.eb') or f == 'TEMPLATE.eb':
                continue

            spec = os.path.join(dirpath, f)
            log.debug("Found easyconfig %s" % spec)
            files.append(spec)

    return files

def process_easyconfig(path, log, onlyBlocks=None, regtest_online=False, validate=True):
    """
    Process easyconfig, returning some information for each block
    """
    blocks = retrieve_blocks_in_spec(path, log, onlyBlocks)

    easyconfigs = []
    for spec in blocks:
        # process for dependencies and real installversionname
        # - use mod? __init__ and importCfg are ignored.
        log.debug("Processing easyconfig %s" % spec)

        # create easyconfig
        try:
            all_stops = [x[0] for x in EasyBlock.get_steps()]
            ec = EasyConfig(spec, validate=validate, valid_module_classes=module_classes(), valid_stops=all_stops)
        except EasyBuildError, err:
            msg = "Failed to process easyconfig %s:\n%s" % (spec, err.msg)
            log.exception(msg)

        name = ec['name']

        # this app will appear as following module in the list
        easyconfig = {
                      'spec': spec,
                      'module': (ec.name, ec.get_installversion()),
                      'dependencies': []
                     }
        if len(blocks) > 1:
            easyconfig['originalSpec'] = path

        for d in ec.dependencies():
            dep = (d['name'], d['tc'])
            log.debug("Adding dependency %s for app %s." % (dep, name))
            easyconfig['dependencies'].append(dep)

        if ec.toolchain.name != 'dummy':
            dep = (ec.toolchain.name, ec.toolchain.version)
            log.debug("Adding toolchain %s as dependency for app %s." % (dep, name))
            easyconfig['dependencies'].append(dep)

        del ec

        # this is used by the parallel builder
        easyconfig['unresolvedDependencies'] = copy.copy(easyconfig['dependencies'])

        easyconfigs.append(easyconfig)

    return easyconfigs

def resolve_dependencies(unprocessed, robot, log, force=False):
    """
    Work through the list of easyconfigs to determine an optimal order
    enabling force results in retaining all dependencies and skipping validation of easyconfigs
    """

    if force:
        # assume that no modules are available when forced
        availableModules = []
        log.info("Forcing all dependencies to be retained.")
    else:
        # Get a list of all available modules (format: [(name, installversion), ...])
        availableModules = Modules().available()

        if len(availableModules) == 0:
            log.warning("No installed modules. Your MODULEPATH is probably incomplete.")

    orderedSpecs = []
    # All available modules can be used for resolving dependencies except
    # those that will be installed
    beingInstalled = [p['module'] for p in unprocessed]
    processed = [m for m in availableModules if not m in beingInstalled]

    # as long as there is progress in processing the modules, keep on trying
    loopcnt = 0
    maxloopcnt = 10000
    robotAddedDependency = True
    while robotAddedDependency:

        robotAddedDependency = False

        # make sure this stops, we really don't want to get stuck in an infinite loop
        loopcnt += 1
        if loopcnt > maxloopcnt:
            msg = "Maximum loop cnt %s reached, so quitting." % maxloopcnt
            log.error(msg)

        # first try resolving dependencies without using external dependencies
        lastProcessedCount = -1
        while len(processed) > lastProcessedCount:
            lastProcessedCount = len(processed)
            orderedSpecs.extend(find_resolved_modules(unprocessed, processed, log))

        # robot: look for an existing dependency, add one
        if robot and len(unprocessed) > 0:

            beingInstalled = [p['module'] for p in unprocessed]

            for module in unprocessed:
                # do not choose a module that is being installed in the current run
                # if they depend, you probably want to rebuild them using the new dependency
                candidates = [d for d in module['dependencies'] if not d in beingInstalled]
                if len(candidates) > 0:
                    # find easyconfig, might not find any
                    path = robot_find_easyconfig(log, robot, candidates[0])

                else:
                    path = None
                    log.debug("No more candidate dependencies to resolve for module %s" % str(module['module']))

                if path:
                    log.info("Robot: resolving dependency %s with %s" % (candidates[0], path))

                    processedSpecs = process_easyconfig(path, log, validate=(not force))

                    # ensure the pathname is equal to the module
                    mods = [spec['module'] for spec in processedSpecs]
                    if not candidates[0] in mods:
                        log.error("easyconfig file %s does not contain module %s" % (path, candidates[0]))

                    unprocessed.extend(processedSpecs)
                    robotAddedDependency = True
                    break

    # there are dependencies that cannot be resolved
    if len(unprocessed) > 0:
        log.debug("List of unresolved dependencies: %s" % unprocessed)
        missingDependencies = {}
        for module in unprocessed:
            for dep in module['dependencies']:
                missingDependencies[dep] = True

        msg = "Dependencies not met. Cannot resolve %s" % missingDependencies.keys()
        log.error(msg)

    log.info("Dependency resolution complete, building as follows:\n%s" % orderedSpecs)
    return orderedSpecs

def find_resolved_modules(unprocessed, processed, log):
    """
    Find modules in unprocessed which can be fully resolved using easyconfigs in processed
    """
    orderedSpecs = []

    for module in unprocessed:
        module['dependencies'] = [d for d in module['dependencies'] if not d in processed]

        if len(module['dependencies']) == 0:
            log.debug("Adding easyconfig %s to final list" % module['spec'])
            orderedSpecs.append(module)
            processed.append(module['module'])

    unprocessed[:] = [m for m in unprocessed if len(m['dependencies']) > 0]

    return orderedSpecs

def process_software_build_specs(options):
    """
    Create a dictionary with specified software build options.
    The options arguments should be a parsed option list (as delivered by OptionParser.parse_args)
    """

    try_to_generate = False
    buildopts = {}

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
            buildopts.update({key: opt})
            # remove this key from the dict of try-options (overruled)
            try_opts_map.pop(key)

    for (key, opt) in try_opts_map.items():
        if opt:
            buildopts.update({key: opt})
            # only when a try option is set do we enable generating easyconfigs
            try_to_generate = True

    # process --toolchain --try-toolchain
    if options.toolchain or options.try_toolchain:

        if options.toolchain:
                tc = options.toolchain.split(',')
                if options.try_toolchain:
                    warning("Ignoring --try-toolchain, only using --toolchain specification.")
        elif options.try_toolchain:
                tc = options.try_toolchain.split(',')
                try_to_generate = True
        else:
            # shouldn't happen
            error("Huh, neither --toolchain or --try-toolchain used?")

        if not len(tc) == 2:
            error("Please specify to toolchain to use as 'name,version' (e.g., 'goalf,1.1.0').")

        [toolchain_name, toolchain_version] = tc
        buildopts.update({'toolchain_name': toolchain_name})
        buildopts.update({'toolchain_version': toolchain_version})

    # process --amend and --try-amend
    if options.amend or options.try_amend:

        amends = []
        if options.amend:
            amends += options.amend
            if options.try_amend:
                warning("Ignoring options passed via --try-amend, only using those passed via --amend.")
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
            buildopts.update({param: value})

    return (try_to_generate, buildopts)

def obtain_path(specs, robot, log, try_to_generate=False):
    """Obtain a path for an easyconfig that matches the given specifications."""

    # if no easyconfig files/paths were provided, but we did get a software name,
    # we can try and find a suitable easyconfig ourselves, or generate one if we can
    (generated, fn) = easyconfig.obtain_ec_for(specs, robot, None, log)
    if not generated:
        return (fn, generated)
    else:
        # if an easyconfig was generated, make sure we're allowed to use it
        if try_to_generate:
            print_msg("Generated an easyconfig file %s, going to use it now..." % fn)
            return (fn, generated)
        else:
            try:
                os.remove(fn)
            except OSError, err:
                warning("Failed to remove generated easyconfig file %s." % fn)
            error("Unable to find an easyconfig for the given specifications: %s; " \
                  "to make EasyBuild try to generate a matching easyconfig, " \
                  "use the --try-X options " % specs)


def robot_find_easyconfig(log, path, module):
    """
    Find an easyconfig for module in path
    """
    name, version = module
    # candidate easyconfig paths
    easyconfigsPaths = easyconfig.create_paths(path, name, version)
    for easyconfigPath in easyconfigsPaths:
        log.debug("Checking easyconfig path %s" % easyconfigPath)
        if os.path.isfile(easyconfigPath):
            log.debug("Found easyconfig file for %s at %s" % (module, easyconfigPath))
            return os.path.abspath(easyconfigPath)

    return None

def retrieve_blocks_in_spec(spec, log, onlyBlocks):
    """
    Easyconfigs can contain blocks (headed by a [Title]-line)
    which contain commands specific to that block. Commands in the beginning of the file
    above any block headers are common and shared between each block.
    """
    regBlock = re.compile(r"^\s*\[([\w.-]+)\]\s*$", re.M)
    regDepBlock = re.compile(r"^\s*block\s*=(\s*.*?)\s*$", re.M)

    cfgName = os.path.basename(spec)
    pieces = regBlock.split(open(spec).read())

    # the first block contains common statements
    common = pieces.pop(0)
    if pieces:
        # make a map of blocks
        blocks = []
        while pieces:
            blockName = pieces.pop(0)
            blockContents = pieces.pop(0)

            if blockName in [b['name'] for b in blocks]:
                msg = "Found block %s twice in %s." % (blockName, spec)
                log.error(msg)

            block = {'name': blockName, 'contents': blockContents}

            # dependency block
            depBlock = regDepBlock.search(blockContents)
            if depBlock:
                dependencies = eval(depBlock.group(1))
                if type(dependencies) == list:
                    block['dependencies'] = dependencies
                else:
                    block['dependencies'] = [dependencies]

            blocks.append(block)

        # make a new easyconfig for each block
        # they will be processed in the same order as they are all described in the original file
        specs = []
        for block in blocks:
            name = block['name']
            if onlyBlocks and not (name in onlyBlocks):
                print_msg("Skipping block %s-%s" % (cfgName, name))
                continue

            (fd, blockPath) = tempfile.mkstemp(prefix='easybuild-', suffix='%s-%s' % (cfgName, name))
            os.close(fd)
            try:
                f = open(blockPath, 'w')
                f.write(common)

                if 'dependencies' in block:
                    for dep in block['dependencies']:
                        if not dep in [b['name'] for b in blocks]:
                            msg = "Block %s depends on %s, but block was not found." % (name, dep)
                            log.error(msg)

                        dep = [b for b in blocks if b['name'] == dep][0]
                        f.write("\n# Dependency block %s" % (dep['name']))
                        f.write(dep['contents'])

                f.write("\n# Main block %s" % name)
                f.write(block['contents'])
                f.close()

            except Exception:
                msg = "Failed to write block %s to easyconfig %s" % (name, spec)
                log.exception(msg)

            specs.append(blockPath)

        log.debug("Found %s block(s) in %s" % (len(specs), spec))
        return specs
    else:
        # no blocks, one file
        return [spec]

def get_build_stats(app, starttime):
    """
    Return build statistics for this build
    """

    buildtime = round(time.time() - starttime, 2)
    buildstats = OrderedDict([
                              ('easybuild-framework_version', str(FRAMEWORK_VERSION)),
                              ('easybuild-easyblocks_version', str(EASYBLOCKS_VERSION)),
                              ('host', os.uname()[1]),
                              ('platform' , platform.platform()),
                              ('cpu_model', systemtools.get_cpu_model()),
                              ('core_count', systemtools.get_core_count()),
                              ('timestamp', int(time.time())),
                              ('build_time', buildtime),
                              ('install_size', app.det_installsize()),
                             ])

    return buildstats

def build_and_install_software(module, options, log, origEnviron, exitOnFailure=True):
    """
    Build the software
    """
    spec = module['spec']

    print_msg("processing EasyBuild easyconfig %s" % spec, log)

    # restore original environment
    log.info("Resetting environment")
    filetools.errorsFoundInLog = 0
    modify_env(os.environ, origEnviron)

    cwd = os.getcwd()

    # load easyblock
    easyblock = options.easyblock
    if not easyblock:
        # try to look in .eb file
        reg = re.compile(r"^\s*easyblock\s*=(.*)$")
        for line in open(spec).readlines():
            match = reg.search(line)
            if match:
                easyblock = eval(match.group(1))
                break

    name = module['module'][0]
    try:
        app_class = get_class(easyblock, log, name=name)
        app = app_class(spec, debug=options.debug, robot_path=options.robot)
        log.info("Obtained application instance of for %s (easyblock: %s)" % (name, easyblock))
    except EasyBuildError, err:
        error("Failed to get application instance for %s (easyblock: %s): %s" % (name, easyblock, err.msg))

    # application settings
    if options.stop:
        log.debug("Stop set to %s" % options.stop)
        app.cfg['stop'] = options.stop

    if options.skip:
        log.debug("Skip set to %s" % options.skip)
        app.cfg['skip'] = options.skip

    # build easyconfig
    errormsg = '(no error)'
    # timing info
    starttime = time.time()
    try:
        result = app.run_all_steps(run_test_cases=(not options.skip_test_cases and app.cfg['tests']),
                                   regtest_online=options.regtest_online)
    except EasyBuildError, err:
        lastn = 300
        errormsg = "autoBuild Failed (last %d chars): %s" % (lastn, err.msg[-lastn:])
        log.exception(errormsg)
        result = False

    ended = "ended"

    # successful build
    if result:

        # collect build stats
        log.info("Collecting build stats...")

        currentbuildstats = app.cfg['buildstats']
        buildstats = get_build_stats(app, starttime)
        log.debug("Build stats: %s" % buildstats)

        if app.cfg['stop']:
            ended = "STOPPED"
            newLogDir = os.path.join(app.builddir, config.log_path())
        else:
            newLogDir = os.path.join(app.installdir, config.log_path())

            try:
                # upload spec to central repository
                repo = get_repository()
                if 'originalSpec' in module:
                    repo.add_easyconfig(module['originalSpec'], app.name, app.get_installversion() + ".block", buildstats, currentbuildstats)
                repo.add_easyconfig(spec, app.name, app.get_installversion(), buildstats, currentbuildstats)
                repo.commit("Built %s/%s" % (app.name, app.get_installversion()))
                del repo
            except EasyBuildError, err:
                log.warn("Unable to commit easyconfig to repository (%s)", err)

        exitCode = 0
        succ = "successfully"
        summary = "COMPLETED"

        # cleanup logs
        app.close_log()
        try:
            if not os.path.isdir(newLogDir):
                os.makedirs(newLogDir)
            applicationLog = os.path.join(newLogDir, os.path.basename(app.logfile))
            shutil.move(app.logfile, applicationLog)
        except IOError, err:
            error("Failed to move log file %s to new log file %s: %s" % (app.logfile, applicationLog, err))

        try:
            shutil.copy(spec, os.path.join(newLogDir, "%s-%s.eb" % (app.name, app.get_installversion())))
        except IOError, err:
            error("Failed to move easyconfig %s to log dir %s: %s" % (spec, newLogDir, err))

    # build failed
    else:
        exitCode = 1
        summary = "FAILED"

        buildDir = ''
        if app.builddir:
            buildDir = " (build directory: %s)" % (app.builddir)
        succ = "unsuccessfully%s:\n%s" % (buildDir, errormsg)

        # cleanup logs
        app.close_log()
        applicationLog = app.logfile

    print_msg("%s: Installation %s %s" % (summary, ended, succ), log)

    # check for errors
    if exitCode > 0 or filetools.errorsFoundInLog > 0:
        print_msg("\nWARNING: Build exited with exit code %d. %d possible error(s) were detected in the " \
                  "build logs, please verify the build.\n" % (exitCode, filetools.errorsFoundInLog),
                  log)

    if app.postmsg:
        print_msg("\nWARNING: %s\n" % app.postmsg, log)

    print_msg("Results of the build can be found in the log file %s" % applicationLog, log)

    del app
    os.chdir(cwd)

    if exitCode > 0:
        # don't exit on failure in test suite
        if exitOnFailure:
            sys.exit(exitCode)
        else:
            return (False, applicationLog)
    else:
        return (True, applicationLog)

def print_avail_params(easyblock, log):
    """
    Print the available easyconfig parameters, for the given easyblock.
    """
    app = get_class(easyblock, log)
    extra = app.extra_options()
    mapping = easyconfig.convert_to_help(EasyConfig.default_config + extra)

    for key, values in mapping.items():
        print "%s" % key.upper()
        print '-' * len(key)
        for name, value in values:
            tabs = "\t" * (3 - (len(name) + 1) / 8)
            print "%s:%s%s" % (name, tabs, value)

        print

def dep_graph(fn, specs, log):
    """
    Create a dependency graph for the given easyconfigs.
    """

    # check whether module names are unique
    # if so, we can omit versions in the graph 
    names = set()
    for spec in specs:
        names.add(spec['module'][0])
    omit_versions = len(names) == len(specs)

    def mk_node_name(mod):
        if omit_versions:
            return mod[0]
        else:
            return '-'.join(mod)

    # enhance list of specs
    for spec in specs:
        spec['module'] = mk_node_name(spec['module'])
        spec['unresolvedDependencies'] = [mk_node_name(s) for s in spec['unresolvedDependencies']] #[s[0] for s in spec['unresolvedDependencies']]

    # build directed graph
    dgr = digraph()
    dgr.add_nodes([spec['module'] for spec in specs])
    for spec in specs:
        for dep in spec['unresolvedDependencies']:
            dgr.add_edge((spec['module'], dep))

    # write to file
    dottxt = dot.write(dgr)
    if fn.endswith(".dot"):
        # create .dot file
        try:
            f = open(fn, "w")
            f.write(dottxt)
            f.close()
        except IOError, err:
            log.error("Failed to create file %s: %s" % (fn, err))
    else:
        # try and render graph in specified file format
        gvv = gv.readstring(dottxt)
        gv.layout(gvv, 'dot')
        gv.render(gvv, fn.split('.')[-1], fn)

    print "Wrote dependency graph to %s" % fn

def write_to_xml(succes, failed, filename):
    """
    Create xml output, using minimal output required according to
    http://stackoverflow.com/questions/4922867/junit-xml-format-specification-that-hudson-supports
    """
    dom = xml.getDOMImplementation()
    root = dom.createDocument(None, "testsuite", None)

    def create_testcase(name):
        el = root.createElement("testcase")
        el.setAttribute("name", name)
        return el

    def create_failure(name, error_type, error):
        el = create_testcase(name)

        # encapsulate in CDATA section
        error_text = root.createCDATASection("\n%s\n" % error)
        failure_el = root.createElement("failure")
        failure_el.setAttribute("type", error_type)
        el.appendChild(failure_el)
        el.lastChild.appendChild(error_text)
        return el

    def create_success(name, stats):
        el = create_testcase(name)
        text = "\n".join(["%s=%s" % (key, value) for (key, value) in stats.items()])
        build_stats = root.createCDATASection("\n%s\n" % text)
        system_out = root.createElement("system-out")
        el.appendChild(system_out)
        el.lastChild.appendChild(build_stats)
        return el

    properties = root.createElement("properties")
    framework_version = root.createElement("property")
    framework_version.setAttribute("name", "easybuild-framework-version")
    framework_version.setAttribute("value", str(FRAMEWORK_VERSION))
    properties.appendChild(framework_version)
    easyblocks_version = root.createElement("property")
    easyblocks_version.setAttribute("name", "easybuild-easyblocks-version")
    easyblocks_version.setAttribute("value", str(EASYBLOCKS_VERSION))
    properties.appendChild(easyblocks_version)

    time = root.createElement("property")
    time.setAttribute("name", "timestamp")
    time.setAttribute("value", str(datetime.now()))
    properties.appendChild(time)

    root.firstChild.appendChild(properties)

    for (obj, fase, error, _) in failed:
        # try to pretty print
        try:
            el = create_failure("%s/%s" % (obj.name, obj.get_installversion()), fase, error)
        except AttributeError:
            el = create_failure(obj, fase, error)

        root.firstChild.appendChild(el)

    for (obj, stats) in succes:
        el = create_success("%s/%s" % (obj.name, obj.get_installversion()), stats)
        root.firstChild.appendChild(el)

    output_file = open(filename, "w")
    root.writexml(output_file)
    output_file.close()

def build_easyconfigs(easyconfigs, output_dir, test_results, options, log):
    """Build the list of easyconfigs."""

    build_stopped = {}

    apploginfo = lambda x,y: x.log.info(y)

    def perform_step(step, obj, method, logfile):
        """Perform method on object if it can be built."""
        if (type(obj) == dict and obj['spec'] not in build_stopped) or obj not in build_stopped:
            try:
                if step == 'initialization':
                    log.info("Running %s step" % step)
                    return parbuild.get_instance(obj, log, robot_path=options.robot)
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
        instance = perform_step('initialization', ec, None, log)
        apps.append(instance)

    base_dir = os.getcwd()
    base_env = copy.deepcopy(os.environ)
    succes = []

    for app in apps:

        # if initialisation step failed, app will be None
        if app: 

            applog = os.path.join(output_dir, "%s-%s.log" % (app.name, app.get_installversion()))

            start_time = time.time()

            # start with a clean slate
            os.chdir(base_dir)
            modify_env(os.environ, base_env)

            steps = EasyBlock.get_steps()

            for (step_name, _, step_methods, _) in steps:
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
                    log.info("Moved existing log file %s to %s" % (applog, old_applog))

                shutil.move(app.logfile, applog)
                log.info("Log file moved to %s" % applog)
            except IOError, err:
                error("Failed to move log file %s to new log file %s: %s" % (app.logfile, applog, err))

            if app not in build_stopped:
                # gather build stats
                build_time = round(time.time() - start_time, 2)
                buildstats = get_build_stats(app, start_time)
                succes.append((app, buildstats))

    for result in test_results:
        log.info("%s crashed with an error during fase: %s, error: %s, log file: %s" % result)

    failed = len(build_stopped)
    total = len(apps)

    log.info("%s of %s packages failed to build!" % (failed, total))

    output_file = os.path.join(output_dir, "easybuild-test.xml")
    log.debug("writing xml output to %s" % output_file)
    write_to_xml(succes, test_results, output_file)

    return failed == 0

def aggregate_xml_in_dirs(base_dir, output_filename):
    """
    Finds all the xml files in the dirs and takes the testcase attribute out of them.
    These are then put in a single output file.
    """
    dom = xml.getDOMImplementation()
    root = dom.createDocument(None, "testsuite", None)
    root.documentElement.setAttribute("name", base_dir)
    properties = root.createElement("properties")
    framework_version = root.createElement("property")
    framework_version.setAttribute("name", "easybuild-framework-version")
    framework_version.setAttribute("value", str(FRAMEWORK_VERSION))
    properties.appendChild(framework_version)
    easyblocks_version = root.createElement("property")
    easyblocks_version.setAttribute("name", "easybuild-easyblocks-version")
    easyblocks_version.setAttribute("value", str(EASYBLOCKS_VERSION))
    properties.appendChild(easyblocks_version)

    time_el = root.createElement("property")
    time_el.setAttribute("name", "timestamp")
    time_el.setAttribute("value", str(datetime.now()))
    properties.appendChild(time_el)

    root.firstChild.appendChild(properties)

    dirs = filter(os.path.isdir, [os.path.join(base_dir, d) for d in os.listdir(base_dir)])

    succes = 0
    total = 0

    for d in dirs:
        xml_file = glob.glob(os.path.join(d, "*.xml"))
        if xml_file:
            # take the first one (should be only one present)
            xml_file = xml_file[0]
            dom = xml.parse(xml_file)
            # only one should be present, we are just discarding the rest
            testcase = dom.getElementsByTagName("testcase")[0]
            root.firstChild.appendChild(testcase)

            total += 1
            if not testcase.getElementsByTagName("failure"):
                succes += 1

    comment = root.createComment("%s out of %s builds succeeded" % (succes, total))
    root.firstChild.insertBefore(comment, properties)
    output_file = open(output_filename, "w")
    root.writexml(output_file, addindent="\t", newl="\n")
    output_file.close()

    print "Aggregate regtest results written to %s" % output_filename

def regtest(options, log, easyconfig_paths):
    """Run regression test, using easyconfigs available in given path."""

    cur_dir = os.getcwd()

    if options.aggregate_regtest:
        output_file = os.path.join(options.aggregate_regtest,
                                   "%s-aggregate.xml" % os.path.basename(options.aggregate_regtest))
        aggregate_xml_in_dirs(options.aggregate_regtest, output_file)
        log.info("aggregated xml files inside %s, output written to: %s" % (options.aggregate_regtest, output_file))
        sys.exit(0)

    # create base directory, which is used to place
    # all log files and the test output as xml
    basename = "easybuild-test-%s" % datetime.now().strftime("%Y%m%d%H%M%S")
    var = config.environmentVariables['test_output_path']
    if options.regtest_output_dir:
        output_dir = options.regtest_output_dir
    elif var in os.environ:
        output_dir = os.path.abspath(os.environ[var])
    else:
        # default: current dir + easybuild-test-[timestamp]
        output_dir = os.path.join(cur_dir, basename)

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # find all easyconfigs
    ecfiles = []
    if easyconfig_paths:
        for path in easyconfig_paths:
            ecfiles += find_easyconfigs(path, log)
    else:
        log.error("No easyconfig paths specified.")

    test_results = []

    # process all the found easyconfig files
    easyconfigs = []
    for ecfile in ecfiles:
        try:
            easyconfigs.extend(process_easyconfig(ecfile, log, None))
        except EasyBuildError, err:
            test_results.append((ecfile, 'parsing_easyconfigs', 'easyconfig file error: %s' % err, log))

    if options.sequential:
        return build_easyconfigs(easyconfigs, output_dir, test_results, options, log)
    else:
        resolved = resolve_dependencies(easyconfigs, options.robot, log)

        cmd = "eb %(spec)s --regtest --sequential -ld"
        command = "unset TMPDIR && cd %s && %s; " % (cur_dir, cmd)
        # retry twice in case of failure, to avoid fluke errors
        command += "if [ $? -ne 0 ]; then %(cmd)s && %(cmd)s; fi" % {'cmd': cmd}

        jobs = parbuild.build_easyconfigs_in_parallel(command, resolved, output_dir, log, robot_path=options.robot)

        print "List of submitted jobs:"
        for job in jobs:
            print "%s: %s" % (job.name, job.jobid)
        print "(%d jobs submitted)" % len(jobs)

        # determine leaf nodes in dependency graph, and report them
        all_deps = set()
        for job in jobs:
            all_deps = all_deps.union(job.deps)

        leaf_nodes = []
        for job in jobs:
            if not job.jobid in all_deps:
                leaf_nodes.append(str(job.jobid).split('.')[0])

        log.info("Job ids of leaf nodes in dep. graph: %s" % ','.join(leaf_nodes))

        log.info("Submitted regression test as jobs, results in %s" % output_dir)

        return True  # success

def list_easyblocks(detailed=False):
    """Get a class tree for easyblocks."""

    classes = {}

    module_regexp = re.compile("^([^_].*)\.py$")

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

    from easybuild.framework.easyblock import EasyBlock
    from easybuild.framework.extension import Extension

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
    for root in roots:
        root = root.__name__
        if detailed:
            print "%s (%s)" % (root, classes[root]['module'])
        else:
            print "%s" % root
        if 'children' in classes[root]:
            print_tree(classes, classes[root]['children'], detailed)
            print ""

def print_tree(classes, classNames, detailed, depth=0):
    """Print list of classes as a tree."""

    for className in classNames:
        classInfo = classes[className]
        if detailed:
            print "%s|-- %s (%s)" % ("|   " * depth, className, classInfo['module'])
        else:
            print "%s|-- %s" % ("|   " * depth, className)
        if 'children' in classInfo:
            print_tree(classes, classInfo['children'], detailed, depth + 1)

def list_toolchains():
    """Show list of known toolchains."""

    _, all_tcs = search_toolchain('')
    all_tcs_names = [x.NAME for x in all_tcs]
    tclist = sorted(zip(all_tcs_names, all_tcs))

    print "List of known toolchains:"

    for (tcname, tcc) in tclist:

        tc = tcc(version='1.2.3')  # version doesn't matter here, but something needs to be there
        tc_elems = set([y for x in dir(tc) if x.endswith('_MODULE_NAME') for y in eval("tc.%s" % x)])

        print "\t%s: %s" % (tcname, ', '.join(sorted(tc_elems)))

# FIXME: remove when Python version on which we rely provides any by itself
def any(ls):
    """Reimplementation of 'any' function, which is not available in Python 2.4 yet."""

    return sum([bool(x) for x in ls]) != 0

if __name__ == "__main__":
    try:
        options, orig_paths, log, logfile, hn, parser = parse_options()
        main(options, orig_paths, log, logfile, hn, parser)
    except EasyBuildError, e:
        sys.stderr.write('ERROR: %s\n' % e.msg)
        sys.exit(1)
