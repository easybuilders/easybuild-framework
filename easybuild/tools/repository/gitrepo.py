# #
# Copyright 2009-2016 Ghent University
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

Git repository

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
@author: Fotis Georgatos (Uni.Lu, NTUA)
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
from easybuild.tools.version import VERSION

_log = fancylogger.getLogger('gitrepo', fname=False)

# optional Python packages, these might be missing
# failing imports are just ignored
# a NameError should be catched where these are used

# GitPython (http://gitorious.org/git-python)
try:
    import git
    from git import GitCommandError
    HAVE_GIT = True
except ImportError:
    _log.debug('Failed to import git module')
    HAVE_GIT = False


class GitRepository(FileRepository):
    """
    Class for git repositories.
    """
    DESCRIPTION = ("A non-empty bare git repository (created with 'git init --bare' or 'git clone --bare'). "
                   "The 1st argument contains the git repository location, which can be a directory or an URL. "
                   "The 2nd argument is a path inside the repository where to save the files.")

    USABLE = HAVE_GIT

    @only_if_module_is_available('git', pkgname='GitPython')
    def __init__(self, *args):
        """
        Initialize git client to None (will be set later)
        All the real logic is in the setup_repo and create_working_copy methods
        """
        self.client = None
        FileRepository.__init__(self, *args)

    def setup_repo(self):
        """
        Set up git repository.
        """
        self.wc = tempfile.mkdtemp(prefix='git-wc-')

    def create_working_copy(self):
        """
        Create git working copy.
        """

        reponame = 'UNKNOWN'
        # try to get a copy of
        try:
            client = git.Git(self.wc)
            client.clone(self.repo)
            reponame = os.listdir(self.wc)[0]
            self.log.debug("rep name is %s" % reponame)
        except (git.GitCommandError, OSError), err:
            # it might already have existed
            self.log.warning("Git local repo initialization failed, it might already exist: %s", err)

        # local repo should now exist, let's connect to it again
        try:
            self.wc = os.path.join(self.wc, reponame)
            self.log.debug("connectiong to git repo in %s" % self.wc)
            self.client = git.Git(self.wc)
        except (git.GitCommandError, OSError), err:
            raise EasyBuildError("Could not create a local git repo in wc %s: %s", self.wc, err)

        # try to get the remote data in the local repo
        try:
            res = self.client.pull()
            self.log.debug("pulled succesfully to %s in %s" % (res, self.wc))
        except (git.GitCommandError, OSError), err:
            raise EasyBuildError("pull in working copy %s went wrong: %s", self.wc, err)

    def add_easyconfig(self, cfg, name, version, stats, append):
        """
        Add easyconfig to git repository.
        """
        dest = FileRepository.add_easyconfig(self, cfg, name, version, stats, append)
        # add it to version control
        if dest:
            try:
                self.client.add(dest)
            except GitCommandError, err:
                self.log.warning("adding %s to git failed: %s" % (dest, err))

    def commit(self, msg=None):
        """
        Commit working copy to git repository
        """
        host = socket.gethostname()
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        user = getpass.getuser()
        completemsg = "%s with EasyBuild v%s @ %s (time: %s, user: %s)" % (msg, VERSION, host, timestamp, user)
        self.log.debug("committing in git with message: %s" % msg)

        self.log.debug("git status: %s" % self.client.status())
        try:
            self.client.commit('-am %s' % completemsg)
            self.log.debug("succesfull commit: %s", self.client.log('HEAD^!'))
        except GitCommandError, err:
            self.log.warning("Commit from working copy %s failed, empty commit? (msg: %s): %s", self.wc, msg, err)
        try:
            info = self.client.push()
            self.log.debug("push info: %s ", info)
        except GitCommandError, err:
            self.log.warning("Push from working copy %s to remote %s failed (msg: %s): %s",
                             self.wc, self.repo, msg, err)

    def cleanup(self):
        """
        Clean up git working copy.
        """
        try:
            self.wc = os.path.dirname(self.wc)
            rmtree2(self.wc)
        except IOError, err:
            raise EasyBuildError("Can't remove working copy %s: %s", self.wc, err)
