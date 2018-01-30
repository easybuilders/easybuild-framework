##
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
##
"""
Interface module to TORQUE (PBS).

:author: Stijn De Weirdt (Ghent University)
:author: Toon Willems (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
from distutils.version import LooseVersion
import os
import re
import tempfile
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import build_option
from easybuild.tools.job.backend import JobBackend
from easybuild.tools.utilities import only_if_module_is_available


_log = fancylogger.getLogger('pbs_python', fname=False)


# extend paramater should be 'NULL' in some functions because this is required by the python api
NULL = 'NULL'
# list of known hold types
KNOWN_HOLD_TYPES = []

try:
    import pbs
    from PBSQuery import PBSQuery
    KNOWN_HOLD_TYPES = [pbs.USER_HOLD, pbs.OTHER_HOLD, pbs.SYSTEM_HOLD]

except ImportError as err:
    _log.debug("Failed to import pbs/PBSQuery from pbs_python."
               " Silently ignoring, this is a real issue only when pbs_python is used as backend for --job")


class PbsPython(JobBackend):
    """
    Manage PBS server communication and create `PbsJob` objects.
    """

    # pbs_python 4.1.0 introduces the pbs.version variable we rely on
    REQ_VERSION = '4.1.0'

    # _check_version is called by __init__, so guard it (too) with the decorator
    @only_if_module_is_available('pbs', pkgname='pbs_python')
    def _check_version(self):
        """Check whether pbs_python version complies with required version."""
        version_regex = re.compile('pbs_python version (?P<version>.*)')
        res = version_regex.search(pbs.version)
        if res:
            version = res.group('version')
            if LooseVersion(version) < LooseVersion(self.REQ_VERSION):
                raise EasyBuildError("Found pbs_python version %s, but version %s or more recent is required",
                                     version, self.REQ_VERSION)
        else:
            raise EasyBuildError("Failed to parse pbs_python version string '%s' using pattern %s",
                                 pbs.version, version_regex.pattern)

    def __init__(self, *args, **kwargs):
        """Constructor."""
        pbs_server = kwargs.pop('pbs_server', None)

        super(PbsPython, self).__init__(*args, **kwargs)

        self.pbs_server = pbs_server or build_option('job_target_resource') or pbs.pbs_default()
        self.conn = None
        self._ppn = None

    def init(self):
        """
        Initialise the job backend.

        Connect to the PBS server & reset list of submitted jobs.
        """
        self.connect_to_server()
        self._submitted = []

    def connect_to_server(self):
        """Connect to PBS server, set and return connection."""
        if not self.conn:
            self.conn = pbs.pbs_connect(self.pbs_server)
        return self.conn

    def queue(self, job, dependencies=frozenset()):
        """
        Add a job to the queue.

        :param dependencies: jobs on which this job depends.
        """
        if dependencies:
            job.add_dependencies(dependencies)
        job._submit()
        self._submitted.append(job)

    def complete(self):
        """
        Complete a bulk job submission.

        Release all user holds on submitted jobs, and disconnect from server.
        """
        for job in self._submitted:
            if job.has_holds():
                self.log.info("releasing user hold on job %s" % job.jobid)
                job.release_hold()

        self.disconnect_from_server()

        # print list of submitted jobs
        submitted_jobs = '; '.join(["%s (%s): %s" % (job.name, job.module, job.jobid) for job in self._submitted])
        print_msg("List of submitted jobs (%d): %s" % (len(self._submitted), submitted_jobs), log=self.log)

        # determine leaf nodes in dependency graph, and report them
        all_deps = set()
        for job in self._submitted:
            all_deps = all_deps.union(job.deps)

        leaf_nodes = []
        for job in self._submitted:
            if job.jobid not in all_deps:
                leaf_nodes.append(str(job.jobid).split('.')[0])

        self.log.info("Job ids of leaf nodes in dep. graph: %s" % ','.join(leaf_nodes))

    def disconnect_from_server(self):
        """Disconnect current connection."""
        pbs.pbs_disconnect(self.conn)
        self.conn = None

    def _get_ppn(self):
        """Guess PBS' `ppn` value for a full node."""
        # cache this value as it's not likely going to change over the
        # `eb` script runtime ...
        if not self._ppn:
            pq = PBSQuery()
            node_vals = pq.getnodes().values()  # only the values, not the names
            interesting_nodes = ('free', 'job-exclusive',)
            res = {}
            for np in [int(x['np'][0]) for x in node_vals if x['state'][0] in interesting_nodes]:
                res.setdefault(np, 0)
                res[np] += 1

            if not res:
                raise EasyBuildError("Could not guess the ppn value of a full node because " +
                                     "there are no free or job-exclusive nodes.")

            # return most frequent
            freq_count, freq_np = max([(j, i) for i, j in res.items()])
            self.log.debug("Found most frequent np %s (%s times) in interesting nodes %s" % (freq_np, freq_count, interesting_nodes))

            self._ppn = freq_np

        return self._ppn

    ppn = property(_get_ppn)

    def make_job(self, script, name, env_vars=None, hours=None, cores=None):
        """Create and return a `PbsJob` object with the given parameters."""
        return PbsJob(self, script, name, env_vars=env_vars, hours=hours, cores=cores, conn=self.conn, ppn=self.ppn)


class PbsJob(object):
    """Interaction with TORQUE"""

    def __init__(self, server, script, name, env_vars=None,
                 hours=None, cores=None, conn=None, ppn=None):
        """
        create a new Job to be submitted to PBS
        env_vars is a dictionary with key-value pairs of environment variables that should be passed on to the job
        hours and cores should be integer values.
        hours can be 1 - (max walltime), cores depends on which cluster it is being run.
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self._server = server
        self.script = script
        if env_vars:
            self.env_vars = env_vars.copy()
        else:
            self.env_vars = {}
        self.name = name

        try:
            self.pbsconn = self._server.connect_to_server()
        except Exception, err:
            raise EasyBuildError("Failed to connect to the default pbs server: %s", err)

        # setup the resources requested

        # validate requested resources!
        max_walltime = build_option('job_max_walltime')
        if hours is None:
            hours = max_walltime
        if hours > max_walltime:
            self.log.warn("Specified %s hours, but this is impossible. (resetting to %s hours)" % (hours, max_walltime))
            hours = max_walltime

        if ppn is None:
            max_cores = server.ppn
        else:
            max_cores = ppn
        if cores is None:
            cores = max_cores
        if cores > max_cores:
            self.log.warn("number of requested cores (%s) was greater than available (%s) " % (cores, max_cores))
            cores = max_cores

        # only allow cores and hours for now.
        self.resources = {
            'walltime': '%s:00:00' % hours,
            'nodes': '1:ppn=%s' % cores,
        }
        # don't specify any queue name to submit to, use the default
        self.queue = None
        # job id of this job
        self.jobid = None
        # list of dependencies for this job
        self.deps = []
        # list of holds that are placed on this job
        self.holds = []

    def __str__(self):
        """Return the job ID as a string."""
        return (str(self.jobid) if self.jobid is not None
                else repr(self))

    def add_dependencies(self, jobs):
        """
        Add dependencies to this job.

        Argument `jobs` is a sequence of `PbsJob` objects.
        """
        self.deps.extend(jobs)

    def _submit(self):
        """Submit the jobscript txt, set self.jobid"""
        txt = self.script
        self.log.debug("Going to submit script %s" % txt)

        # Build default pbs_attributes list
        pbs_attributes = pbs.new_attropl(3)
        pbs_attributes[0].name = pbs.ATTR_N  # Job_Name
        pbs_attributes[0].value = self.name

        output_dir = build_option('job_output_dir')
        pbs_attributes[1].name = pbs.ATTR_o
        pbs_attributes[1].value = os.path.join(output_dir, '%s.o$PBS_JOBID' % self.name)

        pbs_attributes[2].name = pbs.ATTR_e
        pbs_attributes[2].value = os.path.join(output_dir, '%s.e$PBS_JOBID' % self.name)

        # set resource requirements
        resource_attributes = pbs.new_attropl(len(self.resources))
        idx = 0
        for k, v in self.resources.items():
            resource_attributes[idx].name = pbs.ATTR_l  # Resource_List
            resource_attributes[idx].resource = k
            resource_attributes[idx].value = v
            idx += 1
        pbs_attributes.extend(resource_attributes)

        # add job dependencies to attributes
        if self.deps:
            deps_attributes = pbs.new_attropl(1)
            deps_attributes[0].name = pbs.ATTR_depend
            deps_attributes[0].value = ",".join(["afterany:%s" % dep.jobid for dep in self.deps])
            pbs_attributes.extend(deps_attributes)
            self.log.debug("Job deps attributes: %s" % deps_attributes[0].value)

        # submit job with (user) hold
        hold_attributes = pbs.new_attropl(1)
        hold_attributes[0].name = pbs.ATTR_h
        hold_attributes[0].value = pbs.USER_HOLD
        pbs_attributes.extend(hold_attributes)
        self.holds.append(pbs.USER_HOLD)
        self.log.debug("Job hold attributes: %s" % hold_attributes[0].value)

        # add a bunch of variables (added by qsub)
        # also set PBS_O_WORKDIR to os.getcwd()
        os.environ.setdefault('WORKDIR', os.getcwd())

        defvars = ['MAIL', 'HOME', 'PATH', 'SHELL', 'WORKDIR']
        pbsvars = ["PBS_O_%s=%s" % (x, os.environ.get(x, 'NOTFOUND_%s' % x)) for x in defvars]
        # extend PBS variables with specified variables
        pbsvars.extend(["%s=%s" % (name, value) for (name, value) in self.env_vars.items()])
        variable_attributes = pbs.new_attropl(1)
        variable_attributes[0].name = pbs.ATTR_v  # Variable_List
        variable_attributes[0].value = ",".join(pbsvars)

        pbs_attributes.extend(variable_attributes)
        self.log.debug("Job variable attributes: %s" % variable_attributes[0].value)

        # mail settings
        mail_attributes = pbs.new_attropl(1)
        mail_attributes[0].name = pbs.ATTR_m  # Mail_Points
        mail_attributes[0].value = 'n'  # disable all mail
        pbs_attributes.extend(mail_attributes)
        self.log.debug("Job mail attributes: %s" % mail_attributes[0].value)

        fh, scriptfn = tempfile.mkstemp()
        f = os.fdopen(fh, 'w')
        self.log.debug("Writing temporary job script to %s" % scriptfn)
        f.write(txt)
        f.close()

        self.log.debug("Going to submit to queue %s" % self.queue)

        # job submission sometimes fails without producing an error, e.g. when one of the dependency jobs has already finished
        # when that occurs, None will be returned by pbs_submit as job id
        jobid = pbs.pbs_submit(self.pbsconn, pbs_attributes, scriptfn, self.queue, NULL)
        is_error, errormsg = pbs.error()
        if is_error or jobid is None:
            raise EasyBuildError("Failed to submit job script %s (job id: %s, error %s)", scriptfn, jobid, errormsg)
        else:
            self.log.debug("Succesful job submission returned jobid %s" % jobid)
            self.jobid = jobid
            os.remove(scriptfn)

    def set_hold(self, hold_type=None):
        """Set hold on job of specified type."""
        # we can't set this default for hold_type in function signature,
        # because we need to be able to load this module even when the pbs module is not available
        if hold_type is None:
            hold_type = pbs.USER_HOLD
        # only set hold if it wasn't set before
        if hold_type not in self.holds:
            if hold_type not in KNOWN_HOLD_TYPES:
                raise EasyBuildError("set_hold: unknown hold type: %s (supported: %s)", hold_type, KNOWN_HOLD_TYPES)
            # set hold, check for errors, and keep track of this hold
            ec = pbs.pbs_holdjob(self.pbsconn, self.jobid, hold_type, NULL)
            is_error, errormsg = pbs.error()
            if is_error or ec:
                raise EasyBuildError("Failed to set hold of type %s on job %s (is_error: %s, exit code: %s, msg: %s)",
                                     hold_type, self.jobid, is_error, ec, errormsg)
            else:
                self.holds.append(hold_type)
        else:
            self.log.warning("Hold type %s was already set for %s" % (hold_type, self.jobid))

    def release_hold(self, hold_type=None):
        """Release hold on job of specified type."""
        # we can't set this default for hold_type in function signature,
        # because we need to be able to load this module even when the pbs module is not available
        if hold_type is None:
            hold_type = pbs.USER_HOLD
        # only release hold if it was set
        if hold_type in self.holds:
            if hold_type not in KNOWN_HOLD_TYPES:
                raise EasyBuildError("release_hold: unknown hold type: %s (supported: %s)", hold_type, KNOWN_HOLD_TYPES)
            # release hold, check for errors, remove from list of holds
            ec = pbs.pbs_rlsjob(self.pbsconn, self.jobid, hold_type, NULL)
            self.log.debug("Released hold of type %s for job %s" % (hold_type, self.jobid))
            is_error, errormsg = pbs.error()
            if is_error or ec:
                raise EasyBuildError("Failed to release hold type %s on job %s (is_error: %s, exit code: %s, msg: %s)",
                                     hold_type, self.jobid, is_error, ec, errormsg)
            else:
                self.holds.remove(hold_type)
        else:
            self.log.warning("No hold type %s was set for %s, so skipping hold release" % (hold_type, self.jobid))

    def has_holds(self):
        """Return whether this job has holds or not."""
        return bool(self.holds)

    def state(self):
        """
        Return the state of the job
        State can be 'not submitted', 'running', 'queued' or 'finished',
        """
        state = self.info(types=['job_state', 'exec_host'])

        if state is None:
            if self.jobid is None:
                return 'not submitted'
            else:
                return 'finished'

        jid = state['id']

        jstate = state.get('job_state', None)

        def get_uniq_hosts(txt, num=None):
            """
            - txt: format: host1/cpuid+host2/cpuid
            - num: number of nodes to return (default: all)
            """
            if num is None:
                num = -1
            res = []
            for h_c in txt.split('+'):
                h = h_c.split('/')[0]
                if h in res:
                    continue
                res.append(h)
            return res[:num]

        ehosts = get_uniq_hosts(state.get('exec_host', ''), 1)

        self.log.debug("Jobid %s jid %s state %s ehosts %s (%s)" % (self.jobid, jid, jstate, ehosts, state))
        if jstate == 'Q':
            return 'queued'
        else:
            return 'running'

    def info(self, types=None):
        """
        Return jobinfo
        """
        if not self.jobid:
            self.log.debug("no jobid, job is not submitted yet?")
            return None

        # convert single type into list
        if type(types) is str:
            types = [types]

        self.log.debug("Return info types %s" % types)

        # create attribute list to query pbs with
        if types is None:
            jobattr = NULL
        else:
            jobattr = pbs.new_attrl(len(types))
            for idx, attr in enumerate(types):
                jobattr[idx].name = attr

        jobs = pbs.pbs_statjob(self.pbsconn, self.jobid, jobattr, NULL)
        if len(jobs) == 0:
            # no job found, return None info
            res = None
            self.log.debug("No job found. Wrong id %s or job finished? Returning %s" % (self.jobid, res))
            return res
        elif len(jobs) == 1:
            self.log.debug("Request for jobid %s returned one result %s" % (self.jobid, jobs))
        else:
            raise EasyBuildError("Request for jobid %s returned more then one result %s", self.jobid, jobs)

        # only expect to have a list with one element
        j = jobs[0]
        # convert attribs into useable dict
        job_details = dict([(attrib.name, attrib.value) for attrib in j.attribs])
        # manually set 'id' attribute
        job_details['id'] = j.name
        self.log.debug("Found jobinfo %s" % job_details)
        return job_details

    def remove(self):
        """Remove the job with id jobid"""
        result = pbs.pbs_deljob(self.pbsconn, self.jobid, '')  # use empty string, not NULL
        if result:
            raise EasyBuildError("Failed to delete job %s: error %s", self.jobid, result)
        else:
            self.log.debug("Succesfully deleted job %s" % self.jobid)
