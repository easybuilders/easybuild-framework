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
import traceback
from vsc.utils.missing import any

# IMPORTANT this has to be the first easybuild import as it customises the logging
#  expect missing log output when this not the case!
from easybuild.tools.build_log import EasyBuildError, init_logging, print_msg, print_error, stop_logging

import easybuild.tools.config as config
import easybuild.tools.options as eboptions
from easybuild.framework.easyblock import EasyBlock, build_and_install_one
from easybuild.framework.easyconfig.easyconfig import process_easyconfig
from easybuild.framework.easyconfig.tools import dep_graph, get_paths_for, print_dry_run
from easybuild.framework.easyconfig.tools import resolve_dependencies, skip_available
from easybuild.framework.easyconfig.tweak import obtain_path, tweak
from easybuild.tools.config import build_option, get_repository, module_classes, get_repositorypath, set_tmpdir
from easybuild.tools.filetools import cleanup, find_easyconfigs, search_file, write_file
from easybuild.tools.github import fetch_easyconfigs_from_pr
from easybuild.tools.options import process_software_build_specs
from easybuild.tools.parallelbuild import build_easyconfigs_in_parallel
from easybuild.tools.repository.repository import init_repository
from easybuild.tools.testing import create_test_report, post_easyconfigs_pr_test_report, upload_test_report_as_gist
from easybuild.tools.testing import regtest, session_module_list, session_state
from easybuild.tools.version import this_is_easybuild  # from a single location


_log = None


def log_start(eb_command_line, eb_tmpdir):
    """Log startup info."""
    _log.info(this_is_easybuild())

    # log used command line
    _log.info("Command line: %s" % (' '.join(eb_command_line)))

    _log.info("Using %s as temporary directory" % eb_tmpdir)


def alt_easyconfig_paths(tmpdir, tweaked_ecs=False, from_pr=False):
    """Obtain alternative paths for easyconfig files."""
    # prepend robot path with location where tweaked easyconfigs will be placed
    tweaked_ecs_path = None
    if tweaked_ecs:
        tweaked_ecs_path = os.path.join(tmpdir, 'tweaked_easyconfigs')

    pr_path = None
    if from_pr:
        # extend robot search path with location where files touch in PR will be downloaded to
        pr_path = os.path.join(tmpdir, "files_pr%s" % from_pr)

    return tweaked_ecs_path, pr_path


def det_robot_path(robot_option, easyconfigs_paths, tweaked_ecs_path, pr_path, auto_robot=False):
    """Determine robot path."""
    # do not use robot option directly, it's not a list instance (and it shouldn't be modified)
    robot_path = []
    if not robot_option is None:
        if robot_option:
            robot_path = list(robot_option)
            _log.info("Using robot path(s): %s" % robot_path)
        else:
            # if options.robot is not None and False, easyconfigs pkg install path could not be found (see options.py)
            _log.error("No robot paths specified, and unable to determine easybuild-easyconfigs install path.")

    if auto_robot:
        robot_path.extend(easyconfigs_paths)
        _log.info("Extended list of robot paths with paths for installed easyconfigs: %s" % robot_path)

    if tweaked_ecs_path is not None:
        robot_path.insert(0, tweaked_ecs_path)
        _log.info("Prepended list of robot search paths with %s: %s" % (tweaked_ecs_path, robot_path))

    if pr_path is not None:
        robot_path.insert(0, pr_path)
        _log.info("Prepended list of robot search paths with %s: %s" % (pr_path, robot_path))

    return robot_path


def configure(options, config_options_dict, build_options):
    """Configure EasyBuild."""
    # initialise the easybuild configuration
    config.init(options, config_options_dict)

    # building a dependency graph implies force, so that all dependencies are retained
    # and also skips validation of easyconfigs (e.g. checking os dependencies)
    retain_all_deps = False
    if options.dep_graph:
        _log.info("Enabling force to generate dependency graph.")
        options.force = True
        retain_all_deps = True

    if options.dep_graph or options.dry_run or options.dry_run_short:
        options.ignore_osdeps = True

    build_options.update({
        'aggregate_regtest': options.aggregate_regtest,
        'allow_modules_tool_mismatch': options.allow_modules_tool_mismatch,
        'check_osdeps': not options.ignore_osdeps,
        'filter_deps': options.filter_deps,
        'cleanup_builddir': options.cleanup_builddir,
        'debug': options.debug,
        'dry_run': options.dry_run or options.dry_run_short,
        'dump_test_report': options.dump_test_report,
        'easyblock': options.easyblock,
        'experimental': options.experimental,
        'force': options.force,
        'github_user': options.github_user,
        'group': options.group,
        'hidden': options.hidden,
        'ignore_dirs': options.ignore_dirs,
        'modules_footer': options.modules_footer,
        'only_blocks': options.only_blocks,
        'optarch': options.optarch,
        'recursive_mod_unload': options.recursive_module_unload,
        'regtest_output_dir': options.regtest_output_dir,
        'retain_all_deps': retain_all_deps,
        'sequential': options.sequential,
        'set_gid_bit': options.set_gid_bit,
        'skip': options.skip,
        'skip_test_cases': options.skip_test_cases,
        'sticky_bit': options.sticky_bit,
        'stop': options.stop,
        'suffix_modules_path': options.suffix_modules_path,
        'test_report_env_filter': options.test_report_env_filter,
        'umask': options.umask,
        'upload_test_report': options.upload_test_report,
        'valid_module_classes': module_classes(),
        'valid_stops': [x[0] for x in EasyBlock.get_steps()],
        'validate': not options.force,
    })
    config.init_build_options(build_options)


def search(query, short=False):
    """Search for easyconfigs, if a query is provided."""
    search_path = [os.getcwd()]
    robot_path = build_option('robot_path')
    if robot_path:
        search_path = robot_path
    ignore_dirs = config.build_option('ignore_dirs')
    silent = config.build_option('silent')
    search_file(search_path, query, short=short, ignore_dirs=ignore_dirs, silent=silent)


def det_easyconfig_paths(orig_paths, from_pr=None, easyconfigs_pkg_paths=None):
    """
    Determine paths to easyconfig files.
    @param orig_paths: list of original easyconfig paths
    @param from_pr: pull request number to fetch easyconfigs from
    @param easyconfigs_pkg_paths: paths to installed easyconfigs package
    """
    paths = []

    if easyconfigs_pkg_paths is None:
        easyconfigs_pkg_paths = []
    build_specs = build_option('build_specs')
    ignore_dirs = build_option('ignore_dirs')
    robot_path = build_option('robot_path')
    testing = build_option('testing')
    try_to_generate = build_option('try_to_generate')

    if len(orig_paths) == 0:
        if from_pr:
            pr_files = fetch_easyconfigs_from_pr(from_pr)
            paths = [(path, False) for path in pr_files if path.endswith('.eb')]
        elif 'name' in build_specs:
            paths = [obtain_path(build_specs, robot_path, try_to_generate=try_to_generate,
                                 exit_on_error=not testing)]
    else:
        # look for easyconfigs with relative paths in easybuild-easyconfigs package,
        # unless they were found at the given relative paths
        if easyconfigs_pkg_paths:
            # determine which easyconfigs files need to be found, if any
            ecs_to_find = []
            for idx, orig_path in enumerate(orig_paths):
                if orig_path == os.path.basename(orig_path) and not os.path.exists(orig_path):
                    ecs_to_find.append((idx, orig_path))
            _log.debug("List of easyconfig files to find: %s" % ecs_to_find)

            # find missing easyconfigs by walking paths with installed easyconfig files
            for path in easyconfigs_pkg_paths:
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
                    dirnames[:] = [d for d in dirnames if not d in ignore_dirs]

                # stop os.walk insanity as soon as we have all we need (paths loop)
                if len(ecs_to_find) == 0:
                    break

        # indicate that specified paths do not contain generated easyconfig files
        paths = [(path, False) for path in orig_paths]

    return paths


def read_easyconfigs(paths):
    """
    Read/parse easyconfigs
    @params paths: paths to easyconfigs
    """
    build_specs = build_option('build_specs')
    ignore_dirs = build_option('ignore_dirs')
    try_to_generate = build_option('try_to_generate')
    tweaked_ecs_path = build_option('tweaked_ecs_path')

    easyconfigs = []
    generated_ecs = False
    for (path, generated) in paths:
        path = os.path.abspath(path)
        # keep track of whether any files were generated
        generated_ecs |= generated
        if not os.path.exists(path):
            print_error("Can't find path %s" % path)
        try:
            ec_files = find_easyconfigs(path, ignore_dirs=ignore_dirs)
            for ec_file in ec_files:
                # only pass build specs when not generating easyconfig files
                if try_to_generate:
                    ecs = process_easyconfig(ec_file)
                else:
                    ecs = process_easyconfig(ec_file, build_specs=build_specs)
                easyconfigs.extend(ecs)
        except IOError, err:
            _log.error("Processing easyconfigs in path %s failed: %s" % (path, err))

    # tweak obtained easyconfig files, if requested
    # don't try and tweak anything if easyconfigs were generated, since building a full dep graph will fail
    # if easyconfig files for the dependencies are not available
    if try_to_generate and build_specs and not generated_ecs:
        easyconfigs = tweak(easyconfigs, build_specs, targetdir=tweaked_ecs_path)

    return easyconfigs


def submit_jobs(ordered_ecs, cmd_line_opts, testing=False):
    """
    Submit jobs.
    @param ordered_ecs: list of easyconfigs, in the order they should be processed
    @param cmd_line_opts: list of command line options (in 'longopt=value' form)
    """
    curdir = os.getcwd()

    # the options to ignore (help options can't reach here)
    ignore_opts = ['robot', 'job']

    # generate_cmd_line returns the options in form --longopt=value
    opts = [x for x in cmd_line_opts if not x.split('=')[0] in ['--%s' % y for y in ignore_opts]]

    quoted_opts = subprocess.list2cmdline(opts)

    command = "unset TMPDIR && cd %s && eb %%(spec)s %s" % (curdir, quoted_opts)
    _log.info("Command template for jobs: %s" % command)
    if not testing:
        jobs = build_easyconfigs_in_parallel(command, ordered_ecs)
        txt = ["List of submitted jobs:"]
        txt.extend(["%s (%s): %s" % (job.name, job.module, job.jobid) for job in jobs])
        txt.append("(%d jobs submitted)" % len(jobs))

        print_msg("Submitted parallel build jobs, exiting now: %s" % '\n'.join(txt), log=_log)


def build_and_install_software(ecs, init_session_state, exit_on_failure=True):
    """Build and install software for all provided parsed easyconfig files."""
    # obtain a copy of the starting environment so each build can start afresh
    # we shouldn't use the environment from init_session_state, since relevant env vars might have been set since
    # e.g. via easyconfig.handle_allowed_system_deps
    orig_environ = copy.deepcopy(os.environ)

    res = []
    for ec in ecs:
        ec_res = {}
        try:
            (ec_res['success'], app_log, err) = build_and_install_one(ec, orig_environ)
            ec_res['log_file'] = app_log
            if not ec_res['success']:
                ec_res['err'] = EasyBuildError(err)
        except Exception, err:
            # purposely catch all exceptions
            ec_res['success'] = False
            ec_res['err'] = err
            ec_res['traceback'] = traceback.format_exc()

        # keep track of success/total count
        if ec_res['success']:
            test_msg = "Successfully built %s" % ec['spec']
        else:
            test_msg = "Build of %s failed" % ec['spec']
            if 'err' in ec_res:
                test_msg += " (err: %s)" % ec_res['err']

        # dump test report next to log file
        test_report_txt = create_test_report(test_msg, [(ec, ec_res)], init_session_state)
        if 'log_file' in ec_res:
            test_report_fp = "%s_test_report.md" % '.'.join(ec_res['log_file'].split('.')[:-1])
            write_file(test_report_fp, test_report_txt)

        if not ec_res['success'] and exit_on_failure:
            if 'traceback' in ec_res:
                _log.error(ec_res['traceback'])
            else:
                _log.error(test_msg)

        res.append((ec, ec_res))

    return res


def test_report(ecs_with_res, orig_cnt, success, msg, init_session_state):
    """
    Upload/dump test report
    @param ecs_with_res: processed easyconfigs with build result (success/failure)
    @param orig_cnt: number of original easyconfig paths
    @param success: boolean indicating whether all builds were successful
    @param msg: message to be included in test report
    @param init_session_state: initial session state info to include in test report
    """
    dump_path = build_option('dump_test_report')
    pr_nr = build_option('from_pr')
    upload = build_option('upload_test_report')

    if upload:
        msg = msg + " (%d easyconfigs in this PR)" % orig_cnt
        test_report = create_test_report(msg, ecs_with_res, init_session_state, pr_nr=pr_nr, gist_log=True)
        if pr_nr:
            # upload test report to gist and issue a comment in the PR to notify
            msg = post_easyconfigs_pr_test_report(pr_nr, test_report, msg, init_session_state, success)
            print_msg(msg)
        else:
            # only upload test report as a gist
            gist_url = upload_test_report_as_gist(test_report)
            print_msg("Test report uploaded to %s" % gist_url)
    else:
        test_report = create_test_report(msg, ecs_with_res, init_session_state)
    _log.debug("Test report: %s" % test_report)
    if dump_path is not None:
        write_file(dump_path, test_report)
        _log.info("Test report dumped to %s" % dump_path)


def main(testing_data=(None, None, None)):
    """
    Main function: parse command line options, and act accordingly.
    @param testing_data: tuple with command line arguments, log file and boolean indicating whether or not to build
    """
    # purposely session state very early, to avoid modules loaded by EasyBuild meddling in
    init_session_state = session_state()

    # steer behavior when testing main
    testing = testing_data[0] is not None
    args, logfile, do_build = testing_data

    # initialise options
    eb_go = eboptions.parse_options(args=args)
    options = eb_go.options
    orig_paths = eb_go.args

    # set umask (as early as possible)
    if options.umask is not None:
        new_umask = int(options.umask, 8)
        old_umask = os.umask(new_umask)

    # set temporary directory to use
    eb_tmpdir = set_tmpdir(options.tmpdir)

    # initialise logging for main
    global _log
    _log, logfile = init_logging(logfile, logtostdout=options.logtostdout, testing=testing)

    # disallow running EasyBuild as root
    if os.getuid() == 0:
        _log.error("You seem to be running EasyBuild with root privileges which is not wise, so let's end this here.")

    # log startup info
    eb_cmd_line = eb_go.generate_cmd_line() + eb_go.args
    log_start(eb_cmd_line, eb_tmpdir)

    if options.umask is not None:
        _log.info("umask set to '%s' (used to be '%s')" % (oct(new_umask), oct(old_umask)))

    # determine easybuild-easyconfigs package install path
    easyconfigs_pkg_paths = get_paths_for("easyconfigs")
    if not easyconfigs_pkg_paths:
        _log.warning("Failed to determine install path for easybuild-easyconfigs package.")

    # process software build specifications (if any), i.e.
    # software name/version, toolchain name/version, extra patches, ...
    (try_to_generate, build_specs) = process_software_build_specs(options)

    # determine robot path
    # --try-X, --dep-graph, --search use robot path for searching, so enable it with path of installed easyconfigs
    tweaked_ecs = try_to_generate and build_specs
    tweaked_ecs_path, pr_path = alt_easyconfig_paths(eb_tmpdir, tweaked_ecs=tweaked_ecs, from_pr=options.from_pr)
    auto_robot = try_to_generate or options.dep_graph or options.search or options.search_short
    robot_path = det_robot_path(options.robot, easyconfigs_pkg_paths, tweaked_ecs_path, pr_path, auto_robot=auto_robot)
    _log.debug("Full robot path: %s" % robot_path)

    # configure & initialize build options
    config_options_dict = eb_go.get_options_by_section('config')
    build_options = {
        'build_specs': build_specs,
        'command_line': eb_cmd_line,
        'pr_path': pr_path,
        'robot_path': robot_path,
        'silent': testing,
        'testing': testing,
        'try_to_generate': try_to_generate,
        'tweaked_ecs_path': tweaked_ecs_path,
    }
    configure(options, config_options_dict, build_options)

    # update session state
    eb_config = eb_go.generate_cmd_line(add_default=True)
    modlist = session_module_list(testing=testing)  # build options must be initialized first before 'module list' works
    init_session_state.update({'easybuild_configuration': eb_config})
    init_session_state.update({'module_list': modlist})
    _log.debug("Initial session state: %s" % init_session_state)

    # search for easyconfigs, if a query is specified
    query = options.search or options.search_short
    if query:
        search(query, short=not options.search)

    # determine paths to easyconfigs
    paths = det_easyconfig_paths(orig_paths, options.from_pr, easyconfigs_pkg_paths)
    if not paths and not any([options.aggregate_regtest, options.search, options.search_short, options.regtest]):
        print_error(("Please provide one or multiple easyconfig files, or use software build "
                     "options to make EasyBuild search for easyconfigs"),
                     log=_log, opt_parser=eb_go.parser, exit_on_error=not testing)
    _log.debug("Paths: %s" % paths)

    # run regtest
    if options.regtest or options.aggregate_regtest:
        _log.info("Running regression test")
        # fallback: easybuild-easyconfigs install path
        regtest_ok = regtest([path[0] for path in paths] or easyconfigs_pkg_paths)
        if not regtest_ok:
            _log.info("Regression test failed (partially)!")
            sys.exit(31)  # exit -> 3x1t -> 31

    # read easyconfig files
    easyconfigs = read_easyconfigs(paths)

    # dry_run: print all easyconfigs and dependencies, and whether they are already built
    if options.dry_run or options.dry_run_short:
        print_dry_run(easyconfigs, short=not options.dry_run, build_specs=build_specs)

    # cleanup and exit after dry run, searching easyconfigs or submitting regression test
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

    # submit build as job(s), clean up and exit
    if options.job:
        submit_jobs(ordered_ecs, eb_go.generate_cmd_line(), testing=testing)
        if not testing:
            cleanup(logfile, eb_tmpdir, testing)
            sys.exit(0)

    # build software, will exit when errors occurs (except when testing)
    exit_on_failure = not options.dump_test_report and not options.upload_test_report
    if not testing or (testing and do_build):
        ecs_with_res = build_and_install_software(ordered_ecs, init_session_state, exit_on_failure=exit_on_failure)
    else:
        ecs_with_res = [(ec, {}) for ec in ordered_ecs]

    correct_builds_cnt = len([ec_res for (_, ec_res) in ecs_with_res if ec_res.get('success', False)])
    overall_success = correct_builds_cnt == len(ordered_ecs)
    success_msg = "Build succeeded for %s out of %s" % (correct_builds_cnt, len(ordered_ecs))

    repo = init_repository(get_repository(), get_repositorypath())
    repo.cleanup()

    # dump/upload overall test report
    test_report(ecs_with_res, len(paths), overall_success, success_msg, init_session_state)

    print_msg(success_msg, log=_log, silent=testing)

    # cleanup and spec files
    for ec in easyconfigs:
        if 'original_spec' in ec and os.path.isfile(ec['spec']):
            os.remove(ec['spec'])

    # stop logging and cleanup tmp log file, unless one build failed (individual logs are located in eb_tmpdir path)
    stop_logging(logfile, logtostdout=options.logtostdout)
    if overall_success:
        cleanup(logfile, eb_tmpdir, testing)

if __name__ == "__main__":
    try:
        main()
    except EasyBuildError, e:
        sys.stderr.write('ERROR: %s\n' % e.msg)
        sys.exit(1)
