#!/usr/bin/env python
# #
# Copyright 2009-2018 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
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

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
"""
import copy
import os
import stat
import sys
import tempfile
import traceback

# IMPORTANT this has to be the first easybuild import as it customises the logging
#  expect missing log output when this not the case!
from easybuild.tools.build_log import EasyBuildError, init_logging, print_error, print_msg, print_warning, stop_logging

import easybuild.tools.config as config
import easybuild.tools.options as eboptions
from easybuild.framework.easyblock import EasyBlock, build_and_install_one, inject_checksums
from easybuild.framework.easyconfig import EASYCONFIGS_PKG_SUBDIR
from easybuild.framework.easyconfig.easyconfig import verify_easyconfig_filename
from easybuild.framework.easyconfig.style import cmdline_easyconfigs_style_check
from easybuild.framework.easyconfig.tools import alt_easyconfig_paths, categorize_files_by_type, dep_graph
from easybuild.framework.easyconfig.tools import det_easyconfig_paths, dump_env_script, get_paths_for
from easybuild.framework.easyconfig.tools import parse_easyconfigs, review_pr, skip_available
from easybuild.framework.easyconfig.tweak import obtain_ec_for, tweak
from easybuild.tools.config import find_last_log, get_repository, get_repositorypath, build_option
from easybuild.tools.docs import list_software
from easybuild.tools.filetools import adjust_permissions, cleanup, write_file
from easybuild.tools.github import check_github, find_easybuild_easyconfig, install_github_token
from easybuild.tools.github import new_pr, merge_pr, update_pr
from easybuild.tools.hooks import START, END, load_hooks, run_hook
from easybuild.tools.modules import modules_tool
from easybuild.tools.options import parse_external_modules_metadata, process_software_build_specs, use_color
from easybuild.tools.robot import check_conflicts, det_robot_path, dry_run, resolve_dependencies, search_easyconfigs
from easybuild.tools.package.utilities import check_pkg_support
from easybuild.tools.parallelbuild import submit_jobs
from easybuild.tools.repository.repository import init_repository
from easybuild.tools.testing import create_test_report, overall_test_report, regtest, session_state
from easybuild.tools.version import this_is_easybuild

_log = None


def log_start(eb_command_line, eb_tmpdir):
    """Log startup info."""
    _log.info(this_is_easybuild())

    # log used command line
    _log.info("Command line: %s" % (' '.join(eb_command_line)))

    _log.info("Using %s as temporary directory" % eb_tmpdir)


def find_easyconfigs_by_specs(build_specs, robot_path, try_to_generate, testing=False):
    """Find easyconfigs by build specifications."""
    generated, ec_file = obtain_ec_for(build_specs, robot_path, None)
    if generated:
        if try_to_generate:
            print_msg("Generated an easyconfig file %s, going to use it now..." % ec_file, silent=testing)
        else:
            # (try to) cleanup
            try:
                os.remove(ec_file)
            except OSError, err:
                _log.warning("Failed to remove generated easyconfig file %s: %s" % (ec_file, err))

            # don't use a generated easyconfig unless generation was requested (using a --try-X option)
            raise EasyBuildError("Unable to find an easyconfig for the given specifications: %s; "
                                 "to make EasyBuild try to generate a matching easyconfig, "
                                 "use the --try-X options ", build_specs)

    return [(ec_file, generated)]


def build_and_install_software(ecs, init_session_state, exit_on_failure=True, hooks=None):
    """
    Build and install software for all provided parsed easyconfig files.

    :param ecs: easyconfig files to install software with
    :param init_session_state: initial session state, to use in test reports
    :param exit_on_failure: whether or not to exit on installation failure
    :param hooks: list of defined pre- and post-step hooks
    """
    # obtain a copy of the starting environment so each build can start afresh
    # we shouldn't use the environment from init_session_state, since relevant env vars might have been set since
    # e.g. via easyconfig.handle_allowed_system_deps
    init_env = copy.deepcopy(os.environ)

    run_hook(START, hooks)

    res = []
    for ec in ecs:
        ec_res = {}
        try:
            (ec_res['success'], app_log, err) = build_and_install_one(ec, init_env, hooks=hooks)
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
        if 'log_file' in ec_res and ec_res['log_file']:
            test_report_fp = "%s_test_report.md" % '.'.join(ec_res['log_file'].split('.')[:-1])
            parent_dir = os.path.dirname(test_report_fp)
            # parent dir for test report may not be writable at this time, e.g. when --read-only-installdir is used
            if os.stat(parent_dir).st_mode & 0200:
                write_file(test_report_fp, test_report_txt)
            else:
                adjust_permissions(parent_dir, stat.S_IWUSR, add=True, recursive=False)
                write_file(test_report_fp, test_report_txt)
                adjust_permissions(parent_dir, stat.S_IWUSR, add=False, recursive=False)

        if not ec_res['success'] and exit_on_failure:
            if 'traceback' in ec_res:
                raise EasyBuildError(ec_res['traceback'])
            else:
                raise EasyBuildError(test_msg)

        res.append((ec, ec_res))

    run_hook(END, hooks)

    return res


def check_root_usage(allow_use_as_root=False):
    """
    Check whether we are running as root, and act accordingly

    :param allow_use_as_root: allow use of EasyBuild as root (but do print a warning when doing so)
    """
    if os.getuid() == 0:
        if allow_use_as_root:
            msg = "Using EasyBuild as root is NOT recommended, please proceed with care!\n"
            msg += "(this is only allowed because EasyBuild was configured with "
            msg += "--allow-use-as-root-and-accept-consequences)"
            print_warning(msg)
        else:
            raise EasyBuildError("You seem to be running EasyBuild with root privileges which is not wise, "
                                 "so let's end this here.")


def main(args=None, logfile=None, do_build=None, testing=False, modtool=None):
    """
    Main function: parse command line options, and act accordingly.
    :param args: command line arguments to use
    :param logfile: log file to use
    :param do_build: whether or not to actually perform the build
    :param testing: enable testing mode
    """
    # purposely session state very early, to avoid modules loaded by EasyBuild meddling in
    init_session_state = session_state()

    # initialise options
    eb_go = eboptions.parse_options(args=args)
    options = eb_go.options
    orig_paths = eb_go.args

    # set umask (as early as possible)
    if options.umask is not None:
        new_umask = int(options.umask, 8)
        old_umask = os.umask(new_umask)

    # set by option parsers via set_tmpdir
    eb_tmpdir = tempfile.gettempdir()

    search_query = options.search or options.search_filename or options.search_short

    # initialise logging for main
    global _log
    _log, logfile = init_logging(logfile, logtostdout=options.logtostdout,
                                 silent=(testing or options.terse or search_query), colorize=options.color)

    # disallow running EasyBuild as root (by default)
    check_root_usage(allow_use_as_root=options.allow_use_as_root_and_accept_consequences)

    # log startup info
    eb_cmd_line = eb_go.generate_cmd_line() + eb_go.args
    log_start(eb_cmd_line, eb_tmpdir)

    if options.umask is not None:
        _log.info("umask set to '%s' (used to be '%s')" % (oct(new_umask), oct(old_umask)))

    # process software build specifications (if any), i.e.
    # software name/version, toolchain name/version, extra patches, ...
    (try_to_generate, build_specs) = process_software_build_specs(options)

    # determine robot path
    # --try-X, --dep-graph, --search use robot path for searching, so enable it with path of installed easyconfigs
    tweaked_ecs = try_to_generate and build_specs
    tweaked_ecs_paths, pr_path = alt_easyconfig_paths(eb_tmpdir, tweaked_ecs=tweaked_ecs, from_pr=options.from_pr)
    auto_robot = try_to_generate or options.check_conflicts or options.dep_graph or search_query
    robot_path = det_robot_path(options.robot_paths, tweaked_ecs_paths, pr_path, auto_robot=auto_robot)
    _log.debug("Full robot path: %s" % robot_path)

    # configure & initialize build options
    config_options_dict = eb_go.get_options_by_section('config')
    build_options = {
        'build_specs': build_specs,
        'command_line': eb_cmd_line,
        'external_modules_metadata': parse_external_modules_metadata(options.external_modules_metadata),
        'pr_path': pr_path,
        'robot_path': robot_path,
        'silent': testing,
        'try_to_generate': try_to_generate,
        'valid_stops': [x[0] for x in EasyBlock.get_steps()],
    }
    # initialise the EasyBuild configuration & build options
    config.init(options, config_options_dict)
    config.init_build_options(build_options=build_options, cmdline_options=options)

    if modtool is None:
        modtool = modules_tool(testing=testing)

    # check whether any (EasyBuild-generated) modules are loaded already in the current session
    modtool.check_loaded_modules()

    if options.last_log:
        # print location to last log file, and exit
        last_log = find_last_log(logfile) or '(none)'
        print_msg(last_log, log=_log, prefix=False)

    # check whether packaging is supported when it's being used
    if options.package:
        check_pkg_support()
    else:
        _log.debug("Packaging not enabled, so not checking for packaging support.")

    # search for easyconfigs, if a query is specified
    if search_query:
        search_easyconfigs(search_query, short=options.search_short, filename_only=options.search_filename,
                           terse=options.terse)

    # GitHub options that warrant a silent cleanup & exit
    if options.check_github:
        check_github()

    elif options.install_github_token:
        install_github_token(options.github_user, silent=build_option('silent'))

    elif options.merge_pr:
        merge_pr(options.merge_pr)

    elif options.review_pr:
        print review_pr(pr=options.review_pr, colored=use_color(options.color))

    elif options.list_installed_software:
        detailed = options.list_installed_software == 'detailed'
        print list_software(output_format=options.output_format, detailed=detailed, only_installed=True)

    elif options.list_software:
        print list_software(output_format=options.output_format, detailed=options.list_software == 'detailed')

    # non-verbose cleanup after handling GitHub integration stuff or printing terse info
    early_stop_options = [
        options.check_github,
        options.install_github_token,
        options.list_installed_software,
        options.list_software,
        options.merge_pr,
        options.review_pr,
        options.terse,
        search_query,
    ]
    if any(early_stop_options):
        cleanup(logfile, eb_tmpdir, testing, silent=True)
        sys.exit(0)

    # update session state
    eb_config = eb_go.generate_cmd_line(add_default=True)
    modlist = modtool.list()  # build options must be initialized first before 'module list' works
    init_session_state.update({'easybuild_configuration': eb_config})
    init_session_state.update({'module_list': modlist})
    _log.debug("Initial session state: %s" % init_session_state)

    # determine easybuild-easyconfigs package install path
    easyconfigs_pkg_paths = get_paths_for(subdir=EASYCONFIGS_PKG_SUBDIR)
    if not easyconfigs_pkg_paths:
        _log.warning("Failed to determine install path for easybuild-easyconfigs package.")

    if options.install_latest_eb_release:
        if orig_paths:
            raise EasyBuildError("Installing the latest EasyBuild release can not be combined with installing "
                                 "other easyconfigs")
        else:
            eb_file = find_easybuild_easyconfig()
            orig_paths.append(eb_file)

    categorized_paths = categorize_files_by_type(orig_paths)

    # command line options that do not require any easyconfigs to be specified
    new_update_preview_pr = options.new_pr or options.update_pr or options.preview_pr
    no_ec_opts = [options.aggregate_regtest, options.regtest, search_query, new_update_preview_pr]

    # determine paths to easyconfigs
    determined_paths = det_easyconfig_paths(categorized_paths['easyconfigs'])
    if determined_paths:
        # transform paths into tuples, use 'False' to indicate the corresponding easyconfig files were not generated
        paths = [(p, False) for p in determined_paths]
    else:
        if 'name' in build_specs:
            # try to obtain or generate an easyconfig file via build specifications if a software name is provided
            paths = find_easyconfigs_by_specs(build_specs, robot_path, try_to_generate, testing=testing)
        elif any(no_ec_opts):
            paths = determined_paths
        else:
            print_error(("Please provide one or multiple easyconfig files, or use software build "
                         "options to make EasyBuild search for easyconfigs"),
                        log=_log, opt_parser=eb_go.parser, exit_on_error=not testing)
    _log.debug("Paths: %s" % paths)

    # run regtest
    if options.regtest or options.aggregate_regtest:
        _log.info("Running regression test")
        # fallback: easybuild-easyconfigs install path
        regtest_ok = regtest([path[0] for path in paths] or easyconfigs_pkg_paths, modtool)
        if not regtest_ok:
            _log.info("Regression test failed (partially)!")
            sys.exit(31)  # exit -> 3x1t -> 31

    if options.check_style:
        _log.debug("Running style check...")
        if cmdline_easyconfigs_style_check([path[0] for path in paths]):
            print_msg("All style checks passed!", prefix=False)
            cleanup(logfile, eb_tmpdir, testing)
            sys.exit(0)
        else:
            raise EasyBuildError("One or more style checks FAILED!")

    # read easyconfig files
    easyconfigs, generated_ecs = parse_easyconfigs(paths, validate=not options.inject_checksums)

    # verify easyconfig filenames, if desired
    if options.verify_easyconfig_filenames:
        _log.info("Verifying easyconfig filenames...")
        for easyconfig in easyconfigs:
            verify_easyconfig_filename(easyconfig['spec'], easyconfig['ec'], parsed_ec=easyconfig['ec'])

    # tweak obtained easyconfig files, if requested
    # don't try and tweak anything if easyconfigs were generated, since building a full dep graph will fail
    # if easyconfig files for the dependencies are not available
    if try_to_generate and build_specs and not generated_ecs:
        easyconfigs = tweak(easyconfigs, build_specs, modtool, targetdirs=tweaked_ecs_paths)

    forced = options.force or options.rebuild
    dry_run_mode = options.dry_run or options.dry_run_short

    # skip modules that are already installed unless forced, or unless an option is used that warrants not skipping
    if not (forced or dry_run_mode or options.extended_dry_run or new_update_preview_pr or options.inject_checksums):
        retained_ecs = skip_available(easyconfigs, modtool)
        if not testing:
            for skipped_ec in [ec for ec in easyconfigs if ec not in retained_ecs]:
                print_msg("%s is already installed (module found), skipping" % skipped_ec['full_mod_name'])
        easyconfigs = retained_ecs

    # determine an order that will allow all specs in the set to build
    if len(easyconfigs) > 0:
        # resolve dependencies if robot is enabled, except in dry run mode
        # one exception: deps *are* resolved with --new-pr or --update-pr when dry run mode is enabled
        if options.robot and (not dry_run_mode or new_update_preview_pr):
            print_msg("resolving dependencies ...", log=_log, silent=testing)
            ordered_ecs = resolve_dependencies(easyconfigs, modtool)
        else:
            ordered_ecs = easyconfigs
    elif new_update_preview_pr:
        ordered_ecs = None
    else:
        print_msg("No easyconfigs left to be built.", log=_log, silent=testing)
        ordered_ecs = []

    # creating/updating PRs
    if new_update_preview_pr:
        if options.new_pr:
            new_pr(categorized_paths, ordered_ecs, title=options.pr_title, descr=options.pr_descr,
                   commit_msg=options.pr_commit_msg)
        elif options.preview_pr:
            print review_pr(paths=determined_paths, colored=use_color(options.color))
        else:
            update_pr(options.update_pr, categorized_paths, ordered_ecs, commit_msg=options.pr_commit_msg)

    # dry_run: print all easyconfigs and dependencies, and whether they are already built
    elif dry_run_mode:
        txt = dry_run(easyconfigs, modtool, short=not options.dry_run)
        print_msg(txt, log=_log, silent=testing, prefix=False)

    elif options.check_conflicts:
        if check_conflicts(easyconfigs, modtool):
            print_error("One or more conflicts detected!")
            sys.exit(1)
        else:
            print_msg("\nNo conflicts detected!\n", prefix=False)

    # dump source script to set up build environment
    elif options.dump_env_script:
        dump_env_script(easyconfigs)

    elif options.inject_checksums:
        inject_checksums(ordered_ecs, options.inject_checksums)

    # cleanup and exit after dry run, searching easyconfigs or submitting regression test
    stop_options = [options.check_conflicts, dry_run_mode, options.dump_env_script, options.inject_checksums]
    if any(no_ec_opts) or any(stop_options):
        cleanup(logfile, eb_tmpdir, testing)
        sys.exit(0)

    # create dependency graph and exit
    if options.dep_graph:
        _log.info("Creating dependency graph %s" % options.dep_graph)
        dep_graph(options.dep_graph, ordered_ecs)
        cleanup(logfile, eb_tmpdir, testing, silent=True)
        sys.exit(0)

    # submit build as job(s), clean up and exit
    if options.job:
        submit_jobs(ordered_ecs, eb_go.generate_cmd_line(), testing=testing)
        if not testing:
            print_msg("Submitted parallel build jobs, exiting now")
            cleanup(logfile, eb_tmpdir, testing)
            sys.exit(0)

    # build software, will exit when errors occurs (except when testing)
    if not testing or (testing and do_build):
        exit_on_failure = not (options.dump_test_report or options.upload_test_report)
        hooks = load_hooks(options.hooks)

        ecs_with_res = build_and_install_software(ordered_ecs, init_session_state,
                                                  exit_on_failure=exit_on_failure, hooks=hooks)
    else:
        ecs_with_res = [(ec, {}) for ec in ordered_ecs]

    correct_builds_cnt = len([ec_res for (_, ec_res) in ecs_with_res if ec_res.get('success', False)])
    overall_success = correct_builds_cnt == len(ordered_ecs)
    success_msg = "Build succeeded for %s out of %s" % (correct_builds_cnt, len(ordered_ecs))

    repo = init_repository(get_repository(), get_repositorypath())
    repo.cleanup()

    # dump/upload overall test report
    test_report_msg = overall_test_report(ecs_with_res, len(paths), overall_success, success_msg, init_session_state)
    if test_report_msg is not None:
        print_msg(test_report_msg)

    print_msg(success_msg, log=_log, silent=testing)

    # cleanup and spec files
    for ec in easyconfigs:
        if 'original_spec' in ec and os.path.isfile(ec['spec']):
            os.remove(ec['spec'])

    # stop logging and cleanup tmp log file, unless one build failed (individual logs are located in eb_tmpdir)
    stop_logging(logfile, logtostdout=options.logtostdout)
    if overall_success:
        cleanup(logfile, eb_tmpdir, testing)


if __name__ == "__main__":
    try:
        main()
    except EasyBuildError, e:
        print_error(e.msg)
