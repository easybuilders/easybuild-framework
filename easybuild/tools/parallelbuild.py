# #
# Copyright 2012-2018 Ghent University
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
Module for doing parallel builds. This uses a PBS-like cluster. You should be able to submit jobs (which can have
dependencies)

Support for PBS is provided via the PbsJob class. If you want you could create other job classes and use them here.

:author: Toon Willems (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Stijn De Weirdt (Ghent University)
"""
import math
import os
import re

from easybuild.framework.easyblock import get_easyblock_instance
from easybuild.framework.easyconfig.easyconfig import ActiveMNS
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, get_repository, get_repositorypath
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.job.backend import job_backend
from easybuild.tools.repository.repository import init_repository
from vsc.utils import fancylogger


_log = fancylogger.getLogger('parallelbuild', fname=False)


def _to_key(dep):
    """Determine key for specified dependency."""
    return ActiveMNS().det_full_module_name(dep)


def build_easyconfigs_in_parallel(build_command, easyconfigs, output_dir='easybuild-build', prepare_first=True):
    """
    Build easyconfigs in parallel by submitting jobs to a batch-queuing system.
    Return list of jobs submitted.

    Argument `easyconfigs` is a list of easyconfigs which can be
    built: e.g. they have no unresolved dependencies.  This function
    will build them in parallel by submitting jobs.

    :param build_command: build command to use
    :param easyconfigs: list of easyconfig files
    :param output_dir: output directory
    :param prepare_first: prepare by runnning fetch step first for each easyconfig
    """
    _log.info("going to build these easyconfigs in parallel: %s", easyconfigs)

    active_job_backend = job_backend()
    if active_job_backend is None:
        raise EasyBuildError("Can not use --job if no job backend is available.")

    try:
        active_job_backend.init()
    except RuntimeError as err:
        raise EasyBuildError("connection to server failed (%s: %s), can't submit jobs.", err.__class__.__name__, err)

    # dependencies have already been resolved,
    # so one can linearly walk over the list and use previous job id's
    jobs = []

    # keep track of which job builds which module
    module_to_job = {}

    for easyconfig in easyconfigs:
        # this is very important, otherwise we might have race conditions
        # e.g. GCC-4.5.3 finds cloog.tar.gz but it was incorrectly downloaded by GCC-4.6.3
        # running this step here, prevents this
        if prepare_first:
            prepare_easyconfig(easyconfig)

        # the new job will only depend on already submitted jobs
        _log.info("creating job for ec: %s" % easyconfig['ec'])
        new_job = create_job(active_job_backend, build_command, easyconfig, output_dir=output_dir)

        # filter out dependencies marked as external modules
        deps = [d for d in easyconfig['ec'].all_dependencies if not d.get('external_module', False)]

        dep_mod_names = map(ActiveMNS().det_full_module_name, deps)
        job_deps = [module_to_job[dep] for dep in dep_mod_names if dep in module_to_job]

        # actually (try to) submit job
        active_job_backend.queue(new_job, job_deps)
        _log.info("job %s for module %s has been submitted", new_job, new_job.module)

        # update dictionary
        module_to_job[new_job.module] = new_job
        jobs.append(new_job)

    active_job_backend.complete()

    return jobs


def submit_jobs(ordered_ecs, cmd_line_opts, testing=False, prepare_first=True):
    """
    Submit jobs.
    :param ordered_ecs: list of easyconfigs, in the order they should be processed
    :param cmd_line_opts: list of command line options (in 'longopt=value' form)
    :param testing: If `True`, skip actual job submission
    :param prepare_first: prepare by runnning fetch step first for each easyconfig
    """
    curdir = os.getcwd()

    # regex pattern for options to ignore (help options can't reach here)
    ignore_opts = re.compile('^--robot$|^--job$|^--try-.*$')

    # generate_cmd_line returns the options in form --longopt=value
    opts = [o for o in cmd_line_opts if not ignore_opts.match(o.split('=')[0])]

    # compose string with command line options, properly quoted and with '%' characters escaped
    opts_str = ' '.join(opts).replace('%', '%%')

    command = "unset TMPDIR && cd %s && eb %%(spec)s %s %%(add_opts)s --testoutput=%%(output_dir)s" % (curdir, opts_str)
    _log.info("Command template for jobs: %s" % command)
    if testing:
        _log.debug("Skipping actual submission of jobs since testing mode is enabled")
        return command
    else:
        return build_easyconfigs_in_parallel(command, ordered_ecs, prepare_first=prepare_first)


def create_job(job_backend, build_command, easyconfig, output_dir='easybuild-build'):
    """
    Creates a job to build a *single* easyconfig.

    :param job_backend: A factory object for querying server parameters and creating actual job objects
    :param build_command: format string for command, full path to an easyconfig file will be substituted in it
    :param easyconfig: easyconfig as processed by process_easyconfig
    :param output_dir: optional output path; --regtest-output-dir will be used inside the job with this variable

    returns the job
    """
    # capture PYTHONPATH, MODULEPATH and all variables starting with EASYBUILD
    easybuild_vars = {}
    for name in os.environ:
        if name.startswith("EASYBUILD"):
            easybuild_vars[name] = os.environ[name]

    for env_var in ["PYTHONPATH", "MODULEPATH"]:
        if env_var in os.environ:
            easybuild_vars[env_var] = os.environ[env_var]

    _log.info("Dictionary of environment variables passed to job: %s" % easybuild_vars)

    # obtain unique name based on name/easyconfig version tuple
    ec_tuple = (easyconfig['ec']['name'], det_full_ec_version(easyconfig['ec']))
    name = '-'.join(ec_tuple)

    # determine whether additional options need to be passed to the 'eb' command
    add_opts = ''
    if easyconfig['hidden']:
        add_opts += ' --hidden'

    # create command based on build_command template
    command = build_command % {
        'add_opts': add_opts,
        'output_dir': os.path.join(os.path.abspath(output_dir), name),
        'spec': easyconfig['spec'],
    }

    # just use latest build stats
    repo = init_repository(get_repository(), get_repositorypath())
    buildstats = repo.get_buildstats(*ec_tuple)
    extra = {}
    if buildstats:
        previous_time = buildstats[-1]['build_time']
        extra['hours'] = int(math.ceil(previous_time * 2 / 60))

    if build_option('job_cores'):
        extra['cores'] = build_option('job_cores')

    job = job_backend.make_job(command, name, easybuild_vars, **extra)
    job.module = easyconfig['ec'].full_mod_name

    return job


def prepare_easyconfig(ec):
    """
    Prepare for building specified easyconfig (fetch sources)
    :param ec: parsed easyconfig (EasyConfig instance)
    """
    try:
        easyblock_instance = get_easyblock_instance(ec)
        easyblock_instance.update_config_template_run_step()
        easyblock_instance.fetch_step(skip_checksums=True)
        _log.debug("Cleaning up log file %s..." % easyblock_instance.logfile)
        easyblock_instance.close_log()
        os.remove(easyblock_instance.logfile)
    except (OSError, EasyBuildError), err:
        raise EasyBuildError("An error occurred while preparing %s: %s", ec, err)
