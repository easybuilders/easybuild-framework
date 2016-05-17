# #
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
Module for doing parallel builds. This uses a PBS-like cluster. You should be able to submit jobs (which can have
dependencies)

Support for PBS is provided via the PbsJob class. If you want you could create other job classes and use them here.

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import copy
import os
import sys
from datetime import datetime
from time import gmtime, strftime

from easybuild.framework.easyblock import build_easyconfigs
from easybuild.framework.easyconfig.tools import process_easyconfig
from easybuild.framework.easyconfig.tools import skip_available
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.filetools import find_easyconfigs, mkdir, read_file, write_file
from easybuild.tools.github import create_gist, post_comment_in_issue
from easybuild.tools.jenkins import aggregate_xml_in_dirs
from easybuild.tools.parallelbuild import build_easyconfigs_in_parallel
from easybuild.tools.robot import resolve_dependencies
from easybuild.tools.systemtools import get_system_info
from easybuild.tools.version import FRAMEWORK_VERSION, EASYBLOCKS_VERSION
from vsc.utils import fancylogger


_log = fancylogger.getLogger('testing', fname=False)


def regtest(easyconfig_paths, modtool, build_specs=None):
    """
    Run regression test, using easyconfigs available in given path
    @param easyconfig_paths: path of easyconfigs to run regtest on
    @param modtool: ModulesTool instance to use
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    """

    cur_dir = os.getcwd()

    aggregate_regtest = build_option('aggregate_regtest')
    if aggregate_regtest is not None:
        output_file = os.path.join(aggregate_regtest, "%s-aggregate.xml" % os.path.basename(aggregate_regtest))
        aggregate_xml_in_dirs(aggregate_regtest, output_file)
        _log.info("aggregated xml files inside %s, output written to: %s" % (aggregate_regtest, output_file))
        sys.exit(0)

    # create base directory, which is used to place all log files and the test output as xml
    regtest_output_dir = build_option('regtest_output_dir')
    testoutput = build_option('testoutput')
    if regtest_output_dir is not None:
        output_dir = regtest_output_dir
    elif testoutput is not None:
        output_dir = os.path.abspath(testoutput)
    else:
        # default: current dir + easybuild-test-[timestamp]
        dirname = "easybuild-test-%s" % datetime.now().strftime("%Y%m%d%H%M%S")
        output_dir = os.path.join(cur_dir, dirname)

    mkdir(output_dir, parents=True)

    # find all easyconfigs
    ecfiles = []
    if easyconfig_paths:
        for path in easyconfig_paths:
            ecfiles += find_easyconfigs(path, ignore_dirs=build_option('ignore_dirs'))
    else:
        raise EasyBuildError("No easyconfig paths specified.")

    test_results = []

    # process all the found easyconfig files
    easyconfigs = []
    for ecfile in ecfiles:
        try:
            easyconfigs.extend(process_easyconfig(ecfile, build_specs=build_specs))
        except EasyBuildError, err:
            test_results.append((ecfile, 'parsing_easyconfigs', 'easyconfig file error: %s' % err, _log))

    # skip easyconfigs for which a module is already available, unless forced
    if not build_option('force'):
        _log.debug("Skipping easyconfigs from %s that already have a module available..." % easyconfigs)
        easyconfigs = skip_available(easyconfigs, modtool)
        _log.debug("Retained easyconfigs after skipping: %s" % easyconfigs)

    if build_option('sequential'):
        return build_easyconfigs(easyconfigs, output_dir, test_results)
    else:
        resolved = resolve_dependencies(easyconfigs, modtool)

        cmd = "eb %(spec)s --regtest --sequential -ld --testoutput=%(output_dir)s"
        command = "unset TMPDIR && cd %s && %s; " % (cur_dir, cmd)
        # retry twice in case of failure, to avoid fluke errors
        command += "if [ $? -ne 0 ]; then %(cmd)s --force && %(cmd)s --force; fi" % {'cmd': cmd}

        build_easyconfigs_in_parallel(command, resolved, output_dir=output_dir)

        _log.info("Submitted regression test as jobs, results in %s" % output_dir)

        return True  # success


def session_state():
    """Get session state: timestamp, dump of environment, system info."""
    return {
        'time': gmtime(),
        'environment': copy.deepcopy(os.environ),
        'system_info': get_system_info(),
    }


def create_test_report(msg, ecs_with_res, init_session_state, pr_nr=None, gist_log=False):
    """Create test report for easyconfigs PR, in Markdown format."""
    user = build_option('github_user')

    end_time = gmtime()

    # create a gist with a full test report
    test_report = []
    if pr_nr is not None:
        test_report.extend([
            "Test report for https://github.com/hpcugent/easybuild-easyconfigs/pull/%s" % pr_nr,
            "",
        ])
    test_report.extend([
        "#### Test result",
        "%s" % msg,
        "",
    ])

    build_overview = []
    for (ec, ec_res) in ecs_with_res:
        test_log = ''
        if ec_res.get('success', False):
            test_result = 'SUCCESS'
        else:
            # compose test result string
            test_result = 'FAIL '
            if 'err' in ec_res:
                if isinstance(ec_res['err'], EasyBuildError):
                    test_result += '(build issue)'
                else:
                    test_result += '(unhandled exception: %s)' % ec_res['err'].__class__.__name__
            else:
                test_result += '(unknown cause, not an exception?!)'

            # create gist for log file (if desired and available)
            if gist_log and 'log_file' in ec_res:
                logtxt = read_file(ec_res['log_file'])
                partial_log_txt = '\n'.join(logtxt.split('\n')[-500:])
                descr = "(partial) EasyBuild log for failed build of %s" % ec['spec']
                if pr_nr is not None:
                    descr += " (PR #%s)" % pr_nr
                fn = '%s_partial.log' % os.path.basename(ec['spec'])[:-3]
                gist_url = create_gist(partial_log_txt, fn, descr=descr, github_user=user)
                test_log = "(partial log available at %s)" % gist_url

        build_overview.append(" * **%s** _%s_ %s" % (test_result, os.path.basename(ec['spec']), test_log))
    test_report.extend(["#### Overview of tested easyconfigs (in order)"] + build_overview + [""])

    time_format = "%a, %d %b %Y %H:%M:%S +0000 (UTC)"
    start_time = strftime(time_format, init_session_state['time'])
    end_time = strftime(time_format, end_time)
    test_report.extend(["#### Time info", " * start: %s" % start_time, " * end: %s" % end_time, ""])

    eb_config = [x for x in sorted(init_session_state['easybuild_configuration'])]
    test_report.extend([
        "#### EasyBuild info",
        " * easybuild-framework version: %s" % FRAMEWORK_VERSION,
        " * easybuild-easyblocks version: %s" % EASYBLOCKS_VERSION,
        " * command line:",
        "```",
        "eb %s" % ' '.join(sys.argv[1:]),
        "```",
        " * full configuration (includes defaults):",
        "```",
    ] + eb_config + ["````", ""])

    system_info = init_session_state['system_info']
    system_info = [" * _%s:_ %s" % (key.replace('_', ' '), system_info[key]) for key in sorted(system_info.keys())]
    test_report.extend(["#### System info"] + system_info + [""])

    module_list = init_session_state['module_list']
    if module_list:
        module_list = [" * %s" % mod['mod_name'] for mod in module_list]
    else:
        module_list = [" * (none)"]
    test_report.extend(["#### List of loaded modules"] + module_list + [""])

    environ_dump = init_session_state['environment']
    environment = []
    env_filter = build_option('test_report_env_filter')

    for key in sorted(environ_dump.keys()):
        if env_filter is not None and env_filter.search(key):
            continue
        else:
            environment += ["%s = %s" % (key, environ_dump[key])]

    test_report.extend(["#### Environment", "```"] + environment + ["```"])

    return '\n'.join(test_report)


def upload_test_report_as_gist(test_report, descr=None, fn=None):
    """Upload test report as a gist."""
    if descr is None:
        descr = "EasyBuild test report"
    if fn is None:
        fn = 'easybuild_test_report_%s.md' % strftime("%Y%M%d-UTC-%H-%M-%S", gmtime())

    user = build_option('github_user')

    gist_url = create_gist(test_report, descr=descr, fn=fn, github_user=user)
    return gist_url


def post_easyconfigs_pr_test_report(pr_nr, test_report, msg, init_session_state, success):
    """Post test report in a gist, and submit comment in easyconfigs PR."""
    user = build_option('github_user')

    # create gist with test report
    descr = "EasyBuild test report for easyconfigs PR #%s" % pr_nr
    fn = 'easybuild_test_report_easyconfigs_pr%s_%s.md' % (pr_nr, strftime("%Y%M%d-UTC-%H-%M-%S", gmtime()))
    gist_url = upload_test_report_as_gist(test_report, descr=descr, fn=fn)

    # post comment to report test result
    system_info = init_session_state['system_info']
    short_system_info = "%(hostname)s - %(os_type)s %(os_name)s %(os_version)s, %(cpu_model)s, Python %(pyver)s" % {
        'cpu_model': system_info['cpu_model'],
        'hostname': system_info['hostname'],
        'os_name': system_info['os_name'],
        'os_type': system_info['os_type'],
        'os_version': system_info['os_version'],
        'pyver': system_info['python_version'].split(' ')[0],
    }
    comment_lines = [
        "Test report by @%s" % user,
        ('**FAILED**', '**SUCCESS**')[success],
        msg,
        short_system_info,
        "See %s for a full test report." % gist_url,
    ]
    comment = '\n'.join(comment_lines)
    post_comment_in_issue(pr_nr, comment, github_user=user)

    msg = "Test report uploaded to %s and mentioned in a comment in easyconfigs PR#%s" % (gist_url, pr_nr)
    return msg


def overall_test_report(ecs_with_res, orig_cnt, success, msg, init_session_state):
    """
    Upload/dump overall test report
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
            txt = post_easyconfigs_pr_test_report(pr_nr, test_report, msg, init_session_state, success)
        else:
            # only upload test report as a gist
            gist_url = upload_test_report_as_gist(test_report)
            txt = "Test report uploaded to %s" % gist_url
    else:
        test_report = create_test_report(msg, ecs_with_res, init_session_state)
        txt = None
    _log.debug("Test report: %s" % test_report)

    if dump_path is not None:
        write_file(dump_path, test_report)
        _log.info("Test report dumped to %s" % dump_path)

    return txt
