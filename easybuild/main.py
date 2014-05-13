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
from time import gmtime, strftime
from vsc import fancylogger
from vsc.utils.missing import any

# IMPORTANT this has to be the first easybuild import as it customises the logging
#  expect missing log output when this not the case!
from easybuild.tools.build_log import EasyBuildError, print_msg, print_error

import easybuild.tools.config as config
import easybuild.tools.options as eboptions
from easybuild.framework.easyblock import EasyBlock, build_and_install_one
from easybuild.framework.easyconfig.easyconfig import process_easyconfig
from easybuild.framework.easyconfig.tools import dep_graph, get_paths_for, print_dry_run
from easybuild.framework.easyconfig.tools import resolve_dependencies, skip_available
from easybuild.framework.easyconfig.tweak import obtain_path, tweak
from easybuild.tools.config import get_repository, module_classes, get_repositorypath, set_tmpdir
from easybuild.tools.filetools import cleanup, find_easyconfigs, search_file, write_file
from easybuild.tools.github import fetch_easyconfigs_from_pr, fetch_github_token
from easybuild.tools.options import process_software_build_specs
from easybuild.tools.parallelbuild import build_easyconfigs_in_parallel
from easybuild.tools.repository.repository import init_repository
from easybuild.tools.testing import create_test_report, post_easyconfigs_pr_test_report
from easybuild.tools.testing import regtest, session_module_list, session_state
from easybuild.tools.version import this_is_easybuild  # from a single location


_log = None


def build_and_install_software(ecs, init_session_state, exit_on_failure=True):
    """Build and install software for all provided parsed easyconfig files."""
    orig_environ = init_session_state['environment']
    # don't modify in-place
    ecs = copy.deepcopy(ecs)

    for ec in ecs:
        try:
            (ec['success'], app_log, err) = build_and_install_one(ec, orig_environ)
            ec['log_file'] = app_log
            if not ec['success']:
                ec['err'] = EasyBuildError(err)
        except Exception, err:
            # purposely catch all exceptions
            ec['success'] = False
            ec['err'] = err

        # keep track of success/total count
        if ec['success']:
            test_msg = "Successfully built %s" % ec['spec']
        else:
            test_msg = "Build of %s failed" % ec['spec']
            if 'err' in ec:
                test_msg += " (err: %s)" % ec['err']

        # dump test report next to log file
        test_report_txt = create_test_report(test_msg, [ec], init_session_state)
        if 'log_file' in ec:
            test_report_fp = "%s_test_report.md" % '.'.join(ec['log_file'].split('.')[:-1])
            write_file(test_report_fp, test_report_txt)

        if not ec['success'] and exit_on_failure:
            _log.error(test_msg)

    return ecs


def main(testing_data=(None, None, None)):
    """
    Main function:
    @arg options: a tuple: (options, paths, logger, logfile, hn) as defined in parse_options
    This function will:
    - read easyconfig
    - build software
    """

    # purposely session state very early, to avoid modules loaded by EasyBuild meddling in
    init_session_state = session_state()

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
    eb_config = eb_go.generate_cmd_line(add_default=True)
    init_session_state.update({'easybuild_configuration': eb_config})

    # set umask (as early as possible)
    if options.umask is not None:
        new_umask = int(options.umask, 8)
        old_umask = os.umask(new_umask)

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

    if options.umask is not None:
        _log.info("umask set to '%s' (used to be '%s')" % (oct(new_umask), oct(old_umask)))

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

    # make sure both GitHub user name is provided and that GitHub token can be obtained when testing easyconfig PRs
    github_token = None
    pr_nr = options.test_easyconfigs_pr or options.from_pr
    if pr_nr:
        # a GitHub token is only strictly required when testing a PR (to post gists/comments)
        github_token = fetch_github_token(options.github_user, require_token=options.test_easyconfigs_pr is not None)

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

    config.init_build_options({
        'aggregate_regtest': options.aggregate_regtest,
        'allow_modules_tool_mismatch': options.allow_modules_tool_mismatch,
        'check_osdeps': not options.ignore_osdeps,
        'command_line': eb_command_line,
        'debug': options.debug,
        'dry_run': options.dry_run,
        'easyblock': options.easyblock,
        'experimental': options.experimental,
        'force': options.force,
        'github_user': options.github_user,
        'group': options.group,
        'ignore_dirs': options.ignore_dirs,
        'modules_footer': options.modules_footer,
        'only_blocks': options.only_blocks,
        'recursive_mod_unload': options.recursive_module_unload,
        'regtest_output_dir': options.regtest_output_dir,
        'retain_all_deps': retain_all_deps,
        'robot_path': robot_path,
        'sequential': options.sequential,
        'silent': testing,
        'set_gid_bit': options.set_gid_bit,
        'skip': options.skip,
        'skip_test_cases': options.skip_test_cases,
        'sticky_bit': options.sticky_bit,
        'stop': options.stop,
        'umask': options.umask,
        'valid_module_classes': module_classes(),
        'valid_stops': [x[0] for x in EasyBlock.get_steps()],
        'validate': not options.force,
    })

    # obtain list of loaded modules, build options must be initialized first
    modlist = session_module_list()
    init_session_state.update({'module_list': modlist})
    _log.debug("Initial session state: %s" % init_session_state)

    # search for easyconfigs
    if options.search or options.search_short:
        search_path = [os.getcwd()]
        if easyconfigs_paths:
            search_path = easyconfigs_paths
        query = options.search or options.search_short
        ignore_dirs = config.build_option('ignore_dirs')
        silent = config.build_option('silent')
        search_file(search_path, query, short=not options.search, ignore_dirs=ignore_dirs, silent=silent)

    # process software build specifications (if any), i.e.
    # software name/version, toolchain name/version, extra patches, ...
    (try_to_generate, build_specs) = process_software_build_specs(options)

    paths = []
    if len(orig_paths) == 0:
        if pr_nr is not None:
            pr_path = os.path.join(eb_tmpdir, "files_pr%s" % pr_nr)
            pr_files = fetch_easyconfigs_from_pr(pr_nr, path=pr_path, github_user=options.github_user,
                                                 github_token=github_token)
            paths = [(path, False) for path in pr_files if path.endswith('.eb')]
        elif 'name' in build_specs:
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
        regtest_ok = regtest(ec_paths)

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
                ecs = process_easyconfig(ec_file, build_specs=build_specs)
                easyconfigs.extend(ecs)
        except IOError, err:
            _log.error("Processing easyconfigs in path %s failed: %s" % (path, err))

    # before building starts, take snapshot of environment (watch out -t option!)
    os.chdir(os.environ['PWD'])

    # dry_run: print all easyconfigs and dependencies, and whether they are already built
    if options.dry_run or options.dry_run_short:
        print_dry_run(easyconfigs, short=not options.dry_run, build_specs=build_specs)

    if any([options.dry_run, options.dry_run_short, options.regtest, options.search, options.search_short]):
        cleanup(logfile, eb_tmpdir, testing)
        sys.exit(0)

    # skip modules that are already installed unless forced
    if not options.force:
        easyconfigs = skip_available(easyconfigs, testing=testing)

    # determine an order that will allow all specs in the set to build
    if len(easyconfigs) > 0:
        print_msg("resolving dependencies ...", log=_log, silent=testing)
        ordered_ecs = resolve_dependencies(easyconfigs, build_specs=build_specs)
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
            jobs = build_easyconfigs_in_parallel(command, ordered_ecs)
            txt = ["List of submitted jobs:"]
            txt.extend(["%s (%s): %s" % (job.name, job.module, job.jobid) for job in jobs])
            txt.append("(%d jobs submitted)" % len(jobs))

            print_msg("Submitted parallel build jobs, exiting now: %s" % '\n'.join(txt), log=_log)
            cleanup(logfile, eb_tmpdir, testing)
            sys.exit(0)

    # build software, will exit when errors occurs (except when testing)
    exit_on_failure = options.test_easyconfigs_pr is None and options.dump_test_report is None
    if not testing or (testing and do_build):
        ordered_ecs = build_and_install_software(ordered_ecs, init_session_state, exit_on_failure=exit_on_failure)

    correct_builds_cnt = len([ec for ec in ordered_ecs if ec['success']])
    overall_success = correct_builds_cnt == len(ordered_ecs)
    success_msg = "Build succeeded for %s out of %s" % (correct_builds_cnt, len(ordered_ecs))
    print_msg(success_msg, log=_log, silent=testing)

    repo = init_repository(get_repository(), get_repositorypath())
    repo.cleanup()

    # report back in PR in case of testing
    if options.test_easyconfigs_pr:
        msg = success_msg + " (%d easyconfigs in this PR)" % len(paths)
        test_report = create_test_report(msg, ordered_ecs, init_session_state, pr_nr=pr_nr, gist_log=True)
        post_easyconfigs_pr_test_report(pr_nr, test_report, success_msg, init_session_state)
    else:
        test_report = create_test_report(success_msg, ordered_ecs, init_session_state)
    _log.debug("Test report: %s" % test_report)
    if options.dump_test_report is not None:
        write_file(options.dump_test_report, test_report)
        _log.info("Test report dumped to %s" % options.dump_test_report)

    # cleanup and spec files
    for ec in easyconfigs:
        if 'original_spec' in ec and os.path.isfile(ec['spec']):
            os.remove(ec['spec'])

    # cleanup tmp log file, unless one build failed (individual logs are located in eb_tmpdir path)
    if options.logtostdout:
        fancylogger.logToScreen(enable=False, stdout=True)
    else:
        fancylogger.logToFile(logfile, enable=False)
    if overall_success:
        cleanup(logfile, eb_tmpdir, testing)

if __name__ == "__main__":
    try:
        main()
    except EasyBuildError, e:
        sys.stderr.write('ERROR: %s\n' % e.msg)
        sys.exit(1)
