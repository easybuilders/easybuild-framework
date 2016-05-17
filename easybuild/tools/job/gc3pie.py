##
# Copyright 2015-2016 Ghent University
# Copyright 2015 S3IT, University of Zurich
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
##
"""
Interface for submitting jobs via GC3Pie.

@author: Riccardo Murri (University of Zurich)
@author: Kenneth Hoste (Ghent University)
"""
from distutils.version import LooseVersion
from time import gmtime, strftime
import re
import time

from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import build_option
from easybuild.tools.job.backend import JobBackend
from easybuild.tools.utilities import only_if_module_is_available


_log = fancylogger.getLogger('gc3pie', fname=False)


try:
    import gc3libs
    import gc3libs.exceptions
    from gc3libs import Application, Run, create_engine
    from gc3libs.core import Engine
    from gc3libs.quantity import hours as hr
    from gc3libs.workflow import DependentTaskCollection

    # inject EasyBuild logger into GC3Pie
    gc3libs.log = fancylogger.getLogger('gc3pie', fname=False)
    # make handling of log.error compatible with stdlib logging
    gc3libs.log.raiseError = False

    # instruct GC3Pie to not ignore errors, but raise exceptions instead
    gc3libs.UNIGNORE_ALL_ERRORS = True

except ImportError as err:
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

    REQ_VERSION = '2.4.0'
    DEVELOPMENT_VERSION = 'development'  # 'magic' version string indicated non-released version
    REQ_SVN_REVISION = 4287  # use integer value, not a string!

    @only_if_module_is_available('gc3libs', pkgname='gc3pie')
    def __init__(self, *args, **kwargs):
        """GC3Pie constructor."""
        super(GC3Pie, self).__init__(*args, **kwargs)

    # _check_version is called by __init__, so guard it (too) with the decorator
    @only_if_module_is_available('gc3libs', pkgname='gc3pie')
    def _check_version(self):
        """Check whether GC3Pie version complies with required version."""
        # location of __version__ to use may change, depending on the minimal required SVN revision for development versions
        version_str = gc3libs.core.__version__

        version_regex = re.compile(r'^(?P<version>\S*) version \(SVN \$Revision: (?P<svn_rev>\d+)\s*\$\)')
        res = version_regex.search(version_str)
        if res:
            version = res.group('version')
            svn_rev = int(res.group('svn_rev'))
            self.log.debug("Parsed GC3Pie version info: '%s' (SVN rev: '%s')", version, svn_rev)

            if version == self.DEVELOPMENT_VERSION:
                # fall back to checking SVN revision for development versions
                if svn_rev < self.REQ_SVN_REVISION:
                    raise EasyBuildError("Found GC3Pie SVN revision %d, but revision %d or newer is required",
                                         svn_rev, self.REQ_SVN_REVISION)
            else:
                if LooseVersion(version) < LooseVersion(self.REQ_VERSION):
                    raise EasyBuildError("Found GC3Pie version %s, but version %s or more recent is required",
                                         version, self.REQ_VERSION)
        else:
            raise EasyBuildError("Failed to parse GC3Pie version string '%s' using pattern %s",
                                 version_str, version_regex.pattern)

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
        self.jobs = DependentTaskCollection(output_dir=self.output_dir)
        self.job_cnt = 0

        # after polling for job status, sleep for this time duration
        # before polling again (in seconds)
        self.poll_interval = build_option('job_polling_interval')

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
            'output_dir': self.output_dir,
            # log file name (including timestamp to try and ensure unique filename)
            'stdout': 'eb-%s-gc3pie-job-%s.log' % (name, strftime("%Y%M%d-UTC-%H-%M-%S", gmtime()))
        })

        # walltime
        max_walltime = build_option('job_max_walltime')
        if hours is None:
            hours = max_walltime
        if hours > max_walltime:
            self.log.warn("Specified %s hours, but this is impossible. (resetting to %s hours)" % (hours, max_walltime))
            hours = max_walltime
        named_args['requested_walltime'] = hours * hr

        if cores:
            named_args['requested_cores'] = cores
        else:
            self.log.warn("Number of cores to request not specified, falling back to whatever GC3Pie does by default")

        return Application(['/bin/sh', '-c', script], **named_args)

    def queue(self, job, dependencies=frozenset()):
        """
        Add a job to the queue, optionally specifying dependencies.

        @param dependencies: jobs on which this job depends.
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

        # Add your application to the engine. This will NOT submit
        # your application yet, but will make the engine *aware* of
        # the application.
        self._engine.add(self.jobs)

        # in case you want to select a specific resource, call
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
            self._print_status_report()

            # Wait a few seconds...
            time.sleep(self.poll_interval)

        # final status report
        print_msg("Done processing jobs", log=self.log, silent=build_option('silent'))
        self._print_status_report()

    def _print_status_report(self):
        """
        Print a job status report to STDOUT and the log file.

        The number of jobs in each state is reported; the
        figures are extracted from the `stats()` method of the
        currently-running GC3Pie engine.
        """
        stats = self._engine.stats(only=Application)
        states = ', '.join(["%d %s" % (stats[s], s.lower()) for s in stats if s != 'total' and stats[s]])
        print_msg("GC3Pie job overview: %s (total: %s)" % (states, self.job_cnt),
                  log=self.log, silent=build_option('silent'))
