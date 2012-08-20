#!/usr/bin/env python
##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
# Copyright 2012 Toon Willems
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
import platform
import os
import re
import shutil
import sys
import tempfile
import time
from optparse import OptionParser

# optional Python packages, these might be missing
# failing imports are just ignored
# a NameError should be catched where these are used

# PyGraph (used for generating dependency graphs)
try:
    import  pygraph.readwrite.dot as dot
    from pygraph.classes.digraph import digraph
except ImportError, err:
    pass

# graphviz (used for creating dependency graph images)
try:
    sys.path.append('..')
    sys.path.append('/usr/lib/graphviz/python/')
    sys.path.append('/usr/lib64/graphviz/python/')
    import gv
except ImportError, err:
    pass

import easybuild  # required for VERBOSE_VERSION
import easybuild.framework.easyconfig as easyconfig
import easybuild.tools.config as config
import easybuild.tools.filetools as filetools
import easybuild.tools.parallelbuild as parbuild
from easybuild.framework.application import get_class
from easybuild.framework.easyconfig import EasyConfig
from easybuild.tools.build_log import EasyBuildError, initLogger, \
    removeLogHandler, print_msg
from easybuild.tools.class_dumper import dumpClasses
from easybuild.tools.modules import Modules, searchModule, \
    curr_module_paths, mk_module_path
from easybuild.tools.config import getRepository
from easybuild.tools import systemtools


# applications use their own logger, we need to tell them to debug or not
# so this global variable is used.
LOGDEBUG = False

def add_build_options(parser):
    """
    Add build options to options parser
    """
    parser.add_option("-C", "--config",
                        help = "path to EasyBuild config file [default: $EASYBUILDCONFIG or easybuild/easybuild_config.py]")
    parser.add_option("-r", "--robot", metavar="path",
                        help="path to search for easyconfigs for missing dependencies")

    parser.add_option("-a", "--avail-easyconfig-params", action="store_true", help="show available easyconfig parameters")
    parser.add_option("--dump-classes", action="store_true", help="show classes available")
    parser.add_option("--search", help="search for module-files in the robot-directory")

    parser.add_option("-e", "--easyblock", metavar="easyblock.class",
                        help="loads the class from module to process the spec file or dump " \
                               "the options for [default: Application class]")
    parser.add_option("-p", "--pretend", action="store_true",
                        help="does the build/installation in a test directory " \
                               "located in $HOME/easybuildinstall")

    parser.add_option("-s", "--stop", type="choice", choices=EasyConfig.validstops,
                        help="stop the installation after certain step " \
                               "(valid: %s)" % ', '.join(EasyConfig.validstops))
    parser.add_option("-b", "--only-blocks", metavar="blocks", help="Only build blocks blk[,blk2]")
    parser.add_option("-k", "--skip", action="store_true",
                        help="skip existing software (useful for installing additional packages)")
    parser.add_option("-t", "--skip-tests", action="store_true",
                        help="skip testing")
    parser.add_option("-f", "--force", action="store_true", dest="force",
                        help="force to rebuild software even if it's already installed (i.e. can be found as module)")

    parser.add_option("-l", action="store_true", dest="stdoutLog", help="log to stdout")
    parser.add_option("-d", "--debug" , action="store_true", help="log debug messages")
    parser.add_option("-v", "--version", action="store_true", help="show version")
    parser.add_option("--regtest", action="store_true", help="enable regression test mode")
    parser.add_option("--regtest-online", action="store_true", help="enable online regression test mode")
    strictness_options = ['ignore', 'warn', 'error']
    parser.add_option("--strict", type="choice", choices=strictness_options, help="set strictness \
                        level (possible levels: %s" % ', '.join(strictness_options))
    parser.add_option("--job", action="store_true", help="submit the build as job(s)")
    parser.add_option("--dep-graph", metavar="depgraph.<ext>", help="create dependency graph")


def main():
    """
    Main function:
    - parse command line options
    - initialize logger
    - read easyconfig
    - build software
    """
    # disallow running EasyBuild as root
    if os.getuid() == 0:
        sys.stderr.write("ERROR: You seem to be running EasyBuild with root priveleges.\n" \
                        "That's not wise, so let's end this here.\n" \
                        "Exiting.\n")
        sys.exit(1)

    # options parser
    parser = OptionParser()

    parser.usage = "%prog [options] easyconfig [..]"
    parser.description = "Builds software package based on easyconfig (or parse a directory)\n" \
                         "Provide one or more easyconfigs or directories, use -h or --help more information."

    add_build_options(parser)

    (options, paths) = parser.parse_args()

    ## mkstemp returns (fd,filename), fd is from os.open, not regular open!
    fd, logFile = tempfile.mkstemp(suffix='.log', prefix='easybuild-')
    os.close(fd)

    if options.stdoutLog:
        os.remove(logFile)
        logFile = None

    global LOGDEBUG
    LOGDEBUG = options.debug

    configOptions = {}
    if options.pretend:
        configOptions['installPath'] = os.path.join(os.environ['HOME'], 'easybuildinstall')

    if options.only_blocks:
        blocks = options.only_blocks.split(',')
    else:
        blocks = None

    ## Initialize logger
    logFile, log, hn = initLogger(filename=logFile, debug=options.debug, typ="build")

    ## Show version
    if options.version:
        print_msg("This is EasyBuild %s" % easybuild.VERBOSE_VERSION, log)

    ## Initialize configuration
    # - check environment variable EASYBUILDCONFIG
    # - then, check command line option
    # - last, use default config file easybuild_config.py in build.py directory
    config_file = options.config

    if not config_file:
        log.debug("No config file specified on command line, trying other options.")

        config_env_var = config.environmentVariables['configFile']
        if os.getenv(config_env_var):
            log.debug("Environment variable %s, so using that as config file." % config_env_var)
            config_file = os.getenv(config_env_var)
        else:
            appPath = os.path.dirname(os.path.realpath(sys.argv[0]))
            config_file = os.path.join(appPath, "easybuild_config.py")
            log.debug("Falling back to default config: %s" % config_file)

    config.init(config_file, **configOptions)

    # Dump possible options
    if options.avail_easyconfig_params:
        print_avail_params(options.easyblock, log)

    ## Dump available classes
    if options.dump_classes:
        dumpClasses('easybuild.easyblocks')

    ## Search for modules
    if options.search:
        if not options.robot:
            error("Please provide a search-path to --robot when using --search")
        searchModule(options.robot, options.search)

    if options.avail_easyconfig_params or options.dump_classes or options.search or options.version:
        if logFile:
            os.remove(logFile)
        sys.exit(0)

    # set strictness of filetools module
    if options.strict:
        filetools.strictness = options.strict

    # building a dependency graph implies force, so that all dependencies are retained
    # and also skips validation of easyconfigs (e.g. checking os dependencies)
    validate_easyconfigs = True
    retain_all_deps = False
    if options.dep_graph:
        log.info("Enabling force to generate dependency graph.")
        options.force = True
        validate_easyconfigs = False
        retain_all_deps = True

    ## Read easyconfig files
    packages = []
    if len(paths) == 0:
        error("Please provide one or more easyconfig files", optparser=parser)

    for path in paths:
        path = os.path.abspath(path)
        if not (os.path.exists(path)):
            error("Can't find path %s" % path)

        try:
            files = findEasyconfigs(path, log)
            for eb_file in files:
                packages.extend(processEasyconfig(eb_file, log, blocks, validate=validate_easyconfigs))
        except IOError, err:
            log.error("Processing easyconfigs in path %s failed: %s" % (path, err))

    ## Before building starts, take snapshot of environment (watch out -t option!)
    origEnviron = copy.deepcopy(os.environ)
    os.chdir(os.environ['PWD'])

    ## Skip modules that are already installed unless forced
    if not options.force:
        m = Modules()
        packages, checkPackages = [], packages
        for package in checkPackages:
            module = package['module']
            mod = "%s (version %s)" % (module[0], module[1])
            modspath = mk_module_path(curr_module_paths() + [os.path.join(config.installPath("mod"), 'all')])
            if m.exists(module[0], module[1], modspath):
                msg = "%s is already installed (module found in %s), skipping " % (mod, modspath)
                print_msg(msg, log)
                log.info(msg)
            else:
                log.debug("%s is not installed yet, so retaining it" % mod)
                packages.append(package)

    ## Determine an order that will allow all specs in the set to build
    if len(packages) > 0:
        print_msg("resolving dependencies ...", log)
        # force all dependencies to be retained and validation to be skipped for building dep graph
        force = retain_all_deps and not validate_easyconfigs
        orderedSpecs = resolveDependencies(packages, options.robot, log, force=force)
    else:
        print_msg("No packages left to be built.", log)
        orderedSpecs = []

    # create dependency graph and exit
    if options.dep_graph:
        log.info("Creating dependency graph %s" % options.dep_graph)
        try:
            dep_graph(options.dep_graph, orderedSpecs, log)
        except NameError, err:
            log.error("At least one optional Python packages (pygraph, dot, graphviz) required to " \
                      "generate dependency graphs is missing: %s" % err)
        sys.exit(0)

    # submit build as job(s) and exit
    if options.job:
        curdir = os.getcwd()
        easybuild_basedir = os.path.dirname(os.path.dirname(sys.argv[0]))
        eb_path = os.path.join(easybuild_basedir, "eb")

        # Reverse option parser -> string

        # the options to ignore
        ignore = map(parser.get_option, ['--robot', '--help', '--job'])

        # loop over all the different options.
        result_opts = []
        relevant_opts = [o for o in parser.option_list if o not in ignore]
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

        command = "cd %s && %s %%s %s" % (curdir, eb_path, opts)
        jobs = parbuild.build_packages_in_parallel(command, orderedSpecs, "easybuild-build", log)
        print "List of submitted jobs:"
        for job in jobs:
            print "%s: %s" % (job.name, job.jobid)
        print "(%d jobs submitted)" % len(jobs)

        log.info("Submitted parallel build jobs, exiting now")
        sys.exit(0)

    ## Build software, will exit when errors occurs (except when regtesting)
    correct_built_cnt = 0
    all_built_cnt = 0
    for spec in orderedSpecs:
        (success, _) = build(spec, options, log, origEnviron, exitOnFailure=(not options.regtest))
        if success:
            correct_built_cnt += 1
        all_built_cnt += 1

    print_msg("Build succeeded for %s out of %s" % (correct_built_cnt, all_built_cnt), log)

    getRepository().cleanup()
    ## Cleanup tmp log file (all is well, all modules have their own log file)
    try:
        removeLogHandler(hn)
        hn.close()
        if logFile:
            os.remove(logFile)

        for package in packages:
            if 'originalSpec' in package:
                os.remove(package['spec'])

    except IOError, err:
        error("Something went wrong closing and removing the log %s : %s" % (logFile, err))

def error(message, exitCode=1, optparser=None):
    """
    Print error message and exit EasyBuild
    """
    print_msg("ERROR: %s\n" % message)
    if optparser:
        optparser.print_help()
    sys.exit(exitCode)

def findEasyconfigs(path, log):
    """
    Find .eb easyconfig files in path
    """
    if os.path.isfile(path):
        return [path]

    ## Walk through the start directory, retain all files that end in .eb
    files = []
    path = os.path.abspath(path)
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            if not f.endswith('.eb'):
                continue

            spec = os.path.join(dirpath, f)
            log.debug("Found easyconfig %s" % spec)
            files.append(spec)

    return files

def processEasyconfig(path, log, onlyBlocks=None, regtest_online=False, validate=True):
    """
    Process easyconfig, returning some information for each block
    """
    blocks = retrieveBlocksInSpec(path, log, onlyBlocks)

    packages = []
    for spec in blocks:
        ## Process for dependencies and real installversionname
        ## - use mod? __init__ and importCfg are ignored.
        log.debug("Processing easyconfig %s" % spec)

        # create easyconfig
        try:
            eb = EasyConfig(spec, validate=validate)
        except EasyBuildError, err:
            msg = "Failed to process easyconfig %s:\n%s" % (spec, err.msg)
            log.exception(msg)

        name = eb['name']

        ## this app will appear as following module in the list
        package = {
            'spec': spec,
            'module': (eb.name(), eb.installversion()),
            'dependencies': []
        }
        if len(blocks) > 1:
            package['originalSpec'] = path

        for d in eb.dependencies():
            dep = (d['name'], d['tk'])
            log.debug("Adding dependency %s for app %s." % (dep, name))
            package['dependencies'].append(dep)

        if eb.toolkit_name() != 'dummy':
            dep = (eb.toolkit_name(), eb.toolkit_version())
            log.debug("Adding toolkit %s as dependency for app %s." % (dep, name))
            package['dependencies'].append(dep)

        del eb

        # this is used by the parallel builder
        package['unresolvedDependencies'] = copy.copy(package['dependencies'])

        packages.append(package)

    return packages

def resolveDependencies(unprocessed, robot, log, force=False):
    """
    Work through the list of packages to determine an optimal order
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

    ## As long as there is progress in processing the modules, keep on trying
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

        ## First try resolving dependencies without using external dependencies
        lastProcessedCount = -1
        while len(processed) > lastProcessedCount:
            lastProcessedCount = len(processed)
            orderedSpecs.extend(findResolvedModules(unprocessed, processed, log))

        ## Robot: look for an existing dependency, add one
        if robot and len(unprocessed) > 0:

            beingInstalled = [p['module'] for p in unprocessed]

            for module in unprocessed:
                ## Do not choose a module that is being installed in the current run
                ## if they depend, you probably want to rebuild them using the new dependency
                candidates = [d for d in module['dependencies'] if not d in beingInstalled]
                if len(candidates) > 0:
                    ## find easyconfig, might not find any
                    path = robotFindEasyconfig(log, robot, candidates[0])

                else:
                    path = None
                    log.debug("No more candidate dependencies to resolve for module %s" % str(module['module']))

                if path:
                    log.info("Robot: resolving dependency %s with %s" % (candidates[0], path))

                    processedSpecs = processEasyconfig(path, log, validate=(not force))

                    # ensure the pathname is equal to the module
                    mods = [spec['module'] for spec in processedSpecs]
                    if not candidates[0] in mods:
                        log.error("easyconfig file %s does not contain module %s" % (path, candidates[0]))

                    unprocessed.extend(processedSpecs)
                    robotAddedDependency = True
                    break

    ## There are dependencies that cannot be resolved
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

def findResolvedModules(unprocessed, processed, log):
    """
    Find modules in unprocessed which can be fully resolved using packages in processed
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

def robotFindEasyconfig(log, path, module):
    """
    Find an easyconfig for module in path
    """
    name, version = module
    # candidate easyconfig paths
    easyconfigsPaths = [os.path.join(path, name, version + ".eb"),
                         os.path.join(path, name, "%s-%s.eb" % (name, version)),
                         os.path.join(path, name.lower()[0], name, "%s-%s.eb" % (name, version)),
                         os.path.join(path, "%s-%s.eb" % (name, version)),
                         ]
    for easyconfigPath in easyconfigsPaths:
        log.debug("Checking easyconfig path %s" % easyconfigPath)
        if os.path.isfile(easyconfigPath):
            log.debug("Found easyconfig file for %s at %s" % (module, easyconfigPath))
            return os.path.abspath(easyconfigPath)

    return None

def retrieveBlocksInSpec(spec, log, onlyBlocks):
    """
    Easyconfigs can contain blocks (headed by a [Title]-line)
    which contain commands specific to that block. Commands in the beginning of the file
    above any block headers are common and shared between each block.
    """
    regBlock = re.compile(r"^\s*\[([\w.-]+)\]\s*$", re.M)
    regDepBlock = re.compile(r"^\s*block\s*=(\s*.*?)\s*$", re.M)

    cfgName = os.path.basename(spec)
    pieces = regBlock.split(open(spec).read())

    ## The first block contains common statements
    common = pieces.pop(0)
    if pieces:
        ## Make a map of blocks
        blocks = []
        while pieces:
            blockName = pieces.pop(0)
            blockContents = pieces.pop(0)

            if blockName in [b['name'] for b in blocks]:
                msg = "Found block %s twice in %s." % (blockName, spec)
                log.error(msg)

            block = {'name': blockName, 'contents': blockContents}

            ## Dependency block
            depBlock = regDepBlock.search(blockContents)
            if depBlock:
                dependencies = eval(depBlock.group(1))
                if type(dependencies) == list:
                    block['dependencies'] = dependencies
                else:
                    block['dependencies'] = [dependencies]

            blocks.append(block)

        ## Make a new easyconfig for each block
        ## They will be processed in the same order as they are all described in the original file
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
                        f.write("\n## Dependency block %s" % (dep['name']))
                        f.write(dep['contents'])

                f.write("\n## Main block %s" % name)
                f.write(block['contents'])
                f.close()

            except Exception:
                msg = "Failed to write block %s to easyconfig %s" % (name, spec)
                log.exception(msg)

            specs.append(blockPath)

        log.debug("Found %s block(s) in %s" % (len(specs), spec))
        return specs
    else:
        ## no blocks, one file
        return [spec]

def build(module, options, log, origEnviron, exitOnFailure=True):
    """
    Build the software
    """
    spec = module['spec']

    print_msg("processing EasyBuild easyconfig %s" % spec, log)

    ## Restore original environment
    log.info("Resetting environment")
    filetools.errorsFoundInLog = 0
    if not filetools.modifyEnv(os.environ, origEnviron):
        error("Failed changing the environment back to original")

    cwd = os.getcwd()

    ## Load easyblock
    easyblock = options.easyblock
    if not easyblock:
        ## Try to look in .eb file
        reg = re.compile(r"^\s*easyblock\s*=(.*)$")
        for line in open(spec).readlines():
            match = reg.search(line)
            if match:
                easyblock = eval(match.group(1))
                break

    name = module['module'][0]
    try:
        app_class = get_class(easyblock, log, name=name)
        app = app_class(spec, debug=options.debug)
        log.info("Obtained application instance of for %s (easyblock: %s)" % (name, easyblock))
    except EasyBuildError, err:
        error("Failed to get application instance for %s (easyblock: %s): %s" % (name, easyblock, err.msg))

    ## Application settings
    if options.stop:
        log.debug("Stop set to %s" % options.stop)
        app.setcfg('stop', options.stop)

    if options.skip:
        log.debug("Skip set to %s" % options.skip)
        app.setcfg('skip', options.skip)

    ## Build easyconfig
    errormsg = '(no error)'
    # timing info
    starttime = time.time()
    try:
        result = app.autobuild(spec, runTests=not options.skip_tests, regtest_online=options.regtest_online)
    except EasyBuildError, err:
        lastn = 300
        errormsg = "autoBuild Failed (last %d chars): %s" % (lastn, err.msg[-lastn:])
        log.exception(errormsg)
        result = False

    ended = "ended"

    ## Successful build
    if result:

        ## Collect build stats
        log.info("Collecting build stats...")
        buildtime = round(time.time() - starttime, 2)
        installsize = 0
        try:
            # change to home dir, to avoid that cwd no longer exists
            os.chdir(os.getenv('HOME'))

            # walk install dir to determine total size
            for dirpath, _, filenames in os.walk(app.installdir):
                for filename in filenames:
                    fullpath = os.path.join(dirpath, filename)
                    if os.path.exists(fullpath):
                        installsize += os.path.getsize(fullpath)
        except OSError, err:
            log.error("Failed to determine install size: %s" % err)

        currentbuildstats = app.getcfg('buildstats')
        buildstats = {'build_time' : buildtime,
                 'platform' : platform.platform(),
                 'core_count' : systemtools.get_core_count(),
                 'cpu_model': systemtools.get_cpu_model(),
                 'install_size' : installsize,
                 'timestamp' : int(time.time()),
                 'host' : os.uname()[1],
                 }
        log.debug("Build stats: %s" % buildstats)

        if app.getcfg('stop'):
            ended = "STOPPED"
            newLogDir = os.path.join(app.builddir, config.logPath())
        else:
            newLogDir = os.path.join(app.installdir, config.logPath())

            try:
                ## Upload spec to central repository
                repo = getRepository()
                if 'originalSpec' in module:
                    repo.addEasyconfig(module['originalSpec'], app.name(), app.installversion() + ".block", buildstats, currentbuildstats)
                repo.addEasyconfig(spec, app.name(), app.installversion(), buildstats, currentbuildstats)
                repo.commit("Built %s/%s" % (app.name(), app.installversion()))
                del repo
            except EasyBuildError, err:
                log.warn("Unable to commit easyconfig to repository (%s)", err)

        exitCode = 0
        succ = "successfully"
        summary = "COMPLETED"

        ## Cleanup logs
        app.closelog()
        try:
            if not os.path.isdir(newLogDir):
                os.makedirs(newLogDir)
            applicationLog = os.path.join(newLogDir, os.path.basename(app.logfile))
            shutil.move(app.logfile, applicationLog)
        except IOError, err:
            error("Failed to move log file %s to new log file %s: %s" % (app.logfile, applicationLog, err))

        try:
            shutil.copy(spec, os.path.join(newLogDir, "%s-%s.eb" % (app.name(), app.installversion())))
        except IOError, err:
            error("Failed to move easyconfig %s to log dir %s: %s" % (spec, newLogDir, err))

    ## Build failed
    else:
        exitCode = 1
        summary = "FAILED"

        buildDir = ''
        if app.builddir:
            buildDir = " (build directory: %s)" % (app.builddir)
        succ = "unsuccessfully%s:\n%s" % (buildDir, errormsg)

        ## Cleanup logs
        app.closelog()
        applicationLog = app.logfile

    print_msg("%s: Installation %s %s" % (summary, ended, succ), log)

    ## Check for errors
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


if __name__ == "__main__":
    try:
        main()
    except EasyBuildError, e:
        sys.stderr.write('ERROR: %s\n' % e.msg)
        sys.exit(1)
