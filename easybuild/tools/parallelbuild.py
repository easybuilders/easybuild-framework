##
# Copyright 2012-2013 Ghent University
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

import easybuild.tools.config as config
from easybuild.framework.easyblock import get_class
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import get_repository, get_repositorypath
from easybuild.tools.filetools import read_file
from easybuild.tools.module_generator import det_full_module_name
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.pbs_job import PbsJob, connect_to_server, disconnect_from_server, get_ppn
from easybuild.tools.repository import init_repository
from vsc import fancylogger

_log = fancylogger.getLogger('parallelbuild', fname=False)

def build_easyconfigs_in_parallel(build_command, easyconfigs, output_dir, robot_path=None):
    """
    easyconfigs is a list of easyconfigs which can be built (e.g. they have no unresolved dependencies)
    this function will build them in parallel by submitting jobs

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
        prepare_easyconfig(ec, robot_path=robot_path)

        # the new job will only depend on already submitted jobs
        _log.info("creating job for ec: %s" % str(ec))
        new_job = create_job(build_command, ec, output_dir, conn=conn, ppn=ppn)

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


def create_job(build_command, easyconfig, output_dir="", conn=None, ppn=None):
    """
    Creates a job, to build a *single* easyconfig
    build_command is a format string in which a full path to an eb file will be substituted
    easyconfig should be in the format as processEasyConfig returns them
    output_dir is an optional path. EASYBUILDTESTOUTPUT will be set inside the job with this variable
    returns the job
    """
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


def get_easyblock_instance(easyconfig, robot_path=None):
    """
    Get an instance for this easyconfig
    easyconfig is in the format provided by processEasyConfig
    log is a logger object

    returns an instance of EasyBlock (or subclass thereof)
    """
    spec = easyconfig['spec']
    name = easyconfig['ec']['name']

    # handle easyconfigs with custom easyblocks
    easyblock = None
    reg = re.compile(r"^\s*easyblock\s*=(.*)$")
    txt = read_file(spec)
    for line in txt.split('\n'):
        match = reg.search(line)
        if match:
            easyblock = eval(match.group(1))
            break

    app_class = get_class(easyblock, name=name)
    return app_class(spec, debug=True, robot_path=robot_path)


def prepare_easyconfig(ec, robot_path=None):
    """ prepare for building """
    try:
        easyblock_instance = get_easyblock_instance(ec, robot_path=robot_path)
        easyblock_instance.update_config_template_run_step()
        easyblock_instance.fetch_step()
        _log.debug("Cleaning up log file %s..." % easyblock_instance.logfile)
        easyblock_instance.close_log()
        os.remove(easyblock_instance.logfile)
    except (OSError, EasyBuildError), err:
        _log.error("An error occured while preparing %s: %s" % (ec, err))
