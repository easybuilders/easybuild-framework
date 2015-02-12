# #
# Copyright 2009-2014 Ghent University
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
# #
"""
Repository tools

Svn repository

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

from easybuild.tools.filetools import rmtree2
from easybuild.tools.repository.filerepo import FileRepository

_log = fancylogger.getLogger('svnrepo', fname=False)

# optional Python packages, these might be missing
# failing imports are just ignored
# a NameError should be catched where these are used

# PySVN
try:
    import pysvn  # @UnusedImport
    from pysvn import ClientError  # IGNORE:E0611 pysvn fails to recognize ClientError is available
    HAVE_PYSVN = True
except ImportError:
    _log.debug('Failed to import pysvn module')
    HAVE_PYSVN = False


class SvnRepository(FileRepository):
    """
    Class for svn repositories
    """

    DESCRIPTION = ("An SVN repository. The 1st argument contains the "
                   "subversion repository location, this can be a directory or an URL. "
                   "The 2nd argument is a path inside the repository where to save the files.")

    USABLE = HAVE_PYSVN

    def __init__(self, *args):
        """
        Set self.client to None. Real logic is in setupRepo and createWorkingCopy
        """
        self.client = None
        FileRepository.__init__(self, *args)

    def setup_repo(self):
        """
        Set up SVN repository.
        """
        self.repo = os.path.join(self.repo, self.subdir)
        try:
            pysvn.ClientError  # IGNORE:E0611 pysvn fails to recognize ClientError is available
        except NameError, err:
            self.log.error("pysvn not available. Make sure it is installed properly."
                           + " Run 'python -c \"import pysvn\"' to test.", err)

        # try to connect to the repository
        self.log.debug("Try to connect to repository %s" % self.repo)
        try:
            self.client = pysvn.Client()
            self.client.exception_style = 0
        except ClientError:
            self.log.exception("Svn Client initialization failed.")

        try:
            if not self.client.is_url(self.repo):
                self.log.error("Provided repository %s is not a valid svn url" % self.repo)
        except ClientError:
            self.log.exception("Can't connect to svn repository %s" % self.repo)

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
            self.log.exception("Getting info from %s failed." % self.wc)

        try:
            res = self.client.update(self.wc)
            self.log.debug("Updated to revision %s in %s" % (res, self.wc))
        except ClientError:
            self.log.exception("Update in wc %s went wrong" % self.wc)

        if len(res) == 0:
            self.log.error("Update returned empy list (working copy: %s)" % (self.wc))

        if res[0].number == -1:
            # revision number of update is -1
            # means nothing has been checked out
            try:
                res = self.client.checkout(self.repo, self.wc)
                self.log.debug("Checked out revision %s in %s" % (res.number, self.wc))
            except ClientError, err:
                self.log.exception("Checkout of path / in working copy %s went wrong: %s" % (self.wc, err))

    def add_easyconfig(self, cfg, name, version, stats, append):
        """
        Add easyconfig to SVN repository.
        """
        dest = FileRepository.add_easyconfig(self, cfg, name, version, stats, append)
        self.log.debug("destination = %s" % dest)
        if dest:
            self.log.debug("destination status: %s" % self.client.status(dest))

            if self.client and not self.client.status(dest)[0].is_versioned:
                # add it to version control
                self.log.debug("Going to add %s (working copy: %s, cwd %s)" % (dest, self.wc, os.getcwd()))
                self.client.add(dest)

    def commit(self, msg=None):
        """
        Commit working copy to SVN repository
        """
        completemsg = "EasyBuild-commit from %s (time: %s, user: %s) \n%s" % (socket.gethostname(),
                                                                              time.strftime("%Y-%m-%d_%H-%M-%S"),
                                                                              getpass.getuser(), msg)
        try:
            self.client.checkin(self.wc, completemsg, recurse=True)
        except ClientError, err:
            self.log.exception("Commit from working copy %s (msg: %s) failed: %s" % (self.wc, msg, err))

    def cleanup(self):
        """
        Clean up SVN working copy.
        """
        try:
            rmtree2(self.wc)
        except OSError, err:
            self.log.exception("Can't remove working copy %s: %s" % (self.wc, err))

    def export(self, to_path, revision=None):
        """
        Get a copy of the files in this repository to the given path, this will need a setup repo first,
        but can just download the files to the path without version information, if no revision is given this will
        default to the latest revision.
        """
        if not self.client:
            self.setup_repo()
        if revision:
            revision = pysvn.Revision(pysvn.opt_revision_kind.number, revision)
        else:
            revision = pysvn.Revision(pysvn.opt_revision_kind.head)

        _log.debug('exporting %s at revision %s to %s', self.repo, revision, to_path)
        self.client.export(self.repo, to_path, revision=revision)
