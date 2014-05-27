##
# Copyright 2012-2014 Ghent University
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
##
"""
Utility module for working with github

@author: Jens Timmerman (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import base64
import os
import re
import socket
import tempfile
import urllib
import urllib2
from vsc.utils import fancylogger
from vsc.utils.patterns import Singleton


_log = fancylogger.getLogger('github', fname=False)


try:
    import keyring
    HAVE_KEYRING = True
except ImportError, err:
    _log.warning("Failed to import 'keyring' Python module: %s" % err)
    HAVE_KEYRING = False

try:
    from vsc.utils.rest import RestClient
    HAVE_GITHUB_API = True
except ImportError, err:
    _log.warning("Failed to import from 'vsc.utils.rest' Python module: %s" % err)
    HAVE_GITHUB_API = False

from easybuild.tools.filetools import det_patched_files, mkdir


GITHUB_API_URL = 'https://api.github.com'
GITHUB_DIR_TYPE = u'dir'
GITHUB_EB_MAIN = 'hpcugent'
GITHUB_EASYCONFIGS_REPO = 'easybuild-easyconfigs'
GITHUB_FILE_TYPE = u'file'
GITHUB_MERGEABLE_STATE_CLEAN = 'clean'
GITHUB_RAW = 'https://raw.githubusercontent.com'
GITHUB_STATE_CLOSED = 'closed'
HTTP_STATUS_OK = 200
HTTP_STATUS_CREATED = 201
KEYRING_GITHUB_TOKEN = 'github_token'
URL_SEPARATOR = '/'


class Githubfs(object):
    """This class implements some higher level functionality on top of the Github api"""

    def __init__(self, githubuser, reponame, branchname="master", username=None, password=None, token=None):
        """Construct a new githubfs object
        @param githubuser: the github user's repo we want to use.
        @param reponame: The name of the repository we want to use.
        @param branchname: Then name of the branch to use (defaults to master)
        @param username: (optional) your github username.
        @param password: (optional) your github password.
        @param token:    (optional) a github api token.
        """
        if token is None:
            token = fetch_github_token(username)
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.gh = RestClient(GITHUB_API_URL, username=username, password=password, token=token)
        self.githubuser = githubuser
        self.reponame = reponame
        self.branchname = branchname

    @staticmethod
    def join(*args):
        """This method joins 'paths' inside a github repository"""
        args = [x for x in args if x]
        return URL_SEPARATOR.join(args)

    def get_repo(self):
        """Returns the repo as a Github object (from agithub)"""
        return self.gh.repos[self.githubuser][self.reponame]

    def get_path(self, path):
        """returns the path as a Github object (from agithub)"""
        endpoint = self.get_repo()['contents']
        if path:
            for subpath in path.split(URL_SEPARATOR):
                endpoint = endpoint[subpath]
        return endpoint

    @staticmethod
    def isdir(githubobj):
        """Check if this path points to a directory"""
        if isinstance(githubobj,(list, tuple)):
            return True
        else:
            try:
                return githubobj['type'] == GITHUB_DIR_TYPE
            except:
                return False

    @staticmethod
    def isfile(githubobj):
        """Check if this path points to a file"""
        try:
            return githubobj['type'] == GITHUB_FILE_TYPE
        except:
            return False

    def listdir(self, path):
        """List the contents of a directory"""
        path = self.get_path(path)
        listing = path.get(ref=self.branchname)
        self.log.debug("listdir response: %s" % str(listing))
        if listing[0] == 200:
            return listing[1]
        else:
            self.log.warning("error: %s" % str(listing))
            self.log.exception("Invalid response from github (I/O error)")

    def walk(self, top=None, topdown=True):
        """
        Walk the github repo in an os.walk like fashion.
        """
        isdir, listdir =  self.isdir, self.listdir

        # If this fails we blow up, since permissions on a github repo are recursive anyway.j
        githubobjs = listdir(top)
        # listdir works with None, but we want to show a decent 'root dir' name
        dirs, nondirs = [], []
        for githubobj in githubobjs:
            if isdir(githubobj):
                dirs.append(str(githubobj['name']))
            else:
                nondirs.append(str(githubobj['name']))

        if topdown:
            yield top, dirs, nondirs

        for name in dirs:
            new_path = self.join(top, name)
            for x in self.walk(new_path, topdown):
                yield x
        if not topdown:
            yield top, dirs, nondirs

    def read(self, path, api=True):
        """Read the contents of a file and return it
        Or, if api=False it will download the file and return the location of the downloaded file"""
        # we don't need use the api for this, but can also use raw.github.com
        # https://raw.github.com/hpcugent/easybuild/master/README.rst
        if not api:
            outfile = tempfile.mkstemp()[1]
            url = ("http://raw.github.com/%s/%s/%s/%s" % (self.githubuser, self.reponame, self.branchname, path))
            urllib.urlretrieve(url, outfile)
            return outfile
        else:
            obj = self.get_path(path).get(ref=self.branchname)[1]
            if not self.isfile(obj):
                raise GithubError("Error: not a valid file: %s" % str(obj))
            return  base64.b64decode(obj['content'])


class GithubError(Exception):
    """Error raised by the Githubfs"""
    pass


def fetch_easyconfigs_from_pr(pr, path=None, github_user=None):
    """Fetch patched easyconfig files for a particular PR."""

    def download(url, path=None):
        """Download file from specified URL to specified path."""
        if path is not None:
            try:
                _, httpmsg = urllib.urlretrieve(url, path)
                _log.debug("Downloaded %s to %s" % (url, path))
            except IOError, err:
                _log.error("Failed to download %s to %s: %s" % (url, path, err))

            if not httpmsg.type == 'text/plain':
                _log.error("Unexpected file type for %s: %s" % (path, httpmsg.type))
        else:
            try:
                return urllib2.urlopen(url).read()
            except urllib2.URLError, err:
                _log.error("Failed to open %s for reading: %s" % (url, err))

    # a GitHub token is optional here, but can be used if available in order to be less susceptible to rate limiting
    github_token = fetch_github_token(github_user)

    if path is None:
        path = tempfile.mkdtemp()
    else:
        # make sure path exists, create it if necessary
        mkdir(path, parents=True)

    _log.debug("Fetching easyconfigs from PR #%s into %s" % (pr, path))

    # fetch data for specified PR
    g = RestClient(GITHUB_API_URL, username=github_user, token=github_token)
    pr_url = g.repos[GITHUB_EB_MAIN][GITHUB_EASYCONFIGS_REPO].pulls[pr]
    try:
        status, pr_data = pr_url.get()
    except socket.gaierror, err:
        status, pr_data = 0, None
    _log.debug("status: %d, data: %s" % (status, pr_data))
    if not status == HTTP_STATUS_OK:
        tup = (pr, GITHUB_EB_MAIN, GITHUB_EASYCONFIGS_REPO, status, pr_data)
        _log.error("Failed to get data for PR #%d from %s/%s (status: %d %s)" % tup)

    # 'clean' on successful (or missing) test, 'unstable' on failed tests
    stable = pr_data['mergeable_state'] == GITHUB_MERGEABLE_STATE_CLEAN
    if not stable:
        tup = (pr, GITHUB_MERGEABLE_STATE_CLEAN, pr_data['mergeable_state'])
        _log.warning("Mergeable state for PR #%d is not '%s': %s." % tup)

    for key, val in sorted(pr_data.items()):
        _log.debug("\n%s:\n\n%s\n" % (key, val))

    # determine list of changed files via diff
    diff_txt = download(pr_data['diff_url'])

    patched_files = det_patched_files(txt=diff_txt, omit_ab_prefix=True)
    _log.debug("List of patches files: %s" % patched_files)

    # obtain last commit
    status, commits_data = pr_url.commits.get()
    last_commit = commits_data[-1]
    _log.debug("Commits: %s" % commits_data)

    # obtain most recent version of patched files
    for patched_file in patched_files:
        fn = os.path.basename(patched_file)
        sha = last_commit['sha']
        full_url = URL_SEPARATOR.join([GITHUB_RAW, GITHUB_EB_MAIN, GITHUB_EASYCONFIGS_REPO, sha, patched_file])
        _log.info("Downloading %s from %s" % (fn, full_url))
        download(full_url, path=os.path.join(path, fn))

    all_files = [os.path.basename(x) for x in patched_files]
    tmp_files = os.listdir(path)
    if not sorted(tmp_files) == sorted(all_files):
        _log.error("Not all patched files were downloaded to %s: %s vs %s" % (path, tmp_files, all_files))

    ec_files = [os.path.join(path, fn) for fn in tmp_files]

    return ec_files


def create_gist(txt, fn, descr=None, github_user=None):
    """Create a gist with the provided text."""
    if descr is None:
        descr = "(none)"
    github_token = fetch_github_token(github_user)

    body = {
        "description": descr,
        "public": True,
        "files": {
            fn: {
                "content": txt,
            }
        }
    }
    g = RestClient(GITHUB_API_URL, username=github_user, token=github_token)
    status, data = g.gists.post(body=body)

    if not status == HTTP_STATUS_CREATED:
        _log.error("Failed to create gist; status %s, data: %s" % (status, data))

    return data['html_url']


def post_comment_in_issue(issue, txt, repo=GITHUB_EASYCONFIGS_REPO, github_user=None):
    """Post a comment in the specified PR."""
    if not isinstance(issue, int):
        try:
            issue = int(issue)
        except ValueError, err:
            _log.error("Failed to parse specified pull request number '%s' as an int: %s; " % (issue, err))
    github_token = fetch_github_token(github_user)

    g = RestClient(GITHUB_API_URL, username=github_user, token=github_token)
    pr_url = g.repos[GITHUB_EB_MAIN][repo].issues[issue]

    status, data = pr_url.comments.post(body={'body': txt})
    if not status == HTTP_STATUS_CREATED:
        _log.error("Failed to create comment in PR %s#%d; status %s, data: %s" % (repo, issue, status, data))


class GithubToken(object):
    """Representation of a GitHub token."""

    # singleton metaclass: only one instance is created
    __metaclass__ = Singleton

    def __init__(self, user):
        """Initialize: obtain GitHub token for specified user from keyring."""
        self.token = None
        if user is None:
            msg = "No GitHub user name provided, required for fetching GitHub token."
        elif not HAVE_KEYRING:
            msg = "Failed to obtain GitHub token from keyring, "
            msg += "required Python module https://pypi.python.org/pypi/keyring is not available."
        else:
            self.token = keyring.get_password(KEYRING_GITHUB_TOKEN, user)
            if self.token is None:
                tup = (KEYRING_GITHUB_TOKEN, user)
                python_cmd = "import getpass, keyring; keyring.set_password(\"%s\", \"%s\", getpass.getpass())" % tup
                msg = '\n'.join([
                    "Failed to obtain GitHub token for %s" % user,
                    "Use the following procedure to install a GitHub token in your keyring:",
                    "$ python -c '%s'" % python_cmd,
                ])

        if self.token is None:
            # failure, for some reason
            _log.warning(msg)
        else:
            # success
            _log.info("Successfully obtained GitHub token for user %s from keyring." % user)

def fetch_github_token(user):
    """Fetch GitHub token for specified user from keyring."""
    return GithubToken(user).token
