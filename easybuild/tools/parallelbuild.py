# #
# Copyright 2012-2014 Ghent University
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
Module for doing parallel builds. This uses a PBS-like cluster. You should be able to submit jobs (which can have
dependencies)

Support for PBS is provided via the PbsJob class. If you want you could create other job classes and use them here.

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import math
import os
import re
import sys
from datetime import datetime

import easybuild.tools.config as config
from easybuild.framework.easyblock import build_easyconfigs, get_easyblock_instance
from easybuild.framework.easyconfig.tools import process_easyconfig, resolve_dependencies, skip_available
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import get_repository, get_repositorypath
from easybuild.tools.filetools import find_easyconfigs
from easybuild.tools.jenkins import aggregate_xml_in_dirs
from easybuild.tools.module_generator import det_full_module_name
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.pbs_job import PbsJob, connect_to_server, disconnect_from_server, get_ppn
from easybuild.tools.repository import init_repository
from vsc import fancylogger

_log = fancylogger.getLogger('parallelbuild', fname=False)

def build_easyconfigs_in_parallel(build_command, easyconfigs, output_dir=None, build_options=None, build_specs=None):
    """
    easyconfigs is a list of easyconfigs which can be built (e.g. they have no unresolved dependencies)
    this function will build them in parallel by submitting jobs
    @param build_command: build command to use
    @param easyconfigs: list of easyconfig files
    @param output_dir: output directory
    @param build_options: dictionary specifying build options (e.g. robot_path, check_osdeps, ...)
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    returns the jobs
    """
    _log.info("going to build these easyconfigs in parallel: %s", easyconfigs)
    job_ids = {}
    # dependencies have already been resolved,
    # so one can linearly walk over the list and use previous job id's
    jobs = []

    # create a single connection, and reuse it
    conn = connect_to_server()
    if conn is None:
        _log.error("connect_to_server returned %s, can't submit jobs." % (conn))

    # determine ppn once, and pass is to each job being created
    # this avoids having to figure out ppn over and over again, every time creating a temp connection to the server
    ppn = get_ppn()

    def tokey(dep):
        """Determine key for specified dependency."""
        return det_full_module_name(dep)

    for ec in easyconfigs:
        # This is very important, otherwise we might have race conditions
        # e.g. GCC-4.5.3 finds cloog.tar.gz but it was incorrectly downloaded by GCC-4.6.3
        # running this step here, prevents this
        prepare_easyconfig(ec, build_options=build_options, build_specs=build_specs)

        # the new job will only depend on already submitted jobs
        _log.info("creating job for ec: %s" % str(ec))
        new_job = create_job(build_command, ec, output_dir=output_dir, conn=conn, ppn=ppn)

        # sometimes unresolved_deps will contain things, not needed to be build
        job_deps = [job_ids[dep] for dep in map(tokey, ec['unresolved_deps']) if dep in job_ids]
        new_job.add_dependencies(job_deps)

        # place user hold on job to prevent it from starting too quickly,
        # we might still need it in the queue to set it as a dependency for another job;
        # only set hold for job without dependencies, other jobs have a dependency hold set anyway
        with_hold = False
        if not job_deps:
            with_hold = True

        # actually (try to) submit job
        new_job.submit(with_hold)
        _log.info("job for module %s has been submitted (job id: %s)" % (new_job.module, new_job.jobid))

        # update dictionary
        job_ids[new_job.module] = new_job.jobid
        new_job.cleanup()
        jobs.append(new_job)

    # release all user holds on jobs after submission is completed
    for job in jobs:
        if job.has_holds():
            _log.info("releasing hold on job %s" % job.jobid)
            job.release_hold()

    disconnect_from_server(conn)

    return jobs


def create_job(build_command, easyconfig, output_dir=None, conn=None, ppn=None):
    """
    Creates a job, to build a *single* easyconfig
    @param build_command: format string for command, full path to an easyconfig file will be substituted in it
    @param easyconfig: easyconfig as processed by process_easyconfig
    @param output_dir: optional output path; $EASYBUILDTESTOUTPUT will be set inside the job with this variable
    @param conn: open connection to PBS server
    @param ppn: ppn setting to use (# 'processors' (cores) per node to use)
    returns the job
    """
    if output_dir is None:
        output_dir = 'easybuild-build'

    # create command based on build_command template
    command = build_command % {'spec': easyconfig['spec']}

    # capture PYTHONPATH, MODULEPATH and all variables starting with EASYBUILD
    easybuild_vars = {}
    for name in os.environ:
        if name.startswith("EASYBUILD"):
            easybuild_vars[name] = os.environ[name]

    others = ["PYTHONPATH", "MODULEPATH"]

    for env_var in others:
        if env_var in os.environ:
            easybuild_vars[env_var] = os.environ[env_var]

    _log.info("Dictionary of environment variables passed to job: %s" % easybuild_vars)

    # obtain unique name based on name/easyconfig version tuple
    ec_tuple = (easyconfig['ec']['name'], det_full_ec_version(easyconfig['ec']))
    name = '-'.join(ec_tuple)

    var = config.oldstyle_environment_variables['test_output_path']
    easybuild_vars[var] = os.path.join(os.path.abspath(output_dir), name)

    # just use latest build stats
    repo = init_repository(get_repository(), get_repositorypath())
    buildstats = repo.get_buildstats(*ec_tuple)
    resources = {}
    if buildstats:
        previous_time = buildstats[-1]['build_time']
        resources['hours'] = int(math.ceil(previous_time * 2 / 60))

    job = PbsJob(command, name, easybuild_vars, resources=resources, conn=conn, ppn=ppn)
    job.module = det_full_module_name(easyconfig['ec'])

    return job


def prepare_easyconfig(ec, build_options=None, build_specs=None):
    """
    Prepare for building specified easyconfig (fetch sources)
    @param ec: parsed easyconfig
    @param build_options: dictionary specifying build options (e.g. robot_path, check_osdeps, ...)
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    """
    try:
        easyblock_instance = get_easyblock_instance(ec, build_options=build_options, build_specs=build_specs)
        easyblock_instance.update_config_template_run_step()
        easyblock_instance.fetch_step(skip_checksums=True)
        _log.debug("Cleaning up log file %s..." % easyblock_instance.logfile)
        easyblock_instance.close_log()
        os.remove(easyblock_instance.logfile)
    except (OSError, EasyBuildError), err:
        _log.error("An error occured while preparing %s: %s" % (ec, err))


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

        jobs = build_easyconfigs_in_parallel(command, resolved, output_dir=output_dir,
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
