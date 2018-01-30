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
Repository tools

Svn repository

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
"""
import getpass
import os
import socket
import tempfile
import time
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import rmtree2
from easybuild.tools.repository.filerepo import FileRepository
from easybuild.tools.utilities import only_if_module_is_available


_log = fancylogger.getLogger('svnrepo', fname=False)


# optional Python packages, these might be missing
# failing imports are just ignored

# PySVN
try:
    import pysvn  # @UnusedImport
    from pysvn import ClientError  # IGNORE:E0611 pysvn fails to recognize ClientError is available
    HAVE_PYSVN = True
except ImportError:
    _log.debug("Failed to import pysvn module")
    HAVE_PYSVN = False


class SvnRepository(FileRepository):
    """
    Class for svn repositories
    """

    DESCRIPTION = ("An SVN repository. The 1st argument contains the "
                   "subversion repository location, this can be a directory or an URL. "
                   "The 2nd argument is a path inside the repository where to save the files.")

    USABLE = HAVE_PYSVN

    @only_if_module_is_available('pysvn', url='http://pysvn.tigris.org/')
    def __init__(self, *args):
        """
        Set self.client to None. Real logic is in setup_repo and create_working_copy
        """
        self.client = None
        FileRepository.__init__(self, *args)

    def setup_repo(self):
        """
        Set up SVN repository.
        """
        self.repo = os.path.join(self.repo, self.subdir)

        # try to connect to the repository
        self.log.debug("Try to connect to repository %s" % self.repo)
        try:
            self.client = pysvn.Client()
            self.client.exception_style = 0
        except ClientError:
            raise EasyBuildError("Svn Client initialization failed.")

        try:
            if not self.client.is_url(self.repo):
                raise EasyBuildError("Provided repository %s is not a valid svn url", self.repo)
        except ClientError:
            raise EasyBuildError("Can't connect to svn repository %s", self.repo)

    def create_working_copy(self):
        """
        Create SVN working copy.
        """
        self.wc = tempfile.mkdtemp(prefix='svn-wc-')

        # check if tmppath exists
        # this will trigger an error if it does not exist
        try:
            self.client.info2(self.repo, recurse=False)
        except ClientError:
            raise EasyBuildError("Getting info from %s failed.", self.wc)

        try:
            res = self.client.update(self.wc)
            self.log.debug("Updated to revision %s in %s" % (res, self.wc))
        except ClientError:
            raise EasyBuildError("Update in wc %s went wrong", self.wc)

        if len(res) == 0:
            raise EasyBuildError("Update returned empy list (working copy: %s)", self.wc)

        if res[0].number == -1:
            # revision number of update is -1
            # means nothing has been checked out
            try:
                res = self.client.checkout(self.repo, self.wc)
                self.log.debug("Checked out revision %s in %s" % (res.number, self.wc))
            except ClientError, err:
                raise EasyBuildError("Checkout of path / in working copy %s went wrong: %s", self.wc, err)

    def stage_file(self, path):
        """
        Stage file at specified location in repository for commit

        :param path: location of file to stage
        """
        if self.client and not self.client.status(path)[0].is_versioned:
            # add it to version control
            self.log.debug("Going to add %s (working copy: %s, cwd %s)" % (path, self.wc, os.getcwd()))
            self.client.add(path)

    def add_easyconfig(self, cfg, name, version, stats, previous_stats):
        """
        Add easyconfig to SVN repository

        :param cfg: location of easyconfig file
        :param name: software name
        :param version: software install version, incl. toolchain & versionsuffix
        :param stats: build stats, to add to archived easyconfig
        :param previous: list of previous build stats
        :return: location of archived easyconfig
        """
        path = super(SvnRepository, self).add_easyconfig(cfg, name, version, stats, previous_stats)
        self.stage_file(path)
        return path

    def add_patch(self, patch, name):
        """
        Add patch to SVN repository

        :param patch: location of patch file
        :param name: software name
        :return: location of archived patch
        """
        path = super(SvnRepository, self).add_patch(patch, name)
        self.stage_file(path)
        return path

    def commit(self, msg=None):
        """
        Commit working copy to SVN repository
        """
        tup = (socket.gethostname(), time.strftime("%Y-%m-%d_%H-%M-%S"), getpass.getuser(), msg)
        completemsg = "EasyBuild-commit from %s (time: %s, user: %s) \n%s" % tup

        try:
            self.client.checkin(self.wc, completemsg, recurse=True)
        except ClientError, err:
            raise EasyBuildError("Commit from working copy %s (msg: %s) failed: %s", self.wc, msg, err)

    def cleanup(self):
        """
        Clean up SVN working copy.
        """
        try:
            rmtree2(self.wc)
        except OSError, err:
            raise EasyBuildError("Can't remove working copy %s: %s", self.wc, err)
