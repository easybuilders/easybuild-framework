##
# Copyright 2018-2026 Ghent University
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

Authors:

* Kenneth Hoste (Ghent University)
* Emmanuel Kieffer (LuxProvide)
* Xavier Besseron (LuxProvide)
"""
import os
import re
import time
import sys

from easybuild.base import fancylogger
from easybuild.tools import LooseVersion
from easybuild.tools.build_log import EasyBuildError, print_msg, print_warning, EasyBuildExit
from easybuild.tools.config import JOB_DEPS_TYPE_ABORT_ON_ERROR, JOB_DEPS_TYPE_ALWAYS_RUN, build_option
from easybuild.tools.job.backend import JobBackend
from easybuild.tools.filetools import which
from easybuild.tools.run import run_shell_cmd


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
        for cmd in ['sbatch', 'scontrol', 'sacct']:
            path = which(cmd)
            if path is None:
                raise EasyBuildError("Required command '%s' not found", cmd)

        super().__init__(*args, **kwargs)
        # Interval between polls for status of jobs (in seconds), ie between each sacct call
        # Set default explicitly. Default value defined in tools/options.py is 30s does not seem to be used.
        self.job_polling_interval = build_option('job_polling_interval', default=30)
        if self.job_polling_interval < 1:
            raise EasyBuildError("Polling interval for Slurm backend cannot be less than 1s: %s",
                                 self.job_polling_interval)
        self.log.info("Polling interval is : %s", self.job_polling_interval)
        # Maximum number of concurrent jobs (queued and running)
        # Default value set in tools/options.py is 0
        self.job_max_jobs = sys.maxsize if build_option('job_max_jobs') == 0 else build_option('job_max_jobs')
        self.log.info("Maximum number of jobs in the queue is : %s", self.job_max_jobs)
        # Type of dependency to set between jobs
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
        res = run_shell_cmd("sbatch --version", hidden=True)
        slurm_ver = res.output.strip().split(' ')[-1]
        self.log.info("Found Slurm version %s", slurm_ver)

        if LooseVersion(slurm_ver) < LooseVersion(self.REQ_VERSION):
            raise EasyBuildError("Found Slurm version %s, but version %s or more recent is required",
                                 slurm_ver, self.REQ_VERSION)

    def init(self):
        """
        Initialise the PySlurm job backend.
        """
        self._jobs_to_submit = []    # Jobs to be submitted
        self._jobs_queued = {}       # Submitted but not completed
        self._jobs_completed = {}    # Submitted and completed execution successfully (zero exit code)
        self._jobs_failed = {}       # Submitted and completed execution unsuccessfully (non-zero exit code)
        self._jobs_skipped = []      # Not submitted because of failed dependencies or sbatch failed
        self._nb_jobs = 0            # Total number of jobs
        self._nb_jobs_submitted = 0  # Total number of submitted jobs

    def queue(self, job, dependencies=frozenset()):
        """
        Prepare a list of jobs to be submitted.

        :param job: job to queue.
        :param dependencies: jobs on which this job depends.
        """
        self._jobs_to_submit.append((job, dependencies))
        self._nb_jobs += 1

    def complete(self):
        """
        Submit a list of jobs and wait until completion
        """
        assert self._nb_jobs == len(self._jobs_to_submit)
        assert len(self._jobs_queued) == 0
        assert len(self._jobs_completed) == 0
        assert len(self._jobs_failed) == 0
        assert len(self._jobs_skipped) == 0
        assert self._nb_jobs_submitted == 0
        # Print info about the Slurm backend configuration
        print_msg(f"[Slurm backend] Number of jobs to submit: {self._nb_jobs}", log=self.log)
        print_msg(f"[Slurm backend] Max jobs: {self.job_max_jobs}", log=self.log)
        print_msg(f"[Slurm backend] Polling interval: {self.job_polling_interval}", log=self.log)
        # Process all jobs
        while self._nb_jobs > len(self._jobs_completed) + len(self._jobs_failed) + len(self._jobs_skipped):
            # While we still have jobs to submit and we didn't reach job_max_jobs jobs in the queue
            while len(self._jobs_to_submit) > 0 and len(self._jobs_queued) < self.job_max_jobs:
                job, dependencies = self._jobs_to_submit.pop(0)
                # Try to submit the job
                res = self._submit_job(job, dependencies)
                # Check if job was actually submitted
                if res == 'SUBMITTED':
                    assert job.jobid is not None
                    print_msg(f"[Slurm backend] Submitted {job.name} with JobID {job.jobid}", log=self.log)
                    self._jobs_queued[job.jobid] = job
                elif res == 'FAILED_DEPS':
                    print_msg(f"[Slurm backend] Skipped job {job.name} because of failed dependencies", log=self.log)
                    self._jobs_skipped.append((job, dependencies))
                elif res == 'FAILED_SBATCH':
                    # The sbatch command failed, it could be because one dependency completed and left the Slurm queue
                    if job.attempts < 3:
                        # - put the job back at the top of the list of jobs to be submitted
                        # - break the loop to update the jobs status with `sacct` before retrying
                        print_msg(f"[Slurm backend] Failed submission for job {job.name} "
                                  f"after {job.attempts} attempt(s), try again later", log=self.log)
                        self._jobs_to_submit.insert(0, (job, dependencies))
                        job.attempts += 1
                        break
                    else:
                        # - give up for this job and mark it as failed
                        print_msg(f"[Slurm backend] Failed submission for job {job.name} "
                                  f"after {job.attempts} attempts, skip job", log=self.log)
                        self._jobs_skipped.append((job, dependencies))
                else:
                    raise EasyBuildError("Unexpected state after called to submit_job(): %s", res)

            # Wait before checking the state of the jobs
            time.sleep(self.job_polling_interval)

            # If we have still jobs in the queue
            if len(self._jobs_queued) > 0:
                # Get the state of the submitted jobs using sacct
                submitted_job_ids = ','.join([str(job.jobid) for jobid, job in self._jobs_queued.items()])
                cmd = (f"sacct --allocations --noheader --parsable2 "
                       f"--jobs={submitted_job_ids} --format=JobID,State,Elapsed")
                sacct_res = run_shell_cmd(cmd, hidden=True, fail_on_error=False)
                # Handle any error in sacct
                if sacct_res.exit_code != EasyBuildExit.SUCCESS:
                    sacct_message = sacct_res.output.strip()
                    print_warning(f"Failed sacct command: {sacct_message}")
                    # Skip job status update, and return to the polling loop
                    continue
                # Process output of successful sacct
                out = sacct_res.output.strip()
                jobid_status_lines = out.split("\n")
                # Process each line of sacct output
                while len(jobid_status_lines) > 0:
                    # Retrieve info about the job
                    job_id, job_state, job_elapsed = jobid_status_lines.pop(0).split("|")
                    assert job_id in self._jobs_queued
                    job = self._jobs_queued[job_id]
                    job.slurm_state = job_state
                    job.elapsed = job_elapsed
                    # Udate the jobs_XXX dictionaries based on the job state
                    # cf https://slurm.schedmd.com/job_state_codes.html#states
                    if job_state == 'PENDING' or job_state == 'RUNNING':
                        # Nothing to be done, already in _jobs_queued
                        pass
                    elif job_state == 'COMPLETED':
                        self._jobs_completed[job_id] = job
                        del self._jobs_queued[job_id]
                    else:
                        # States 'FAILED', 'CANCELLED' and everything else
                        self._jobs_failed[job_id] = job
                        del self._jobs_queued[job_id]
                # Assert consistency of internal state
                assert self._nb_jobs == (len(self._jobs_to_submit)
                                         + len(self._jobs_queued)
                                         + len(self._jobs_completed)
                                         + len(self._jobs_failed)
                                         + len(self._jobs_skipped))
                assert self._nb_jobs_submitted == (len(self._jobs_queued)
                                                   + len(self._jobs_completed)
                                                   + len(self._jobs_failed)
                                                   + len(self._jobs_skipped))
                # Report current status
                self._print_status_report()

        print_msg("[Slurm backend] Done processing jobs", log=self.log)
        # Print a detailed summary of the results
        self._print_final_report()
        # Fail if at least one job has failed
        if len(self._jobs_failed) > 0 or len(self._jobs_skipped) > 0:
            error_msg = "%d jobs failed, %d jobs skipped" % (len(self._jobs_failed), len(self._jobs_skipped))
            raise EasyBuildError(error_msg)
        else:
            return os.EX_OK

    def make_job(self, script, name, env_vars=None, hours=None, cores=None):
        """Create and return a job dict with the given parameters."""
        return SlurmJob(script, name, env_vars=env_vars, hours=hours, cores=cores)

    def _submit_job(self, job, dependencies):
        """
        Submit a job to Slurm using sbatch.

        :param job: job to submit with sbatch.
        :param dependencies: jobs on which this job depends.
        :returns: the string 'SUBMITTED', 'FAILED_DEPS' or 'FAILED_SBATCH' based on the result of the submission.
        """
        submit_cmd = 'sbatch'
        # Submitting the job to the queue
        if dependencies:
            # Slurm job dependencies only work with recently-finished jobs, so
            # 1. Check the status of the jobs finished at the last polling
            # 2. Use Slurm `--dependency` to handle the on-going jobs (or recently finished)

            # Check if any finished dependency failed
            failed_deps = [d for d in dependencies if (d.is_finished() and not d.is_finished_ok())]
            if len(failed_deps) > 0:
                # If any failed dependency, skip submission
                str_failed_deps = ' '.join(["%s (%s: %s)" % (d.name, d.jobid, d.slurm_state) for d in failed_deps])
                job.message = "Failed dependencies: " + str_failed_deps
                self.log.info(f"Do not submit job {job.name} because of the following "
                              f"failed dependency: {str_failed_deps})")
                return 'FAILED_DEPS'
            # Get dependencies that did not finish running -> SUBMITTED, PENDING or RUNNING
            active_deps = [d for d in dependencies if (d.is_active())]
            # Indicate active dependencies to sbatch if there are any
            if len(active_deps) > 0:
                # Only use active dependencies because Slurm dependency only
                # work with 'recent' jobs (ie jobs still visible with squeue)
                job.job_specs['dependency'] = self.job_deps_type + ':' + ':'.join(str(d.jobid) for d in active_deps)
                # Make sure job that has invalid dependencies doesn't remain queued indefinitely
                submit_cmd += " --kill-on-invalid-dep=yes"

        self.log.info("Submitting job with following specs: %s", job.job_specs)
        for key in sorted(job.job_specs):
            submit_cmd += ' --%s "%s"' % (key, job.job_specs[key])

        cmd_res = run_shell_cmd(submit_cmd, hidden=True, fail_on_error=False)

        if cmd_res.exit_code != EasyBuildExit.SUCCESS:
            submission_message = cmd_res.output.strip()
            job.message = f"Submission failed, sbatch returned: '{submission_message}'"
            print_warning(f"Failed sbatch submission for job {job.name} with: {submission_message}")
            return 'FAILED_SBATCH'

        jobid_regex = re.compile("^Submitted batch job (?P<jobid>[0-9]+)")

        regex_res = jobid_regex.search(cmd_res.output)
        if regex_res:
            job.jobid = regex_res.group('jobid')
            self.log.info("Job submitted, got job ID %s", job.jobid)
        else:
            raise EasyBuildError("Failed to determine job ID from output of submission command: %s", cmd_res.output)

        self._nb_jobs_submitted += 1
        # Assume job state is 'PENDING' until it is updated again with sacct
        job.slurm_state = 'PENDING'
        return 'SUBMITTED'

    def _print_status_report(self):
        """
        Print a job status report to STDOUT and the log file.

        The number of jobs in each state is reported; the figures are extracted
        from the job lists maintained by the Slurm backend, and updated periodically
        by calling `squeue` after every 'job_polling_interval'.
        """
        # Count the jobs per status
        nb_to_submit = len(self._jobs_to_submit)
        nb_submitted = self._nb_jobs_submitted
        nb_pending = len([job.jobid for _, job in self._jobs_queued.items() if job.slurm_state == 'PENDING'])
        nb_running = len([job.jobid for _, job in self._jobs_queued.items() if job.slurm_state == 'RUNNING'])
        nb_completed = len(self._jobs_completed)
        nb_failed = len(self._jobs_failed)
        nb_skipped = len(self._jobs_skipped)
        nb_total = self._nb_jobs
        # Print summary
        msg = "[Slurm backend] Job overview: "
        msg += f"{nb_to_submit} not submitted, "
        msg += f"{nb_submitted} submitted, "
        msg += f"{nb_pending} pending, "
        msg += f"{nb_running} running, "
        msg += f"{nb_completed} completed, "
        msg += f"{nb_failed} failed, "
        msg += f"{nb_skipped} skipped "
        msg += f"(total: {nb_total}) "
        print_msg(msg, log=self.log, silent=build_option('silent'))

    def _print_final_report(self):
        """
        Print the final report of the job status to STDOUT and the log file.

        The report is organized in three categories:
        - completed jobs, for which EasyBuild ended successfully,
        - failed jobs, for which EasyBuild execution returned an error,
        - skipped jobs, that didn't run because of failed dependencies or submission error.

        For each job, it gives useful information for the user:
        - job name, ie the software name and version,
        - job status, as returned by Slurm or the Slurm backend if skipped,
        - job id, if successfully submitted,
        - execution time, if relevant,
        - log file for executed jobs, or the failure reason.
        """
        # Summary of completed jobs
        print_msg("[Slurm backend] List of completed jobs (%d):" % (len(self._jobs_completed)))
        for job in self._jobs_completed.values():
            logfile = job.job_specs['output'].replace("%j", str(job.jobid))
            msg = f"Job OK! Log file: {logfile}"
            self._print_final_report_line(job.name, job.slurm_state, job.jobid, job.elapsed, msg)
        # Summary of failed jobs
        print_msg("[Slurm backend] List of failed jobs (%d):" % (len(self._jobs_failed)))
        for job in self._jobs_failed.values():
            if job.slurm_state == 'FAILED':
                logfile = job.job_specs['output'].replace("%j", str(job.jobid))
                str_reason = f"Job failed! Log file: {logfile}"
            elif job.slurm_state == 'CANCELLED':
                str_reason = "Job cancelled! Failed dependencies?"
            else:
                str_reason = "Unknown reason!"
            self._print_final_report_line(job.name, job.slurm_state, job.jobid, job.elapsed, str_reason)
        # Summary of skipped jobs
        print_msg("[Slurm backend] List of skipped jobs (%d):" % (len(self._jobs_skipped)))
        for job, _deps in self._jobs_skipped:
            self._print_final_report_line(job.name, "SKIPPED", "Not submitted", "-", job.message)

    def _print_final_report_line(self, name, status, jobid, duration, msg):
        """
        Print a single line of the final report, for a given job

        For each job, it gives useful information for the user:
        - job name, ie the software name and version
        - job id, if successfully submitted
        - job status, as returned by Slurm or the Slurm backend if skipped
        - log file for executed jobs, or the failure reason
        """
        print_msg(f"    {name:60} | {status:>16} | {jobid:>13} | {duration:>12} | {msg}")


class SlurmJob:
    """Job class for SLURM jobs."""

    def __init__(self, script, name, env_vars=None, hours=None, cores=None):
        """Create a new Job to be submitted to SLURM."""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.jobid = None
        self.script = script
        self.name = name
        self.output_dir = build_option('job_output_dir') or ''
        self.message = None  # Store submission error or skip reason
        self.attempts = 1
        self.elapsed = None
        self.slurm_state = None  # Value returned by Slurm, cf https://slurm.schedmd.com/job_state_codes.html#states

        self.job_specs = {
            'job-name': self.name,
            # pattern for output file for submitted job;
            # SLURM replaces %j with job ID (see https://slurm.schedmd.com/sbatch.html#lbAH)
            # %x (job name) replacement needs SLURM >= 17.02.1, thus we add name ourselves
            'output': '%s-%%j.out' % os.path.join(self.output_dir, self.name),
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
            self.job_specs['ntasks'] = 1
            self.job_specs['cpus-per-task'] = cores
        else:
            self.log.warning("Number of cores to request not specified, falling back to whatever Slurm does by default")

    def is_active(self):
        """Return true if job has been submitted and it has not finished yet."""
        # Possible state values: https://slurm.schedmd.com/job_state_codes.html#states
        return self.slurm_state == 'PENDING' or self.slurm_state == 'RUNNING' or self.slurm_state == 'SUSPENDED'

    def is_finished(self):
        """Return true if has finished."""
        # Possible state values: https://slurm.schedmd.com/job_state_codes.html#states
        return self.slurm_state is not None and not self.is_active()

    def is_finished_ok(self):
        """Return true if has finished successfully."""
        # Possible state values: https://slurm.schedmd.com/job_state_codes.html#states
        return self.slurm_state == 'COMPLETED'
