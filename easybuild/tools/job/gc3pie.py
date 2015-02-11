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
"""Interface for submitting jobs via gc3pie"""


try:
    from gc3libs import Application, Run, create_engine
    from gc3libs.core import Engine
    from gc3libs.quantity import hours as hr
    from gc3libs.workflow import DependentTaskCollection
    HAVE_GC3PIE = True
except ImportError:
    HAVE_GC3PIE = False

from easybuild.tools.job import JobServer


# eb --job --job-backend=GC3Pie
class GC3Pie(JobServer):
    """
    Use the GC3Pie__ framework to submit and monitor compilation jobs.

    In contrast with acessing an external service, GC3Pie implements
    its own workflow manager, which means ``eb --job
    --job-backend=GC3Pie`` will keep running until all jobs have
    terminated.

    .. __: http://gc3pie.googlecode.com/
    """

    USABLE = HAVE_GC3PIE

    def begin(self):
        """
        Start a bulk job submission.

        Removes any reference to previously-submitted jobs.
        """
        self._jobs = DependentTaskCollection()

    def make_job(self, server, script, name, env_vars=None, hours=None, cores=None):
        """
        Create and return a job object with the given parameters.

        First argument `server` is an instance of the corresponding
        `JobServer` class, i.e., a `GC3Pie`:class: instance in this case.

        Second argument `script` is the content of the job script
        itself, i.e., the sequence of shell commands that will be
        executed.

        Third argument `name` sets the job human-readable name.

        Fourth (optional) argument `env_vars` is a dictionary with
        key-value pairs of environment variables that should be passed
        on to the job.

        Fifth and sith (optional) arguments `hours` and `cores` should be
        integer values:
        * hours must be in the range 1 .. MAX_WALLTIME;
        * cores depends on which cluster the job is being run.
        """
        extra_args = {}
        if env_vars:
            extra_args['environment'] = env_vars
        if hours:
            extra_args['requested_walltime'] = hours*hr
        if cores:
            extra_args['requested_cores'] = cores
        return Application(
            # arguments
            arguments=script.split(), # FIXME: breaks if args contain spaces!
            # no need to stage files in or out
            inputs=[],
            outputs=[],
            # where should the output (STDOUT/STDERR) files be downloaded to?
            output_dir=('/tmp/%s' % name),
            # capture STDOUT and STDERR
            stdout='stdout.log',
            join=True,
            **extra_args
            )

    def submit(self, job, after=frozenset()):
        """
        Submit a job to the batch-queueing system, optionally specifying dependencies.

        If second optional argument `after` is given, it must be a
        sequence of jobs that must be successfully terminated before
        the new job can run.

        Actual submission is delayed until `commit()` is called.
        """
        self._jobs.add(job, after)

    def commit(self):
        """
        End a bulk job submission.

        Releases any jobs that were possibly queued since the last
        `begin()` call.

        No more job submissions should be attempted after `commit()`
        has been called, until `begin()` is invoked again.
        """
        # Create an instance of `Engine` using the configuration file present
        # in your home directory.
        engine = gc3libs.create_engine()

        # Add your application to the engine. This will NOT submit
        # your application yet, but will make the engine *aware* of
        # the application.
        engine.add(self._jobs)

        # in case you want to select a specific resource, call
        # `Engine.select_resource(<resource_name>)`

        # Periodically check the status of your application.
        while self._jobs.execution.state != Run.State.TERMINATED:
            # `Engine.progress()` will do the GC3Pie magic:
            # submit new jobs, update status of submitted jobs, get
            # results of terminating jobs etc...
            engine.progress()

            # Wait a few seconds...
            time.sleep(1)
