#!/usr/bin/env python
##
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
##
"""
Main entry point for EasyBuild: build software from .eb input file

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
"""

import copy
import glob
import platform
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import xml.dom.minidom as xml
from datetime import datetime
from vsc import fancylogger

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
import easybuild.tools.options as eboptions
import easybuild.tools.parallelbuild as parbuild
from easybuild.framework.easyblock import EasyBlock, get_class
from easybuild.framework.easyconfig import EasyConfig, get_paths_for
from easybuild.tools import systemtools
from easybuild.tools.build_log import  EasyBuildError, print_msg, print_error, print_warning
from easybuild.tools.version import this_is_easybuild, FRAMEWORK_VERSION, EASYBLOCKS_VERSION  # from a single location
from easybuild.tools.config import get_repository, module_classes
from easybuild.tools.filetools import modify_env
from easybuild.tools.modules import Modules, search_module
from easybuild.tools.modules import curr_module_paths, mk_module_path
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.utilities import any

log = None

def main(testing_data=(None, None)):
    """
    Main function:
    @arg options: a tuple: (options, paths, logger, logfile, hn) as defined in parse_options
    This function will:
    - read easyconfig
    - build software
    """
    # disallow running EasyBuild as root
    if os.getuid() == 0:
        sys.stderr.write("ERROR: You seem to be running EasyBuild with root privileges.\n" \
                        "That's not wise, so let's end this here.\n" \
                        "Exiting.\n")
        sys.exit(1)

    # steer behavior when testing main
    testing = testing_data[0] is not None
    args, logfile = testing_data

    # initialise options
    (options, orig_paths, opt_parser, cmd_args) = eboptions.parse_options(args=args)

    # initialise logging for main
    if options.logtostdout:
        fancylogger.logToScreen(enable=True, stdout=True)
    else:
        if logfile is None:
            # mkstemp returns (fd,filename), fd is from os.open, not regular open!
            fd, logfile = tempfile.mkstemp(suffix='.log', prefix='easybuild-')
            os.close(fd)

        fancylogger.logToFile(logfile)
        print_msg('temporary log file in case of crash %s' % (logfile), log=None, silent=testing)

    global log
    log = fancylogger.getLogger(fname=False)

    # hello world!
    log.info(this_is_easybuild())

    # set strictness of filetools module
    if options.strict:
        filetools.strictness = options.strict

    if not options.robot is None:
        if options.robot:
            log.info("Using robot path: %s" % options.robot)
        else:
            log.error("No robot path specified, and unable to determine easybuild-easyconfigs install path.")

    # determine easybuild-easyconfigs package install path
    easyconfigs_paths = get_paths_for("easyconfigs", robot_path=options.robot)
    easyconfigs_pkg_full_path = None

    if easyconfigs_paths:
        easyconfigs_pkg_full_path = easyconfigs_paths[0]
        if not options.robot:
            search_path = easyconfigs_pkg_full_path
        else:
            search_path = options.robot
    else:
        log.info("Failed to determine install path for easybuild-easyconfigs package.")

    if options.robot:
        easyconfigs_paths = [options.robot] + easyconfigs_paths

    configOptions = {}
    if options.pretend:
        configOptions['install_path'] = os.path.join(os.environ['HOME'], 'easybuildinstall')

    # default location of configfile is set as default in the config option
    config.init(options.config, **configOptions)

    # search for modules
    if options.search:
        search_module(search_path, options.search)

    # process software build specifications (if any), i.e.
    # software name/version, toolchain name/version, extra patches, ...
    (try_to_generate, software_build_specs) = process_software_build_specs(options)

    paths = []
    if len(orig_paths) == 0:
        if software_build_specs.has_key('name'):
            paths = [obtain_path(software_build_specs, easyconfigs_paths,
                                 try_to_generate=try_to_generate, exit_on_error=not testing)]
        elif not any([options.aggregate_regtest, options.search, options.regtest]):
            print_error(("Please provide one or multiple easyconfig files, or use software build "
                  "options to make EasyBuild search for easyconfigs"),
                  log=log, opt_parser=opt_parser, exit_on_error=not testing)
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
                        log.info("Found %s in %s: %s" % (orig_paths[i], easyconfigs_pkg_full_path,
                                                         easyconfigs_map[orig_paths[i]]))
                        orig_paths[i] = easyconfigs_map[orig_paths[i]]

        # indicate that specified paths do not contain generated easyconfig files
        paths = [(path, False) for path in orig_paths]

    log.debug("Paths: %s" % paths)

    # run regtest
    if options.regtest or options.aggregate_regtest:
        log.info("Running regression test")
        if paths:
            regtest_ok = regtest(options, [path[0] for path in paths])
        else:  # fallback: easybuild-easyconfigs install path
            regtest_ok = regtest(options, [easyconfigs_pkg_full_path])

        if not regtest_ok:
            log.info("Regression test failed (partially)!")
            sys.exit(31)  # exit -> 3x1t -> 31

    if any([options.search, options.regtest]):
        cleanup_logfile_and_exit(logfile, testing, True)

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
            print_error("Can't find path %s" % path)

        try:
            files = find_easyconfigs(path)
            for f in files:
                if not generated and try_to_generate and software_build_specs:
                    ec_file = easyconfig.tweak(f, None, software_build_specs)
                else:
                    ec_file = f
                easyconfigs.extend(process_easyconfig(ec_file, options.only_blocks,
                                                      validate=validate_easyconfigs))
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
                print_msg(msg, log, silent=testing)
                log.info(msg)
            else:
                log.debug("%s is not installed yet, so retaining it" % mod)
                easyconfigs.append(ec)

    # determine an order that will allow all specs in the set to build
    if len(easyconfigs) > 0:
        print_msg("resolving dependencies ...", log, silent=testing)
        # force all dependencies to be retained and validation to be skipped for building dep graph
        force = retain_all_deps and not validate_easyconfigs
        orderedSpecs = resolve_dependencies(easyconfigs, options.robot, force=force)
    else:
        print_msg("No easyconfigs left to be built.", log, silent=testing)
        orderedSpecs = []

    # create dependency graph and exit
    if options.dep_graph:
        log.info("Creating dependency graph %s" % options.dep_graph)
        try:
            dep_graph(options.dep_graph, orderedSpecs)
        except NameError, err:
            log.error("An optional Python packages required to " \
                      "generate dependency graphs is missing: %s" % "\n".join(graph_errors))
        sys.exit(0)

    # submit build as job(s) and exit
    if options.job:
        curdir = os.getcwd()

        # the options to ignore (help options can't reach here)
        ignore_opts = ['robot', 'job']

        # cmd_args is in form --longopt=value
        opts = [x for x in cmd_args if not x.split('=')[0] in ['--%s' % y for y in ignore_opts]]

        quoted_opts = subprocess.list2cmdline(opts)

        command = "unset TMPDIR && cd %s && eb %%(spec)s %s" % (curdir, quoted_opts)
        log.info("Command template for jobs: %s" % command)
        if not testing:
            jobs = parbuild.build_easyconfigs_in_parallel(command, orderedSpecs, "easybuild-build",
                                                          robot_path=options.robot)
            txt = ["List of submitted jobs:"]
            txt.extend(["%s: %s" % (job.name, job.jobid) for job in jobs])
            txt.append("(%d jobs submitted)" % len(jobs))

            msg = "\n".join(txt)
            log.info("Submitted parallel build jobs, exiting now (%s)." % msg)
            print msg

            cleanup_logfile_and_exit(logfile, testing, True)

            sys.exit(0)

    # build software, will exit when errors occurs (except when regtesting)
    correct_built_cnt = 0
    all_built_cnt = 0
    if not testing:
        for spec in orderedSpecs:
            (success, _) = build_and_install_software(spec, options, origEnviron, silent=testing)
            if success:
                correct_built_cnt += 1
            all_built_cnt += 1

    print_msg("Build succeeded for %s out of %s" % (correct_built_cnt, all_built_cnt), log, silent=testing)

    get_repository().cleanup()

    # cleanup and spec files
    for ec in easyconfigs:
        if 'originalSpec' in ec and os.path.isfile(ec['spec']):
            os.remove(ec['spec'])

    # cleanup tmp log file (all is well, all modules have their own log file)
    if options.logtostdout:
        fancylogger.logToScreen(enable=False, stdout=True)
    else:
        fancylogger.logToFile(logfile, enable=False)
        cleanup_logfile_and_exit(logfile, testing, False)
        logfile = None

    return logfile

def cleanup_logfile_and_exit(logfile, testing, doexit):
    """Cleanup the logfile and exit"""
    if not testing and logfile is not None:
        os.remove(logfile)
        print_msg('temporary log file %s has been removed.' % (logfile), log=None, silent=testing)
    if doexit:
        sys.exit(0)

def find_easyconfigs(path):
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

def process_easyconfig(path, onlyBlocks=None, regtest_online=False, validate=True):
    """
    Process easyconfig, returning some information for each block
    """
    blocks = retrieve_blocks_in_spec(path, onlyBlocks)

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

def resolve_dependencies(unprocessed, robot, force=False):
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
            log.warning("No installed modules. Your MODULEPATH is probably incomplete: %s" % os.getenv('MODULEPATH'))

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
            orderedSpecs.extend(find_resolved_modules(unprocessed, processed))

        # robot: look for an existing dependency, add one
        if robot and len(unprocessed) > 0:

            beingInstalled = [p['module'] for p in unprocessed]

            for module in unprocessed:
                # do not choose a module that is being installed in the current run
                # if they depend, you probably want to rebuild them using the new dependency
                candidates = [d for d in module['dependencies'] if not d in beingInstalled]
                if len(candidates) > 0:
                    # find easyconfig, might not find any
                    path = robot_find_easyconfig(robot, candidates[0])

                else:
                    path = None
                    log.debug("No more candidate dependencies to resolve for module %s" % str(module['module']))

                if path:
                    log.info("Robot: resolving dependency %s with %s" % (candidates[0], path))

                    processedSpecs = process_easyconfig(path, validate=(not force))

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

def find_resolved_modules(unprocessed, processed):
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

    # process --toolchain --try-toolchain (sanity check done in tools.options)
    tc = options.toolchain or options.try_toolchain
    if tc:
        if options.toolchain and options.try_toolchain:
            print_warning("Ignoring --try-toolchain, only using --toolchain specification.")
        elif options.try_toolchain:
            try_to_generate = True
        buildopts.update({'toolchain_name': tc[0],
                          'toolchain_version': tc[1],
                          })

    # process --amend and --try-amend
    if options.amend or options.try_amend:

        amends = []
        if options.amend:
            amends += options.amend
            if options.try_amend:
                print_warning("Ignoring options passed via --try-amend, only using those passed via --amend.")
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

def obtain_path(specs, paths, try_to_generate=False, exit_on_error=True, silent=False):
    """Obtain a path for an easyconfig that matches the given specifications."""

    # if no easyconfig files/paths were provided, but we did get a software name,
    # we can try and find a suitable easyconfig ourselves, or generate one if we can
    (generated, fn) = easyconfig.obtain_ec_for(specs, paths, None)
    if not generated:
        return (fn, generated)
    else:
        # if an easyconfig was generated, make sure we're allowed to use it
        if try_to_generate:
            print_msg("Generated an easyconfig file %s, going to use it now..." % fn, silent=silent)
            return (fn, generated)
        else:
            try:
                os.remove(fn)
            except OSError, err:
                print_warning("Failed to remove generated easyconfig file %s." % fn)
            print_error(("Unable to find an easyconfig for the given specifications: %s; "
                  "to make EasyBuild try to generate a matching easyconfig, "
                  "use the --try-X options ") % specs, log=log, exit_on_error=exit_on_error)


def robot_find_easyconfig(path, module):
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

def retrieve_blocks_in_spec(spec, onlyBlocks, silent=False):
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
                print_msg("Skipping block %s-%s" % (cfgName, name), silent=silent)
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

def build_and_install_software(module, options, origEnviron, exitOnFailure=True, silent=False):
    """
    Build the software
    """
    spec = module['spec']

    print_msg("processing EasyBuild easyconfig %s" % spec, log, silent=silent)

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
        app_class = get_class(easyblock, name=name)
        app = app_class(spec, debug=options.debug, robot_path=options.robot)
        log.info("Obtained application instance of for %s (easyblock: %s)" % (name, easyblock))
    except EasyBuildError, err:
        print_error("Failed to get application instance for %s (easyblock: %s): %s" % (name, easyblock, err.msg), silent=silent)

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
            print_error("Failed to move log file %s to new log file %s: %s" % (app.logfile, applicationLog, err))

        try:
            shutil.copy(spec, os.path.join(newLogDir, "%s-%s.eb" % (app.name, app.get_installversion())))
        except IOError, err:
            print_error("Failed to move easyconfig %s to log dir %s: %s" % (spec, newLogDir, err))

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

    print_msg("%s: Installation %s %s" % (summary, ended, succ), log, silent=silent)

    # check for errors
    if exitCode > 0 or filetools.errorsFoundInLog > 0:
        print_msg("\nWARNING: Build exited with exit code %d. %d possible error(s) were detected in the " \
                  "build logs, please verify the build.\n" % (exitCode, filetools.errorsFoundInLog),
                  log, silent=silent)

    if app.postmsg:
        print_msg("\nWARNING: %s\n" % app.postmsg, log, silent=silent)

    print_msg("Results of the build can be found in the log file %s" % applicationLog, log, silent=silent)

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

def dep_graph(fn, specs):
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
        spec['unresolvedDependencies'] = [mk_node_name(s) for s in spec['unresolvedDependencies']]  # [s[0] for s in spec['unresolvedDependencies']]

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

def build_easyconfigs(easyconfigs, output_dir, test_results, options):
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
                    log.info("Running %s step" % step)
                    return parbuild.get_easyblock_instance(obj, robot_path=options.robot)
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
                print_error("Failed to move log file %s to new log file %s: %s" % (app.logfile, applog, err))

            if app not in build_stopped:
                # gather build stats
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


def regtest(options, easyconfig_paths):
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
            ecfiles += find_easyconfigs(path)
    else:
        log.error("No easyconfig paths specified.")

    test_results = []

    # process all the found easyconfig files
    easyconfigs = []
    for ecfile in ecfiles:
        try:
            easyconfigs.extend(process_easyconfig(ecfile, None))
        except EasyBuildError, err:
            test_results.append((ecfile, 'parsing_easyconfigs', 'easyconfig file error: %s' % err, log))

    if options.sequential:
        return build_easyconfigs(easyconfigs, output_dir, test_results, options)
    else:
        resolved = resolve_dependencies(easyconfigs, options.robot)

        cmd = "eb %(spec)s --regtest --sequential -ld"
        command = "unset TMPDIR && cd %s && %s; " % (cur_dir, cmd)
        # retry twice in case of failure, to avoid fluke errors
        command += "if [ $? -ne 0 ]; then %(cmd)s && %(cmd)s; fi" % {'cmd': cmd}

        jobs = parbuild.build_easyconfigs_in_parallel(command, resolved, output_dir, robot_path=options.robot)

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

if __name__ == "__main__":
    try:
        main()
    except EasyBuildError, e:
        sys.stderr.write('ERROR: %s\n' % e.msg)
        sys.exit(1)
