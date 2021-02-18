##
# Copyright 2018-2021 Ghent University
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
##
"""
Support for using Slurm as a backend for --job

:author: Kenneth Hoste (Ghent University)
"""
import re
from distutils.version import LooseVersion

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import JOB_DEPS_TYPE_ABORT_ON_ERROR, JOB_DEPS_TYPE_ALWAYS_RUN, build_option
from easybuild.tools.job.backend import JobBackend
from easybuild.tools.filetools import which
from easybuild.tools.run import run_cmd


_log = fancylogger.getLogger('slurm', fname=False)


class Slurm(JobBackend):
    """
    Manage SLURM server communication and create `SlurmJob` objects.
    """

    # Oldest version tested, may also work with earlier releases
    REQ_VERSION = '16.05'

    def __init__(self, *args, **kwargs):
        """Constructor."""

        # early check for required commands
        for cmd in ['sbatch', 'scontrol']:
            path = which(cmd)
            if path is None:
                raise EasyBuildError("Required command '%s' not found", cmd)

        super(Slurm, self).__init__(*args, **kwargs)

        job_deps_type = build_option('job_deps_type')
        if job_deps_type is None:
            job_deps_type = JOB_DEPS_TYPE_ABORT_ON_ERROR
            self.log.info("Using default job dependency type: %s", job_deps_type)
        else:
            self.log.info("Using specified job dependency type: %s", job_deps_type)

        if job_deps_type == JOB_DEPS_TYPE_ABORT_ON_ERROR:
            self.job_deps_type = 'afterok'
        elif job_deps_type == JOB_DEPS_TYPE_ALWAYS_RUN:
            self.job_deps_type = 'afterany'
        else:
            raise EasyBuildError("Unknown job dependency type specified: %s", job_deps_type)

    def _check_version(self):
        """Check whether version of Slurm complies with required version."""
        (out, _) = run_cmd("sbatch --version", trace=False)
        slurm_ver = out.strip().split(' ')[-1]
        self.log.info("Found Slurm version %s", slurm_ver)

        if LooseVersion(slurm_ver) < LooseVersion(self.REQ_VERSION):
            raise EasyBuildError("Found Slurm version %s, but version %s or more recent is required",
                                 slurm_ver, self.REQ_VERSION)

    def init(self):
        """
        Initialise the PySlurm job backend.
        """
        self._submitted = []

    def queue(self, job, dependencies=frozenset()):
        """
        Add a job to the queue.

        :param dependencies: jobs on which this job depends.
        """
        submit_cmd = 'sbatch'

        if dependencies:
            job.job_specs['dependency'] = self.job_deps_type + ':' + ':'.join(str(d.jobid) for d in dependencies)
            # make sure job that has invalid dependencies doesn't remain queued indefinitely
            submit_cmd += " --kill-on-invalid-dep=yes"

        # submit job with hold in place
        job.job_specs['hold'] = True

        self.log.info("Submitting job with following specs: %s", job.job_specs)
        for key in sorted(job.job_specs):
            if key in ['hold']:
                if job.job_specs[key]:
                    submit_cmd += " --%s" % key
            else:
                submit_cmd += ' --%s "%s"' % (key, job.job_specs[key])

        (out, _) = run_cmd(submit_cmd, trace=False)

        jobid_regex = re.compile("^Submitted batch job (?P<jobid>[0-9]+)")

        res = jobid_regex.search(out)
        if res:
            job.jobid = res.group('jobid')
            self.log.info("Job submitted, got job ID %s", job.jobid)
        else:
            raise EasyBuildError("Failed to determine job ID from output of submission command: %s", out)

        self._submitted.append(job)

    def complete(self):
        """
        Complete a bulk job submission.

        Release all user holds on submitted jobs, and disconnect from server.
        """
        job_ids = []
        for job in self._submitted:
            if job.job_specs['hold']:
                self.log.info("releasing user hold on job %s" % job.jobid)
                job_ids.append(job.jobid)

        if job_ids:
            run_cmd("scontrol release %s" % ' '.join(job_ids), trace=False)

        submitted_jobs = '; '.join(["%s (%s): %s" % (job.name, job.module, job.jobid) for job in self._submitted])
        print_msg("List of submitted jobs (%d): %s" % (len(self._submitted), submitted_jobs), log=self.log)

    def make_job(self, script, name, env_vars=None, hours=None, cores=None):
        """Create and return a job dict with the given parameters."""
        return SlurmJob(script, name, env_vars=env_vars, hours=hours, cores=cores)


class SlurmJob(object):
    """Job class for SLURM jobs."""

    def __init__(self, script, name, env_vars=None, hours=None, cores=None):
        """Create a new Job to be submitted to SLURM."""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.jobid = None
        self.script = script
        self.name = name

        self.job_specs = {
            'job-name': self.name,
            # pattern for output file for submitted job;
            # SLURM replaces %j with job ID (see https://slurm.schedmd.com/sbatch.html#lbAH)
            # %x (job name) replacement needs SLURM >= 17.02.1, thus we add name ourselves
            'output': '%s-%%j.out' % self.name,
            'wrap': self.script,
        }

        if env_vars:
            self.job_specs['export'] = ','.join(sorted(env_vars.keys()))

        max_walltime = build_option('job_max_walltime')
        if hours is None:
            hours = max_walltime
        if hours > max_walltime:
            self.log.warning("Specified %s hours, but this is impossible. (resetting to %s)" % (hours, max_walltime))
            hours = max_walltime
        self.job_specs['time'] = hours * 60

        if cores:
            self.job_specs['nodes'] = 1
            self.job_specs['ntasks'] = cores
        else:
            self.log.warning("Number of cores to request not specified, falling back to whatever Slurm does by default")
