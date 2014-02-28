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
Set of repository tools

We have a plain filesystem, an svn and a git repository

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
@author: Fotis Georgatos (University of Luxembourg)
"""
import getpass
import os
import socket
import tempfile
import time
from vsc import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.tools import stats_to_str
from easybuild.tools.filetools import rmtree2, read_file, write_file
from easybuild.tools.version import VERBOSE_VERSION

_log = fancylogger.getLogger('repository', fname=False)

# optional Python packages, these might be missing
# failing imports are just ignored
# a NameError should be catched where these are used

# GitPython
try:
    import git
    from git import GitCommandError
    HAVE_GIT = True
except ImportError:
    _log.debug('Failed to import git module')
    HAVE_GIT = False

# PySVN
try:
    import pysvn  # @UnusedImport
    from pysvn import ClientError  # IGNORE:E0611 pysvn fails to recognize ClientError is available
    HAVE_PYSVN = True
except ImportError:
    _log.debug('Failed to import pysvn module')
    HAVE_PYSVN = False


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
        Then, setupRepo and createWorkingCopy will be called (in that order)
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.subdir = subdir
        self.repo = repo_path
        self.wc = None
        self.setup_repo()
        self.create_working_copy()

    def setup_repo(self):
        """
        Set up repository.
        """
        pass

    def create_working_copy(self):
        """
        Create working copy.
        """
        pass

    def add_easyconfig(self, cfg, name, version, stats, previous):
        """
        Add easyconfig to repository.
        cfg is the filename of the eb file
        Stats contains some build stats, this should be a list of dictionaries.
        previous is the list of previous buildstats
        """
        pass

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
        pass


class FileRepository(Repository):
    """Class for file repositories."""

    DESCRIPTION = ("A plain flat file repository. "
                   "The 1st argument contains the directory where the files are stored. "
                   "The optional 2nd argument is a subdir in that path.")

    def setup_repo(self):
        """
        for file based repos this will create the repo directory
        if it doesn't exist.

        if a subdir is specified also create the subdir
        """
        if not os.path.isdir(self.repo):
            os.makedirs(self.repo)

        full_path = os.path.join(self.repo, self.subdir)
        if not os.path.isdir(full_path):
            os.makedirs(full_path)

    def create_working_copy(self):
        """ set the working directory to the repo directory """
        # for sake of convenience
        self.wc = self.repo

    def add_easyconfig(self, cfg, name, version, stats, previous):
        """
        Add the eb-file for software name and version to the repository.
        stats should be a dict containing statistics.
        if previous is true -> append the statistics to the file
        This will return the path to the created file (for use in subclasses)
        """
        # create directory for eb file
        full_path = os.path.join(self.wc, self.subdir, name)
        if not os.path.isdir(full_path):
            os.makedirs(full_path)

        # destination
        dest = os.path.join(full_path, "%s.eb" % version)

        txt = "# Built with EasyBuild version %s on %s\n" % (VERBOSE_VERSION, time.strftime("%Y-%m-%d_%H-%M-%S"))

        # copy file
        txt += read_file(cfg)

        # append a line to the eb file so that we don't have git merge conflicts
        if not previous:
            statsprefix = "\n# Build statistics\nbuildstats = ["
            statssuffix = "]\n"
        else:
            # statstemplate = "\nbuildstats.append(%s)\n"
            statsprefix = "\nbuildstats.append("
            statssuffix = ")\n"

        txt += statsprefix + stats_to_str(stats) + statssuffix
        write_file(dest, txt)

        return dest

    def get_buildstats(self, name, ec_version):
        """
        return the build statistics
        """
        full_path = os.path.join(self.wc, self.subdir, name)
        if not os.path.isdir(full_path):
            self.log.debug("module (%s) has not been found in the repo" % name)
            return []

        dest = os.path.join(full_path, "%s.eb" % ec_version)
        if not os.path.isfile(dest):
            self.log.debug("version %s for %s has not been found in the repo" % (ec_version, name))
            return []

        eb = EasyConfig(dest, build_options={'validate': False})
        return eb['buildstats']


class GitRepository(FileRepository):
    """
    Class for git repositories.
    """
    DESCRIPTION = ("A non-empty bare git repository (created with 'git init --bare' or 'git clone --bare'). "
                   "The 1st argument contains the git repository location, which can be a directory or an URL. "
                   "The 2nd argument is a path inside the repository where to save the files.")

    USABLE = HAVE_GIT

    def __init__(self, *args):
        """
        Initialize git client to None (will be set later)
        All the real logic is in the setupRepo and createWorkingCopy methods
        """
        self.client = None
        FileRepository.__init__(self, *args)

    def setup_repo(self):
        """
        Set up git repository.
        """
        try:
            git.GitCommandError
        except NameError, err:
            self.log.exception("It seems like GitPython is not available: %s" % err)

        self.wc = tempfile.mkdtemp(prefix='git-wc-')

    def create_working_copy(self):
        """
        Create git working copy.
        """

        reponame = 'UNKNOWN'
        # try to get a copy of
        try:
            client = git.Git(self.wc)
            out = client.clone(self.repo)
            # out  = 'Cloning into easybuild...'
            reponame = out.split("\n")[0].split()[-1].strip(".").strip("'")
            self.log.debug("rep name is %s" % reponame)
        except git.GitCommandError, err:
            # it might already have existed
            self.log.warning("Git local repo initialization failed, it might already exist: %s" % err)

        # local repo should now exist, let's connect to it again
        try:
            self.wc = os.path.join(self.wc, reponame)
            self.log.debug("connectiong to git repo in %s" % self.wc)
            self.client = git.Git(self.wc)
        except (git.GitCommandError, OSError), err:
            self.log.error("Could not create a local git repo in wc %s: %s" % (self.wc, err))

        # try to get the remote data in the local repo
        try:
            res = self.client.pull()
            self.log.debug("pulled succesfully to %s in %s" % (res, self.wc))
        except (git.GitCommandError, OSError), err:
            self.log.exception("pull in working copy %s went wrong: %s" % (self.wc, err))

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
        self.log.debug("committing in git: %s" % msg)
        completemsg = "EasyBuild-commit from %s (time: %s, user: %s) \n%s" % (socket.gethostname(),
                                                                              time.strftime("%Y-%m-%d_%H-%M-%S"),
                                                                              getpass.getuser(),
                                                                              msg)
        self.log.debug("git status: %s" % self.client.status())
        try:
            self.client.commit('-am "%s"' % completemsg)
            self.log.debug("succesfull commit")
        except GitCommandError, err:
            self.log.warning("Commit from working copy %s (msg: %s) failed, empty commit?\n%s" % (self.wc, msg, err))
        try:
            info = self.client.push()
            self.log.debug("push info: %s " % info)
        except GitCommandError, err:
            self.log.warning("Push from working copy %s to remote %s (msg: %s) failed: %s" % (self.wc,
                                                                                              self.repo,
                                                                                              msg,
                                                                                              err))

    def cleanup(self):
        """
        Clean up git working copy.
        """
        try:
            self.wc = os.path.dirname(self.wc)
            rmtree2(self.wc)
        except IOError, err:
            self.log.exception("Can't remove working copy %s: %s" % (self.wc, err))


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
            raise pysvn.ClientError  # IGNORE:E0611 pysvn fails to recognize ClientError is available
        except NameError, err:
            self.log.exception("pysvn not available (%s). Make sure it is installed " % err +
                               "properly. Run 'python -c \"import pysvn\"' to test.")

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


def avail_repositories(check_useable=True):
    """
    Return all available repositories.
        check_useable: boolean, if True, only return usable repositories
    """
    class_dict = dict([(x.__name__, x) for x in get_subclasses(Repository) if x.USABLE or not check_useable])

    if not 'FileRepository' in class_dict:
        _log.error('avail_repositories: FileRepository missing from list of repositories')

    return class_dict


def init_repository(repository, repository_path):
    """Return an instance of the selected repository class."""
    if isinstance(repository, Repository):
        return repository
    elif isinstance(repository, basestring):
        repo = avail_repositories().get(repository)
        try:
            if isinstance(repository_path, basestring):
                return repo(repository_path)
            elif isinstance(repository_path, (tuple, list)) and len(repository_path) <= 2:
                return repo(*repository_path)
            else:
                _log.error('repository_path should be a string or list/tuple of maximum 2 elements (current: %s, type %s)' %
                           (repository_path, type(repository_path)))
        except Exception, err:
            _log.error('Failed to create a repository instance for %s (class %s) with args %s (msg: %s)' %
                       (repository, repo.__name__, repository_path, err))
    else:
        _log.error('Unknown typo of repository spec: %s (type %s)' % (repo, type(repo)))
