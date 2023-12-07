# #
# Copyright 2009-2023 Ghent University
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

Mercurial repository

Authors:

* Stijn De Weirdt (Ghent University)
* Dries Verdegem (Ghent University)
* Kenneth Hoste (Ghent University)
* Pieter De Baets (Ghent University)
* Jens Timmerman (Ghent University)
* Toon Willems (Ghent University)
* Ward Poelmans (Ghent University)
* Fotis Georgatos (University of Luxembourg)
* Cedric Clerget (University of Franche-Comte)
"""
import getpass
import socket
import tempfile
import time

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import remove_dir
from easybuild.tools.repository.filerepo import FileRepository

_log = fancylogger.getLogger('hgrepo', fname=False)

# optional Python packages, these might be missing
# failing imports are just ignored
# a NameError should be catched where these are used

# python-hglib
try:
    import hglib
    from hglib.error import CapabilityError as HgCapabilityError
    from hglib.error import CommandError as HgCommandError
    from hglib.error import ResponseError as HgResponseError
    from hglib.error import ServerError as HgServerError
    HAVE_HG = True
except ImportError:
    _log.debug('Failed to import hglib module')
    HAVE_HG = False


class HgRepository(FileRepository):
    """
    Class for hg repositories.
    """
    DESCRIPTION = ("A non-empty mercurial repository (created with 'hg init' or 'hg clone'). "
                   "The 1st argument contains the mercurial repository location, which can be a directory or an URL. "
                   "The 2nd argument is ignored.")

    USABLE = HAVE_HG

    def __init__(self, *args):
        """
        Initialize mercurial client to None (will be set later)
        All the real logic is in the setup_repo and create_working_copy methods
        """
        self.client = None
        FileRepository.__init__(self, *args)

    def setup_repo(self):
        """
        Set up mercurial repository.
        """
        if not HAVE_HG:
            raise EasyBuildError("python-hglib is not available, which is required for Mercurial support.")

        self.wc = tempfile.mkdtemp(prefix='hg-wc-')

    def create_working_copy(self):
        """
        Create mercurial working copy.
        """

        # try to get a copy of
        try:
            hglib.clone(self.repo, self.wc)
            self.log.debug("repo %s cloned in %s" % (self.repo, self.wc))
        except (HgCommandError, OSError) as err:
            # it might already have existed
            self.log.warning("Mercurial local repo initialization failed, it might already exist: %s" % err)

        # local repo should now exist, let's connect to it again
        try:
            self.log.debug("connection to mercurial repo in %s" % self.wc)
            self.client = hglib.open(self.wc)
        except HgServerError as err:
            raise EasyBuildError("Could not connect to local mercurial repo: %s", err)
        except (HgCapabilityError, HgResponseError) as err:
            raise EasyBuildError("Server response: %s", err)
        except (OSError, ValueError) as err:
            raise EasyBuildError("Could not create a local mercurial repo in wc %s: %s", self.wc, err)

        # try to get the remote data in the local repo
        try:
            self.client.pull()
            self.log.debug("pulled succesfully in %s" % self.wc)
        except (HgCommandError, HgServerError, HgResponseError, OSError, ValueError) as err:
            raise EasyBuildError("pull in working copy %s went wrong: %s", self.wc, err)

    def stage_file(self, path):
        """
        Stage file at specified location in repository for commit

        :param path: location of file to stage
        """
        try:
            self.client.add(path)
        except (HgCommandError, HgServerError, HgResponseError, ValueError) as err:
            self.log.warning("adding %s to mercurial repository failed: %s", path, err)

    def add_easyconfig(self, cfg, name, version, stats, previous_stats):
        """
        Add easyconfig to Mercurial repository

        :param cfg: location of easyconfig file
        :param name: software name
        :param version: software install version, incl. toolchain & versionsuffix
        :param stats: build stats, to add to archived easyconfig
        :param previous_stats: list of previous build stats
        :return: location of archived easyconfig
        """
        path = super(HgRepository, self).add_easyconfig(cfg, name, version, stats, previous_stats)
        self.stage_file(path)
        return path

    def add_patch(self, patch, name):
        """
        Add patch to Mercurial repository

        :param patch: location of patch file
        :param name: software name
        :return: location of archived patch
        """
        path = super(HgRepository, self).add_patch(patch, name)
        self.stage_file(path)
        return path

    def commit(self, msg=None):
        """
        Commit working copy to mercurial repository
        """
        user = getpass.getuser()
        self.log.debug("%s committing in mercurial repository: %s" % (user, msg))
        tup = (socket.gethostname(), time.strftime("%Y-%m-%d_%H-%M-%S"), user, msg)
        completemsg = "EasyBuild-commit from %s (time: %s, user: %s) \n%s" % tup

        self.log.debug("hg status: %s" % self.client.status())
        try:
            self.client.commit('"%s"' % completemsg, user=user)
            self.log.debug("succesfull commit")
        except (HgCommandError, HgServerError, HgResponseError, ValueError) as err:
            self.log.warning("Commit from working copy %s (msg: %s) failed, empty commit?\n%s" % (self.wc, msg, err))
        try:
            if self.client.push():
                info = "pushed"
            else:
                info = "nothing to push"
            self.log.debug("push info: %s " % info)
        except (HgCommandError, HgServerError, HgResponseError, ValueError) as err:
            tup = (self.wc, self.repo, msg, err)
            self.log.warning("Push from working copy %s to remote %s (msg: %s) failed: %s" % tup)

    def cleanup(self):
        """
        Clean up mercurial working copy.
        """
        try:
            remove_dir(self.wc)
        except IOError as err:
            raise EasyBuildError("Can't remove working copy %s: %s", self.wc, err)
