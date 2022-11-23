#!/usr/bin/env python
# #
# Copyright 2009-2022 Ghent University
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
:author: Maxime Boissonneault (Compute Canada)
"""
import copy
import os
import stat
import sys
import traceback

# IMPORTANT this has to be the first easybuild import as it customises the logging
#  expect missing log output when this not the case!
from easybuild.tools.build_log import EasyBuildError, print_error, print_msg, print_warning, stop_logging

from easybuild.framework.easyblock import build_and_install_one, inject_checksums, inject_checksums_to_json
from easybuild.framework.easyconfig import EASYCONFIGS_PKG_SUBDIR
from easybuild.framework.easyconfig import easyconfig
from easybuild.framework.easystack import parse_easystack
from easybuild.framework.easyconfig.easyconfig import clean_up_easyconfigs
from easybuild.framework.easyconfig.easyconfig import fix_deprecated_easyconfigs, verify_easyconfig_filename
from easybuild.framework.easyconfig.style import cmdline_easyconfigs_style_check
from easybuild.framework.easyconfig.tools import categorize_files_by_type, dep_graph, det_copy_ec_specs
from easybuild.framework.easyconfig.tools import det_easyconfig_paths, dump_env_script, get_paths_for
from easybuild.framework.easyconfig.tools import parse_easyconfigs, review_pr, run_contrib_checks, skip_available
from easybuild.framework.easyconfig.tweak import obtain_ec_for, tweak
from easybuild.tools.config import find_last_log, get_repository, get_repositorypath, build_option
from easybuild.tools.containers.common import containerize
from easybuild.tools.docs import list_software
from easybuild.tools.filetools import adjust_permissions, cleanup, copy_files, dump_index, load_index
from easybuild.tools.filetools import locate_files, read_file, register_lock_cleanup_signal_handlers, write_file
from easybuild.tools.github import check_github, close_pr, find_easybuild_easyconfig
from easybuild.tools.github import add_pr_labels, install_github_token, list_prs, merge_pr, new_branch_github, new_pr
from easybuild.tools.github import new_pr_from_branch
from easybuild.tools.github import sync_branch_with_develop, sync_pr_with_develop, update_branch, update_pr
from easybuild.tools.hooks import START, END, load_hooks, run_hook
from easybuild.tools.modules import modules_tool
from easybuild.tools.options import opts_dict_to_eb_opts, set_up_configuration, use_color
from easybuild.tools.output import COLOR_GREEN, COLOR_RED, STATUS_BAR, colorize, print_checks, rich_live_cm
from easybuild.tools.output import start_progress_bar, stop_progress_bar, update_progress_bar
from easybuild.tools.robot import check_conflicts, dry_run, missing_deps, resolve_dependencies, search_easyconfigs
from easybuild.tools.package.utilities import check_pkg_support
from easybuild.tools.parallelbuild import submit_jobs
from easybuild.tools.repository.repository import init_repository
from easybuild.tools.systemtools import check_easybuild_deps
from easybuild.tools.testing import create_test_report, overall_test_report, regtest, session_state


_log = None


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
            except OSError as err:
                _log.warning("Failed to remove generated easyconfig file %s: %s" % (ec_file, err))

            # don't use a generated easyconfig unless generation was requested (using a --try-X option)
            raise EasyBuildError("Unable to find an easyconfig for the given specifications: %s; "
                                 "to make EasyBuild try to generate a matching easyconfig, "
                                 "use the --try-X options ", build_specs)

    return [(ec_file, generated)]


def build_and_install_software(ecs, init_session_state, exit_on_failure=True):
    """
    Build and install software for all provided parsed easyconfig files.

    :param ecs: easyconfig files to install software with
    :param init_session_state: initial session state, to use in test reports
    :param exit_on_failure: whether or not to exit on installation failure
    """
    # obtain a copy of the starting environment so each build can start afresh
    # we shouldn't use the environment from init_session_state, since relevant env vars might have been set since
    # e.g. via easyconfig.handle_allowed_system_deps
    init_env = copy.deepcopy(os.environ)

    start_progress_bar(STATUS_BAR, size=len(ecs))

    res = []
    ec_results = []
    failed_cnt = 0

    for ec in ecs:

        ec_res = {}
        try:
            (ec_res['success'], app_log, err) = build_and_install_one(ec, init_env)
            ec_res['log_file'] = app_log
            if not ec_res['success']:
                ec_res['err'] = EasyBuildError(err)
        except Exception as err:
            # purposely catch all exceptions
            ec_res['success'] = False
            ec_res['err'] = err
            ec_res['traceback'] = traceback.format_exc()

        if ec_res['success']:
            ec_results.append(ec['full_mod_name'] + ' (' + colorize('OK', COLOR_GREEN) + ')')
        else:
            ec_results.append(ec['full_mod_name'] + ' (' + colorize('FAILED', COLOR_RED) + ')')
            failed_cnt += 1

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
            if os.stat(parent_dir).st_mode & 0o200:
                write_file(test_report_fp, test_report_txt['full'])
            else:
                adjust_permissions(parent_dir, stat.S_IWUSR, add=True, recursive=False)
                write_file(test_report_fp, test_report_txt['full'])
                adjust_permissions(parent_dir, stat.S_IWUSR, add=False, recursive=False)

        if not ec_res['success'] and exit_on_failure:
            if 'traceback' in ec_res:
                raise EasyBuildError(ec_res['traceback'])
            else:
                raise EasyBuildError(test_msg)

        res.append((ec, ec_res))

        if failed_cnt:
            # if installations failed: indicate th
            status_label = ' (%s): ' % colorize('%s failed!' % failed_cnt, COLOR_RED)
            failed_ecs = [x for x in ec_results[::-1] if 'FAILED' in x]
            ok_ecs = [x for x in ec_results[::-1] if x not in failed_ecs]
            status_label += ', '.join(failed_ecs + ok_ecs)
        else:
            status_label = ': ' + ', '.join(ec_results[::-1])

        update_progress_bar(STATUS_BAR, label=status_label)

    stop_progress_bar(STATUS_BAR)

    return res


def run_contrib_style_checks(ecs, check_contrib, check_style):
    """
    Handle running of contribution and style checks on specified easyconfigs (if desired).

    :return: boolean indicating whether or not any checks were actually performed
    """
    check_actions = {
        'contribution': (check_contrib, run_contrib_checks),
        'style': (check_style, cmdline_easyconfigs_style_check),
    }
    for check_label, (run_check, check_function) in sorted(check_actions.items()):
        if run_check:
            _log.info("Running %s checks on %d specified easyconfigs...", check_label, len(ecs))
            if check_function(ecs):
                print_msg("\n>> All %s checks PASSed!\n" % check_label, prefix=False)
            else:
                print_msg('', prefix=False)
                raise EasyBuildError("One or more %s checks FAILED!" % check_label)

    return check_contrib or check_style


def clean_exit(logfile, tmpdir, testing, silent=False):
    """Small utility function to perform a clean exit."""
    cleanup(logfile, tmpdir, testing, silent=silent)
    sys.exit(0)


def process_easystack(easystack_path, args, logfile, testing, init_session_state, do_build):
    """
    Process an EasyStack file. That means, parsing, looping over all items in the EasyStack file
    building (where requested) the individual items, etc

    :param easystack_path: path to EasyStack file to be processed
    :param args: original command line arguments as received by main()
    :param logfile: log file to use
    :param testing: enable testing mode
    :param init_session_state: initial session state, to use in test reports
    :param do_build: whether or not to actually perform the build
    """
    easystack = parse_easystack(easystack_path)

    global _log

    # TODO: insert fast loop that validates if all command line options are valid. If there are errors in options,
    # we want to know early on, and this loop potentially builds a lot of packages and could take very long
    # for path in orig_paths:
    #     validate_command_opts(args, opts_per_ec[path])

    # Loop over each item in the EasyStack file, each time updating the config
    # This is because each item in an EasyStack file can have options associated with it
    do_cleanup = True
    for (path, ec_opts) in easystack.ec_opt_tuples:
        _log.debug("Starting build for %s" % path)
        # wipe easyconfig caches
        easyconfig._easyconfigs_cache.clear()
        easyconfig._easyconfig_files_cache.clear()

        # If EasyConfig specific arguments were supplied in EasyStack file
        # merge arguments with original command line args
        if ec_opts is not None:
            _log.debug("EasyConfig specific options have been specified for "
                       "%s in the EasyStack file: %s", path, ec_opts)
            if args is None:
                args = sys.argv[1:]
            ec_args = opts_dict_to_eb_opts(ec_opts)
            # By appending ec_args to args, ec_args take priority
            new_args = args + ec_args
            _log.info("Argument list for %s after merging command line arguments with EasyConfig specific "
                      "options from the EasyStack file: %s", path, new_args)
        else:
            # If no EasyConfig specific arguments are defined, use original args.
            # That way,set_up_configuration restores the original config
            new_args = args

        # Reconfigure
        eb_go, cfg_settings = set_up_configuration(args=new_args, logfile=logfile, testing=testing,
                                                   reconfigure=True, silent=True)
        # Since we reconfigure, we should also reload hooks and get current module tools
        hooks = load_hooks(eb_go.options.hooks)
        modtool = modules_tool(testing=testing)

        # Process actual item in the EasyStack file
        do_cleanup &= process_eb_args([path], eb_go, cfg_settings, modtool, testing, init_session_state,
                                      hooks, do_build)

    return do_cleanup


def process_eb_args(eb_args, eb_go, cfg_settings, modtool, testing, init_session_state, hooks, do_build):
    """
    Remainder of main function, actually process provided arguments (list of files/paths),
    according to specified options.

    :param eb_args: list of arguments that were specified to 'eb' command (or an easystack file);
                 includes filenames/paths of files to process
                 (mostly easyconfig files, but can also includes patch files, etc.)
    :param eb_go: EasyBuildOptions instance (option parser)
    :param cfg_settings: as returned by set_up_configuration
    :param modtool: the modules tool, as returned by modules_tool()
    :param testing: bool whether we're running in test mode
    :param init_session_state: initial session state, to use in test reports
    :param hooks: hooks, as loaded by load_hooks from the options
    :param do_build: whether or not to actually perform the build
    """
    options = eb_go.options

    global _log

    # determine easybuild-easyconfigs package install path
    easyconfigs_pkg_paths = get_paths_for(subdir=EASYCONFIGS_PKG_SUBDIR)
    if not easyconfigs_pkg_paths:
        _log.warning("Failed to determine install path for easybuild-easyconfigs package.")

    if options.install_latest_eb_release:
        if eb_args:
            raise EasyBuildError("Installing the latest EasyBuild release can not be combined with installing "
                                 "other easyconfigs")
        else:
            eb_file = find_easybuild_easyconfig()
            eb_args.append(eb_file)

    # Unpack cfg_settings
    (build_specs, _log, logfile, robot_path, search_query, eb_tmpdir, try_to_generate,
     from_pr_list, tweaked_ecs_paths) = cfg_settings

    if options.copy_ec:
        # figure out list of files to copy + target location (taking into account --from-pr)
        eb_args, target_path = det_copy_ec_specs(eb_args, from_pr_list)

    categorized_paths = categorize_files_by_type(eb_args)

    # command line options that do not require any easyconfigs to be specified
    pr_options = options.new_branch_github or options.new_pr or options.new_pr_from_branch or options.preview_pr
    pr_options = pr_options or options.sync_branch_with_develop or options.sync_pr_with_develop
    pr_options = pr_options or options.update_branch_github or options.update_pr
    no_ec_opts = [options.aggregate_regtest, options.regtest, pr_options, search_query]

    # determine paths to easyconfigs
    determined_paths = det_easyconfig_paths(categorized_paths['easyconfigs'])

    # only copy easyconfigs here if we're not using --try-* (that's handled below)
    copy_ec = options.copy_ec and not tweaked_ecs_paths

    if copy_ec or options.fix_deprecated_easyconfigs or options.show_ec:

        if options.copy_ec:
            # at this point some paths may still just be filenames rather than absolute paths,
            # so try to determine full path for those too via robot search path
            paths = locate_files(eb_args, robot_path)

            copy_files(paths, target_path, target_single_file=True, allow_empty=False, verbose=True)

        elif options.fix_deprecated_easyconfigs:
            fix_deprecated_easyconfigs(determined_paths)

        elif options.show_ec:
            for path in determined_paths:
                print_msg("Contents of %s:" % path)
                print_msg(read_file(path), prefix=False)

        return True

    if determined_paths:
        # transform paths into tuples, use 'False' to indicate the corresponding easyconfig files were not generated
        paths = [(p, False) for p in determined_paths]
    elif 'name' in build_specs:
        # try to obtain or generate an easyconfig file via build specifications if a software name is provided
        paths = find_easyconfigs_by_specs(build_specs, robot_path, try_to_generate, testing=testing)
    elif any(no_ec_opts):
        paths = determined_paths
    else:
        print_error("Please provide one or multiple easyconfig files, or use software build " +
                    "options to make EasyBuild search for easyconfigs",
                    log=_log, opt_parser=eb_go.parser, exit_on_error=not testing)
    _log.debug("Paths: %s", paths)

    # run regtest
    if options.regtest or options.aggregate_regtest:
        _log.info("Running regression test")
        # fallback: easybuild-easyconfigs install path
        regtest_ok = regtest([x for (x, _) in paths] or easyconfigs_pkg_paths, modtool)
        if not regtest_ok:
            _log.info("Regression test failed (partially)!")
            sys.exit(31)  # exit -> 3x1t -> 31

    # read easyconfig files
    try:
        validate = not options.inject_checksums and not options.inject_checksums_to_json
        easyconfigs, generated_ecs = parse_easyconfigs(paths, validate=validate)
    except Exception as err:
        # Catch any exception in easyconfig parsing, so we can generate a test report if required
        if options.dump_test_report or options.upload_test_report:
            # dump/upload overall test report
            fail_msg = "Failed during parsing of the easyconfigs, so no ecs were built"
            test_report_msg = overall_test_report([], len(paths), False, fail_msg, init_session_state,
                                                  ec_parse_error=err)
            if test_report_msg is not None:
                _log.info(test_report_msg)

        raise err

    # handle --check-contrib & --check-style options
    if run_contrib_style_checks([ec['ec'] for ec in easyconfigs], options.check_contrib, options.check_style):
        return True

    # verify easyconfig filenames, if desired
    if options.verify_easyconfig_filenames:
        _log.info("Verifying easyconfig filenames...")
        for ec in easyconfigs:
            verify_easyconfig_filename(ec['spec'], ec['ec'], parsed_ec=ec['ec'])

    # tweak obtained easyconfig files, if requested
    # don't try and tweak anything if easyconfigs were generated, since building a full dep graph will fail
    # if easyconfig files for the dependencies are not available
    if try_to_generate and build_specs and not generated_ecs:
        easyconfigs = tweak(easyconfigs, build_specs, modtool, targetdirs=tweaked_ecs_paths)

    if options.containerize:
        # if --containerize/-C create a container recipe (and optionally container image), and stop
        containerize(easyconfigs)
        return True

    forced = options.force or options.rebuild
    dry_run_mode = options.dry_run or options.dry_run_short or options.missing_modules

    keep_available_modules = forced or dry_run_mode or options.extended_dry_run or pr_options or options.copy_ec
    keep_available_modules = keep_available_modules or options.inject_checksums or options.sanity_check_only
    keep_available_modules = keep_available_modules or options.inject_checksums_to_json

    # skip modules that are already installed unless forced, or unless an option is used that warrants not skipping
    if not keep_available_modules:
        retained_ecs = skip_available(easyconfigs, modtool)
        if not testing:
            for skipped_ec in [ec for ec in easyconfigs if ec not in retained_ecs]:
                print_msg("%s is already installed (module found), skipping" % skipped_ec['full_mod_name'])
        easyconfigs = retained_ecs

    # keep track for which easyconfigs we should set the corresponding module as default
    if options.set_default_module:
        for ec in easyconfigs:
            ec['ec'].set_default_module = True

    # determine an order that will allow all specs in the set to build
    if len(easyconfigs) > 0:
        # resolve dependencies if robot is enabled, except in dry run mode
        # one exception: deps *are* resolved with --new-pr or --update-pr when dry run mode is enabled
        if options.robot and (not dry_run_mode or pr_options):
            print_msg("resolving dependencies ...", log=_log, silent=testing)
            ordered_ecs = resolve_dependencies(easyconfigs, modtool)
        else:
            ordered_ecs = easyconfigs
    elif pr_options:
        ordered_ecs = None
    else:
        print_msg("No easyconfigs left to be built.", log=_log, silent=testing)
        ordered_ecs = []

    if options.copy_ec and tweaked_ecs_paths:
        all_specs = [spec['spec'] for spec in
                     resolve_dependencies(easyconfigs, modtool, retain_all_deps=True, raise_error_missing_ecs=False)]
        tweaked_ecs_in_all_ecs = [path for path in all_specs if
                                  any(tweaked_ecs_path in path for tweaked_ecs_path in tweaked_ecs_paths)]
        if tweaked_ecs_in_all_ecs:
            # Clean them, then copy them
            clean_up_easyconfigs(tweaked_ecs_in_all_ecs)
            copy_files(tweaked_ecs_in_all_ecs, target_path, allow_empty=False, verbose=True)

        return True

    # creating/updating PRs
    if pr_options:
        if options.new_pr:
            new_pr(categorized_paths, ordered_ecs)
        elif options.new_branch_github:
            new_branch_github(categorized_paths, ordered_ecs)
        elif options.new_pr_from_branch:
            new_pr_from_branch(options.new_pr_from_branch)
        elif options.preview_pr:
            print(review_pr(paths=determined_paths, colored=use_color(options.color)))
        elif options.sync_branch_with_develop:
            sync_branch_with_develop(options.sync_branch_with_develop)
        elif options.sync_pr_with_develop:
            sync_pr_with_develop(options.sync_pr_with_develop)
        elif options.update_branch_github:
            update_branch(options.update_branch_github, categorized_paths, ordered_ecs)
        elif options.update_pr:
            update_pr(options.update_pr, categorized_paths, ordered_ecs)
        else:
            raise EasyBuildError("Unknown PR option!")

    # dry_run: print all easyconfigs and dependencies, and whether they are already built
    elif dry_run_mode:
        if options.missing_modules:
            txt = missing_deps(easyconfigs, modtool)
        else:
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
        with rich_live_cm():
            inject_checksums(ordered_ecs, options.inject_checksums)

    elif options.inject_checksums_to_json:
        with rich_live_cm():
            inject_checksums_to_json(ordered_ecs, options.inject_checksums_to_json)

    # cleanup and exit after dry run, searching easyconfigs or submitting regression test
    stop_options = [
        dry_run_mode,
        options.check_conflicts,
        options.dump_env_script,
        options.inject_checksums,
        options.inject_checksums_to_json,
    ]
    if any(no_ec_opts) or any(stop_options):
        return True

    # create dependency graph and exit
    if options.dep_graph:
        _log.info("Creating dependency graph %s" % options.dep_graph)
        dep_graph(options.dep_graph, ordered_ecs)
        return True

    # submit build as job(s), clean up and exit
    if options.job:
        submit_jobs(ordered_ecs, eb_go.generate_cmd_line(), testing=testing)
        if not testing:
            print_msg("Submitted parallel build jobs, exiting now")
            return True

    # build software, will exit when errors occurs (except when testing)
    if not testing or (testing and do_build):
        exit_on_failure = not (options.dump_test_report or options.upload_test_report)

        with rich_live_cm():
            ecs_with_res = build_and_install_software(ordered_ecs, init_session_state,
                                                      exit_on_failure=exit_on_failure)
    else:
        ecs_with_res = [(ec, {}) for ec in ordered_ecs]

    correct_builds_cnt = len([ec_res for (_, ec_res) in ecs_with_res if ec_res.get('success', False)])
    overall_success = correct_builds_cnt == len(ordered_ecs)
    success_msg = "Build succeeded "
    if build_option('ignore_test_failure'):
        success_msg += "(with --ignore-test-failure) "
    success_msg += "for %s out of %s" % (correct_builds_cnt, len(ordered_ecs))

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

    run_hook(END, hooks)

    return overall_success


def main(args=None, logfile=None, do_build=None, testing=False, modtool=None):
    """
    Main function: parse command line options, and act accordingly.
    :param args: command line arguments to use
    :param logfile: log file to use
    :param do_build: whether or not to actually perform the build
    :param testing: enable testing mode
    """

    register_lock_cleanup_signal_handlers()

    # if $CDPATH is set, unset it, it'll only cause trouble...
    # see https://github.com/easybuilders/easybuild-framework/issues/2944
    if 'CDPATH' in os.environ:
        del os.environ['CDPATH']

    # When EB is run via `exec` the special bash variable $_ is not set
    # So emulate this here to allow (module) scripts depending on that to work
    if '_' not in os.environ:
        os.environ['_'] = sys.executable

    # purposely session state very early, to avoid modules loaded by EasyBuild meddling in
    init_session_state = session_state()
    eb_go, cfg_settings = set_up_configuration(args=args, logfile=logfile, testing=testing)
    options, orig_paths = eb_go.options, eb_go.args

    global _log
    (build_specs, _log, logfile, robot_path, search_query, eb_tmpdir, try_to_generate,
     from_pr_list, tweaked_ecs_paths) = cfg_settings

    # load hook implementations (if any)
    hooks = load_hooks(options.hooks)

    run_hook(START, hooks)

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

    if options.check_eb_deps:
        print_checks(check_easybuild_deps(modtool))

    # GitHub options that warrant a silent cleanup & exit
    if options.check_github:
        check_github()

    elif options.install_github_token:
        install_github_token(options.github_user, silent=build_option('silent'))

    elif options.close_pr:
        close_pr(options.close_pr, motivation_msg=options.close_pr_msg)

    elif options.list_prs:
        print(list_prs(options.list_prs))

    elif options.merge_pr:
        merge_pr(options.merge_pr)

    elif options.review_pr:
        print(review_pr(pr=options.review_pr, colored=use_color(options.color), testing=testing,
                        max_ecs=options.review_pr_max, filter_ecs=options.review_pr_filter))

    elif options.add_pr_labels:
        add_pr_labels(options.add_pr_labels)

    elif options.list_installed_software:
        detailed = options.list_installed_software == 'detailed'
        print(list_software(output_format=options.output_format, detailed=detailed, only_installed=True))

    elif options.list_software:
        print(list_software(output_format=options.output_format, detailed=options.list_software == 'detailed'))

    elif options.create_index:
        print_msg("Creating index for %s..." % options.create_index, prefix=False)
        index_fp = dump_index(options.create_index, max_age_sec=options.index_max_age)
        index = load_index(options.create_index)
        print_msg("Index created at %s (%d files)" % (index_fp, len(index)), prefix=False)

    # non-verbose cleanup after handling GitHub integration stuff or printing terse info
    early_stop_options = [
        options.add_pr_labels,
        options.check_eb_deps,
        options.check_github,
        options.create_index,
        options.install_github_token,
        options.list_installed_software,
        options.list_software,
        options.close_pr,
        options.list_prs,
        options.merge_pr,
        options.review_pr,
        options.terse,
        search_query,
    ]
    if any(early_stop_options):
        clean_exit(logfile, eb_tmpdir, testing, silent=True)

    # update session state
    eb_config = eb_go.generate_cmd_line(add_default=True)
    modlist = modtool.list()  # build options must be initialized first before 'module list' works
    init_session_state.update({'easybuild_configuration': eb_config})
    init_session_state.update({'module_list': modlist})
    _log.debug("Initial session state: %s" % init_session_state)

    if options.skip_test_step:
        if options.ignore_test_failure:
            raise EasyBuildError("Found both ignore-test-failure and skip-test-step enabled. "
                                 "Please use only one of them.")
        else:
            print_warning("Will not run the test step as requested via skip-test-step. "
                          "Consider using ignore-test-failure instead and verify the results afterwards")

    # if EasyStack file is provided, parse it, and loop over the items in the EasyStack file
    if options.easystack:
        if len(orig_paths) > 0:
            msg = '\n'.join([
                "Passing additional arguments when building from an EasyStack file is not supported.",
                "The following arguments will be ignored:",
            ] + orig_paths)
            print_warning(msg)
        do_cleanup = process_easystack(options.easystack, args, logfile, testing, init_session_state, do_build)
    else:
        do_cleanup = process_eb_args(orig_paths, eb_go, cfg_settings, modtool, testing, init_session_state,
                                     hooks, do_build)

    # stop logging and cleanup tmp log file, unless one build failed (individual logs are located in eb_tmpdir)
    stop_logging(logfile, logtostdout=options.logtostdout)
    if do_cleanup:
        cleanup(logfile, eb_tmpdir, testing, silent=False)


if __name__ == "__main__":
    try:
        main()
    except EasyBuildError as err:
        print_error(err.msg)
    except KeyboardInterrupt as err:
        print_error("Cancelled by user: %s" % err)
