# #
# Copyright 2009-2014 Ghent University
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
# #
"""
Repository tools

Mercurial repository

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
@author: Fotis Georgatos (University of Luxembourg)
@author: Cedric Clerget (University of Franche-Comte)
"""
import getpass
import socket
import tempfile
import time
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import rmtree2
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
            client = hglib.clone(self.repo, self.wc)
            self.log.debug("repo %s cloned in %s" % (self.repo, self.wc))
        except (HgCommandError, OSError), err:
            # it might already have existed
            self.log.warning("Mercurial local repo initialization failed, it might already exist: %s" % err)

        # local repo should now exist, let's connect to it again
        try:
            self.log.debug("connection to mercurial repo in %s" % self.wc)
            self.client = hglib.open(self.wc)
        except HgServerError, err:
            raise EasyBuildError("Could not connect to local mercurial repo: %s", err)
        except (HgCapabilityError, HgResponseError), err:
            raise EasyBuildError("Server response: %s", err)
        except (OSError, ValueError), err:
            raise EasyBuildError("Could not create a local mercurial repo in wc %s: %s", self.wc, err)

        # try to get the remote data in the local repo
        try:
            self.client.pull()
            self.log.debug("pulled succesfully in %s" % self.wc)
        except (HgCommandError, HgServerError, HgResponseError, OSError, ValueError), err:
            raise EasyBuildError("pull in working copy %s went wrong: %s", self.wc, err)

    def add_easyconfig(self, cfg, name, version, stats, append):
        """
        Add easyconfig to mercurial repository.
        """
        dest = FileRepository.add_easyconfig(self, cfg, name, version, stats, append)
        # add it to version control
        if dest:
            try:
                self.client.add(dest)
            except (HgCommandError, HgServerError, HgResponseError, ValueError), err:
                self.log.warning("adding %s to mercurial repository failed: %s" % (dest, err))

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
        except (HgCommandError, HgServerError, HgResponseError, ValueError), err:
            self.log.warning("Commit from working copy %s (msg: %s) failed, empty commit?\n%s" % (self.wc, msg, err))
        try:
            if self.client.push():
                info = "pushed"
            else:
                info = "nothing to push"
            self.log.debug("push info: %s " % info)
        except (HgCommandError, HgServerError, HgResponseError, ValueError), err:
            tup = (self.wc, self.repo, msg, err)
            self.log.warning("Push from working copy %s to remote %s (msg: %s) failed: %s" % tup)

    def cleanup(self):
        """
        Clean up mercurial working copy.
        """
        try:
            rmtree2(self.wc)
        except IOError, err:
            raise EasyBuildError("Can't remove working copy %s: %s", self.wc, err)
