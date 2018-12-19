# #
# Copyright 2009-2018 Ghent University
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
Generic support for dealing with repositories

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
"""
from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.utilities import import_available_modules

_log = fancylogger.getLogger('repository', fname=False)


class Repository(object):
    """
    Interface for repositories
    """

    DESCRIPTION = None

    USABLE = True  # can the Repository be used?

    def __init__(self, repo_path, subdir=''):
        """
        Initialize a repository. self.repo and self.subdir will be set.
        self.wc will be set to None.
        Then, setup_repo and create_working_copy will be called (in that order)
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.subdir = subdir
        self.repo = repo_path
        self.wc = None
        self.initialized = False

    def init(self):
        """Prepare repository for use."""
        self.setup_repo()
        self.create_working_copy()
        self.initialized = True

    def is_initialized(self):
        """Indicate whether repository was initialized."""
        return self.initialized

    def setup_repo(self):
        """
        Set up repository.
        """
        raise NotImplementedError

    def create_working_copy(self):
        """
        Create working copy.
        """
        raise NotImplementedError

    def stage_file(self, path):
        """
        Stage file at specified location in repository for commit

        :param path: location of file to stage
        """
        raise NotImplementedError

    def add_easyconfig(self, cfg, name, version, stats, previous):
        """
        Add easyconfig to repository

        :param cfg: location of easyconfig file
        :param name: software name
        :param version: software install version, incl. toolchain & versionsuffix
        :param stats: build stats, to add to archived easyconfig
        :param previous: list of previous build stats
        :return: location of archived easyconfig
        """
        raise NotImplementedError

    def add_patch(self, patch):
        """
        Add patch file to repository

        :param patch: location of patch file
        :param name: software name
        :return: location of archived patch
        """
        raise NotImplementedError

    def commit(self, msg=None):
        """
        Commit working copy
        - add msg
        - add more info to msg
        """
        # does nothing by default
        pass

    def cleanup(self):
        """
        Clean up working copy.
        """
        pass

    def get_buildstats(self, name, ec_version):
        """
        Get the build statististics for software with name and easyconfig version
        """
        raise NotImplementedError


def avail_repositories(check_useable=True):
    """
    Return all available repositories.
        check_useable: boolean, if True, only return usable repositories
    """
    import_available_modules('easybuild.tools.repository')

    class_dict = dict([(x.__name__, x) for x in get_subclasses(Repository) if x.USABLE or not check_useable])

    if not 'FileRepository' in class_dict:
        raise EasyBuildError("avail_repositories: FileRepository missing from list of repositories")

    return class_dict


def init_repository(repository, repository_path):
    """Return an instance of the selected repository class."""
    inited_repo = None
    if isinstance(repository, Repository):
        inited_repo = repository
    elif isinstance(repository, basestring):
        repo = avail_repositories().get(repository)
        try:
            if isinstance(repository_path, basestring):
                inited_repo = repo(repository_path)
            elif isinstance(repository_path, (tuple, list)) and len(repository_path) <= 2:
                inited_repo = repo(*repository_path)
            else:
                raise EasyBuildError("repository_path should be a string or list/tuple of maximum 2 elements "
                                     "(current: %s, type %s)", repository_path, type(repository_path))
        except Exception, err:
            raise EasyBuildError("Failed to create a repository instance for %s (class %s) with args %s (msg: %s)",
                                 repository, repo.__name__, repository_path, err)
    else:
        raise EasyBuildError("Unknown typo of repository spec: %s (type %s)", repo, type(repo))

    inited_repo.init()
    return inited_repo
