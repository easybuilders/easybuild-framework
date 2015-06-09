##
# Copyright 2015-2015 Ghent University
# Copyright 2015 S3IT, University of Zurich
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
Interface for submitting jobs via GC3Pie.

@author: Riccardo Murri (University of Zurich)
@author: Kenneth Hoste (Ghent University)
"""
import os
import time

from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import build_option
from easybuild.tools.job.backend import JobBackend


_log = fancylogger.getLogger('gc3pie', fname=False)


try:
    import gc3libs
    from gc3libs import Application, Run, create_engine
    from gc3libs.core import Engine
    from gc3libs.quantity import hours as hr
    from gc3libs.workflow import DependentTaskCollection

    # inject EasyBuild logger into GC3Pie
    gc3libs.log = fancylogger.getLogger('gc3pie', fname=False)
    # make handling of log.error compatible with stdlib logging
    gc3libs.log.raiseError = False

    # GC3Pie is available, no need guard against import errors
    def gc3pie_imported(fn):
        """No-op decorator."""
        return fn

except ImportError as err:
    _log.debug("Failed to import gc3libs from GC3Pie."
               " Silently ignoring, this is a real issue only when GC3Pie is used as backend for --job")

    # GC3Pie not available, turn method in a raised EasyBuildError
    def gc3pie_imported(_):
        """Decorator which raises an EasyBuildError because GC3Pie is not available."""
        def fail(_):
            """Raise EasyBuildError since GC3Pie is not available."""
            errmsg = "gc3libs not available. Please make sure GC3Pie is installed and usable: %s"
            raise EasyBuildError(errmsg, err)

        return fail


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
    # After polling for job status, sleep for this time duration
    # before polling again. Duration is expressed in seconds.
    POLL_INTERVAL = 30

    @gc3pie_imported
    def init(self):
        """
        Initialise the job backend.

        Start a new list of submitted jobs.
        """
        self.output_dir = os.path.join(os.getcwd(), 'easybuild-gc3pie-jobs')
        self.jobs = DependentTaskCollection(output_dir=self.output_dir)

    @gc3pie_imported
    def make_job(self, script, name, env_vars=None, hours=None, cores=None):
        """
        Create and return a job object with the given parameters.

        First argument `server` is an instance of the corresponding
        `JobBackend` class, i.e., a `GC3Pie`:class: instance in this case.

        Second argument `script` is the content of the job script
        itself, i.e., the sequence of shell commands that will be
        executed.

        Third argument `name` sets the job human-readable name.

        Fourth (optional) argument `env_vars` is a dictionary with
        key-value pairs of environment variables that should be passed
        on to the job.

        Fifth and sixth (optional) arguments `hours` and `cores` should be
        integer values:
        * hours must be in the range 1 .. MAX_WALLTIME;
        * cores depends on which cluster the job is being run.
        """
        named_args = {
            'jobname': name, # job name in GC3Pie
            'name':    name, # job name in EasyBuild
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
            'output_dir': os.path.join(self.output_dir, name),
            # log file name
            'stdout': 'eb.log',
        })

        # resources
        if hours:
            named_args['requested_walltime'] = hours * hr
        if cores:
            named_args['requested_cores'] = cores

        return Application(['/bin/sh', '-c', script], **named_args)

    @gc3pie_imported
    def queue(self, job, dependencies=frozenset()):
        """
        Add a job to the queue, optionally specifying dependencies.

        @param dependencies: jobs on which this job depends.
        """
        self.jobs.add(job, dependencies)

    @gc3pie_imported
    def complete(self):
        """
        Complete a bulk job submission.

        Create engine, and progress it until all jobs have terminated.
        """
        # Create an instance of `Engine` using the configuration file present
        # in your home directory.
        self._engine = create_engine()

        # Add your application to the engine. This will NOT submit
        # your application yet, but will make the engine *aware* of
        # the application.
        self._engine.add(self.jobs)

        # in case you want to select a specific resource, call
        # `Engine.select_resource(<resource_name>)`

        # Periodically check the status of your application.
        while self.jobs.execution.state != Run.State.TERMINATED:
            # `Engine.progress()` will do the GC3Pie magic:
            # submit new jobs, update status of submitted jobs, get
            # results of terminating jobs etc...
            self._engine.progress()

            # report progress
            self._print_status_report(['total', 'SUBMITTED', 'RUNNING', 'ok', 'failed'])

            # Wait a few seconds...
            time.sleep(self.POLL_INTERVAL)

        # final status report
        self._print_status_report(['total', 'ok', 'failed'])

    @gc3pie_imported
    def _print_status_report(self, states=('total', 'ok', 'failed')):
        """
        Print a job status report to STDOUT and the log file.

        The number of jobs in any of the given states is reported; the
        figures are extracted from the `stats()` method of the
        currently-running GC3Pie engine.  Additional keyword arguments
        can override specific stats; this is used, e.g., to correctly
        report the number of total jobs right from the start.
        """
        stats = self._engine.stats(only=Application)
        job_overview = ', '.join(["%d %s" % (stats[s], s.lower()) for s in states if stats[s]])
        print_msg("GC3Pie job overview: %s" % job_overview, log=_log, silent=build_option('silent'))
