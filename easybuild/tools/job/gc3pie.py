##
# Copyright 2015-2022 Ghent University
# Copyright 2015 S3IT, University of Zurich
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
Interface for submitting jobs via GC3Pie.

:author: Riccardo Murri (University of Zurich)
:author: Kenneth Hoste (Ghent University)
"""
from distutils.version import LooseVersion
import os
from time import gmtime, strftime
import time

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError, print_msg, print_warning
from easybuild.tools.config import JOB_DEPS_TYPE_ABORT_ON_ERROR, JOB_DEPS_TYPE_ALWAYS_RUN, build_option
from easybuild.tools.job.backend import JobBackend
from easybuild.tools.utilities import only_if_module_is_available


_log = fancylogger.getLogger('gc3pie', fname=False)


try:
    import gc3libs
    import gc3libs.exceptions
    from gc3libs import Application, Run, create_engine
    from gc3libs.quantity import hours as hr
    from gc3libs.workflow import AbortOnError, DependentTaskCollection

    # inject EasyBuild logger into GC3Pie
    gc3libs.log = fancylogger.getLogger('gc3pie', fname=False)
    # make handling of log.error compatible with stdlib logging
    gc3libs.log.raiseError = False

    # instruct GC3Pie to not ignore errors, but raise exceptions instead
    gc3libs.UNIGNORE_ALL_ERRORS = True

    # note: order of class inheritance is important!
    class AbortingDependentTaskCollection(AbortOnError, DependentTaskCollection):
        """
        A `DependentTaskCollection`:class: that aborts execution upon error.

        This is used to stop the build process in case some dependency
        fails.  See also `<https://github.com/easybuilders/easybuild-framework/issues/1441>`_
        """
        pass

except ImportError:
    _log.debug("Failed to import gc3libs from GC3Pie."
               " Silently ignoring, this is a real issue only when GC3Pie is used as backend for --job")


# eb --job --job-backend=GC3Pie
class GC3Pie(JobBackend):
    """
    Use the GC3Pie framework to submit and monitor compilation jobs,
    see http://gc3pie.readthedocs.org/.

    In contrast with accessing an external service, GC3Pie implements
    its own workflow manager, which means ``eb --job
    --job-backend=GC3Pie`` will keep running until all jobs have
    terminated.
    """

    REQ_VERSION = '2.5.0'

    @only_if_module_is_available('gc3libs', pkgname='gc3pie')
    def __init__(self, *args, **kwargs):
        """GC3Pie JobBackend constructor."""
        super(GC3Pie, self).__init__(*args, **kwargs)

    # _check_version is called by __init__, so guard it (too) with the decorator
    @only_if_module_is_available('gc3libs', pkgname='gc3pie')
    def _check_version(self):
        """Check whether GC3Pie version complies with required version."""

        try:
            from pkg_resources import get_distribution, DistributionNotFound
            pkg = get_distribution('gc3pie')

            if LooseVersion(pkg.version) < LooseVersion(self.REQ_VERSION):
                raise EasyBuildError("Found GC3Pie version %s, but version %s or more recent is required",
                                     pkg.version, self.REQ_VERSION)

        except ImportError:
            print_warning("Failed to check required GC3Pie version (>= %s)", self.REQ_VERSION)

        except DistributionNotFound as err:
            raise EasyBuildError("Cannot load GC3Pie package: %s", err)

    def init(self):
        """
        Initialise the GC3Pie job backend.
        """
        # List of config files for GC3Pie; non-existing ones will be
        # silently ignored.  The list here copies GC3Pie's default,
        # for the principle of minimal surprise, but there is no
        # strict requirement that this be done and EB could actually
        # choose to use a completely distinct set of conf. files.
        self.config_files = gc3libs.Default.CONFIG_FILE_LOCATIONS[:]
        cfgfile = build_option('job_backend_config')
        if cfgfile:
            self.config_files.append(cfgfile)

        self.output_dir = build_option('job_output_dir')
        self.job_cnt = 0

        job_deps_type = build_option('job_deps_type')
        if job_deps_type is None:
            job_deps_type = JOB_DEPS_TYPE_ABORT_ON_ERROR
            self.log.info("Using default job dependency type: %s", job_deps_type)
        else:
            self.log.info("Using specified job dependency type: %s", job_deps_type)

        if job_deps_type == JOB_DEPS_TYPE_ALWAYS_RUN:
            self.jobs = DependentTaskCollection(output_dir=self.output_dir)
        elif job_deps_type == JOB_DEPS_TYPE_ABORT_ON_ERROR:
            self.jobs = AbortingDependentTaskCollection(output_dir=self.output_dir)
        else:
            raise EasyBuildError("Unknown job dependency type specified: %s", job_deps_type)

        # after polling for job status, sleep for this time duration
        # before polling again (in seconds)
        self.poll_interval = build_option('job_polling_interval')

    def make_job(self, script, name, env_vars=None, hours=None, cores=None):
        """
        Create and return a job object with the given parameters.

        Argument *script* is the content of the job script
        itself, i.e., the sequence of shell commands that will be
        executed.

        Argument *name* sets the job's human-readable name.

        Optional argument *env_vars* is a dictionary with
        key-value pairs of environment variables that should be passed
        on to the job.

        Optional arguments *hours* and *cores* should be
        integer values:
        - *hours* must be in the range 1 .. ``MAX_WALLTIME``;
        - *cores* depends on which cluster the job is being run.
        """
        named_args = {
            'jobname': name,  # job name in GC3Pie
            'name': name,  # job name in EasyBuild
        }

        # environment
        if env_vars:
            named_args['environment'] = env_vars

        # input/output files for job (none)
        named_args['inputs'] = []
        named_args['outputs'] = []

        # job logs
        named_args.update({
            # join stdout/stderr in a single log
            'join': True,
            # location for log file
            'output_dir': self.output_dir,
            # log file name (including timestamp to try and ensure unique filename)
            'stdout': 'eb-%s-gc3pie-job-%s.log' % (name, strftime("%Y%M%d-UTC-%H-%M-%S", gmtime()))
        })

        # walltime
        max_walltime = build_option('job_max_walltime')
        if hours is None:
            hours = max_walltime
        if hours > max_walltime:
            self.log.warning("Specified %s hours, but this is impossible. (resetting to %s)" % (hours, max_walltime))
            hours = max_walltime
        named_args['requested_walltime'] = hours * hr

        if cores:
            named_args['requested_cores'] = cores
        else:
            self.log.warning("Number of cores to request not specified, falling back to GC3Pie default")

        return Application(['/bin/sh', '-c', script], **named_args)

    def queue(self, job, dependencies=frozenset()):
        """
        Add a job to the queue, optionally specifying dependencies.

        :param dependencies: jobs on which this job depends.
        """
        self.jobs.add(job, dependencies)
        # since it's not trivial to determine the correct job count from self.jobs, we keep track of a count ourselves
        self.job_cnt += 1

    def complete(self):
        """
        Complete a bulk job submission.

        Create engine, and progress it until all jobs have terminated.
        """
        # create an instance of `Engine` using the list of configuration files
        try:
            self._engine = create_engine(*self.config_files, resource_errors_are_fatal=True)

        except gc3libs.exceptions.Error as err:
            raise EasyBuildError("Failed to create GC3Pie engine: %s", err)

        # make sure that all job log files end up in the same directory, rather than renaming the output directory
        # see https://gc3pie.readthedocs.org/en/latest/programmers/api/gc3libs/core.html#gc3libs.core.Engine
        self._engine.retrieve_overwrites = True

        # some sites may not be happy with flooding the cluster with build jobs...
        self._engine.max_in_flight = build_option('job_max_jobs') or 0

        # Add your application to the engine. This will NOT submit
        # your application yet, but will make the engine *aware* of
        # the application.
        self._engine.add(self.jobs)

        # select a specific execution resource?
        target_resource = build_option('job_target_resource')
        if target_resource:
            res = self._engine.select_resource(target_resource)
            if res == 0:
                raise EasyBuildError("Failed to select target resource '%s' in GC3Pie", target_resource)

        # Periodically check the status of your application.
        while self.jobs.execution.state != Run.State.TERMINATED:
            # `Engine.progress()` will do the GC3Pie magic:
            # submit new jobs, update status of submitted jobs, get
            # results of terminating jobs etc...
            self._engine.progress()

            # report progress
            stats = self._engine.counts(only=Application)
            self._print_status_report(stats)

            # Wait a few seconds...
            time.sleep(self.poll_interval)

        # final status report
        print_msg("Done processing jobs", log=self.log, silent=build_option('silent'))
        self._print_status_report(stats)

        # fail if at least one job has failed
        if stats['failed'] > 0:
            error_msg = "%d jobs failed: %s" % (stats['failed'], ', '.join(self._list_failed_jobs()))
            raise EasyBuildError(error_msg)
        else:
            return os.EX_OK

    def _print_status_report(self, stats):
        """
        Print a job status report to STDOUT and the log file.

        The number of jobs in each state is reported; the
        figures are extracted from the `counts()` method of the
        currently-running GC3Pie engine.
        """
        states = ', '.join(["%d %s" % (stats[s], s.lower()) for s in stats
                            if s != 'total' and stats[s]])
        print_msg("GC3Pie job overview: %s (total: %s)" % (states, self.job_cnt),
                  log=self.log, silent=build_option('silent'))

    def _list_failed_jobs(self):
        """
        Return list of names of failed build jobs.
        """
        failed = []
        for job in self._engine.iter_tasks(only_cls=Application):
            if job.execution.returncode != 0:
                failed.append(job.name)
        return failed
