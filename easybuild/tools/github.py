##
# Copyright 2012-2021 Ghent University
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
##
"""
Utility module for working with github

:author: Jens Timmerman (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Toon Willems (Ghent University)
"""
import base64
import copy
import getpass
import glob
import functools
import itertools
import os
import random
import re
import socket
import sys
import tempfile
import time
from datetime import datetime, timedelta
from distutils.version import LooseVersion

from easybuild.base import fancylogger
from easybuild.framework.easyconfig.easyconfig import EASYCONFIGS_ARCHIVE_DIR
from easybuild.framework.easyconfig.easyconfig import copy_easyconfigs, copy_patch_files, det_file_info
from easybuild.framework.easyconfig.easyconfig import process_easyconfig
from easybuild.framework.easyconfig.parser import EasyConfigParser
from easybuild.tools.build_log import EasyBuildError, print_msg, print_warning
from easybuild.tools.config import build_option
from easybuild.tools.filetools import apply_patch, copy_dir, copy_easyblocks, copy_framework_files
from easybuild.tools.filetools import det_patched_files, download_file, extract_file
from easybuild.tools.filetools import get_easyblock_class_name, mkdir, read_file, symlink, which, write_file
from easybuild.tools.py2vs3 import HTTPError, URLError, ascii_letters, urlopen
from easybuild.tools.systemtools import UNKNOWN, get_tool_version
from easybuild.tools.utilities import nub, only_if_module_is_available


_log = fancylogger.getLogger('github', fname=False)


try:
    import keyring
    HAVE_KEYRING = True
except ImportError as err:
    _log.warning("Failed to import 'keyring' Python module: %s" % err)
    HAVE_KEYRING = False

try:
    from easybuild.base.rest import RestClient
    HAVE_GITHUB_API = True
except ImportError as err:
    _log.warning("Failed to import from 'easybuild.base.rest' Python module: %s" % err)
    HAVE_GITHUB_API = False

try:
    import git
    from git import GitCommandError
except ImportError as err:
    _log.warning("Failed to import 'git' Python module: %s", err)


GITHUB_URL = 'https://github.com'
GITHUB_API_URL = 'https://api.github.com'
GITHUB_BRANCH_MAIN = 'main'
GITHUB_BRANCH_MASTER = 'master'
GITHUB_DIR_TYPE = u'dir'
GITHUB_EB_MAIN = 'easybuilders'
GITHUB_EASYBLOCKS_REPO = 'easybuild-easyblocks'
GITHUB_EASYCONFIGS_REPO = 'easybuild-easyconfigs'
GITHUB_FRAMEWORK_REPO = 'easybuild-framework'
GITHUB_DEVELOP_BRANCH = 'develop'
GITHUB_FILE_TYPE = u'file'
GITHUB_PR_STATE_OPEN = 'open'
GITHUB_PR_STATES = [GITHUB_PR_STATE_OPEN, 'closed', 'all']
GITHUB_PR_ORDER_CREATED = 'created'
GITHUB_PR_ORDERS = [GITHUB_PR_ORDER_CREATED, 'updated', 'popularity', 'long-running']
GITHUB_PR_DIRECTION_DESC = 'desc'
GITHUB_PR_DIRECTIONS = ['asc', GITHUB_PR_DIRECTION_DESC]
GITHUB_MAX_PER_PAGE = 100
GITHUB_MERGEABLE_STATE_CLEAN = 'clean'
GITHUB_PR = 'pull'
GITHUB_RAW = 'https://raw.githubusercontent.com'
GITHUB_STATE_CLOSED = 'closed'
HTTP_STATUS_OK = 200
HTTP_STATUS_CREATED = 201
HTTP_STATUS_NO_CONTENT = 204
KEYRING_GITHUB_TOKEN = 'github_token'
URL_SEPARATOR = '/'

STATUS_PENDING = 'pending'
STATUS_SUCCESS = 'success'

VALID_CLOSE_PR_REASONS = {
    'archived': 'uses an archived toolchain',
    'inactive': 'no activity for > 6 months',
    'obsolete': 'obsoleted by more recent PRs',
    'retest': 'closing and reopening to trigger tests',
}


def pick_default_branch(github_owner):
    """Determine default name to use."""
    # use 'main' as default branch for 'easybuilders' organisation,
    # otherwise use 'master'
    if github_owner == GITHUB_EB_MAIN:
        branch = GITHUB_BRANCH_MAIN
    else:
        branch = GITHUB_BRANCH_MASTER

    return branch


class Githubfs(object):
    """This class implements some higher level functionality on top of the Github api"""

    def __init__(self, githubuser, reponame, branchname=None, username=None, password=None, token=None):
        """Construct a new githubfs object
        :param githubuser: the github user's repo we want to use.
        :param reponame: The name of the repository we want to use.
        :param branchname: Then name of the branch to use (defaults to 'main' for easybuilders org, 'master' otherwise)
        :param username: (optional) your github username.
        :param password: (optional) your github password.
        :param token:    (optional) a github api token.
        """
        if branchname is None:
            branchname = pick_default_branch(githubuser)

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
        if isinstance(githubobj, (list, tuple)):
            return True
        else:
            try:
                return githubobj['type'] == GITHUB_DIR_TYPE
            except Exception:
                return False

    @staticmethod
    def isfile(githubobj):
        """Check if this path points to a file"""
        try:
            return githubobj['type'] == GITHUB_FILE_TYPE
        except Exception:
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
            raise EasyBuildError("Invalid response from github (I/O error)")

    def walk(self, top=None, topdown=True):
        """
        Walk the github repo in an os.walk like fashion.
        """
        isdir, listdir = self.isdir, self.listdir

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
        # https://raw.github.com/easybuilders/easybuild/main/README.rst
        if not api:
            outfile = tempfile.mkstemp()[1]
            url = '/'.join([GITHUB_RAW, self.githubuser, self.reponame, self.branchname, path])
            download_file(os.path.basename(path), url, outfile)
            return outfile
        else:
            obj = self.get_path(path).get(ref=self.branchname)[1]
            if not self.isfile(obj):
                raise GithubError("Error: not a valid file: %s" % str(obj))
            return base64.b64decode(obj['content'])


class GithubError(Exception):
    """Error raised by the Githubfs"""
    pass


def github_api_get_request(request_f, github_user=None, token=None, **kwargs):
    """
    Helper method, for performing get requests to GitHub API.
    :param request_f: function that should be called to compose request, providing a RestClient instance
    :param github_user: GitHub user name (to try and obtain matching GitHub token if none is provided)
    :param token: GitHub token to use
    :return: tuple with return status and data
    """
    if github_user is None:
        github_user = build_option('github_user')

    if token is None:
        token = fetch_github_token(github_user)

    # if we don't have a GitHub token, don't pass username either;
    # this makes sense for read-only actions like fetching files from PRs
    if token is None:
        _log.info("Not specifying username since no GitHub token is available for %s", github_user)
        github_user = None

    url = request_f(RestClient(GITHUB_API_URL, username=github_user, token=token))

    try:
        status, data = url.get(**kwargs)
    except socket.gaierror as err:
        _log.warning("Error occurred while performing get request: %s", err)
        status, data = 0, None

    _log.debug("get request result for %s: status: %d, data: %s", url.url, status, data)
    return (status, data)


def github_api_put_request(request_f, github_user=None, token=None, **kwargs):
    """
    Helper method, for performing put requests to GitHub API.
    :param request_f: function that should be called to compose request, providing a RestClient instance
    :param github_user: GitHub user name (to try and obtain matching GitHub token if none is provided)
    :param token: GitHub token to use
    :return: tuple with return status and data
    """
    if github_user is None:
        github_user = build_option('github_user')

    if token is None:
        token = fetch_github_token(github_user)

    url = request_f(RestClient(GITHUB_API_URL, username=github_user, token=token))

    try:
        status, data = url.put(**kwargs)
    except socket.gaierror as err:
        _log.warning("Error occurred while performing put request: %s", err)
        status, data = 0, {'message': err}

    if status == 200:
        _log.info("Put request successful: %s", data['message'])
    elif status in [405, 409]:
        raise EasyBuildError("FAILED: %s", data['message'])
    else:
        raise EasyBuildError("FAILED: %s", data.get('message', "(unknown reason)"))

    _log.debug("get request result for %s: status: %d, data: %s", url.url, status, data)
    return (status, data)


def fetch_latest_commit_sha(repo, account, branch=None, github_user=None, token=None):
    """
    Fetch latest SHA1 for a specified repository and branch.
    :param repo: GitHub repository
    :param account: GitHub account
    :param branch: branch to fetch latest SHA1 for
    :param github_user: name of GitHub user to use
    :param token: GitHub token to use
    :return: latest SHA1
    """
    if branch is None:
        branch = pick_default_branch(account)

    status, data = github_api_get_request(lambda x: x.repos[account][repo].branches,
                                          github_user=github_user, token=token, per_page=GITHUB_MAX_PER_PAGE)
    if status != HTTP_STATUS_OK:
        raise EasyBuildError("Failed to get latest commit sha for branch %s from %s/%s (status: %d %s)",
                             branch, account, repo, status, data)

    res = None
    for entry in data:
        if entry[u'name'] == branch:
            res = entry['commit']['sha']
            break

    if res is None:
        error_msg = "No branch with name %s found in repo %s/%s" % (branch, account, repo)
        if len(data) >= GITHUB_MAX_PER_PAGE:
            error_msg += "; only %d branches were checked (too many branches in %s/%s?)" % (len(data), account, repo)
        raise EasyBuildError(error_msg + ': ' + ', '.join([x[u'name'] for x in data]))

    return res


def download_repo(repo=GITHUB_EASYCONFIGS_REPO, branch=None, account=GITHUB_EB_MAIN, path=None, github_user=None):
    """
    Download entire GitHub repo as a tar.gz archive, and extract it into specified path.
    :param repo: repo to download
    :param branch: branch to download
    :param account: GitHub account to download repo from
    :param path: path to extract to
    :param github_user: name of GitHub user to use
    """
    if branch is None:
        branch = pick_default_branch(account)

    # make sure path exists, create it if necessary
    if path is None:
        path = tempfile.mkdtemp()

    # add account subdir
    path = os.path.join(path, account)
    mkdir(path, parents=True)

    extracted_dir_name = '%s-%s' % (repo, branch)
    base_name = '%s.tar.gz' % branch
    latest_commit_sha = fetch_latest_commit_sha(repo, account, branch, github_user=github_user)

    expected_path = os.path.join(path, extracted_dir_name)
    latest_sha_path = os.path.join(expected_path, 'latest-sha')

    # check if directory already exists, don't download if 'latest-sha' file indicates that it's up to date
    if os.path.exists(latest_sha_path):
        sha = read_file(latest_sha_path).split('\n')[0].rstrip()
        if latest_commit_sha == sha:
            _log.debug("Not redownloading %s/%s as it already exists: %s" % (account, repo, expected_path))
            return expected_path

    url = URL_SEPARATOR.join([GITHUB_URL, account, repo, 'archive', base_name])

    target_path = os.path.join(path, base_name)
    _log.debug("downloading repo %s/%s as archive from %s to %s" % (account, repo, url, target_path))
    download_file(base_name, url, target_path, forced=True)
    _log.debug("%s downloaded to %s, extracting now" % (base_name, path))

    base_dir = extract_file(target_path, path, forced=True, change_into_dir=False)
    extracted_path = os.path.join(base_dir, extracted_dir_name)

    # check if extracted_path exists
    if not os.path.isdir(extracted_path):
        raise EasyBuildError("%s should exist and contain the repo %s at branch %s", extracted_path, repo, branch)

    write_file(latest_sha_path, latest_commit_sha, forced=True)

    _log.debug("Repo %s at branch %s extracted into %s" % (repo, branch, extracted_path))
    return extracted_path


def pr_files_cache(func):
    """
    Decorator to cache result of fetch_files_from_pr.
    """
    cache = {}

    @functools.wraps(func)
    def cache_aware_func(pr, path=None, github_user=None, github_account=None, github_repo=None):
        """Retrieve cached result, or fetch files from PR & cache result."""
        # cache key is combination of all function arguments (incl. optional ones)
        key = (pr, github_account, github_repo, path)

        if key in cache and all(os.path.exists(x) for x in cache[key]):
            _log.info("Using cached value for fetch_files_from_pr for PR #%s (account=%s, repo=%s, path=%s)",
                      pr, github_account, github_repo, path)
            return cache[key]
        else:
            res = func(pr, path=path, github_user=github_user, github_account=github_account, github_repo=github_repo)
            cache[key] = res
            return res

    # expose clear/update methods of cache + cache itself to wrapped function
    cache_aware_func._cache = cache  # useful in tests
    cache_aware_func.clear_cache = cache.clear
    cache_aware_func.update_cache = cache.update

    return cache_aware_func


@pr_files_cache
def fetch_files_from_pr(pr, path=None, github_user=None, github_account=None, github_repo=None):
    """Fetch patched files for a particular PR."""

    if github_user is None:
        github_user = build_option('github_user')

    if github_repo is None:
        github_repo = GITHUB_EASYCONFIGS_REPO

    if path is None:
        if github_repo == GITHUB_EASYCONFIGS_REPO:
            pr_paths = build_option('pr_paths')
            if pr_paths:
                # figure out directory for this specific PR (see also alt_easyconfig_paths)
                cands = [p for p in pr_paths if p.endswith('files_pr%s' % pr)]
                if len(cands) == 1:
                    path = cands[0]
                else:
                    raise EasyBuildError("Failed to isolate path for PR #%s from list of PR paths: %s", pr, pr_paths)

        elif github_repo == GITHUB_EASYBLOCKS_REPO:
            path = os.path.join(tempfile.gettempdir(), 'ebs_pr%s' % pr)
        else:
            raise EasyBuildError("Unknown repo: %s" % github_repo)

    if path is None:
        path = tempfile.mkdtemp()
    else:
        # make sure path exists, create it if necessary
        mkdir(path, parents=True)

    if github_account is None:
        github_account = build_option('pr_target_account')

    if github_repo == GITHUB_EASYCONFIGS_REPO:
        easyfiles = 'easyconfigs'
    elif github_repo == GITHUB_EASYBLOCKS_REPO:
        easyfiles = 'easyblocks'
    else:
        raise EasyBuildError("Don't know how to fetch files from repo %s", github_repo)

    subdir = os.path.join('easybuild', easyfiles)

    _log.debug("Fetching %s from %s/%s PR #%s into %s", easyfiles, github_account, github_repo, pr, path)
    pr_data, _ = fetch_pr_data(pr, github_account, github_repo, github_user)

    pr_merged = pr_data['merged']
    pr_closed = pr_data['state'] == GITHUB_STATE_CLOSED and not pr_merged

    pr_target_branch = pr_data['base']['ref']
    _log.info("Target branch for PR #%s: %s", pr, pr_target_branch)

    # download target branch of PR so we can try and apply the PR patch on top of it
    repo_target_branch = download_repo(repo=github_repo, account=github_account, branch=pr_target_branch,
                                       github_user=github_user)

    # determine list of changed files via diff
    diff_fn = os.path.basename(pr_data['diff_url'])
    diff_filepath = os.path.join(path, diff_fn)
    download_file(diff_fn, pr_data['diff_url'], diff_filepath, forced=True)
    diff_txt = read_file(diff_filepath)
    _log.debug("Diff for PR #%s:\n%s", pr, diff_txt)

    patched_files = det_patched_files(txt=diff_txt, omit_ab_prefix=True, github=True, filter_deleted=True)
    _log.debug("List of patched files for PR #%s: %s", pr, patched_files)

    final_path = None

    # try to apply PR patch on top of target branch, unless the PR is closed or already merged
    if pr_merged:
        _log.info("PR is already merged, so using current version of PR target branch")
        final_path = repo_target_branch

    elif not pr_closed:
        try:
            _log.debug("Trying to apply PR patch %s to %s...", diff_filepath, repo_target_branch)
            apply_patch(diff_filepath, repo_target_branch, use_git=True)
            _log.info("Using %s which included PR patch to test PR #%s", repo_target_branch, pr)
            final_path = repo_target_branch

        except EasyBuildError as err:
            _log.warning("Ignoring problem that occured when applying PR patch: %s", err)

    if final_path is None:

        if pr_closed:
            print_warning("Using %s from closed PR #%s" % (easyfiles, pr))

        # obtain most recent version of patched files
        for patched_file in [f for f in patched_files if subdir in f]:
            # path to patch file, incl. subdir it is in
            fn = patched_file.split(subdir)[1].strip(os.path.sep)
            sha = pr_data['head']['sha']
            full_url = URL_SEPARATOR.join([GITHUB_RAW, github_account, github_repo, sha, patched_file])
            _log.info("Downloading %s from %s", fn, full_url)
            download_file(fn, full_url, path=os.path.join(path, fn), forced=True)

        final_path = path

    # symlink directories into expected place if they're not there yet
    if final_path != path:
        dirpath = os.path.join(final_path, subdir)
        for eb_dir in os.listdir(dirpath):
            symlink(os.path.join(dirpath, eb_dir), os.path.join(path, os.path.basename(eb_dir)))

    # sanity check: make sure all patched files are downloaded
    files = []
    for patched_file in [f for f in patched_files if subdir in f]:
        fn = patched_file.split(easyfiles)[1].strip(os.path.sep)
        full_path = os.path.join(path, fn)
        if os.path.exists(full_path):
            files.append(full_path)
        else:
            raise EasyBuildError("Couldn't find path to patched file %s", full_path)

    return files


def fetch_easyblocks_from_pr(pr, path=None, github_user=None):
    """Fetch patched easyconfig files for a particular PR."""
    return fetch_files_from_pr(pr, path, github_user, github_repo=GITHUB_EASYBLOCKS_REPO)


def fetch_easyconfigs_from_pr(pr, path=None, github_user=None):
    """Fetch patched easyconfig files for a particular PR."""
    return fetch_files_from_pr(pr, path, github_user, github_repo=GITHUB_EASYCONFIGS_REPO)


def create_gist(txt, fn, descr=None, github_user=None, github_token=None):
    """Create a gist with the provided text."""

    dry_run = build_option('dry_run') or build_option('extended_dry_run')

    if descr is None:
        descr = "(none)"

    if github_token is None:
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

    if dry_run:
        status, data = HTTP_STATUS_CREATED, {'html_url': 'https://gist.github.com/DRY_RUN'}
    else:
        g = RestClient(GITHUB_API_URL, username=github_user, token=github_token)
        status, data = g.gists.post(body=body)

    if status != HTTP_STATUS_CREATED:
        raise EasyBuildError("Failed to create gist; status %s, data: %s", status, data)

    return data['html_url']


def delete_gist(gist_id, github_user=None, github_token=None):
    """Delete gist with specified ID."""

    if github_token is None:
        github_token = fetch_github_token(github_user)

    gh = RestClient(GITHUB_API_URL, username=github_user, token=github_token)
    status, data = gh.gists[gist_id].delete()

    if status != HTTP_STATUS_NO_CONTENT:
        raise EasyBuildError("Failed to delete gist with ID %s: status %s, data: %s", status, data)


def post_comment_in_issue(issue, txt, account=GITHUB_EB_MAIN, repo=GITHUB_EASYCONFIGS_REPO, github_user=None):
    """Post a comment in the specified PR."""
    if not isinstance(issue, int):
        try:
            issue = int(issue)
        except ValueError as err:
            raise EasyBuildError("Failed to parse specified pull request number '%s' as an int: %s; ", issue, err)

    dry_run = build_option('dry_run') or build_option('extended_dry_run')

    msg = "Adding comment to %s issue #%s: '%s'" % (repo, issue, txt)
    if dry_run:
        msg = "[DRY RUN] " + msg
    print_msg(msg, log=_log, prefix=False)

    if not dry_run:
        github_token = fetch_github_token(github_user)

        g = RestClient(GITHUB_API_URL, username=github_user, token=github_token)
        pr_url = g.repos[account][repo].issues[issue]

        status, data = pr_url.comments.post(body={'body': txt})
        if not status == HTTP_STATUS_CREATED:
            raise EasyBuildError("Failed to create comment in PR %s#%d; status %s, data: %s", repo, issue, status, data)


def init_repo(path, repo_name, silent=False):
    """
    Initialize a new Git repository at the specified location.

    :param path: location where Git repository should be initialized
    :param repo_name: name of Git repository
    :param silent: keep quiet (don't print any messages)
    """
    repo_path = os.path.join(path, repo_name)

    if not os.path.exists(repo_path):
        mkdir(repo_path, parents=True)

    # clone repo in git_working_dirs_path to repo_path
    git_working_dirs_path = build_option('git_working_dirs_path')
    if git_working_dirs_path:
        workdir = os.path.join(git_working_dirs_path, repo_name)
        if os.path.exists(workdir):
            print_msg("cloning git repo from %s..." % workdir, silent=silent)
            try:
                workrepo = git.Repo(workdir)
                workrepo.clone(repo_path)
            except GitCommandError as err:
                raise EasyBuildError("Failed to clone git repo at %s: %s", workdir, err)

    # initalize repo in repo_path
    try:
        repo = git.Repo.init(repo_path)
    except GitCommandError as err:
        raise EasyBuildError("Failed to init git repo at %s: %s", repo_path, err)

    _log.debug("temporary git working directory ready at %s", repo_path)

    return repo


def setup_repo_from(git_repo, github_url, target_account, branch_name, silent=False):
    """
    Set up repository by checking out specified branch from repository at specified URL.

    :param git_repo: git.Repo instance
    :param github_url: URL to GitHub repository
    :param target_account: name of GitHub account that owns GitHub repository at specified URL
    :param branch_name: name of branch to check out
    :param silent: keep quiet (don't print any messages)
    """
    _log.debug("Cloning from %s", github_url)

    if target_account is None:
        raise EasyBuildError("target_account not specified in setup_repo_from!")

    # salt to use for names of remotes/branches that are created
    salt = ''.join(random.choice(ascii_letters) for _ in range(5))

    remote_name = 'pr_target_account_%s_%s' % (target_account, salt)

    origin = git_repo.create_remote(remote_name, github_url)
    if not origin.exists():
        raise EasyBuildError("%s does not exist?", github_url)

    # git fetch
    # can't use --depth to only fetch a shallow copy, since pushing to another repo from a shallow copy doesn't work
    print_msg("fetching branch '%s' from %s..." % (branch_name, github_url), silent=silent)
    res = None
    try:
        res = origin.fetch()
    except GitCommandError as err:
        raise EasyBuildError("Failed to fetch branch '%s' from %s: %s", branch_name, github_url, err)

    if res:
        if res[0].flags & res[0].ERROR:
            raise EasyBuildError("Fetching branch '%s' from remote %s failed: %s", branch_name, origin, res[0].note)
        else:
            _log.debug("Fetched branch '%s' from remote %s (note: %s)", branch_name, origin, res[0].note)
    else:
        raise EasyBuildError("Fetching branch '%s' from remote %s failed: empty result", branch_name, origin)

    # git checkout -b <branch>; git pull
    if hasattr(origin.refs, branch_name):
        origin_branch = getattr(origin.refs, branch_name)
    else:
        raise EasyBuildError("Branch '%s' not found at %s", branch_name, github_url)

    _log.debug("Checking out branch '%s' from remote %s", branch_name, github_url)
    try:
        origin_branch.checkout(b=branch_name)
    except GitCommandError as err:
        alt_branch = '%s_%s' % (branch_name, salt)
        _log.debug("Trying to work around checkout error ('%s') by using different branch name '%s'", err, alt_branch)
        try:
            origin_branch.checkout(b=alt_branch, force=True)
        except GitCommandError as err:
            raise EasyBuildError("Failed to check out branch '%s' from repo at %s: %s", alt_branch, github_url, err)

    return remote_name


def setup_repo(git_repo, target_account, target_repo, branch_name, silent=False, git_only=False):
    """
    Set up repository by checking out specified branch for specfied GitHub account/repository.

    :param git_repo: git.Repo instance
    :param target_account: name of GitHub account that owns GitHub repository
    :param target_repo: name of GitHib repository
    :param branch_name: name of branch to check out
    :param silent: keep quiet (don't print any messages)
    :param git_only: only use git@github.com repo URL, skip trying https://github.com first
    """
    tmpl_github_urls = [
        'git@github.com:%s/%s.git',
    ]
    if not git_only:
        tmpl_github_urls.insert(0, 'https://github.com/%s/%s.git')

    res = None
    errors = []
    for tmpl_github_url in tmpl_github_urls:
        github_url = tmpl_github_url % (target_account, target_repo)
        try:
            res = setup_repo_from(git_repo, github_url, target_account, branch_name, silent=silent)
            break

        except EasyBuildError as err:
            errors.append("Checking out branch '%s' from %s failed: %s" % (branch_name, github_url, err))

    if res:
        return res
    else:
        raise EasyBuildError('\n'.join(errors))


@only_if_module_is_available('git', pkgname='GitPython')
def _easyconfigs_pr_common(paths, ecs, start_branch=None, pr_branch=None, start_account=None, commit_msg=None):
    """
    Common code for new_pr and update_pr functions:
    * check whether all supplied paths point to existing files
    * create temporary clone of target git repository
    * fetch/checkout specified starting branch
    * copy files to right location
    * stage/commit all files in PR branch
    * push PR branch to GitHub (to account specified by --github-user)

    :param paths: paths to categorized lists of files (easyconfigs, files to delete, patches)
    :param ecs: list of parsed easyconfigs, incl. for dependencies (if robot is enabled)
    :param start_branch: name of branch to use as base for PR
    :param pr_branch: name of branch to push to GitHub
    :param start_account: name of GitHub account to use as base for PR
    :param commit_msg: commit message to use
    """
    # we need files to create the PR with
    non_existing_paths = []
    ec_paths = []
    if paths['easyconfigs'] or paths['py_files']:
        for path in paths['easyconfigs'] + paths['py_files']:
            if not os.path.exists(path):
                non_existing_paths.append(path)
            else:
                ec_paths.append(path)

        if non_existing_paths:
            raise EasyBuildError("One or more non-existing paths specified: %s", ', '.join(non_existing_paths))

    if not any(paths.values()):
        raise EasyBuildError("No paths specified")

    pr_target_repo = det_pr_target_repo(paths)
    if pr_target_repo is None:
        raise EasyBuildError("Failed to determine target repository, please specify it via --pr-target-repo!")

    # initialize repository
    git_working_dir = tempfile.mkdtemp(prefix='git-working-dir')
    git_repo = init_repo(git_working_dir, pr_target_repo)
    repo_path = os.path.join(git_working_dir, pr_target_repo)

    if pr_target_repo not in [GITHUB_EASYCONFIGS_REPO, GITHUB_EASYBLOCKS_REPO, GITHUB_FRAMEWORK_REPO]:
        raise EasyBuildError("Don't know how to create/update a pull request to the %s repository", pr_target_repo)

    if start_account is None:
        start_account = build_option('pr_target_account')

    if start_branch is None:
        # if start branch is not specified, we're opening a new PR
        # account to use is determined by active EasyBuild configuration (--github-org or --github-user)
        target_account = build_option('github_org') or build_option('github_user')

        if target_account is None:
            raise EasyBuildError("--github-org or --github-user must be specified!")

        # if branch to start from is specified, we're updating an existing PR
        start_branch = build_option('pr_target_branch')
    else:
        # account to target is the one that owns the branch used to open PR
        # (which may be different from account used to push update!)
        target_account = start_account

    # set up repository
    setup_repo(git_repo, start_account, pr_target_repo, start_branch)

    _log.debug("git status: %s", git_repo.git.status())

    # copy easyconfig files to right place
    target_dir = os.path.join(git_working_dir, pr_target_repo)
    print_msg("copying files to %s..." % target_dir)
    file_info = COPY_FUNCTIONS[pr_target_repo](ec_paths, target_dir)

    # figure out commit message to use
    if commit_msg:
        cnt = len(file_info['paths_in_repo'])
        _log.debug("Using specified commit message for all %d new/modified files at once: %s", cnt, commit_msg)
    elif pr_target_repo == GITHUB_EASYCONFIGS_REPO and all(file_info['new']) and not paths['files_to_delete']:
        # automagically derive meaningful commit message if all easyconfig files are new
        commit_msg = "adding easyconfigs: %s" % ', '.join(os.path.basename(p) for p in file_info['paths_in_repo'])
        if paths['patch_files']:
            commit_msg += " and patches: %s" % ', '.join(os.path.basename(p) for p in paths['patch_files'])
    elif pr_target_repo == GITHUB_EASYBLOCKS_REPO and all(file_info['new']):
        commit_msg = "adding easyblocks: %s" % ', '.join(os.path.basename(p) for p in file_info['paths_in_repo'])
    else:
        raise EasyBuildError("A meaningful commit message must be specified via --pr-commit-msg when "
                             "modifying/deleting files or targeting the framework repo.")

    # figure out to which software name patches relate, and copy them to the right place
    if paths['patch_files']:
        patch_specs = det_patch_specs(paths['patch_files'], file_info, [target_dir])

        print_msg("copying patch files to %s..." % target_dir)
        patch_info = copy_patch_files(patch_specs, target_dir)

    # determine path to files to delete (if any)
    deleted_paths = []
    for fn in paths['files_to_delete']:
        fullpath = os.path.join(repo_path, fn)
        if os.path.exists(fullpath):
            deleted_paths.append(fullpath)
        else:
            # if no existing relative path is specified, assume just the easyconfig file name is provided
            hits = glob.glob(os.path.join(repo_path, 'easybuild', 'easyconfigs', '*', '*', fn))
            if len(hits) == 1:
                deleted_paths.append(hits[0])
            else:
                raise EasyBuildError("Path doesn't exist or file to delete isn't found in target branch: %s", fn)

    dep_info = {
        'ecs': [],
        'paths_in_repo': [],
        'new': [],
    }

    # include missing easyconfigs for dependencies, if robot is enabled
    if ecs is not None:

        abs_paths = [os.path.realpath(os.path.abspath(path)) for path in ec_paths]
        dep_paths = [ec['spec'] for ec in ecs if os.path.realpath(ec['spec']) not in abs_paths]
        _log.info("Paths to easyconfigs for missing dependencies: %s", dep_paths)
        all_dep_info = copy_easyconfigs(dep_paths, target_dir)

        # only consider new easyconfig files for dependencies (not updated ones)
        for idx in range(len(all_dep_info['ecs'])):
            if all_dep_info['new'][idx]:
                for key in dep_info:
                    dep_info[key].append(all_dep_info[key][idx])

    # checkout target branch
    if pr_branch is None:
        if ec_paths and pr_target_repo == GITHUB_EASYCONFIGS_REPO:
            label = file_info['ecs'][0].name + re.sub('[.-]', '', file_info['ecs'][0].version)
        elif pr_target_repo == GITHUB_EASYBLOCKS_REPO and paths.get('py_files'):
            label = os.path.splitext(os.path.basename(paths['py_files'][0]))[0]
        else:
            label = ''.join(random.choice(ascii_letters) for _ in range(10))
        pr_branch = '%s_new_pr_%s' % (time.strftime("%Y%m%d%H%M%S"), label)

    # create branch to commit to and push;
    # use force to avoid errors if branch already exists (OK since this is a local temporary copy of the repo)
    git_repo.create_head(pr_branch, force=True).checkout()
    _log.info("New branch '%s' created to commit files to", pr_branch)

    # stage
    _log.debug("Staging all %d new/modified easyconfigs", len(file_info['paths_in_repo']))
    git_repo.index.add(file_info['paths_in_repo'])
    git_repo.index.add(dep_info['paths_in_repo'])

    if paths['patch_files']:
        _log.debug("Staging all %d new/modified patch files", len(patch_info['paths_in_repo']))
        git_repo.index.add(patch_info['paths_in_repo'])

    # stage deleted files
    if deleted_paths:
        git_repo.index.remove(deleted_paths)

    # overview of modifications
    if build_option('extended_dry_run'):
        print_msg("\nFull patch:\n", log=_log, prefix=False)
        print_msg(git_repo.git.diff(cached=True) + '\n', log=_log, prefix=False)

    diff_stat = git_repo.git.diff(cached=True, stat=True)
    if not diff_stat:
        raise EasyBuildError("No changed files found when comparing to current develop branch. "
                             "Refused to make empty pull request.")

    # commit
    git_repo.index.commit(commit_msg)

    push_branch_to_github(git_repo, target_account, pr_target_repo, pr_branch)

    return file_info, deleted_paths, git_repo, pr_branch, diff_stat, pr_target_repo


def create_remote(git_repo, account, repo, https=False):
    """
    Create remote in specified git working directory for specified account & repository.

    :param git_repo: git.Repo instance to use (after init_repo & setup_repo)
    :param account: GitHub account name
    :param repo: repository name
    :param https: use https:// URL rather than git@
    """

    if https:
        github_url = 'https://github.com/%s/%s.git' % (account, repo)
    else:
        github_url = 'git@github.com:%s/%s.git' % (account, repo)

    salt = ''.join(random.choice(ascii_letters) for _ in range(5))
    remote_name = 'github_%s_%s' % (account, salt)

    try:
        remote = git_repo.create_remote(remote_name, github_url)
    except GitCommandError as err:
        raise EasyBuildError("Failed to create remote %s for %s: %s", remote_name, github_url, err)

    return remote


def push_branch_to_github(git_repo, target_account, target_repo, branch):
    """
    Push specified branch to GitHub from specified git repository.

    :param git_repo: git.Repo instance to use (after init_repo & setup_repo)
    :param target_account: GitHub account name
    :param target_repo: repository name
    :param branch: name of branch to push
    """
    if target_account is None:
        raise EasyBuildError("target_account not specified in push_branch_to_github!")

    # push to GitHub
    remote = create_remote(git_repo, target_account, target_repo)

    dry_run = build_option('dry_run') or build_option('extended_dry_run')

    github_url = 'git@github.com:%s/%s.git' % (target_account, target_repo)

    push_branch_msg = "pushing branch '%s' to remote '%s' (%s)" % (branch, remote.name, github_url)
    if dry_run:
        print_msg(push_branch_msg + ' [DRY RUN]', log=_log)
    else:
        print_msg(push_branch_msg, log=_log)
        try:
            res = remote.push(branch)
        except GitCommandError as err:
            raise EasyBuildError("Failed to push branch '%s' to GitHub (%s): %s", branch, github_url, err)

        if res:
            if res[0].ERROR & res[0].flags:
                raise EasyBuildError("Pushing branch '%s' to remote %s (%s) failed: %s",
                                     branch, remote, github_url, res[0].summary)
            else:
                _log.debug("Pushed branch %s to remote %s (%s): %s", branch, remote, github_url, res[0].summary)
        else:
            raise EasyBuildError("Pushing branch '%s' to remote %s (%s) failed: empty result",
                                 branch, remote, github_url)


def is_patch_for(patch_name, ec):
    """Check whether specified patch matches any patch in the provided EasyConfig instance."""
    res = False

    patches = copy.copy(ec['patches'])

    with ec.disable_templating():
        # take into account both list of extensions (via exts_list) and components (cfr. Bundle easyblock)
        for entry in itertools.chain(ec['exts_list'], ec.get('components', [])):
            if isinstance(entry, (list, tuple)) and len(entry) == 3 and isinstance(entry[2], dict):
                templates = {'name': entry[0], 'version': entry[1]}
                options = entry[2]
                patches.extend(p[0] % templates if isinstance(p, (tuple, list)) else p % templates
                               for p in options.get('patches', []))

    for patch in patches:
        if isinstance(patch, (tuple, list)):
            patch = patch[0]
        if patch == patch_name:
            res = True
            break

    return res


def det_patch_specs(patch_paths, file_info, ec_dirs):
    """ Determine software names for patch files """
    print_msg("determining software names for patch files...")
    patch_specs = []
    for patch_path in patch_paths:
        soft_name = None
        patch_file = os.path.basename(patch_path)

        # consider patch lists of easyconfigs being provided
        for ec in file_info['ecs']:
            if is_patch_for(patch_file, ec):
                soft_name = ec['name']
                break

        if soft_name:
            patch_specs.append((patch_path, soft_name))
        else:
            # fall back on scanning all eb files for patches
            print("Matching easyconfig for %s not found on the first try:" % patch_path)
            print("scanning all easyconfigs to determine where patch file belongs (this may take a while)...")
            soft_name = find_software_name_for_patch(patch_file, ec_dirs)
            if soft_name:
                patch_specs.append((patch_path, soft_name))
            else:
                # still nothing found
                raise EasyBuildError("Failed to determine software name to which patch file %s relates", patch_path)

    return patch_specs


def find_software_name_for_patch(patch_name, ec_dirs):
    """
    Scan all easyconfigs in the robot path(s) to determine which software a patch file belongs to

    :param patch_name: name of the patch file
    :param ecs_dirs: list of directories to consider when looking for easyconfigs
    :return: name of the software that this patch file belongs to (if found)
    """

    soft_name = None

    ignore_dirs = build_option('ignore_dirs')
    all_ecs = []
    for ec_dir in ec_dirs:
        for (dirpath, dirnames, filenames) in os.walk(ec_dir):
            # Exclude ignored dirs
            if ignore_dirs:
                dirnames[:] = [i for i in dirnames if i not in ignore_dirs]
            for fn in filenames:
                # TODO: In EasyBuild 5.x only check for '*.eb' files
                if fn != 'TEMPLATE.eb' and os.path.splitext(fn)[1] not in ('.py', '.patch'):
                    path = os.path.join(dirpath, fn)
                    rawtxt = read_file(path)
                    if 'patches' in rawtxt:
                        all_ecs.append(path)

    # Usual patch names are <software>-<version>_fix_foo.patch
    # So search those ECs first
    patch_stem = os.path.splitext(patch_name)[0]
    # Extract possible sw name and version according to above scheme
    # Those might be the same as the whole patch stem, which is OK
    possible_sw_name = patch_stem.split('-')[0].lower()
    possible_sw_name_version = patch_stem.split('_')[0].lower()

    def ec_key(path):
        filename = os.path.basename(path).lower()
        # Put files with one of those as the prefix first, then sort by name
        return (
            not filename.startswith(possible_sw_name_version),
            not filename.startswith(possible_sw_name),
            filename
        )
    all_ecs.sort(key=ec_key)

    nr_of_ecs = len(all_ecs)
    for idx, path in enumerate(all_ecs):
        if soft_name:
            break
        try:
            ecs = process_easyconfig(path, validate=False)
            for ec in ecs:
                if is_patch_for(patch_name, ec['ec']):
                    soft_name = ec['ec']['name']
                    break
        except EasyBuildError as err:
            _log.debug("Ignoring easyconfig %s that fails to parse: %s", path, err)
        sys.stdout.write('\r%s of %s easyconfigs checked' % (idx + 1, nr_of_ecs))
        sys.stdout.flush()

    sys.stdout.write('\n')
    return soft_name


def check_pr_eligible_to_merge(pr_data):
    """
    Check whether PR is eligible for merging.

    :param pr_data: PR data obtained through GitHub API
    :return: boolean value indicates whether PR is eligible
    """
    res = True

    def not_eligible(msg):
        """Helper function to warn about PR not being eligible for merging"""
        print_msg("%s => not eligible for merging!" % msg, stderr=True, prefix=False)
        return False

    target = '%s/%s' % (pr_data['base']['repo']['owner']['login'], pr_data['base']['repo']['name'])
    print_msg("Checking eligibility of %s PR #%s for merging..." % (target, pr_data['number']), prefix=False)

    # check target branch, must be branch name specified in --pr-target-branch (usually 'develop')
    pr_target_branch = build_option('pr_target_branch')
    msg_tmpl = "* targets %s branch: %%s" % pr_target_branch
    if pr_data['base']['ref'] == pr_target_branch:
        print_msg(msg_tmpl % 'OK', prefix=False)
    else:
        res = not_eligible(msg_tmpl % "FAILED; found '%s'" % pr_data['base']['ref'])

    # check test suite result, Travis must give green light
    msg_tmpl = "* test suite passes: %s"
    if pr_data['status_last_commit'] == STATUS_SUCCESS:
        print_msg(msg_tmpl % 'OK', prefix=False)
    elif pr_data['status_last_commit'] == STATUS_PENDING:
        res = not_eligible(msg_tmpl % "pending...")
    else:
        res = not_eligible(msg_tmpl % "(status: %s)" % pr_data['status_last_commit'])

    if pr_data['base']['repo']['name'] == GITHUB_EASYCONFIGS_REPO:
        # check for successful test report (checked in reverse order)
        msg_tmpl = "* last test report is successful: %s"
        test_report_regex = re.compile(r"^Test report by @\S+")
        test_report_found = False
        for comment in pr_data['issue_comments'][::-1]:
            comment = comment['body']
            if test_report_regex.search(comment):
                if 'SUCCESS' in comment:
                    print_msg(msg_tmpl % 'OK', prefix=False)
                    test_report_found = True
                    break
                elif 'FAILED' in comment:
                    res = not_eligible(msg_tmpl % 'FAILED')
                    test_report_found = True
                    break
                else:
                    print_warning("Failed to determine outcome of test report for comment:\n%s" % comment)

        if not test_report_found:
            res = not_eligible(msg_tmpl % "(no test reports found)")

    # check for approved review
    approved_review_by = []
    for review in pr_data['reviews']:
        if review['state'] == 'APPROVED':
            approved_review_by.append(review['user']['login'])

    # check for requested changes
    changes_requested_by = []
    for review in pr_data['reviews']:
        if review['state'] == 'CHANGES_REQUESTED':
            if review['user']['login'] not in approved_review_by + changes_requested_by:
                changes_requested_by.append(review['user']['login'])

    msg_tmpl = "* no pending change requests: %s"
    if changes_requested_by:
        res = not_eligible(msg_tmpl % 'FAILED (changes requested by %s)' % ', '.join(changes_requested_by))
    else:
        print_msg(msg_tmpl % 'OK', prefix=False)

    msg_tmpl = "* approved review: %s"
    if approved_review_by:
        print_msg(msg_tmpl % 'OK (by %s)' % ', '.join(approved_review_by), prefix=False)
    else:
        res = not_eligible(msg_tmpl % 'MISSING')

    # check whether a milestone is set
    msg_tmpl = "* milestone is set: %s"
    if pr_data['milestone']:
        milestone = pr_data['milestone']['title']
        if '.x' in milestone:
            milestone += ", please change to the next release milestone once the PR is merged"
        print_msg(msg_tmpl % "OK (%s)" % milestone, prefix=False)
    else:
        res = not_eligible(msg_tmpl % 'no milestone found')

    # check github mergeable state
    msg_tmpl = "* mergeable state is clean: %s"
    if pr_data['merged']:
        print_msg(msg_tmpl % "PR is already merged", prefix=False)
    elif pr_data['mergeable_state'] == GITHUB_MERGEABLE_STATE_CLEAN:
        print_msg(msg_tmpl % "OK", prefix=False)
    else:
        reason = "FAILED (mergeable state is '%s')" % pr_data['mergeable_state']
        res = not_eligible(msg_tmpl % reason)

    return res


def reasons_for_closing(pr_data):
    """
    Look for valid reasons to close PR by comparing with existing easyconfigs.
    """

    if pr_data['status_last_commit']:
        print_msg("Status of last commit is %s\n" % pr_data['status_last_commit'].upper(), prefix=False)

    if pr_data['issue_comments']:
        last_comment = pr_data['issue_comments'][-1]
        timestamp = last_comment['updated_at'].replace('T', ' at ')[:-1]
        username = last_comment['user']['login']
        print_msg("Last comment on %s, by %s, was:\n\n%s" % (timestamp, username, last_comment['body']), prefix=False)

    if pr_data['reviews']:
        last_review = pr_data['reviews'][-1]
        timestamp = last_review['submitted_at'].replace('T', ' at ')[:-1]
        username = last_review['user']['login']
        state, body = last_review['state'], last_review['body']
        print_msg("Last reviewed on %s by %s, state %s\n\n%s" % (timestamp, username, state, body), prefix=False)

    possible_reasons = []

    print_msg("No activity since %s" % pr_data['updated_at'].replace('T', ' at ')[:-1], prefix=False)

    # check if PR is inactive for more than 6 months
    last_updated = datetime.strptime(pr_data['updated_at'], "%Y-%m-%dT%H:%M:%SZ")
    if datetime.now() - last_updated > timedelta(days=180):
        possible_reasons.append('inactive')

    robot_paths = build_option('robot_path')

    pr_files = [p for p in fetch_easyconfigs_from_pr(pr_data['number']) if p.endswith('.eb')]

    obsoleted = []
    uses_archived_tc = []
    for pr_file in pr_files:
        pr_ec = EasyConfigParser(pr_file).get_config_dict()
        pr_tc = '%s-%s' % (pr_ec['toolchain']['name'], pr_ec['toolchain']['version'])
        print_msg("* %s-%s" % (pr_ec['name'], pr_ec['version']), prefix=False)
        for robot_path in robot_paths:
            # check if PR easyconfig uses an archived toolchain
            path = os.path.join(robot_path, EASYCONFIGS_ARCHIVE_DIR, pr_tc[0].lower(), pr_tc.split('-')[0])
            for (dirpath, _, filenames) in os.walk(path):
                for fn in filenames:
                    if fn.endswith('.eb'):
                        ec = EasyConfigParser(os.path.join(dirpath, fn)).get_config_dict()
                        if ec.get('easyblock') == 'Toolchain':
                            if 'versionsuffix' in ec:
                                archived_tc = '%s-%s%s' % (ec['name'], ec['version'], ec.get('versionsuffix'))
                            else:
                                archived_tc = '%s-%s' % (ec['name'], ec['version'])
                            if pr_tc == archived_tc:
                                print_msg(" - uses archived toolchain %s" % pr_tc, prefix=False)
                                uses_archived_tc.append(pr_ec)

            # check if there is a newer version of PR easyconfig
            newer_versions = set()
            for (dirpath, _, filenames) in os.walk(os.path.join(robot_path, pr_ec['name'].lower()[0], pr_ec['name'])):
                for fn in filenames:
                    if fn.endswith('.eb'):
                        ec = EasyConfigParser(os.path.join(dirpath, fn)).get_config_dict()
                        if LooseVersion(ec['version']) > LooseVersion(pr_ec['version']):
                            newer_versions.add(ec['version'])

            if newer_versions:
                print_msg(" - found newer versions %s" % ", ".join(sorted(newer_versions)), prefix=False)
                obsoleted.append(pr_ec)

    if uses_archived_tc:
        possible_reasons.append('archived')

    if any(e['name'] in pr_data['title'] for e in obsoleted):
        possible_reasons.append('obsolete')

    return possible_reasons


def close_pr(pr, motivation_msg=None):
    """
    Close specified pull request

    :param pr: PR number
    :param motivation_msg: string containing motivation for closing the PR
    """
    github_user = build_option('github_user')
    if github_user is None:
        raise EasyBuildError("GitHub user must be specified to use --close-pr")

    pr_target_account = build_option('pr_target_account')
    pr_target_repo = build_option('pr_target_repo') or GITHUB_EASYCONFIGS_REPO

    pr_data, _ = fetch_pr_data(pr, pr_target_account, pr_target_repo, github_user, full=True)

    if pr_data['state'] == GITHUB_STATE_CLOSED:
        raise EasyBuildError("PR #%d from %s/%s is already closed.", pr, pr_target_account, pr_target_repo)

    pr_owner = pr_data['user']['login']
    msg = "\n%s/%s PR #%s was submitted by %s, " % (pr_target_account, pr_target_repo, pr, pr_owner)
    msg += "you are using GitHub account '%s'\n" % github_user
    msg += "\nPR Title: \"%s\"\n" % pr_data['title']
    print_msg(msg, prefix=False)

    dry_run = build_option('dry_run') or build_option('extended_dry_run')

    reopen = motivation_msg == VALID_CLOSE_PR_REASONS['retest']

    if not motivation_msg:
        print_msg("No reason or message specified, looking for possible reasons\n")
        possible_reasons = reasons_for_closing(pr_data)

        if not possible_reasons:
            raise EasyBuildError("No reason specified and none found from PR data, "
                                 "please use --close-pr-reasons or --close-pr-msg")
        else:
            motivation_msg = ", ".join([VALID_CLOSE_PR_REASONS[reason] for reason in possible_reasons])
            print_msg("\nNo reason specified but found possible reasons: %s.\n" % motivation_msg, prefix=False)

    msg = "@%s, this PR is being closed for the following reason(s): %s." % (pr_data['user']['login'], motivation_msg)
    if not reopen:
        msg += "\nPlease don't hesitate to reopen this PR or add a comment if you feel this contribution is still "
        msg += "relevant.\nFor more information on our policy w.r.t. closing PRs, see "
        msg += "https://easybuild.readthedocs.io/en/latest/Contributing.html"
        msg += "#why-a-pull-request-may-be-closed-by-a-maintainer"
    post_comment_in_issue(pr, msg, account=pr_target_account, repo=pr_target_repo, github_user=github_user)

    if dry_run:
        print_msg("[DRY RUN] Closed %s/%s PR #%s" % (pr_target_account, pr_target_repo, pr), prefix=False)
        if reopen:
            print_msg("[DRY RUN] Reopened %s/%s PR #%s" % (pr_target_account, pr_target_repo, pr), prefix=False)
    else:
        github_token = fetch_github_token(github_user)
        if github_token is None:
            raise EasyBuildError("GitHub token for user '%s' must be available to use --close-pr", github_user)
        g = RestClient(GITHUB_API_URL, username=github_user, token=github_token)
        pull_url = g.repos[pr_target_account][pr_target_repo].pulls[pr]
        body = {'state': 'closed'}
        status, data = pull_url.post(body=body)
        if not status == HTTP_STATUS_OK:
            raise EasyBuildError("Failed to close PR #%s; status %s, data: %s", pr, status, data)
        if reopen:
            body = {'state': 'open'}
            status, data = pull_url.post(body=body)
            if not status == HTTP_STATUS_OK:
                raise EasyBuildError("Failed to reopen PR #%s; status %s, data: %s", pr, status, data)


def list_prs(params, per_page=GITHUB_MAX_PER_PAGE, github_user=None):
    """
    List pull requests according to specified selection/order parameters

    :param params: 3-tuple with selection parameters for PRs (<state>, <sort>, <direction>),
                   see https://developer.github.com/v3/pulls/#parameters
    """
    parameters = {
        'state': params[0],
        'sort': params[1],
        'direction': params[2],
        'per_page': per_page,
    }
    print_msg("Listing PRs with parameters: %s" % ', '.join(k + '=' + str(parameters[k]) for k in sorted(parameters)))

    pr_target_account = build_option('pr_target_account')
    pr_target_repo = build_option('pr_target_repo') or GITHUB_EASYCONFIGS_REPO

    pr_data, _ = fetch_pr_data(None, pr_target_account, pr_target_repo, github_user, **parameters)

    lines = []
    for pr in pr_data:
        lines.append("PR #%s: %s" % (pr['number'], pr['title']))

    return '\n'.join(lines)


def merge_pr(pr):
    """
    Merge specified pull request
    """
    github_user = build_option('github_user')
    if github_user is None:
        raise EasyBuildError("GitHub user must be specified to use --merge-pr")

    pr_target_account = build_option('pr_target_account')
    pr_target_repo = build_option('pr_target_repo') or GITHUB_EASYCONFIGS_REPO

    pr_data, _ = fetch_pr_data(pr, pr_target_account, pr_target_repo, github_user, full=True)

    msg = "\n%s/%s PR #%s was submitted by %s, " % (pr_target_account, pr_target_repo, pr, pr_data['user']['login'])
    msg += "you are using GitHub account '%s'\n" % github_user
    msg += "\nPR title: %s\n\n" % pr_data['title']
    print_msg(msg, prefix=False)
    if pr_data['user']['login'] == github_user:
        raise EasyBuildError("Please do not merge your own PRs!")

    force = build_option('force')
    dry_run = build_option('dry_run') or build_option('extended_dry_run')

    if not dry_run:
        if pr_data['merged']:
            raise EasyBuildError("This PR is already merged.")
        elif pr_data['state'] == GITHUB_STATE_CLOSED:
            raise EasyBuildError("This PR is closed.")

    def merge_url(gh):
        """Utility function to fetch merge URL for a specific PR."""
        return gh.repos[pr_target_account][pr_target_repo].pulls[pr].merge

    if check_pr_eligible_to_merge(pr_data) or force:
        print_msg("\nReview %s merging pull request!\n" % ("OK,", "FAILed, yet forcibly")[force], prefix=False)

        comment = "Going in, thanks @%s!" % pr_data['user']['login']
        post_comment_in_issue(pr, comment, account=pr_target_account, repo=pr_target_repo, github_user=github_user)

        if dry_run:
            print_msg("[DRY RUN] Merged %s/%s pull request #%s" % (pr_target_account, pr_target_repo, pr), prefix=False)
        else:
            body = {
                'commit_message': pr_data['title'],
                'sha': pr_data['head']['sha'],
            }
            github_api_put_request(merge_url, github_user, body=body)
    else:
        print_warning("Review indicates this PR should not be merged (use -f/--force to do so anyway)")


def det_pr_labels(file_info, pr_target_repo):
    """
    Determine labels for a pull request based on provided information on files changed by that pull request.
    """
    labels = []
    if pr_target_repo == GITHUB_EASYCONFIGS_REPO:
        if any(file_info['new_folder']):
            labels.append('new')
        if any(file_info['new_file_in_existing_folder']):
            labels.append('update')
    elif pr_target_repo == GITHUB_EASYBLOCKS_REPO:
        if any(file_info['new']):
            labels.append('new')
    return labels


def post_pr_labels(pr, labels):
    """
    Update PR labels
    """
    pr_target_account = build_option('pr_target_account')
    pr_target_repo = build_option('pr_target_repo') or GITHUB_EASYCONFIGS_REPO

    # fetch GitHub token if available
    github_user = build_option('github_user')
    if github_user is None:
        _log.info("GitHub user not specified, not adding labels to PR# %s" % pr)
        return False

    github_token = fetch_github_token(github_user)
    if github_token is None:
        _log.info("GitHub token for user '%s' not found, not adding labels to PR# %s" % (github_user, pr))
        return False

    dry_run = build_option('dry_run') or build_option('extended_dry_run')

    if not dry_run:
        g = RestClient(GITHUB_API_URL, username=github_user, token=github_token)

        pr_url = g.repos[pr_target_account][pr_target_repo].issues[pr]
        try:
            status, data = pr_url.labels.post(body=labels)
            if status == HTTP_STATUS_OK:
                print_msg("Added labels %s to PR#%s" % (', '.join(labels), pr), log=_log, prefix=False)
                return True
        except HTTPError as err:
            _log.info("Failed to add labels to PR# %s: %s." % (pr, err))
            return False
    else:
        return True


def add_pr_labels(pr, branch=GITHUB_DEVELOP_BRANCH):
    """
    Try to determine and add labels to PR.
    :param pr: pull request number in easybuild-easyconfigs repo
    :param branch: easybuild-easyconfigs branch to compare with
    """
    pr_target_repo = build_option('pr_target_repo') or GITHUB_EASYCONFIGS_REPO
    if pr_target_repo != GITHUB_EASYCONFIGS_REPO:
        raise EasyBuildError("Adding labels to PRs for repositories other than easyconfigs hasn't been implemented yet")

    tmpdir = tempfile.mkdtemp()

    download_repo_path = download_repo(branch=branch, path=tmpdir)

    pr_files = [p for p in fetch_easyconfigs_from_pr(pr) if p.endswith('.eb')]

    file_info = det_file_info(pr_files, download_repo_path)

    pr_target_account = build_option('pr_target_account')
    github_user = build_option('github_user')
    pr_data, _ = fetch_pr_data(pr, pr_target_account, pr_target_repo, github_user)
    pr_labels = [x['name'] for x in pr_data['labels']]

    expected_labels = det_pr_labels(file_info, pr_target_repo)
    missing_labels = [x for x in expected_labels if x not in pr_labels]

    dry_run = build_option('dry_run') or build_option('extended_dry_run')

    if missing_labels:
        missing_labels_txt = ', '.join(["'%s'" % ml for ml in missing_labels])
        print_msg("PR #%s should be labelled %s" % (pr, missing_labels_txt), log=_log, prefix=False)
        if not dry_run and not post_pr_labels(pr, missing_labels):
            print_msg("Could not add labels %s to PR #%s" % (missing_labels_txt, pr), log=_log, prefix=False)
    else:
        print_msg("Could not determine any missing labels for PR #%s" % pr, log=_log, prefix=False)


@only_if_module_is_available('git', pkgname='GitPython')
def new_branch_github(paths, ecs, commit_msg=None):
    """
    Create new branch on GitHub using specified files

    :param paths: paths to categorized lists of files (easyconfigs, files to delete, patches, files with .py extension)
    :param ecs: list of parsed easyconfigs, incl. for dependencies (if robot is enabled)
    :param commit_msg: commit message to use
    """
    branch_name = build_option('pr_branch_name')
    if commit_msg is None:
        commit_msg = build_option('pr_commit_msg')

    # create branch, commit files to it & push to GitHub
    res = _easyconfigs_pr_common(paths, ecs, pr_branch=branch_name, commit_msg=commit_msg)

    return res


@only_if_module_is_available('git', pkgname='GitPython')
def new_pr_from_branch(branch_name, title=None, descr=None, pr_target_repo=None, pr_metadata=None, commit_msg=None):
    """
    Create new pull request from specified branch on GitHub.
    """

    if descr is None:
        descr = build_option('pr_descr')
    if commit_msg is None:
        commit_msg = build_option('pr_commit_msg')
    if title is None:
        title = build_option('pr_title') or commit_msg

    pr_target_account = build_option('pr_target_account')
    pr_target_branch = build_option('pr_target_branch')
    if pr_target_repo is None:
        pr_target_repo = build_option('pr_target_repo') or GITHUB_EASYCONFIGS_REPO

    # fetch GitHub token (required to perform actions on GitHub)
    github_user = build_option('github_user')
    if github_user is None:
        raise EasyBuildError("GitHub user must be specified to open a pull request")

    github_token = fetch_github_token(github_user)
    if github_token is None:
        raise EasyBuildError("GitHub token for user '%s' must be available to open a pull request", github_user)

    # GitHub organisation or GitHub user where branch is located
    github_account = build_option('github_org') or github_user

    if pr_metadata:
        file_info, deleted_paths, diff_stat = pr_metadata
    else:
        # initialize repository
        git_working_dir = tempfile.mkdtemp(prefix='git-working-dir')
        git_repo = init_repo(git_working_dir, pr_target_repo)

        # check out PR branch, and sync with current develop
        setup_repo(git_repo, github_account, pr_target_repo, branch_name)

        print_msg("syncing '%s' with current '%s/develop' branch..." % (branch_name, pr_target_account), log=_log)
        sync_with_develop(git_repo, branch_name, pr_target_account, pr_target_repo)

        # checkout target branch, to obtain diff with PR branch
        # make sure right branch is being used by checking it out via remotes/*
        print_msg("checking out target branch '%s/%s'..." % (pr_target_account, pr_target_branch), log=_log)
        remote = create_remote(git_repo, pr_target_account, pr_target_repo, https=True)
        git_repo.git.fetch(remote.name)
        if pr_target_branch in [b.name for b in git_repo.branches]:
            git_repo.delete_head(pr_target_branch, force=True)

        full_target_branch_ref = 'remotes/%s/%s' % (remote.name, pr_target_branch)
        git_repo.git.checkout(full_target_branch_ref, track=True, force=True)

        diff_stat = git_repo.git.diff(full_target_branch_ref, branch_name, stat=True)

        print_msg("determining metadata for pull request based on changed files...", log=_log)

        # figure out list of new/changed & deletes files compared to target branch
        difflist = git_repo.head.commit.diff(branch_name)
        changed_files, ec_paths, deleted_paths, patch_paths = [], [], [], []
        for diff in difflist:
            path = diff.b_path
            changed_files.append(path)
            if diff.deleted_file:
                deleted_paths.append(path)
            elif path.endswith('.eb'):
                ec_paths.append(path)
            elif path.endswith('.patch'):
                patch_paths.append(path)

        if changed_files:
            from_branch = '%s/%s' % (github_account, branch_name)
            to_branch = '%s/%s' % (pr_target_account, pr_target_branch)
            msg = ["found %d changed file(s) in '%s' relative to '%s':" % (len(changed_files), from_branch, to_branch)]
            if ec_paths:
                msg.append("* %d new/changed easyconfig file(s):" % len(ec_paths))
                msg.extend(["  " + x for x in ec_paths])
            if patch_paths:
                msg.append("* %d patch(es):" % len(patch_paths))
                msg.extend(["  " + x for x in patch_paths])
            if deleted_paths:
                msg.append("* %d deleted file(s)" % len(deleted_paths))
                msg.extend(["  " + x for x in deleted_paths])

            print_msg('\n'.join(msg), log=_log)
        else:
            raise EasyBuildError("No changes in '%s' branch compared to current 'develop' branch!", branch_name)

        # copy repo while target branch is still checked out
        tmpdir = tempfile.mkdtemp()
        target_dir = os.path.join(tmpdir, pr_target_repo)
        copy_dir(os.path.join(git_working_dir, pr_target_repo), target_dir, force_in_dry_run=True)

        # check out PR branch to determine info on changed/added files relative to target branch
        # make sure right branch is being used by checkout it out via remotes/*
        print_msg("checking out PR branch '%s/%s'..." % (github_account, branch_name), log=_log)
        remote = create_remote(git_repo, github_account, pr_target_repo, https=True)
        git_repo.git.fetch(remote.name)
        if branch_name in [b.name for b in git_repo.branches]:
            git_repo.delete_head(branch_name, force=True)
        git_repo.git.checkout('remotes/%s/%s' % (remote.name, branch_name), track=True, force=True)

        # path to easyconfig files is expected to be absolute in det_file_info
        ec_paths = [os.path.join(git_working_dir, pr_target_repo, x) for x in ec_paths]

        file_info = det_file_info(ec_paths, target_dir)

    labels = det_pr_labels(file_info, pr_target_repo)

    if pr_target_repo == GITHUB_EASYCONFIGS_REPO:
        # only use most common toolchain(s) in toolchain label of PR title
        toolchains = ['%(name)s/%(version)s' % ec['toolchain'] for ec in file_info['ecs']]
        toolchains_counted = sorted([(toolchains.count(tc), tc) for tc in nub(toolchains)])
        toolchain_label = ','.join([tc for (cnt, tc) in toolchains_counted if cnt == toolchains_counted[-1][0]])

        # only use most common module class(es) in moduleclass label of PR title
        classes = [ec['moduleclass'] for ec in file_info['ecs']]
        classes_counted = sorted([(classes.count(c), c) for c in nub(classes)])
        class_label = ','.join([tc for (cnt, tc) in classes_counted if cnt == classes_counted[-1][0]])

    if title is None:
        if pr_target_repo == GITHUB_EASYCONFIGS_REPO:
            if file_info['ecs'] and all(file_info['new']) and not deleted_paths:
                # mention software name/version in PR title (only first 3)
                names_and_versions = nub(["%s v%s" % (ec.name, ec.version) for ec in file_info['ecs']])
                if len(names_and_versions) <= 3:
                    main_title = ', '.join(names_and_versions)
                else:
                    main_title = ', '.join(names_and_versions[:3] + ['...'])

                title = "{%s}[%s] %s" % (class_label, toolchain_label, main_title)

                # if Python is listed as a dependency, then mention Python version(s) in PR title
                pyver = []
                for ec in file_info['ecs']:
                    # iterate over all dependencies (incl. build dependencies & multi-deps)
                    for dep in ec.dependencies():
                        if dep['name'] == 'Python':
                            # check whether Python is listed as a multi-dep if it's marked as a build dependency
                            if dep['build_only'] and 'Python' not in ec['multi_deps']:
                                continue
                            else:
                                pyver.append(dep['version'])
                if pyver:
                    title += " w/ Python %s" % ' + '.join(sorted(nub(pyver)))
        elif pr_target_repo == GITHUB_EASYBLOCKS_REPO:
            if file_info['eb_names'] and all(file_info['new']) and not deleted_paths:
                plural = 's' if len(file_info['eb_names']) > 1 else ''
                title = "new easyblock%s for %s" % (plural, (', '.join(file_info['eb_names'])))

    if title is None:
        raise EasyBuildError("Don't know how to make a PR title for this PR. "
                             "Please include a title (use --pr-title)")

    full_descr = "(created using `eb --new-pr`)\n"
    if descr is not None:
        full_descr += descr

    # create PR
    pr_target_branch = build_option('pr_target_branch')
    dry_run = build_option('dry_run') or build_option('extended_dry_run')

    msg = '\n'.join([
        '',
        "Opening pull request%s" % ('', " [DRY RUN]")[dry_run],
        "* target: %s/%s:%s" % (pr_target_account, pr_target_repo, pr_target_branch),
        "* from: %s/%s:%s" % (github_account, pr_target_repo, branch_name),
        "* title: \"%s\"" % title,
        "* labels: %s" % (', '.join(labels) or '(none)'),
        "* description:",
        '"""',
        full_descr,
        '"""',
        "* overview of changes:\n%s" % diff_stat,
        '',
    ])
    print_msg(msg, log=_log, prefix=False)

    if not dry_run:
        g = RestClient(GITHUB_API_URL, username=github_user, token=github_token)
        pulls_url = g.repos[pr_target_account][pr_target_repo].pulls
        body = {
            'base': pr_target_branch,
            'head': '%s:%s' % (github_account, branch_name),
            'title': title,
            'body': full_descr,
        }
        status, data = pulls_url.post(body=body)
        if not status == HTTP_STATUS_CREATED:
            raise EasyBuildError("Failed to open PR for branch %s; status %s, data: %s", branch_name, status, data)

        print_msg("Opened pull request: %s" % data['html_url'], log=_log, prefix=False)

        if labels:
            pr = data['html_url'].split('/')[-1]
            if not post_pr_labels(pr, labels):
                print_msg("This PR should be labelled %s" % ', '.join(labels), log=_log, prefix=False)


def new_pr(paths, ecs, title=None, descr=None, commit_msg=None):
    """
    Open new pull request using specified files

    :param paths: paths to categorized lists of files (easyconfigs, files to delete, patches)
    :param ecs: list of parsed easyconfigs, incl. for dependencies (if robot is enabled)
    :param title: title to use for pull request
    :param descr: description to use for description
    :param commit_msg: commit message to use
    """

    if commit_msg is None:
        commit_msg = build_option('pr_commit_msg')

    # create new branch in GitHub
    res = new_branch_github(paths, ecs, commit_msg=commit_msg)
    file_info, deleted_paths, _, branch_name, diff_stat, pr_target_repo = res

    new_pr_from_branch(branch_name, title=title, descr=descr, pr_target_repo=pr_target_repo,
                       pr_metadata=(file_info, deleted_paths, diff_stat), commit_msg=commit_msg)


def det_account_branch_for_pr(pr_id, github_user=None, pr_target_repo=None):
    """Determine account & branch corresponding to pull request with specified id."""

    if github_user is None:
        github_user = build_option('github_user')

    if github_user is None:
        raise EasyBuildError("GitHub username (--github-user) must be specified!")

    pr_target_account = build_option('pr_target_account')
    if pr_target_repo is None:
        pr_target_repo = build_option('pr_target_repo') or GITHUB_EASYCONFIGS_REPO

    pr_data, _ = fetch_pr_data(pr_id, pr_target_account, pr_target_repo, github_user)

    # branch that corresponds with PR is supplied in form <account>:<branch_label>
    account = pr_data['head']['label'].split(':')[0]
    branch = ':'.join(pr_data['head']['label'].split(':')[1:])
    github_target = '%s/%s' % (pr_target_account, pr_target_repo)
    print_msg("Determined branch name corresponding to %s PR #%s: %s" % (github_target, pr_id, branch), log=_log)

    return account, branch


def det_pr_target_repo(paths):
    """Determine target repository for pull request from given cagetorized list of files

    :param paths: paths to categorized lists of files (easyconfigs, files to delete, patches, .py files)
    """
    pr_target_repo = build_option('pr_target_repo')

    # determine target repository for PR based on which files are provided
    # (see categorize_files_by_type function)
    if pr_target_repo is None:

        _log.info("Trying to derive target repository based on specified files...")

        easyconfigs, files_to_delete, patch_files, py_files = [paths[key] for key in sorted(paths.keys())]

        # Python files provided, and no easyconfig files or patches
        if py_files and not (easyconfigs or patch_files):

            _log.info("Only Python files provided, no easyconfig files or patches...")

            # if all Python files are easyblocks, target repo should be easyblocks;
            # otherwise, target repo is assumed to be framework
            if all(get_easyblock_class_name(path) for path in py_files):
                pr_target_repo = GITHUB_EASYBLOCKS_REPO
                _log.info("All Python files are easyblocks, target repository is assumed to be %s", pr_target_repo)
            else:
                pr_target_repo = GITHUB_FRAMEWORK_REPO
                _log.info("Not all Python files are easyblocks, target repository is assumed to be %s", pr_target_repo)

        # if no Python files are provided, only easyconfigs & patches, or if files to delete are .eb files,
        # then target repo is assumed to be easyconfigs
        elif easyconfigs or patch_files or (files_to_delete and all(x.endswith('.eb') for x in files_to_delete)):
            pr_target_repo = GITHUB_EASYCONFIGS_REPO
            _log.info("Only easyconfig and patch files found, target repository is assumed to be %s", pr_target_repo)

        else:
            _log.info("No Python files, easyconfigs or patches found, can't derive target repository...")

    return pr_target_repo


@only_if_module_is_available('git', pkgname='GitPython')
def update_branch(branch_name, paths, ecs, github_account=None, commit_msg=None):
    """
    Update specified branch in GitHub using specified files

    :param paths: paths to categorized lists of files (easyconfigs, files to delete, patches)
    :param github_account: GitHub account where branch is located
    :param ecs: list of parsed easyconfigs, incl. for dependencies (if robot is enabled)
    :param commit_msg: commit message to use
    """
    if commit_msg is None:
        commit_msg = build_option('pr_commit_msg')

    if commit_msg is None:
        raise EasyBuildError("A meaningful commit message must be specified via --pr-commit-msg when using --update-pr")

    if github_account is None:
        github_account = build_option('github_user') or build_option('github_org')

    _, _, _, _, diff_stat, pr_target_repo = _easyconfigs_pr_common(paths, ecs, start_branch=branch_name,
                                                                   pr_branch=branch_name, start_account=github_account,
                                                                   commit_msg=commit_msg)

    print_msg("Overview of changes:\n%s\n" % diff_stat, log=_log, prefix=False)

    full_repo = '%s/%s' % (github_account, pr_target_repo)
    msg = "pushed updated branch '%s' to %s" % (branch_name, full_repo)
    if build_option('dry_run') or build_option('extended_dry_run'):
        msg += " [DRY RUN]"
    print_msg(msg, log=_log)


@only_if_module_is_available('git', pkgname='GitPython')
def update_pr(pr_id, paths, ecs, commit_msg=None):
    """
    Update specified pull request using specified files

    :param pr_id: ID of pull request to update
    :param paths: paths to categorized lists of files (easyconfigs, files to delete, patches)
    :param ecs: list of parsed easyconfigs, incl. for dependencies (if robot is enabled)
    :param commit_msg: commit message to use
    """

    pr_target_repo = det_pr_target_repo(paths)
    if pr_target_repo is None:
        raise EasyBuildError("Failed to determine target repository, please specify it via --pr-target-repo!")

    github_account, branch_name = det_account_branch_for_pr(pr_id, pr_target_repo=pr_target_repo)

    update_branch(branch_name, paths, ecs, github_account=github_account, commit_msg=commit_msg)

    full_repo = '%s/%s' % (build_option('pr_target_account'), pr_target_repo)
    msg = "updated https://github.com/%s/pull/%s" % (full_repo, pr_id)
    if build_option('dry_run') or build_option('extended_dry_run'):
        msg += " [DRY RUN]"
    print_msg(msg, log=_log)


def check_online_status():
    """
    Check whether we currently are online
    Return True if online, else a list of error messages
    """
    # Try repeatedly and with different URLs to cater for flaky servers
    # E.g. Github returned "HTTP Error 403: Forbidden" and "HTTP Error 406: Not Acceptable" randomly
    # Timeout and repeats set to total 1 minute
    urls = [GITHUB_API_URL + '/rate_limit', GITHUB_URL, GITHUB_API_URL]
    num_repeats = 6
    errors = set()  # Use set to record only unique errors
    for attempt in range(num_repeats):
        # Cycle through URLs
        url = urls[attempt % len(urls)]
        try:
            urlopen(url, timeout=10)
            errors = None
            break
        except URLError as err:
            errors.add('%s: %s' % (url, err))
    return sorted(errors) if errors else True


def check_github():
    """
    Check status of GitHub integration, and report back.
    * check whether GitHub username is available
    * check whether a GitHub token is available, and whether it works
    * check whether git and GitPython are available
    * check whether push access to own GitHub repositories works
    * check whether creating gists works
    * check whether location to local working directories for Git repositories is available (not strictly needed)
    """
    debug = build_option('debug')

    # start by assuming that everything works, individual checks will disable action that won't work
    status = {}
    for action in ['--from-pr', '--new-pr', '--review-pr', '--upload-test-report', '--update-pr']:
        status[action] = True

    print_msg("\nChecking status of GitHub integration...\n", log=_log, prefix=False)

    # check whether we're online; if not, half of the checks are going to fail...
    print_msg("Making sure we're online...", log=_log, prefix=False, newline=False)
    online_state = check_online_status()
    if online_state is True:
        print_msg("OK\n", log=_log, prefix=False)
    else:
        print_msg("FAIL (%s)", ', '.join(online_state), log=_log, prefix=False)
        raise EasyBuildError("checking status of GitHub integration must be done online")

    # GitHub user
    print_msg("* GitHub user...", log=_log, prefix=False, newline=False)
    github_user = build_option('github_user')
    github_account = build_option('github_org') or build_option('github_user')

    if github_user is None:
        check_res = "(none available) => FAIL"
        status['--new-pr'] = status['--update-pr'] = status['--upload-test-report'] = False
    else:
        check_res = "%s => OK" % github_user

    print_msg(check_res, log=_log, prefix=False)

    # check GitHub token
    print_msg("* GitHub token...", log=_log, prefix=False, newline=False)
    github_token = fetch_github_token(github_user)
    if github_token is None:
        check_res = "(no token found) => FAIL"
    else:
        # don't print full token, should be kept secret!
        partial_token = '%s..%s' % (github_token[:3], github_token[-3:])
        token_descr = partial_token + " (len: %d)" % len(github_token)
        if validate_github_token(github_token, github_user):
            check_res = "%s => OK (validated)" % token_descr
        else:
            check_res = "%s => FAIL (validation failed)" % token_descr

    if 'FAIL' in check_res:
        status['--new-pr'] = status['--update-pr'] = status['--upload-test-report'] = False

    print_msg(check_res, log=_log, prefix=False)

    # check git command
    print_msg("* git command...", log=_log, prefix=False, newline=False)
    git_cmd = which('git')
    git_version = get_tool_version('git')
    if git_cmd:
        if git_version in [UNKNOWN, None]:
            check_res = "%s version => FAIL" % git_version
        else:
            check_res = "OK (\"%s\")" % git_version
    else:
        check_res = "(not found) => FAIL"

    if 'FAIL' in check_res:
        status['--new-pr'] = status['--update-pr'] = False

    print_msg(check_res, log=_log, prefix=False)

    # check GitPython module
    print_msg("* GitPython module...", log=_log, prefix=False, newline=False)
    if 'git' in sys.modules:
        git_check = True
        git_attrs = ['GitCommandError', 'Repo']
        for attr in git_attrs:
            git_check &= attr in dir(git)

        if git_check:
            check_res = "OK (GitPython version %s)" % git.__version__
        else:
            check_res = "FAIL (import ok, but module doesn't provide what is expected)"
    else:
        check_res = "FAIL (import failed)"

    if 'FAIL' in check_res:
        status['--new-pr'] = status['--update-pr'] = False

    print_msg(check_res, log=_log, prefix=False)

    # test push access to own GitHub repository: try to clone repo and push a test branch
    msg = "* push access to %s/%s repo @ GitHub..." % (github_account, GITHUB_EASYCONFIGS_REPO)
    print_msg(msg, log=_log, prefix=False, newline=False)
    git_working_dir = tempfile.mkdtemp(prefix='git-working-dir')
    git_repo, res, push_err = None, None, None
    branch_name = 'test_branch_%s' % ''.join(random.choice(ascii_letters) for _ in range(5))
    try:
        git_repo = init_repo(git_working_dir, GITHUB_EASYCONFIGS_REPO, silent=not debug)
        remote_name = setup_repo(git_repo, github_account, GITHUB_EASYCONFIGS_REPO, GITHUB_DEVELOP_BRANCH,
                                 silent=not debug, git_only=True)
        git_repo.create_head(branch_name)
        res = getattr(git_repo.remotes, remote_name).push(branch_name)
    except Exception as err:
        _log.warning("Exception when testing push access to %s/%s: %s", github_account, GITHUB_EASYCONFIGS_REPO, err)
        push_err = err

    if res:
        if res[0].flags & res[0].ERROR:
            _log.warning("Error occurred when pushing test branch to GitHub: %s", res[0].summary)
            check_res = "FAIL (error occurred)"
        else:
            check_res = "OK"
    elif github_user:
        if 'git' in sys.modules:
            ver, req_ver = git.__version__, '1.0'
            if LooseVersion(ver) < LooseVersion(req_ver):
                check_res = "FAIL (GitPython version %s is too old, should be version %s or newer)" % (ver, req_ver)
            elif "Could not read from remote repository" in str(push_err):
                check_res = "FAIL (GitHub SSH key missing? %s)" % push_err
            else:
                check_res = "FAIL (unexpected exception: %s)" % push_err
        else:
            check_res = "FAIL (GitPython is not available)"
    else:
        check_res = "FAIL (no GitHub user specified)"

    if 'FAIL' in check_res:
        status['--new-pr'] = status['--update-pr'] = False

    print_msg(check_res, log=_log, prefix=False)

    # cleanup: delete test branch that was pushed to GitHub
    if git_repo and push_err is None:
        try:
            getattr(git_repo.remotes, remote_name).push(branch_name, delete=True)
        except GitCommandError as err:
            sys.stderr.write("WARNING: failed to delete test branch from GitHub: %s\n" % err)

    # test creating a gist
    print_msg("* creating gists...", log=_log, prefix=False, newline=False)
    gist_url = None
    try:
        gist_url = create_gist("This is just a test", 'test.txt', descr='test123', github_user=github_user,
                               github_token=github_token)
        gist_id = gist_url.split('/')[-1]
        _log.info("Gist with ID %s successfully created, now deleting it again...", gist_id)

        delete_gist(gist_id, github_user=github_user, github_token=github_token)
        _log.info("Gist with ID %s deleted!", gist_id)
    except Exception as err:
        _log.warning("Exception occurred when trying to create & delete gist: %s", err)

    if gist_url and re.match('https://gist.github.com/[0-9a-f]+$', gist_url):
        check_res = "OK"
    else:
        check_res = "FAIL (gist_url: %s)" % gist_url
        status['--upload-test-report'] = False

    print_msg(check_res, log=_log, prefix=False)

    # check whether location to local working directories for Git repositories is available (not strictly needed)
    print_msg("* location to Git working dirs... ", log=_log, prefix=False, newline=False)
    git_working_dirs_path = build_option('git_working_dirs_path')
    if git_working_dirs_path:
        check_res = "OK (%s)" % git_working_dirs_path
    else:
        check_res = "not found (suboptimal)"

    print_msg(check_res, log=_log, prefix=False)

    # report back
    if all(status.values()):
        msg = "\nAll checks PASSed!\n"
    else:
        msg = '\n'.join([
            '',
            "One or more checks FAILed, GitHub configuration not fully complete!",
            "See http://easybuild.readthedocs.org/en/latest/Integration_with_GitHub.html#configuration for help.",
            '',
        ])
    print_msg(msg, log=_log, prefix=False)

    print_msg("Status of GitHub integration:", log=_log, prefix=False)
    for action in sorted(status):
        res = ("not supported", 'OK')[status[action]]
        print_msg("* %s: %s" % (action, res), log=_log, prefix=False)
    print_msg('', prefix=False)


def fetch_github_token(user):
    """Fetch GitHub token for specified user from keyring."""

    token, msg = None, None

    if user is None:
        msg = "No GitHub user name provided, required for fetching GitHub token."
    elif not HAVE_KEYRING:
        msg = "Failed to obtain GitHub token from keyring, "
        msg += "required Python module https://pypi.python.org/pypi/keyring is not available."
    else:
        try:
            token = keyring.get_password(KEYRING_GITHUB_TOKEN, user)
        except Exception as err:
            _log.warning("Exception occurred when fetching GitHub token: %s", err)

        if token is None:
            python_cmd = '; '.join([
                "import getpass, keyring",
                "keyring.set_password(\"%s\", \"%s\", getpass.getpass())" % (KEYRING_GITHUB_TOKEN, user),
            ])
            msg = '\n'.join([
                "Failed to obtain GitHub token for %s" % user,
                "Use the following procedure to install a GitHub token in your keyring:",
                "$ python -c '%s'" % python_cmd,
            ])

    if token is None:
        # failed to obtain token, log message explaining why
        _log.warning(msg)
    else:
        _log.info("Successfully obtained GitHub token for user %s from keyring." % user)

    return token


@only_if_module_is_available('keyring')
def install_github_token(github_user, silent=False):
    """
    Install specified GitHub token for specified user.

    :param github_user: GitHub user to install token for
    :param silent: keep quiet (don't print any messages)
    """
    if github_user is None:
        raise EasyBuildError("GitHub user must be specified to install GitHub token")

    # check if there's a token available already
    current_token = fetch_github_token(github_user)

    if current_token:
        current_token = '%s..%s' % (current_token[:3], current_token[-3:])
        if build_option('force'):
            msg = "WARNING: overwriting installed token '%s' for user '%s'..." % (current_token, github_user)
            print_msg(msg, prefix=False, silent=silent)
        else:
            raise EasyBuildError("Installed token '%s' found for user '%s', not overwriting it without --force",
                                 current_token, github_user)

    # get token to install
    token = getpass.getpass(prompt="Token: ").strip()

    # validate token before installing it
    print_msg("Validating token...", prefix=False, silent=silent)
    valid_token = validate_github_token(token, github_user)
    if valid_token:
        print_msg("Token seems to be valid, installing it.", prefix=False, silent=silent)
    else:
        raise EasyBuildError("Token validation failed, not installing it. Please verify your token and try again.")

    # install token
    keyring.set_password(KEYRING_GITHUB_TOKEN, github_user, token)
    print_msg("Token '%s..%s' installed!" % (token[:3], token[-3:]), prefix=False, silent=silent)


def validate_github_token(token, github_user):
    """
    Check GitHub token:
    * see if it conforms expectations (only [a-f]+[0-9] characters, length of 40)
    * see if it can be used for authenticated access
    """
    # cfr. https://github.blog/2021-04-05-behind-githubs-new-authentication-token-formats/
    token_regex = re.compile('^ghp_[a-zA-Z0-9]{36}$')
    token_regex_old_format = re.compile('^[0-9a-f]{40}$')

    # token should be 40 characters long, and only contain characters in [0-9a-f]
    sanity_check = bool(token_regex.match(token))
    if sanity_check:
        _log.info("Sanity check on token passed")
    else:
        _log.warning("Sanity check on token failed; token doesn't match pattern '%s'", token_regex.pattern)
        sanity_check = bool(token_regex_old_format.match(token))
        if sanity_check:
            _log.info("Sanity check on token (old format) passed")
        else:
            _log.warning("Sanity check on token failed; token doesn't match pattern '%s'",
                         token_regex_old_format.pattern)

    # try and determine sha of latest commit in easybuilders/easybuild-easyconfigs repo through authenticated access
    sha = None
    try:
        sha = fetch_latest_commit_sha(GITHUB_EASYCONFIGS_REPO, GITHUB_EB_MAIN,
                                      branch=GITHUB_DEVELOP_BRANCH, github_user=github_user, token=token)
    except Exception as err:
        _log.warning("An exception occurred when trying to use token for authenticated GitHub access: %s", err)

    sha_regex = re.compile('^[0-9a-f]{40}$')
    token_test = bool(sha_regex.match(sha or ''))
    if token_test:
        _log.info("GitHub token can be used for authenticated GitHub access, validation passed")

    return sanity_check and token_test


def find_easybuild_easyconfig(github_user=None):
    """
    Fetches the latest EasyBuild version eb file from GitHub

    :param github_user: name of GitHub user to use when querying GitHub
    """
    dev_repo = download_repo(GITHUB_EASYCONFIGS_REPO, branch=GITHUB_DEVELOP_BRANCH,
                             account=GITHUB_EB_MAIN, github_user=github_user)
    eb_parent_path = os.path.join(dev_repo, 'easybuild', 'easyconfigs', 'e', 'EasyBuild')
    files = os.listdir(eb_parent_path)

    # find most recent version
    file_versions = []
    for eb_file in files:
        txt = read_file(os.path.join(eb_parent_path, eb_file))
        for line in txt.split('\n'):
            if re.search(r'^version\s*=', line):
                scope = {}
                exec(line, scope)
                version = scope['version']
                file_versions.append((LooseVersion(version), eb_file))

    if file_versions:
        fn = sorted(file_versions)[-1][1]
    else:
        raise EasyBuildError("Couldn't find any EasyBuild easyconfigs")

    eb_file = os.path.join(eb_parent_path, fn)
    return eb_file


def det_commit_status(account, repo, commit_sha, github_user):
    """
    Determine status of specified commit (pending, error, failure, success)

    We combine two different things here:

    * the combined commit status (Travis CI sets a commit status)
    * results of check suites (set by CI run in GitHub Actions)
    """
    def commit_status_url(gh):
        """Helper function to grab combined status of latest commit."""
        # see https://docs.github.com/en/rest/reference/repos#get-the-combined-status-for-a-specific-reference
        return gh.repos[account][repo].commits[commit_sha].status

    def check_suites_url(gh):
        """Helper function to grab status of latest commit."""
        return gh.repos[account][repo].commits[commit_sha]['check-suites']

    # first check combined commit status (set by e.g. Travis CI)
    status, commit_status_data = github_api_get_request(commit_status_url, github_user)
    if status != HTTP_STATUS_OK:
        raise EasyBuildError("Failed to get status of commit %s from %s/%s (status: %d %s)",
                             commit_sha, account, repo, status, commit_status_data)

    commit_status_count = commit_status_data['total_count']
    combined_commit_status = commit_status_data['state']
    _log.info("Found combined commit status set by %d contexts: %s", commit_status_count, combined_commit_status)

    # if state is 'pending', we need to check whether anything is actually setting a commit status;
    # if not (total_count == 0), then the state will stay 'pending' so we should ignore it;
    # see also https://github.com/easybuilders/easybuild-framework/issues/3405
    if commit_status_count == 0 and combined_commit_status == STATUS_PENDING:
        combined_commit_status = None
        _log.info("Ignoring %s combined commit status, since total count is 0", combined_commit_status)

    # set preliminary result based on combined commit status
    result = combined_commit_status

    # also take into account check suites (used by CI in GitHub Actions)

    # Checks API is currently available for developers to preview,
    # so we need to provide this accept header;
    # see "Preview notice" at https://docs.github.com/en/rest/reference/checks#list-check-suites-for-a-git-reference
    headers = {'Accept': "application/vnd.github.antiope-preview+json"}

    status, check_suites_data = github_api_get_request(check_suites_url, github_user, headers=headers)

    # take into that there may be multiple check suites;
    for check_suite_data in check_suites_data['check_suites']:
        # status can be 'queued', 'in_progress', or 'completed'
        status = check_suite_data['status']

        # if any check suite hasn't completed yet, final result is still pending
        if status in ['queued', 'in_progress']:
            result = STATUS_PENDING

        # if check suite is completed, take the conclusion into account
        elif status == 'completed':
            conclusion = check_suite_data['conclusion']
            if conclusion == STATUS_SUCCESS:
                # only set result if it hasn't been decided yet based on combined commit status
                if result is None:
                    result = STATUS_SUCCESS
            else:
                # any other conclusion determines the final result,
                # no need to check other test suites
                result = conclusion
                break
        else:
            app_name = check_suite_data.get('app', {}).get('name', 'UNKNOWN')
            raise EasyBuildError("Unknown check suite status set by %s: '%s'", app_name, status)

    return result


def fetch_pr_data(pr, pr_target_account, pr_target_repo, github_user, full=False, **parameters):
    """Fetch PR data from GitHub"""

    def pr_url(gh):
        """Utility function to fetch data for a specific PR."""
        if pr is None:
            return gh.repos[pr_target_account][pr_target_repo].pulls
        else:
            return gh.repos[pr_target_account][pr_target_repo].pulls[pr]

    try:
        status, pr_data = github_api_get_request(pr_url, github_user, **parameters)
    except HTTPError as err:
        raise EasyBuildError("Failed to get data for PR #%d from %s/%s (%s)\n"
                             "Please check PR #, account and repo.",
                             pr, pr_target_account, pr_target_repo, err)

    if status != HTTP_STATUS_OK:
        raise EasyBuildError("Failed to get data for PR #%d from %s/%s (status: %d %s)",
                             pr, pr_target_account, pr_target_repo, status, pr_data)

    if full:
        # also fetch status of last commit
        pr_data['status_last_commit'] = det_commit_status(pr_target_account, pr_target_repo,
                                                          pr_data['head']['sha'], github_user)

        # also fetch comments
        def comments_url(gh):
            """Helper function to grab comments for this PR."""
            return gh.repos[pr_target_account][pr_target_repo].issues[pr].comments

        status, comments_data = github_api_get_request(comments_url, github_user, **parameters)
        if status != HTTP_STATUS_OK:
            raise EasyBuildError("Failed to get comments for PR #%d from %s/%s (status: %d %s)",
                                 pr, pr_target_account, pr_target_repo, status, comments_data)
        pr_data['issue_comments'] = comments_data

        # also fetch reviews
        def reviews_url(gh):
            """Helper function to grab reviews for this PR"""
            return gh.repos[pr_target_account][pr_target_repo].pulls[pr].reviews

        status, reviews_data = github_api_get_request(reviews_url, github_user, **parameters)
        if status != HTTP_STATUS_OK:
            raise EasyBuildError("Failed to get reviews for PR #%d from %s/%s (status: %d %s)",
                                 pr, pr_target_account, pr_target_repo, status, reviews_data)
        pr_data['reviews'] = reviews_data

    return pr_data, pr_url


def sync_with_develop(git_repo, branch_name, github_account, github_repo):
    """Sync specified branch with develop branch."""

    # pull in latest version of 'develop' branch from central repository
    msg = "pulling latest version of '%s' branch from %s/%s..." % (GITHUB_DEVELOP_BRANCH, github_account, github_repo)
    print_msg(msg, log=_log)
    remote = create_remote(git_repo, github_account, github_repo, https=True)

    # fetch latest version of develop branch
    pull_out = git_repo.git.pull(remote.name, GITHUB_DEVELOP_BRANCH)
    _log.debug("Output of 'git pull %s %s': %s", remote.name, GITHUB_DEVELOP_BRANCH, pull_out)

    # fetch to make sure we can check out the 'develop' branch
    fetch_out = git_repo.git.fetch(remote.name)
    _log.debug("Output of 'git fetch %s': %s", remote.name, fetch_out)

    _log.debug("Output of 'git branch -a': %s", git_repo.git.branch(a=True))
    _log.debug("Output of 'git remote -v': %s", git_repo.git.remote(v=True))

    # create 'develop' branch (with force if one already exists),
    git_repo.create_head(GITHUB_DEVELOP_BRANCH, remote.refs.develop, force=True).checkout()

    # check top of git log
    git_log_develop = git_repo.git.log('-n 3')
    _log.debug("Top of 'git log' for %s branch:\n%s", GITHUB_DEVELOP_BRANCH, git_log_develop)

    # checkout PR branch, and merge develop branch in it (which will create a merge commit)
    print_msg("merging '%s' branch into PR branch '%s'..." % (GITHUB_DEVELOP_BRANCH, branch_name), log=_log)
    git_repo.git.checkout(branch_name)
    merge_out = git_repo.git.merge(GITHUB_DEVELOP_BRANCH)
    _log.debug("Output of 'git merge %s':\n%s", GITHUB_DEVELOP_BRANCH, merge_out)

    # check git log, should show merge commit on top
    post_merge_log = git_repo.git.log('-n 3')
    _log.debug("Top of 'git log' after 'git merge %s':\n%s", GITHUB_DEVELOP_BRANCH, post_merge_log)


def sync_pr_with_develop(pr_id):
    """Sync pull request with specified ID with current develop branch."""
    github_user = build_option('github_user')
    if github_user is None:
        raise EasyBuildError("GitHub user must be specified to use --sync-pr-with-develop")

    target_account = build_option('pr_target_account')
    target_repo = build_option('pr_target_repo') or GITHUB_EASYCONFIGS_REPO

    pr_account, pr_branch = det_account_branch_for_pr(pr_id)

    # initialize repository
    git_working_dir = tempfile.mkdtemp(prefix='git-working-dir')
    git_repo = init_repo(git_working_dir, target_repo)

    setup_repo(git_repo, pr_account, target_repo, pr_branch)

    sync_with_develop(git_repo, pr_branch, target_account, target_repo)

    # push updated branch back to GitHub (unless we're doing a dry run)
    return push_branch_to_github(git_repo, pr_account, target_repo, pr_branch)


def sync_branch_with_develop(branch_name):
    """Sync branch with specified name with current develop branch."""
    github_user = build_option('github_user')
    if github_user is None:
        raise EasyBuildError("GitHub user must be specified to use --sync-branch-with-develop")

    target_account = build_option('pr_target_account')
    target_repo = build_option('pr_target_repo') or GITHUB_EASYCONFIGS_REPO

    # initialize repository
    git_working_dir = tempfile.mkdtemp(prefix='git-working-dir')
    git_repo = init_repo(git_working_dir, target_repo)

    # GitHub organisation or GitHub user where branch is located
    github_account = build_option('github_org') or github_user

    setup_repo(git_repo, github_account, target_repo, branch_name)

    sync_with_develop(git_repo, branch_name, target_account, target_repo)

    # push updated branch back to GitHub (unless we're doing a dry run)
    return push_branch_to_github(git_repo, github_account, target_repo, branch_name)


# copy functions for --new-pr
COPY_FUNCTIONS = {
    GITHUB_EASYCONFIGS_REPO: copy_easyconfigs,
    GITHUB_EASYBLOCKS_REPO: copy_easyblocks,
    GITHUB_FRAMEWORK_REPO: copy_framework_files,
}
