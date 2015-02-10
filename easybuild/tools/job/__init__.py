# #
# This file is part of EasyBuild, see:
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
# #


from vsc.utils.missing import get_subclasses

from easybuild.tools.config import get_job


def avail_job_factories():
    """
    Return all known job execution backends.
    """
    class_dict = dict([(x.__name__, x) for x in get_subclasses(Job)])
    return class_dict


def job_factory(testing=False):
    """
    Return interface to job factory.
    """
    job_factory = get_job()
    job_factory_class = avail_job_factories().get(job_factory)
    return job_factory_class(testing=testing)
