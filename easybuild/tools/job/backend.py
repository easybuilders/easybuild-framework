##
# Copyright 2015-2016 Ghent University
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
Abstract interface for submitting jobs and related utilities.

@author: Riccardo Murri (University of Zurich)
@author: Kenneth Hoste (Ghent University)
"""

from abc import ABCMeta, abstractmethod

from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.tools.config import get_job_backend
from easybuild.tools.utilities import import_available_modules


class JobBackend(object):
    __metaclass__ = ABCMeta

    def __init__(self):
        """Constructor."""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self._check_version()

    @abstractmethod
    def _check_version(self):
        """Check whether version of backend complies with required version."""
        pass

    @abstractmethod
    def init(self):
        """
        Initialise the job backend, to start a bulk job submission.

        Jobs may be queued and only actually submitted when `complete()`
        is called.
        """
        pass

    @abstractmethod
    def make_job(self, script, name, env_vars=None, hours=None, cores=None):
        """
        Create and return a `Job` object with the given parameters.

        See the `Job`:class: constructor for an explanation of what
        the arguments are.
        """
        pass

    @abstractmethod
    def queue(self, job, dependencies=frozenset()):
        """
        Add a job to the queue.

        If second optional argument `dependencies` is given, it must be a
        sequence of jobs that must be successfully terminated before
        the new job can run.

        Note that actual submission may be delayed until `complete()` is
        called.
        """
        pass

    @abstractmethod
    def complete(self):
        """
        Complete a bulk job submission.

        Releases any jobs that were possibly queued since the last
        `init()` call.

        No more job submissions should be attempted after `complete()`
        has been called, until a `init()` is invoked again.
        """
        pass


def avail_job_backends(check_usable=True):
    """
    Return all known job execution backends.
    """
    import_available_modules('easybuild.tools.job')
    class_dict = dict([(x.__name__, x) for x in get_subclasses(JobBackend)])
    return class_dict


def job_backend():
    """
    Return interface to job server, or `None` if none is available.
    """
    job_backend = get_job_backend()
    if job_backend is None:
        return None
    job_backend_class = avail_job_backends().get(job_backend)
    return job_backend_class()
