#!/usr/bin/env python
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
from vsc.utils.missing import any

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

# IMPORTANT this has to be the first easybuild import as it customises the logging
#  expect missing log output when this not the case!
from easybuild.tools.build_log import  EasyBuildError, print_msg, print_error, print_warning

import easybuild.framework.easyconfig as easyconfig
import easybuild.tools.config as config
import easybuild.tools.filetools as filetools
import easybuild.tools.options as eboptions
import easybuild.tools.parallelbuild as parbuild
from easybuild.framework.easyblock import EasyBlock, get_class
from easybuild.framework.easyconfig.easyconfig import EasyConfig, ITERATE_OPTIONS
from easybuild.framework.easyconfig.format.version import EasyVersion
from easybuild.framework.easyconfig.format.one import retrieve_blocks_in_spec
from easybuild.framework.easyconfig.tools import get_paths_for
from easybuild.tools import systemtools
from easybuild.tools.config import get_repository, module_classes, get_log_filename, get_repositorypath
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.module_generator import det_full_module_name
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.modules import curr_module_paths, mk_module_path, modules_tool
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.repository import init_repository
from easybuild.tools.version import this_is_easybuild, FRAMEWORK_VERSION, EASYBLOCKS_VERSION  # from a single location


_log = None


def main(testing_data=(None, None, None)):
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
    args, logfile, do_build = testing_data

    # initialise options
    eb_go = eboptions.parse_options(args=args)
    options = eb_go.options
    orig_paths = eb_go.args

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

    global _log
    _log = fancylogger.getLogger(fname=False)

    # hello world!
    _log.info(this_is_easybuild())

    # set strictness of filetools module
    if options.strict:
        filetools.strictness = options.strict

    if not options.robot is None:
        if options.robot:
            _log.info("Using robot path: %s" % options.robot)
        else:
            _log.error("No robot path specified, and unable to determine easybuild-easyconfigs install path.")

    # determine easybuild-easyconfigs package install path
    easyconfigs_paths = get_paths_for("easyconfigs", robot_path=options.robot)
    easyconfigs_pkg_full_path = None

    search_path = os.getcwd()
    if easyconfigs_paths:
        easyconfigs_pkg_full_path = easyconfigs_paths[0]
        if not options.robot:
            search_path = easyconfigs_pkg_full_path
        else:
            search_path = options.robot
    else:
        _log.info("Failed to determine install path for easybuild-easyconfigs package.")

    if options.robot:
        easyconfigs_paths = [options.robot] + easyconfigs_paths

    # initialise the easybuild configuration
    config.init(options, eb_go.get_options_by_section('config'))

    # search for easyconfigs
    if options.search:
        search_file(search_path, options.search, silent=testing)

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
                  log=_log, opt_parser=eb_go.parser, exit_on_error=not testing)
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
            for idx, orig_path in enumerate(orig_paths):
                if not os.path.isabs(orig_path) and not os.path.exists(orig_path):
                    if orig_path in easyconfigs_map:
                        _log.info("Found %s in %s: %s" % (orig_path, easyconfigs_pkg_full_path,
                                                         easyconfigs_map[orig_path]))
                        orig_paths[idx] = easyconfigs_map[orig_path]

        # indicate that specified paths do not contain generated easyconfig files
        paths = [(path, False) for path in orig_paths]

    _log.debug("Paths: %s" % paths)

    # run regtest
    if options.regtest or options.aggregate_regtest:
        _log.info("Running regression test")
        if paths:
            regtest_ok = regtest(options, [path[0] for path in paths])
        else:  # fallback: easybuild-easyconfigs install path
            regtest_ok = regtest(options, [easyconfigs_pkg_full_path])

        if not regtest_ok:
            _log.info("Regression test failed (partially)!")
            sys.exit(31)  # exit -> 3x1t -> 31

    if any([options.search, options.regtest]):
        cleanup_logfile_and_exit(logfile, testing, True)

    # building a dependency graph implies force, so that all dependencies are retained
    # and also skips validation of easyconfigs (e.g. checking os dependencies)
    validate_easyconfigs = True
    retain_all_deps = False
    if options.dep_graph:
        _log.info("Enabling force to generate dependency graph.")
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
                    ec_file = easyconfig.tools.tweak(f, None, software_build_specs)
                else:
                    ec_file = f
                easyconfigs.extend(process_easyconfig(ec_file, options.only_blocks,
                                                      validate=validate_easyconfigs))
        except IOError, err:
            _log.error("Processing easyconfigs in path %s failed: %s" % (path, err))

    # before building starts, take snapshot of environment (watch out -t option!)
    orig_environ = copy.deepcopy(os.environ)
    os.chdir(os.environ['PWD'])

    # dry_run: print all easyconfigs and dependencies, and whether they are already built
    if options.dry_run:
        print_dry_run(easyconfigs, options.robot)
        sys.exit(0)

    # skip modules that are already installed unless forced
    if not options.force:
        easyconfigs = skip_available(easyconfigs, testing=testing)

    # determine an order that will allow all specs in the set to build
    if len(easyconfigs) > 0:
        print_msg("resolving dependencies ...", log=_log, silent=testing)
        # force all dependencies to be retained and validation to be skipped for building dep graph
        force = retain_all_deps and not validate_easyconfigs
        orderedSpecs = resolve_dependencies(easyconfigs, options.robot, force=force)
    else:
        print_msg("No easyconfigs left to be built.", log=_log, silent=testing)
        orderedSpecs = []

    # create dependency graph and exit
    if options.dep_graph:
        _log.info("Creating dependency graph %s" % options.dep_graph)
        try:
            dep_graph(options.dep_graph, orderedSpecs)
        except NameError, err:
            errors = "\n".join(graph_errors)
            msg = "An optional Python packages required to generate dependency graphs is missing: %s" % errors
            _log.error("%s\nerr: %s" % (msg, err))
        sys.exit(0)

    # submit build as job(s) and exit
    if options.job:
        curdir = os.getcwd()

        # the options to ignore (help options can't reach here)
        ignore_opts = ['robot', 'job']

        # generate_cmd_line returns the options in form --longopt=value
        opts = [x for x in eb_go.generate_cmd_line() if not x.split('=')[0] in ['--%s' % y for y in ignore_opts]]

        quoted_opts = subprocess.list2cmdline(opts)

        command = "unset TMPDIR && cd %s && eb %%(spec)s %s" % (curdir, quoted_opts)
        _log.info("Command template for jobs: %s" % command)
        if not testing:
            jobs = parbuild.build_easyconfigs_in_parallel(command, orderedSpecs, "easybuild-build",
                                                          robot_path=options.robot)
            txt = ["List of submitted jobs:"]
            txt.extend(["%s (%s): %s" % (job.name, job.module, job.jobid) for job in jobs])
            txt.append("(%d jobs submitted)" % len(jobs))

            msg = "\n".join(txt)
            _log.info("Submitted parallel build jobs, exiting now (%s)." % msg)
            print msg

            cleanup_logfile_and_exit(logfile, testing, True)

            sys.exit(0)

    # build software, will exit when errors occurs (except when regtesting)
    correct_built_cnt = 0
    all_built_cnt = 0
    if not testing or (testing and do_build):
        for spec in orderedSpecs:
            (success, _) = build_and_install_software(spec, options, orig_environ, silent=testing)
            if success:
                correct_built_cnt += 1
            all_built_cnt += 1

    print_msg("Build succeeded for %s out of %s" % (correct_built_cnt, all_built_cnt), log=_log, silent=testing)

    repo = init_repository(get_repository(), get_repositorypath())
    repo.cleanup()

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
            _log.debug("Found easyconfig %s" % spec)
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
        _log.debug("Processing easyconfig %s" % spec)

        # create easyconfig
        try:
            all_stops = [x[0] for x in EasyBlock.get_steps()]
            ec = EasyConfig(spec, validate=validate, valid_module_classes=module_classes(), valid_stops=all_stops)
        except EasyBuildError, err:
            msg = "Failed to process easyconfig %s:\n%s" % (spec, err.msg)
            _log.exception(msg)

        name = ec['name']

        # this app will appear as following module in the list
        easyconfig = {
            'ec': ec,
            'spec': spec,
            'module': det_full_module_name(ec),
            'dependencies': [],
            'builddependencies': [],
        }
        if len(blocks) > 1:
            easyconfig['originalSpec'] = path

        # add build dependencies
        for dep in ec.builddependencies():
            _log.debug("Adding build dependency %s for app %s." % (dep, name))
            easyconfig['builddependencies'].append(dep)

        # add dependencies (including build dependencies)
        for dep in ec.dependencies():
            _log.debug("Adding dependency %s for app %s." % (dep, name))
            easyconfig['dependencies'].append(dep)

        # add toolchain as dependency too
        if ec.toolchain.name != DUMMY_TOOLCHAIN_NAME:
            dep = ec.toolchain.as_dict()
            _log.debug("Adding toolchain %s as dependency for app %s." % (dep, name))
            easyconfig['dependencies'].append(dep)

        del ec

        # this is used by the parallel builder
        easyconfig['unresolved_deps'] = copy.deepcopy(easyconfig['dependencies'])

        easyconfigs.append(easyconfig)

    return easyconfigs


def skip_available(easyconfigs, testing=False):
    """Skip building easyconfigs for which a module is already available."""
    m = modules_tool()
    easyconfigs, check_easyconfigs = [], easyconfigs
    for ec in check_easyconfigs:
        module = ec['module']
        if m.exists(module):
            msg = "%s is already installed (module found), skipping" % module
            print_msg(msg, log=_log, silent=testing)
            _log.info(msg)
        else:
            _log.debug("%s is not installed yet, so retaining it" % module)
            easyconfigs.append(ec)
    return easyconfigs


def resolve_dependencies(unprocessed, robot, force=False):
    """
    Work through the list of easyconfigs to determine an optimal order
    enabling force results in retaining all dependencies and skipping validation of easyconfigs
    """

    if force:
        # assume that no modules are available when forced
        available_modules = []
        _log.info("Forcing all dependencies to be retained.")
    else:
        # Get a list of all available modules (format: [(name, installversion), ...])
        available_modules = modules_tool().available()

        if len(available_modules) == 0:
            _log.warning("No installed modules. Your MODULEPATH is probably incomplete: %s" % os.getenv('MODULEPATH'))

    ordered_ecs = []
    # All available modules can be used for resolving dependencies except
    # those that will be installed
    being_installed = [p['module'] for p in unprocessed]
    processed = [m for m in available_modules if not m in being_installed]

    _log.debug('unprocessed before resolving deps: %s' % unprocessed)

    # as long as there is progress in processing the modules, keep on trying
    loopcnt = 0
    maxloopcnt = 10000
    robot_add_dep = True
    while robot_add_dep:

        robot_add_dep = False

        # make sure this stops, we really don't want to get stuck in an infinite loop
        loopcnt += 1
        if loopcnt > maxloopcnt:
            msg = "Maximum loop cnt %s reached, so quitting." % maxloopcnt
            _log.error(msg)

        # first try resolving dependencies without using external dependencies
        last_processed_count = -1
        while len(processed) > last_processed_count:
            last_processed_count = len(processed)
            ordered_ecs.extend(find_resolved_modules(unprocessed, processed))

        # robot: look for an existing dependency, add one
        if robot and len(unprocessed) > 0:

            being_installed = [det_full_module_name(p['ec'], eb_ns=True) for p in unprocessed]

            for entry in unprocessed:
                # do not choose an entry that is being installed in the current run
                # if they depend, you probably want to rebuild them using the new dependency
                deps = entry['dependencies']
                candidates = [d for d in deps if not det_full_module_name(d, eb_ns=True) in being_installed]
                if len(candidates) > 0:
                    cand_dep = candidates[0]
                    # find easyconfig, might not find any
                    _log.debug("Looking for easyconfig for %s" % str(cand_dep))
                    path = robot_find_easyconfig(robot, cand_dep['name'], det_full_ec_version(cand_dep))

                else:
                    path = None
                    mod_name = det_full_module_name(entry['ec'], eb_ns=True)
                    _log.debug("No more candidate dependencies to resolve for %s" % mod_name)

                if path is not None:
                    cand_dep = candidates[0]
                    _log.info("Robot: resolving dependency %s with %s" % (cand_dep, path))

                    processed_ecs = process_easyconfig(path, validate=(not force))

                    # ensure that selected easyconfig provides required dependency
                    mods = [det_full_module_name(spec['ec']) for spec in processed_ecs]
                    dep_mod_name = det_full_module_name(cand_dep)
                    if not dep_mod_name in mods:
                        _log.error("easyconfig file %s does not contain module %s (mods: %s)" % (path, dep_mod_name, mods))

                    unprocessed.extend(processed_ecs)
                    robot_add_dep = True
                    break

    _log.debug('unprocessed after resolving deps: %s' % unprocessed)

    # there are dependencies that cannot be resolved
    if len(unprocessed) > 0:
        _log.debug("List of unresolved dependencies: %s" % unprocessed)
        missing_dependencies = []
        for ec in unprocessed:
            for dep in ec['dependencies']:
                missing_dependencies.append('%s for %s' % (det_full_module_name(dep, eb_ns=True), dep))

        msg = "Dependencies not met. Cannot resolve %s" % missing_dependencies
        _log.error(msg)

    _log.info("Dependency resolution complete, building as follows:\n%s" % ordered_ecs)
    return ordered_ecs


def find_resolved_modules(unprocessed, processed):
    """
    Find easyconfigs in unprocessed which can be fully resolved using easyconfigs in processed
    """
    ordered_ecs = []

    for ec in unprocessed:
        ec['dependencies'] = [d for d in ec['dependencies'] if not det_full_module_name(d) in processed]

        if len(ec['dependencies']) == 0:
            _log.debug("Adding easyconfig %s to final list" % ec['spec'])
            ordered_ecs.append(ec)
            processed.append(ec['module'])

    unprocessed[:] = [m for m in unprocessed if len(m['dependencies']) > 0]

    return ordered_ecs


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
    (generated, fn) = easyconfig.tools.obtain_ec_for(specs, paths, None)
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
                  "use the --try-X options ") % specs, log=_log, exit_on_error=exit_on_error)


def robot_find_easyconfig(path, name, version):
    """
    Find an easyconfig for module in path
    """
    # candidate easyconfig paths
    easyconfigsPaths = easyconfig.tools.create_paths(path, name, version)
    for easyconfigPath in easyconfigsPaths:
        _log.debug("Checking easyconfig path %s" % easyconfigPath)
        if os.path.isfile(easyconfigPath):
            _log.debug("Found easyconfig file for name %s, version %s at %s" % (name, version, easyconfigPath))
            return os.path.abspath(easyconfigPath)

    return None


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
                              ('core_count', systemtools.get_avail_core_count()),
                              ('timestamp', int(time.time())),
                              ('build_time', buildtime),
                              ('install_size', app.det_installsize()),
                             ])

    return buildstats


def build_and_install_software(module, options, orig_environ, exitOnFailure=True, silent=False):
    """
    Build the software
    """
    spec = module['spec']

    print_msg("processing EasyBuild easyconfig %s" % spec, log=_log, silent=silent)

    # restore original environment
    _log.info("Resetting environment")
    filetools.errorsFoundInLog = 0
    modify_env(os.environ, orig_environ)

    cwd = os.getcwd()

    # load easyblock
    easyblock = options.easyblock
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
        app = app_class(spec, debug=options.debug, robot_path=options.robot, silent=silent)
        _log.info("Obtained application instance of for %s (easyblock: %s)" % (name, easyblock))
    except EasyBuildError, err:
        print_error("Failed to get application instance for %s (easyblock: %s): %s" % (name, easyblock, err.msg), silent=silent)

    # application settings
    if options.stop:
        _log.debug("Stop set to %s" % options.stop)
        app.cfg['stop'] = options.stop

    if options.skip:
        _log.debug("Skip set to %s" % options.skip)
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
        _log.exception(errormsg)
        result = False

    ended = "ended"

    # successful build
    if result:

        # collect build stats
        _log.info("Collecting build stats...")

        currentbuildstats = app.cfg['buildstats']
        buildstats = get_build_stats(app, starttime)
        _log.debug("Build stats: %s" % buildstats)

        if app.cfg['stop']:
            ended = "STOPPED"
            new_log_dir = os.path.join(app.builddir, config.log_path())
        else:
            new_log_dir = os.path.join(app.installdir, config.log_path())

            try:
                # upload spec to central repository
                repo = init_repository(get_repository(), get_repositorypath())
                if 'originalSpec' in module:
                    block = det_full_ec_version(app.cfg) + ".block"
                    repo.add_easyconfig(module['originalSpec'], app.name, block, buildstats, currentbuildstats)
                repo.add_easyconfig(spec, app.name, det_full_ec_version(app.cfg), buildstats, currentbuildstats)
                repo.commit("Built %s" % det_full_module_name(app.cfg))
                del repo
            except EasyBuildError, err:
                _log.warn("Unable to commit easyconfig to repository: %s", err)

        exitCode = 0
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
        exitCode = 1
        summary = "FAILED"

        buildDir = ''
        if app.builddir:
            buildDir = " (build directory: %s)" % (app.builddir)
        succ = "unsuccessfully%s:\n%s" % (buildDir, errormsg)

        # cleanup logs
        app.close_log()
        application_log = app.logfile

    print_msg("%s: Installation %s %s" % (summary, ended, succ), log=_log, silent=silent)

    # check for errors
    if exitCode > 0 or filetools.errorsFoundInLog > 0:
        print_msg("\nWARNING: Build exited with exit code %d. %d possible error(s) were detected in the " \
                  "build logs, please verify the build.\n" % (exitCode, filetools.errorsFoundInLog),
                  _log, silent=silent)

    if app.postmsg:
        print_msg("\nWARNING: %s\n" % app.postmsg, _log, silent=silent)

    print_msg("Results of the build can be found in the log file %s" % application_log, _log, silent=silent)

    del app
    os.chdir(cwd)

    if exitCode > 0:
        # don't exit on failure in test suite
        if exitOnFailure:
            sys.exit(exitCode)
        else:
            return (False, application_log)
    else:
        return (True, application_log)


def dep_graph(fn, specs, silent=False):
    """
    Create a dependency graph for the given easyconfigs.
    """

    # check whether module names are unique
    # if so, we can omit versions in the graph
    names = set()
    for spec in specs:
        names.add(spec['ec']['name'])
    omit_versions = len(names) == len(specs)

    def mk_node_name(spec):
        if omit_versions:
            return spec['name']
        else:
            return det_full_module_name(spec)

    # enhance list of specs
    for spec in specs:
        spec['module'] = mk_node_name(spec['ec'])
        spec['unresolved_deps'] = [mk_node_name(s) for s in spec['unresolved_deps']]

    # build directed graph
    dgr = digraph()
    dgr.add_nodes([spec['module'] for spec in specs])
    for spec in specs:
        for dep in spec['unresolved_deps']:
            dgr.add_edge((spec['module'], dep))

    # write to file
    dottxt = dot.write(dgr)
    if fn.endswith(".dot"):
        # create .dot file
        write_file(fn, dottxt)
    else:
        # try and render graph in specified file format
        gvv = gv.readstring(dottxt)
        gv.layout(gvv, 'dot')
        gv.render(gvv, fn.split('.')[-1], fn)

    if not silent:
        print "Wrote dependency graph for %d easyconfigs to %s" % (len(specs), fn)


def search_file(path, query, silent=False):
    """
    Search for a particular file (only prints)
    """
    print_msg("Searching for %s in %s " % (query.lower(), path), log=_log, silent=silent)

    query = query.lower()
    for (dirpath, dirnames, filenames) in os.walk(path, topdown=True):
        for filename in filenames:
            filename = os.path.join(dirpath, filename)
            if filename.lower().find(query) != -1:
                print_msg("- %s" % filename, log=_log, silent=silent)

        # do not consider (certain) hidden directories
        # note: we still need to consider e.g., .local !
        # replace list elements using [:], so os.walk doesn't process deleted directories
        # see http://stackoverflow.com/questions/13454164/os-walk-without-hidden-folders
        # TODO (see #623): add a configuration option with subdirs to ignore (also taken into account for --robot)
        dirnames[:] = [d for d in dirnames if not d in ['.git', '.svn']]


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
            el = create_failure(obj.mod_name, fase, error)
        except AttributeError:
            el = create_failure(obj, fase, error)

        root.firstChild.appendChild(el)

    for (obj, stats) in succes:
        el = create_success(obj.mod_name, stats)
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
                    _log.info("Running %s step" % step)
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
                buildstats = get_build_stats(app, start_time)
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
        _log.info("aggregated xml files inside %s, output written to: %s" % (options.aggregate_regtest, output_file))
        sys.exit(0)

    # create base directory, which is used to place
    # all log files and the test output as xml
    basename = "easybuild-test-%s" % datetime.now().strftime("%Y%m%d%H%M%S")
    var = config.oldstyle_environment_variables['test_output_path']
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
        _log.error("No easyconfig paths specified.")

    test_results = []

    # process all the found easyconfig files
    easyconfigs = []
    for ecfile in ecfiles:
        try:
            easyconfigs.extend(process_easyconfig(ecfile, None))
        except EasyBuildError, err:
            test_results.append((ecfile, 'parsing_easyconfigs', 'easyconfig file error: %s' % err, _log))

    # skip easyconfigs for which a module is already available, unless forced
    if not options.force:
        _log.debug("Skipping easyconfigs from %s that already have a module available..." % easyconfigs)
        easyconfigs = skip_available(easyconfigs)
        _log.debug("Retained easyconfigs after skipping: %s" % easyconfigs)

    if options.sequential:
        return build_easyconfigs(easyconfigs, output_dir, test_results, options)
    else:
        resolved = resolve_dependencies(easyconfigs, options.robot)

        cmd = "eb %(spec)s --regtest --sequential -ld"
        command = "unset TMPDIR && cd %s && %s; " % (cur_dir, cmd)
        # retry twice in case of failure, to avoid fluke errors
        command += "if [ $? -ne 0 ]; then %(cmd)s --force && %(cmd)s --force; fi" % {'cmd': cmd}

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

        _log.info("Job ids of leaf nodes in dep. graph: %s" % ','.join(leaf_nodes))

        _log.info("Submitted regression test as jobs, results in %s" % output_dir)

        return True  # success

def print_dry_run(easyconfigs, robot=None):
    if robot is None:
        print_msg("Dry run: printing build status of easyconfigs")
        all_specs = easyconfigs
    else: 
        print_msg("Dry run: printing build status of easyconfigs and dependencies")
        all_specs = resolve_dependencies(easyconfigs, robot, True)
    unbuilt_specs = skip_available(all_specs, True)
    dry_run_fmt = "%3s %s (module: %s)"
    for spec in all_specs:
        if spec in unbuilt_specs:
            ans = '[ ]'
        else:
            ans = '[x]'
        mod = det_full_module_name(spec['ec'])
        print dry_run_fmt % (ans, spec['spec'], mod)
    


if __name__ == "__main__":
    try:
        main()
    except EasyBuildError, e:
        sys.stderr.write('ERROR: %s\n' % e.msg)
        sys.exit(1)
