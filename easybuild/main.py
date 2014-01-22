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
@author: Ward Poelmans (Ghent University)
@author: Fotis Georgatos (University of Luxembourg)
"""

import copy
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from vsc import fancylogger
from vsc.utils.missing import any

# IMPORTANT this has to be the first easybuild import as it customises the logging
#  expect missing log output when this not the case!
from easybuild.tools.build_log import EasyBuildError, get_build_stats, print_msg, print_error, print_warning

import easybuild.framework.easyconfig as easyconfig
import easybuild.tools.config as config
import easybuild.tools.filetools as filetools
import easybuild.tools.options as eboptions
import easybuild.tools.parallelbuild as parbuild
from easybuild.framework.easyblock import EasyBlock, build_and_install_software
from easybuild.framework.easyconfig.tools import dep_graph, get_paths_for, obtain_path, process_easyconfig
from easybuild.framework.easyconfig.tools import resolve_dependencies, skip_available, tweak
from easybuild.tools import systemtools
from easybuild.tools.config import get_repository, module_classes, get_log_filename, get_repositorypath, set_tmpdir
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import aggregate_xml_in_dirs, cleanup, det_common_path_prefix, find_easyconfigs
from easybuild.tools.filetools import read_file, search_file, write_file, write_to_xml
from easybuild.tools.module_generator import det_full_module_name
from easybuild.tools.modules import modules_tool
from easybuild.tools.options import process_software_build_specs
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
        sys.stderr.write("ERROR: You seem to be running EasyBuild with root privileges.\n"
                         "That's not wise, so let's end this here.\n"
                         "Exiting.\n")
        sys.exit(1)

    # steer behavior when testing main
    testing = testing_data[0] is not None
    args, logfile, do_build = testing_data

    # initialise options
    eb_go = eboptions.parse_options(args=args)
    options = eb_go.options
    orig_paths = eb_go.args

    # set temporary directory to use
    eb_tmpdir = set_tmpdir(options.tmpdir)

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

    _log.info("Using %s as temporary directory" % eb_tmpdir)

    # set strictness of filetools module
    if options.strict:
        filetools.strictness = options.strict

    if not options.robot is None:
        if options.robot:
            _log.info("Using robot path(s): %s" % options.robot)
        else:
            _log.error("No robot paths specified, and unable to determine easybuild-easyconfigs install path.")

    # determine easybuild-easyconfigs package install path
    easyconfigs_paths = get_paths_for("easyconfigs", robot_path=options.robot)
    # keep track of paths for install easyconfigs, so we can obtain find specified easyconfigs
    easyconfigs_pkg_full_paths = easyconfigs_paths[:]
    if not easyconfigs_paths:
        _log.warning("Failed to determine install path for easybuild-easyconfigs package.")

    # specified robot paths are preferred over installed easyconfig files
    if options.robot:
        easyconfigs_paths = options.robot + easyconfigs_paths
        options.robot.extend(easyconfigs_paths)
        _log.info("Extended list of robot paths with paths for installed easyconfigs: %s" % options.robot)

    # initialise the easybuild configuration
    config.init(options, eb_go.get_options_by_section('config'))

    # building a dependency graph implies force, so that all dependencies are retained
    # and also skips validation of easyconfigs (e.g. checking os dependencies)
    if options.dep_graph:
        _log.info("Enabling force to generate dependency graph.")
        options.force = True

    build_options = {
        'aggregate_regtest': options.aggregate_regtest,
        'check_osdeps': not options.ignore_osdeps,
        'debug': options.debug,
        'dry_run': options.dry_run,
        'easyblock': options.easyblock,
        'force': options.force,
        'ignore_dirs': options.ignore_dirs,
        'only_blocks': options.only_blocks,
        'regtest_online': options.regtest_online,
        'regtest_output_dir': options.regtest_output_dir,
        'robot_path': options.robot,
        'sequential': options.sequential,
        'silent': testing,
        'skip': options.skip,
        'skip_test_cases': options.skip_test_cases,
        'stop': options.stop,
        'valid_module_classes': module_classes(),
        'valid_stops': [x[0] for x in EasyBlock.get_steps()],
        'validate': not options.force,
    }

    # search for easyconfigs
    if options.search or options.search_short:
        search_path = [os.getcwd()]
        if easyconfigs_paths:
            search_path = easyconfigs_paths
        query = options.search or options.search_short
        search_file(search_path, query, build_options=build_options, short=not options.search)

    # process software build specifications (if any), i.e.
    # software name/version, toolchain name/version, extra patches, ...
    (try_to_generate, build_specs) = process_software_build_specs(options)

    paths = []
    if len(orig_paths) == 0:
        if 'name' in build_specs:
            paths = [obtain_path(build_specs, easyconfigs_paths, try_to_generate=try_to_generate,
                                 exit_on_error=not testing)]
        elif not any([options.aggregate_regtest, options.search, options.search_short, options.regtest]):
            print_error(("Please provide one or multiple easyconfig files, or use software build "
                         "options to make EasyBuild search for easyconfigs"),
                        log=_log, opt_parser=eb_go.parser, exit_on_error=not testing)
    else:
        # look for easyconfigs with relative paths in easybuild-easyconfigs package,
        # unless they were found at the given relative paths
        if easyconfigs_pkg_full_paths:
            # determine which easyconfigs files need to be found, if any
            ecs_to_find = []
            for idx, orig_path in enumerate(orig_paths):
                if orig_path == os.path.basename(orig_path) and not os.path.exists(orig_path):
                    ecs_to_find.append((idx, orig_path))
            _log.debug("List of easyconfig files to find: %s" % ecs_to_find)

            # find missing easyconfigs by walking paths with installed easyconfig files
            for path in easyconfigs_pkg_full_paths:
                _log.debug("Looking for missing easyconfig files (%d left) in %s..." % (len(ecs_to_find), path))
                for (subpath, dirnames, filenames) in os.walk(path, topdown=True):
                    for idx, orig_path in ecs_to_find[:]:
                        if orig_path in filenames:
                            full_path = os.path.join(subpath, orig_path)
                            _log.info("Found %s in %s: %s" % (orig_path, path, full_path))
                            orig_paths[idx] = full_path
                            # if file was found, stop looking for it (first hit wins)
                            ecs_to_find.remove((idx, orig_path))

                    # stop os.walk insanity as soon as we have all we need (os.walk loop)
                    if len(ecs_to_find) == 0:
                        break

                    # ignore subdirs specified to be ignored by replacing items in dirnames list used by os.walk
                    dirnames[:] = [d for d in dirnames if not d in options.ignore_dirs]

                # stop os.walk insanity as soon as we have all we need (paths loop)
                if len(ecs_to_find) == 0:
                    break

        # indicate that specified paths do not contain generated easyconfig files
        paths = [(path, False) for path in orig_paths]

    _log.debug("Paths: %s" % paths)

    # run regtest
    if options.regtest or options.aggregate_regtest:
        _log.info("Running regression test")
        if paths:
            ec_paths = [path[0] for path in paths]
        else:  # fallback: easybuild-easyconfigs install path
            ec_paths = easyconfigs_pkg_full_paths
        regtest_ok = regtest(options, ec_paths, build_options=build_options, build_specs=build_specs)

        if not regtest_ok:
            _log.info("Regression test failed (partially)!")
            sys.exit(31)  # exit -> 3x1t -> 31

    # read easyconfig files
    easyconfigs = []
    for (path, generated) in paths:
        path = os.path.abspath(path)
        if not (os.path.exists(path)):
            print_error("Can't find path %s" % path)

        try:
            files = find_easyconfigs(path, ignore_dirs=options.ignore_dirs)
            for f in files:
                if not generated and try_to_generate and build_specs:
                    ec_file = tweak(f, None, build_specs)
                else:
                    ec_file = f
                ecs = process_easyconfig(ec_file, build_options=build_options, build_specs=build_specs)
                easyconfigs.extend(ecs)
        except IOError, err:
            _log.error("Processing easyconfigs in path %s failed: %s" % (path, err))

    # before building starts, take snapshot of environment (watch out -t option!)
    orig_environ = copy.deepcopy(os.environ)
    os.chdir(os.environ['PWD'])

    # dry_run: print all easyconfigs and dependencies, and whether they are already built
    if options.dry_run or options.dry_run_short:
        print_dry_run(easyconfigs, short=not options.dry_run, build_options=build_options, build_specs=build_specs)

    if any([options.dry_run, options.dry_run_short, options.regtest, options.search, options.search_short]):
        cleanup(logfile, eb_tmpdir, testing)
        sys.exit(0)

    # skip modules that are already installed unless forced
    if not options.force:
        easyconfigs = skip_available(easyconfigs, testing=testing)

    # determine an order that will allow all specs in the set to build
    if len(easyconfigs) > 0:
        print_msg("resolving dependencies ...", log=_log, silent=testing)
        ordered_ecs = resolve_dependencies(easyconfigs, build_options=build_options, build_specs=build_specs)
    else:
        print_msg("No easyconfigs left to be built.", log=_log, silent=testing)
        ordered_ecs = []

    # create dependency graph and exit
    if options.dep_graph:
        _log.info("Creating dependency graph %s" % options.dep_graph)
        dep_graph(options.dep_graph, ordered_ecs)
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
            jobs = parbuild.build_easyconfigs_in_parallel(command, ordered_ecs, build_options=build_options,
                                                          build_specs=build_specs)
            txt = ["List of submitted jobs:"]
            txt.extend(["%s (%s): %s" % (job.name, job.module, job.jobid) for job in jobs])
            txt.append("(%d jobs submitted)" % len(jobs))

            msg = "\n".join(txt)
            _log.info("Submitted parallel build jobs, exiting now (%s)." % msg)
            print msg

            cleanup(logfile, eb_tmpdir, testing)

            sys.exit(0)

    # build software, will exit when errors occurs (except when regtesting)
    correct_built_cnt = 0
    all_built_cnt = 0
    if not testing or (testing and do_build):
        for ec in ordered_ecs:
            (success, _) = build_and_install_software(ec, orig_environ, build_options=build_options,
                                                      build_specs=build_specs)
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
    cleanup(logfile, eb_tmpdir, testing)


def build_easyconfigs(easyconfigs, output_dir, test_results, build_options=None):
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
                    return parbuild.get_easyblock_instance(obj, build_options=build_options)
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

    cpu_model = systemtools.get_cpu_model()
    core_count = systemtools.get_avail_core_count()
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
                buildstats = get_build_stats(app, start_time, cpu_model, core_count)
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


def regtest(easyconfig_paths, build_options=None, build_specs=None):
    """
    Run regression test, using easyconfigs available in given path
    @param easyconfig_paths: path of easyconfigs to run regtest on
    @param build_options: dictionary specifying build options (e.g. robot_path, check_osdeps, ...)
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    """

    cur_dir = os.getcwd()

    aggregate_regtest = build_options.get('aggregate_regtest', None)
    if aggregate_regtest is not None:
        output_file = os.path.join(aggregate_regtest, "%s-aggregate.xml" % os.path.basename(aggregate_regtest))
        aggregate_xml_in_dirs(aggregate_regtest, output_file)
        _log.info("aggregated xml files inside %s, output written to: %s" % (aggregate_regtest, output_file))
        sys.exit(0)

    # create base directory, which is used to place
    # all log files and the test output as xml
    basename = "easybuild-test-%s" % datetime.now().strftime("%Y%m%d%H%M%S")
    var = config.oldstyle_environment_variables['test_output_path']

    regtest_output_dir = build_options.get('regtest_output_dir', None)
    if regtest_output_dir is not None:
        output_dir = regtest_output_dir
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
            ecfiles += find_easyconfigs(path, ignore_dirs=build_options.get('ignore_dirs', []))
    else:
        _log.error("No easyconfig paths specified.")

    test_results = []

    # process all the found easyconfig files
    easyconfigs = []
    for ecfile in ecfiles:
        try:
            easyconfigs.extend(process_easyconfig(ecfile, build_options=build_options, build_specs=build_specs))
        except EasyBuildError, err:
            test_results.append((ecfile, 'parsing_easyconfigs', 'easyconfig file error: %s' % err, _log))

    # skip easyconfigs for which a module is already available, unless forced
    if not build_options.get('force', False):
        _log.debug("Skipping easyconfigs from %s that already have a module available..." % easyconfigs)
        easyconfigs = skip_available(easyconfigs)
        _log.debug("Retained easyconfigs after skipping: %s" % easyconfigs)

    if build_options.get('sequential', False):
        return build_easyconfigs(easyconfigs, output_dir, test_results, build_options=build_options)
    else:
        resolved = resolve_dependencies(easyconfigs, build_options=build_options, build_specs=build_specs)

        cmd = "eb %(spec)s --regtest --sequential -ld"
        command = "unset TMPDIR && cd %s && %s; " % (cur_dir, cmd)
        # retry twice in case of failure, to avoid fluke errors
        command += "if [ $? -ne 0 ]; then %(cmd)s --force && %(cmd)s --force; fi" % {'cmd': cmd}

        jobs = parbuild.build_easyconfigs_in_parallel(command, resolved, output_dir=output_dir,
                                                      build_options=build_options, build_specs=build_specs)

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


def print_dry_run(easyconfigs, short=False, build_options=None, build_specs=None):
    """
    Print dry run information
    @param easyconfigs: list of easyconfig files
    @param short: print short output (use a variable for the common prefix)
    @param build_options: dictionary specifying build options (e.g. robot_path, check_osdeps, ...)
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    """
    lines = []
    if build_options.get('robot_path', None) is None:
        lines.append("Dry run: printing build status of easyconfigs")
        all_specs = easyconfigs
    else:
        lines.append("Dry run: printing build status of easyconfigs and dependencies")
        build_options = copy.deepcopy(build_options)
        build_options.update({
            'force': True,
            'check_osdeps': False,
        })
        all_specs = resolve_dependencies(easyconfigs, build_options=build_options, build_specs=build_specs)

    unbuilt_specs = skip_available(all_specs, testing=True)
    dry_run_fmt = " * [%1s] %s (module: %s)"  # markdown compatible (list of items with checkboxes in front)

    var_name = 'CFGS'
    common_prefix = det_common_path_prefix([spec['spec'] for spec in all_specs])
    # only allow short if common prefix is long enough
    short = short and common_prefix is not None and len(common_prefix) > len(var_name) * 2
    for spec in all_specs:
        if spec in unbuilt_specs:
            ans = ' '
        else:
            ans = 'x'
        mod = det_full_module_name(spec['ec'])

        if short:
            item = os.path.join('$%s' % var_name, spec['spec'][len(common_prefix) + 1:])
        else:
            item = spec['spec']
        lines.append(dry_run_fmt % (ans, item, mod))

    if short:
        # insert after 'Dry run:' message
        lines.insert(1, "%s=%s" % (var_name, common_prefix))
    silent = build_options.get('silent', False)
    print_msg('\n'.join(lines), log=_log, silent=silent, prefix=False)


if __name__ == "__main__":
    try:
        main()
    except EasyBuildError, e:
        sys.stderr.write('ERROR: %s\n' % e.msg)
        sys.exit(1)
