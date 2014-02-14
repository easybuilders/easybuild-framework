#!/usr/bin/env python
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
import os
import subprocess
import sys
import tempfile
from vsc import fancylogger
from vsc.utils.missing import any

# IMPORTANT this has to be the first easybuild import as it customises the logging
#  expect missing log output when this not the case!
from easybuild.tools.build_log import EasyBuildError, print_msg, print_error

import easybuild.tools.config as config
import easybuild.tools.options as eboptions
from easybuild.framework.easyblock import EasyBlock, build_and_install_software
from easybuild.framework.easyconfig.tools import dep_graph, get_paths_for, obtain_path, print_dry_run
from easybuild.framework.easyconfig.tools import process_easyconfig, resolve_dependencies, skip_available, tweak
from easybuild.tools.config import get_repository, module_classes, get_repositorypath, set_tmpdir
from easybuild.tools.filetools import cleanup, find_easyconfigs, search_file
from easybuild.tools.options import process_software_build_specs
from easybuild.tools.parallelbuild import build_easyconfigs_in_parallel, regtest
from easybuild.tools.repository import init_repository
from easybuild.tools.version import this_is_easybuild  # from a single location


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

    # how was EB called?
    eb_command_line = eb_go.generate_cmd_line() + eb_go.args
    _log.info("Command line: %s" % (" ".join(eb_command_line)))

    _log.info("Using %s as temporary directory" % eb_tmpdir)

    if not options.robot is None:
        if options.robot:
            _log.info("Using robot path(s): %s" % options.robot)
        else:
            _log.error("No robot paths specified, and unable to determine easybuild-easyconfigs install path.")

    # do not pass options.robot, it's not a list instance (and it shouldn't be modified)
    robot_path = None
    if options.robot:
        robot_path = list(options.robot)

    # determine easybuild-easyconfigs package install path
    easyconfigs_paths = get_paths_for("easyconfigs", robot_path=robot_path)
    # keep track of paths for install easyconfigs, so we can obtain find specified easyconfigs
    easyconfigs_pkg_full_paths = easyconfigs_paths[:]
    if not easyconfigs_paths:
        _log.warning("Failed to determine install path for easybuild-easyconfigs package.")

    # specified robot paths are preferred over installed easyconfig files
    if robot_path:
        robot_path.extend(easyconfigs_paths)
        easyconfigs_paths = robot_path[:]
        _log.info("Extended list of robot paths with paths for installed easyconfigs: %s" % robot_path)

    # initialise the easybuild configuration
    config.init(options, eb_go.get_options_by_section('config'))

    # building a dependency graph implies force, so that all dependencies are retained
    # and also skips validation of easyconfigs (e.g. checking os dependencies)
    retain_all_deps = False
    if options.dep_graph:
        _log.info("Enabling force to generate dependency graph.")
        options.force = True
        retain_all_deps = True

    build_options = {
        'aggregate_regtest': options.aggregate_regtest,
        'check_osdeps': not options.ignore_osdeps,
        'command_line': eb_command_line,
        'debug': options.debug,
        'dry_run': options.dry_run,
        'easyblock': options.easyblock,
        'experimental': options.experimental,
        'force': options.force,
        'ignore_dirs': options.ignore_dirs,
        'modules_footer': options.modules_footer,
        'only_blocks': options.only_blocks,
        'recursive_mod_unload': options.recursive_module_unload,
        'regtest_online': options.regtest_online,
        'regtest_output_dir': options.regtest_output_dir,
        'retain_all_deps': retain_all_deps,
        'robot_path': robot_path,
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
        regtest_ok = regtest(ec_paths, build_options=build_options, build_specs=build_specs)

        if not regtest_ok:
            _log.info("Regression test failed (partially)!")
            sys.exit(31)  # exit -> 3x1t -> 31

    # read easyconfig files
    easyconfigs = []
    for (path, generated) in paths:
        path = os.path.abspath(path)
        if not os.path.exists(path):
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
            jobs = build_easyconfigs_in_parallel(command, ordered_ecs, build_options=build_options,
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


if __name__ == "__main__":
    try:
        main()
    except EasyBuildError, e:
        sys.stderr.write('ERROR: %s\n' % e.msg)
        sys.exit(1)
