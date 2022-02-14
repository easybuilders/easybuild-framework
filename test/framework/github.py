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
Unit tests for talking to GitHub.

@author: Jens Timmerman (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import base64
import os
import random
import re
import sys
import textwrap
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from time import gmtime
from unittest import TextTestRunner

import easybuild.tools.testing
from easybuild.base.rest import RestClient
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.tools import categorize_files_by_type
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, module_classes, update_build_option
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.github import GITHUB_EASYCONFIGS_REPO, GITHUB_EASYBLOCKS_REPO, GITHUB_MERGEABLE_STATE_CLEAN
from easybuild.tools.github import VALID_CLOSE_PR_REASONS
from easybuild.tools.github import pick_default_branch
from easybuild.tools.testing import create_test_report, post_pr_test_report, session_state
from easybuild.tools.py2vs3 import HTTPError, URLError, ascii_letters
import easybuild.tools.github as gh

try:
    import keyring
    HAVE_KEYRING = True
except ImportError:
    HAVE_KEYRING = False


# test account, for which a token may be available
GITHUB_TEST_ACCOUNT = 'easybuild_test'
# the user & repo to use in this test (https://github.com/easybuilders/testrepository)
GITHUB_USER = "easybuilders"
GITHUB_REPO = "testrepository"
# branch to test
GITHUB_BRANCH = 'main'


class GithubTest(EnhancedTestCase):
    """ small test for The github package
    This should not be to much, since there is an hourly limit of request
    for non authenticated users of 50"""

    def setUp(self):
        """Test setup."""
        super(GithubTest, self).setUp()

        self.github_token = gh.fetch_github_token(GITHUB_TEST_ACCOUNT)

        if self.github_token is None:
            username, token = None, None
        else:
            username, token = GITHUB_TEST_ACCOUNT, self.github_token

        self.ghfs = gh.Githubfs(GITHUB_USER, GITHUB_REPO, GITHUB_BRANCH, username, None, token)

        self.skip_github_tests = self.github_token is None and os.getenv('FORCE_EB_GITHUB_TESTS') is None

        self.orig_testing_create_gist = easybuild.tools.testing.create_gist

    def tearDown(self):
        """Cleanup after running test."""
        easybuild.tools.testing.create_gist = self.orig_testing_create_gist

        super(GithubTest, self).tearDown()

    def test_github_pick_default_branch(self):
        """Test pick_default_branch function."""

        self.assertEqual(pick_default_branch('easybuilders'), 'main')
        self.assertEqual(pick_default_branch('foobar'), 'master')

    def test_github_walk(self):
        """test the gitubfs walk function"""
        if self.skip_github_tests:
            print("Skipping test_walk, no GitHub token available?")
            return

        try:
            expected = [
                (None, ['a_directory', 'second_dir'], ['README.md']),
                ('a_directory', ['a_subdirectory'], ['a_file.txt']),
                ('a_directory/a_subdirectory', [], ['a_file.txt']), ('second_dir', [], ['a_file.txt']),
            ]
            self.assertEqual([x for x in self.ghfs.walk(None)], expected)
        except IOError:
            pass

    def test_github_read_api(self):
        """Test the githubfs read function"""
        if self.skip_github_tests:
            print("Skipping test_read_api, no GitHub token available?")
            return

        try:
            self.assertEqual(self.ghfs.read("a_directory/a_file.txt").strip(), b"this is a line of text")
        except IOError:
            pass

    def test_github_read(self):
        """Test the githubfs read function without using the api"""
        if self.skip_github_tests:
            print("Skipping test_read, no GitHub token available?")
            return

        try:
            fp = self.ghfs.read("a_directory/a_file.txt", api=False)
            self.assertEqual(read_file(fp).strip(), "this is a line of text")
            os.remove(fp)
        except (IOError, OSError):
            pass

    def test_github_add_pr_labels(self):
        """Test add_pr_labels function."""
        if self.skip_github_tests:
            print("Skipping test_add_pr_labels, no GitHub token available?")
            return

        build_options = {
            'pr_target_account': GITHUB_USER,
            'pr_target_repo': GITHUB_EASYBLOCKS_REPO,
            'github_user':  GITHUB_TEST_ACCOUNT,
            'dry_run': True,
        }
        init_config(build_options=build_options)

        self.mock_stdout(True)
        error_pattern = "Adding labels to PRs for repositories other than easyconfigs hasn't been implemented yet"
        self.assertErrorRegex(EasyBuildError, error_pattern, gh.add_pr_labels, 1)
        self.mock_stdout(False)

        build_options['pr_target_repo'] = GITHUB_EASYCONFIGS_REPO
        init_config(build_options=build_options)

        # PR #11262 includes easyconfigs that use 'dummy' toolchain,
        # so we need to allow triggering deprecated behaviour
        self.allow_deprecated_behaviour()

        self.mock_stdout(True)
        self.mock_stderr(True)
        gh.add_pr_labels(11262)
        stdout = self.get_stdout()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertTrue("Could not determine any missing labels for PR #11262" in stdout)

        self.mock_stdout(True)
        self.mock_stderr(True)
        gh.add_pr_labels(8006)  # closed, unmerged, unlabeled PR
        stdout = self.get_stdout()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertTrue("PR #8006 should be labelled 'update'" in stdout)

    def test_github_fetch_pr_data(self):
        """Test fetch_pr_data function."""
        if self.skip_github_tests:
            print("Skipping test_fetch_pr_data, no GitHub token available?")
            return

        pr_data, _ = gh.fetch_pr_data(1, GITHUB_USER, GITHUB_REPO, GITHUB_TEST_ACCOUNT)

        self.assertEqual(pr_data['number'], 1)
        self.assertEqual(pr_data['title'], "a pr")
        self.assertFalse(any(key in pr_data for key in ['issue_comments', 'review', 'status_last_commit']))

        pr_data, _ = gh.fetch_pr_data(2, GITHUB_USER, GITHUB_REPO, GITHUB_TEST_ACCOUNT, full=True)
        self.assertEqual(pr_data['number'], 2)
        self.assertEqual(pr_data['title'], "an open pr (do not close this please)")
        self.assertTrue(pr_data['issue_comments'])
        self.assertEqual(pr_data['issue_comments'][0]['body'], "this is a test")
        self.assertTrue(pr_data['reviews'])
        self.assertEqual(pr_data['reviews'][0]['state'], "APPROVED")
        self.assertEqual(pr_data['reviews'][0]['user']['login'], 'boegel')
        self.assertEqual(pr_data['status_last_commit'], None)

    def test_github_list_prs(self):
        """Test list_prs function."""
        if self.skip_github_tests:
            print("Skipping test_list_prs, no GitHub token available?")
            return

        parameters = ('closed', 'created', 'asc')

        init_config(build_options={'pr_target_account': GITHUB_USER,
                                   'pr_target_repo': GITHUB_REPO})

        expected = "PR #1: a pr"

        self.mock_stdout(True)
        output = gh.list_prs(parameters, per_page=1, github_user=GITHUB_TEST_ACCOUNT)
        stdout = self.get_stdout()
        self.mock_stdout(False)

        self.assertTrue(stdout.startswith("== Listing PRs with parameters: "))

        self.assertEqual(expected, output)

    def test_github_reasons_for_closing(self):
        """Test reasons_for_closing function."""
        if self.skip_github_tests:
            print("Skipping test_reasons_for_closing, no GitHub token available?")
            return

        repo_owner = gh.GITHUB_EB_MAIN
        repo_name = gh.GITHUB_EASYCONFIGS_REPO

        build_options = {
            'dry_run': True,
            'github_user': GITHUB_TEST_ACCOUNT,
            'pr_target_account': repo_owner,
            'pr_target_repo': repo_name,
            'robot_path': [],
        }
        init_config(build_options=build_options)

        pr_data, _ = gh.fetch_pr_data(1844, repo_owner, repo_name, GITHUB_TEST_ACCOUNT, full=True)

        self.mock_stdout(True)
        self.mock_stderr(True)
        # can't easily check return value, since auto-detected reasons may change over time if PR is touched
        res = gh.reasons_for_closing(pr_data)
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)

        self.assertTrue(isinstance(res, list))
        self.assertEqual(stderr.strip(), "WARNING: Using easyconfigs from closed PR #1844")
        patterns = [
            "Status of last commit is SUCCESS",
            "Last comment on",
            "No activity since",
            "* QEMU-2.4.0",
        ]
        for pattern in patterns:
            self.assertTrue(pattern in stdout, "Pattern '%s' found in: %s" % (pattern, stdout))

    def test_github_close_pr(self):
        """Test close_pr function."""
        if self.skip_github_tests:
            print("Skipping test_close_pr, no GitHub token available?")
            return

        build_options = {
            'dry_run': True,
            'github_user': GITHUB_TEST_ACCOUNT,
            'pr_target_account': GITHUB_USER,
            'pr_target_repo': GITHUB_REPO,
        }
        init_config(build_options=build_options)

        self.mock_stdout(True)
        gh.close_pr(2, motivation_msg='just a test')
        stdout = self.get_stdout()
        self.mock_stdout(False)

        patterns = [
            "easybuilders/testrepository PR #2 was submitted by migueldiascosta",
            "[DRY RUN] Adding comment to testrepository issue #2: '" +
            "@migueldiascosta, this PR is being closed for the following reason(s): just a test",
            "[DRY RUN] Closed easybuilders/testrepository PR #2",
        ]
        for pattern in patterns:
            self.assertTrue(pattern in stdout, "Pattern '%s' found in: %s" % (pattern, stdout))

        retest_msg = VALID_CLOSE_PR_REASONS['retest']

        self.mock_stdout(True)
        gh.close_pr(2, motivation_msg=retest_msg)
        stdout = self.get_stdout()
        self.mock_stdout(False)

        patterns = [
            "easybuilders/testrepository PR #2 was submitted by migueldiascosta",
            "[DRY RUN] Adding comment to testrepository issue #2: '" +
            "@migueldiascosta, this PR is being closed for the following reason(s): %s" % retest_msg,
            "[DRY RUN] Closed easybuilders/testrepository PR #2",
            "[DRY RUN] Reopened easybuilders/testrepository PR #2",
        ]
        for pattern in patterns:
            self.assertTrue(pattern in stdout, "Pattern '%s' found in: %s" % (pattern, stdout))

    def test_github_fetch_easyblocks_from_pr(self):
        """Test fetch_easyblocks_from_pr function."""
        if self.skip_github_tests:
            print("Skipping test_fetch_easyblocks_from_pr, no GitHub token available?")
            return

        init_config(build_options={
            'pr_target_account': gh.GITHUB_EB_MAIN,
        })

        # PR with new easyblock plus non-easyblock file
        all_ebs_pr1964 = ['lammps.py']

        # PR with changed easyblock
        all_ebs_pr1967 = ['siesta.py']

        # PR with more than one easyblock
        all_ebs_pr1949 = ['configuremake.py', 'rpackage.py']

        for pr, all_ebs in [(1964, all_ebs_pr1964), (1967, all_ebs_pr1967), (1949, all_ebs_pr1949)]:
            try:
                tmpdir = os.path.join(self.test_prefix, 'pr%s' % pr)
                eb_files = gh.fetch_easyblocks_from_pr(pr, path=tmpdir, github_user=GITHUB_TEST_ACCOUNT)
                self.assertEqual(sorted(all_ebs), sorted([os.path.basename(f) for f in eb_files]))
            except URLError as err:
                print("Ignoring URLError '%s' in test_fetch_easyblocks_from_pr" % err)

    def test_github_fetch_easyconfigs_from_pr(self):
        """Test fetch_easyconfigs_from_pr function."""
        if self.skip_github_tests:
            print("Skipping test_fetch_easyconfigs_from_pr, no GitHub token available?")
            return

        init_config(build_options={
            'pr_target_account': gh.GITHUB_EB_MAIN,
        })

        # PR for rename of arrow to Arrow,
        # see https://github.com/easybuilders/easybuild-easyconfigs/pull/8007/files
        all_ecs_pr8007 = [
            'Arrow-0.7.1-intel-2017b-Python-3.6.3.eb',
            'bat-0.3.3-fix-pyspark.patch',
            'bat-0.3.3-intel-2017b-Python-3.6.3.eb',
        ]
        # PR where also files are patched in test/
        # see https://github.com/easybuilders/easybuild-easyconfigs/pull/6587/files
        all_ecs_pr6587 = [
            'WIEN2k-18.1-foss-2018a.eb',
            'WIEN2k-18.1-gimkl-2017a.eb',
            'WIEN2k-18.1-intel-2018a.eb',
            'libxc-4.2.3-foss-2018a.eb',
            'libxc-4.2.3-gimkl-2017a.eb',
            'libxc-4.2.3-intel-2018a.eb',
        ]
        # PR where files are renamed
        # see https://github.com/easybuilders/easybuild-easyconfigs/pull/7159/files
        all_ecs_pr7159 = [
            'DOLFIN-2018.1.0.post1-foss-2018a-Python-3.6.4.eb',
            'OpenFOAM-5.0-20180108-foss-2018a.eb',
            'OpenFOAM-5.0-20180108-intel-2018a.eb',
            'OpenFOAM-6-foss-2018b.eb',
            'OpenFOAM-6-intel-2018a.eb',
            'OpenFOAM-v1806-foss-2018b.eb',
            'PETSc-3.9.3-foss-2018a.eb',
            'SCOTCH-6.0.6-foss-2018a.eb',
            'SCOTCH-6.0.6-foss-2018b.eb',
            'SCOTCH-6.0.6-intel-2018a.eb',
            'Trilinos-12.12.1-foss-2018a-Python-3.6.4.eb'
        ]

        for pr, all_ecs in [(8007, all_ecs_pr8007), (6587, all_ecs_pr6587), (7159, all_ecs_pr7159)]:
            try:
                tmpdir = os.path.join(self.test_prefix, 'pr%s' % pr)
                ec_files = gh.fetch_easyconfigs_from_pr(pr, path=tmpdir, github_user=GITHUB_TEST_ACCOUNT)
                self.assertEqual(sorted(all_ecs), sorted([os.path.basename(f) for f in ec_files]))
            except URLError as err:
                print("Ignoring URLError '%s' in test_fetch_easyconfigs_from_pr" % err)

    def test_github_fetch_files_from_pr_cache(self):
        """Test caching for fetch_files_from_pr."""
        if self.skip_github_tests:
            print("Skipping test_fetch_files_from_pr_cache, no GitHub token available?")
            return

        init_config(build_options={
            'pr_target_account': gh.GITHUB_EB_MAIN,
        })

        # clear cache first, to make sure we start with a clean slate
        gh.fetch_files_from_pr.clear_cache()
        self.assertFalse(gh.fetch_files_from_pr._cache)

        pr7159_filenames = [
            'DOLFIN-2018.1.0.post1-foss-2018a-Python-3.6.4.eb',
            'OpenFOAM-5.0-20180108-foss-2018a.eb',
            'OpenFOAM-5.0-20180108-intel-2018a.eb',
            'OpenFOAM-6-foss-2018b.eb',
            'OpenFOAM-6-intel-2018a.eb',
            'OpenFOAM-v1806-foss-2018b.eb',
            'PETSc-3.9.3-foss-2018a.eb',
            'SCOTCH-6.0.6-foss-2018a.eb',
            'SCOTCH-6.0.6-foss-2018b.eb',
            'SCOTCH-6.0.6-intel-2018a.eb',
            'Trilinos-12.12.1-foss-2018a-Python-3.6.4.eb'
        ]
        pr7159_files = gh.fetch_easyconfigs_from_pr(7159, path=self.test_prefix, github_user=GITHUB_TEST_ACCOUNT)
        self.assertEqual(sorted(pr7159_filenames), sorted(os.path.basename(f) for f in pr7159_files))

        # check that cache has been populated for PR 7159
        self.assertEqual(len(gh.fetch_files_from_pr._cache.keys()), 1)

        # github_account value is None (results in using default 'easybuilders')
        cache_key = (7159, None, 'easybuild-easyconfigs', self.test_prefix)
        self.assertTrue(cache_key in gh.fetch_files_from_pr._cache.keys())

        cache_entry = gh.fetch_files_from_pr._cache[cache_key]
        self.assertEqual(sorted([os.path.basename(f) for f in cache_entry]), sorted(pr7159_filenames))

        # same query should return result from cache entry
        res = gh.fetch_easyconfigs_from_pr(7159, path=self.test_prefix, github_user=GITHUB_TEST_ACCOUNT)
        self.assertEqual(res, pr7159_files)

        # inject entry in cache and check result of matching query
        pr_id = 12345
        tmpdir = os.path.join(self.test_prefix, 'easyblocks-pr-12345')
        pr12345_files = [
            os.path.join(tmpdir, 'foo.py'),
            os.path.join(tmpdir, 'bar.py'),
        ]
        for fp in pr12345_files:
            write_file(fp, '')

        # github_account value is None (results in using default 'easybuilders')
        cache_key = (pr_id, None, 'easybuild-easyblocks', tmpdir)
        gh.fetch_files_from_pr.update_cache({cache_key: pr12345_files})

        res = gh.fetch_easyblocks_from_pr(12345, tmpdir)
        self.assertEqual(sorted(pr12345_files), sorted(res))

    def test_github_fetch_latest_commit_sha(self):
        """Test fetch_latest_commit_sha function."""
        if self.skip_github_tests:
            print("Skipping test_fetch_latest_commit_sha, no GitHub token available?")
            return

        sha = gh.fetch_latest_commit_sha('easybuild-framework', 'easybuilders', github_user=GITHUB_TEST_ACCOUNT)
        self.assertTrue(re.match('^[0-9a-f]{40}$', sha))
        sha = gh.fetch_latest_commit_sha('easybuild-easyblocks', 'easybuilders', github_user=GITHUB_TEST_ACCOUNT,
                                         branch='develop')
        self.assertTrue(re.match('^[0-9a-f]{40}$', sha))

    def test_github_download_repo(self):
        """Test download_repo function."""
        if self.skip_github_tests:
            print("Skipping test_download_repo, no GitHub token available?")
            return

        cwd = os.getcwd()

        # default: download tarball for master branch of easybuilders/easybuild-easyconfigs repo
        path = gh.download_repo(path=self.test_prefix, github_user=GITHUB_TEST_ACCOUNT)
        repodir = os.path.join(self.test_prefix, 'easybuilders', 'easybuild-easyconfigs-main')
        self.assertTrue(os.path.samefile(path, repodir))
        self.assertTrue(os.path.exists(repodir))
        shafile = os.path.join(repodir, 'latest-sha')
        self.assertTrue(re.match('^[0-9a-f]{40}$', read_file(shafile)))
        self.assertTrue(os.path.exists(os.path.join(repodir, 'easybuild', 'easyconfigs', 'f', 'foss', 'foss-2019b.eb')))

        # current directory should not have changed after calling download_repo
        self.assertTrue(os.path.samefile(cwd, os.getcwd()))

        # existing downloaded repo is not reperformed, except if SHA is different
        account, repo, branch = 'boegel', 'easybuild-easyblocks', 'develop'
        repodir = os.path.join(self.test_prefix, account, '%s-%s' % (repo, branch))
        latest_sha = gh.fetch_latest_commit_sha(repo, account, branch=branch, github_user=GITHUB_TEST_ACCOUNT)

        # put 'latest-sha' fail in place, check whether repo was (re)downloaded (should not)
        shafile = os.path.join(repodir, 'latest-sha')
        write_file(shafile, latest_sha)
        path = gh.download_repo(repo=repo, branch=branch, account=account, path=self.test_prefix,
                                github_user=GITHUB_TEST_ACCOUNT)
        self.assertTrue(os.path.samefile(path, repodir))
        self.assertEqual(os.listdir(repodir), ['latest-sha'])

        # remove 'latest-sha' file and verify that download was performed
        os.remove(shafile)
        path = gh.download_repo(repo=repo, branch=branch, account=account, path=self.test_prefix,
                                github_user=GITHUB_TEST_ACCOUNT)
        self.assertTrue(os.path.samefile(path, repodir))
        self.assertTrue('easybuild' in os.listdir(repodir))
        self.assertTrue(re.match('^[0-9a-f]{40}$', read_file(shafile)))
        self.assertTrue(os.path.exists(os.path.join(repodir, 'easybuild', 'easyblocks', '__init__.py')))

    def test_install_github_token(self):
        """Test for install_github_token function."""
        if self.skip_github_tests:
            print("Skipping test_install_github_token, no GitHub token available?")
            return

        if not HAVE_KEYRING:
            print("Skipping test_install_github_token, keyring module not available")
            return

        random_user = ''.join(random.choice(ascii_letters) for _ in range(10))
        self.assertEqual(gh.fetch_github_token(random_user), None)

        # poor mans mocking of getpass
        # inject leading/trailing spaces to verify stripping of provided value
        def fake_getpass(*args, **kwargs):
            return ' ' + self.github_token + '  '

        orig_getpass = gh.getpass.getpass
        gh.getpass.getpass = fake_getpass

        token_installed = False
        try:
            gh.install_github_token(random_user, silent=True)
            token_installed = True
        except Exception as err:
            print(err)

        gh.getpass.getpass = orig_getpass

        token = gh.fetch_github_token(random_user)

        # cleanup
        if token_installed:
            keyring.delete_password(gh.KEYRING_GITHUB_TOKEN, random_user)

        # deliberately not using assertEqual, keep token secret!
        self.assertTrue(token_installed)
        self.assertTrue(token == self.github_token)

    def test_validate_github_token(self):
        """Test for validate_github_token function."""
        if self.skip_github_tests:
            print("Skipping test_validate_github_token, no GitHub token available?")
            return

        if not HAVE_KEYRING:
            print("Skipping test_validate_github_token, keyring module not available")
            return

        self.assertTrue(gh.validate_github_token(self.github_token, GITHUB_TEST_ACCOUNT))

        # if a token in the old format is available, test with that too
        token_old_format = os.getenv('TEST_GITHUB_TOKEN_OLD_FORMAT')
        if token_old_format:
            self.assertTrue(gh.validate_github_token(token_old_format, GITHUB_TEST_ACCOUNT))

    def test_github_find_easybuild_easyconfig(self):
        """Test for find_easybuild_easyconfig function"""
        if self.skip_github_tests:
            print("Skipping test_find_easybuild_easyconfig, no GitHub token available?")
            return
        path = gh.find_easybuild_easyconfig(github_user=GITHUB_TEST_ACCOUNT)
        expected = os.path.join('e', 'EasyBuild', r'EasyBuild-[1-9]+\.[0-9]+\.[0-9]+\.eb')
        regex = re.compile(expected)
        self.assertTrue(regex.search(path), "Pattern '%s' found in '%s'" % (regex.pattern, path))
        self.assertTrue(os.path.exists(path), "Path %s exists" % path)

    def test_github_find_patches(self):
        """ Test for find_software_name_for_patch """
        test_dir = os.path.dirname(os.path.abspath(__file__))
        ec_path = os.path.join(test_dir, 'easyconfigs')
        init_config(build_options={
            'allow_modules_tool_mismatch': True,
            'minimal_toolchains': True,
            'use_existing_modules': True,
            'external_modules_metadata': ConfigObj(),
            'silent': True,
            'valid_module_classes': module_classes(),
            'validate': False,
        })
        self.mock_stdout(True)
        ec = gh.find_software_name_for_patch('toy-0.0_fix-silly-typo-in-printf-statement.patch', [ec_path])
        txt = self.get_stdout()
        self.mock_stdout(False)

        self.assertTrue(ec == 'toy')
        reg = re.compile(r'[1-9]+ of [1-9]+ easyconfigs checked')
        self.assertTrue(re.search(reg, txt))

        self.assertEqual(gh.find_software_name_for_patch('test.patch', []), None)

        # check behaviour of find_software_name_for_patch when non-UTF8 patch files are present (only with Python 3)
        if sys.version_info[0] >= 3:
            non_utf8_patch = os.path.join(self.test_prefix, 'problem.patch')
            with open(non_utf8_patch, 'wb') as fp:
                fp.write(bytes("+  ximage->byte_order=T1_byte_order; /* Set t1lib\xb4s byteorder */\n", 'iso_8859_1'))

            self.assertEqual(gh.find_software_name_for_patch('test.patch', [self.test_prefix]), None)

    def test_github_det_commit_status(self):
        """Test det_commit_status function."""

        if self.skip_github_tests:
            print("Skipping test_det_commit_status, no GitHub token available?")
            return

        # ancient commit, from Jenkins era
        commit_sha = 'ec5d6f7191676a86a18404616691796a352c5f1d'
        res = gh.det_commit_status('easybuilders', 'easybuild-easyconfigs', commit_sha, GITHUB_TEST_ACCOUNT)
        self.assertEqual(res, 'success')

        # commit with failing tests from Travis CI era (no GitHub Actions yet)
        commit_sha = 'd0c62556caaa78944722dc84bbb1072bf9688f74'
        res = gh.det_commit_status('easybuilders', 'easybuild-easyconfigs', commit_sha, GITHUB_TEST_ACCOUNT)
        self.assertEqual(res, 'failure')

        # commit with passing tests from Travis CI era (no GitHub Actions yet)
        commit_sha = '21354990e4e6b4ca169b93d563091db4c6b2693e'
        res = gh.det_commit_status('easybuilders', 'easybuild-easyconfigs', commit_sha, GITHUB_TEST_ACCOUNT)
        self.assertEqual(res, 'success')

        # commit with failing tests, tested by both Travis CI and GitHub Actions
        commit_sha = '3a596de93dd95b651b0d1503562d888409364a96'
        res = gh.det_commit_status('easybuilders', 'easybuild-easyconfigs', commit_sha, GITHUB_TEST_ACCOUNT)
        self.assertEqual(res, 'failure')

        # commit with passing tests, tested by both Travis CI and GitHub Actions
        commit_sha = '1fba8ac835d62e78cdc7988b08f4409a1570cef1'
        res = gh.det_commit_status('easybuilders', 'easybuild-easyconfigs', commit_sha, GITHUB_TEST_ACCOUNT)
        self.assertEqual(res, 'success')

        # commit with failing tests, only tested by GitHub Actions
        commit_sha = 'd7130683f02fe8284df3557f0b2fd3947c2ea153'
        res = gh.det_commit_status('easybuilders', 'easybuild-easyconfigs', commit_sha, GITHUB_TEST_ACCOUNT)
        self.assertEqual(res, 'failure')

        # commit with passing tests, only tested by GitHub Actions
        commit_sha = 'e6df09700a1b90c63b4f760eda4b590ee1a9c2fd'
        res = gh.det_commit_status('easybuilders', 'easybuild-easyconfigs', commit_sha, GITHUB_TEST_ACCOUNT)
        self.assertEqual(res, 'success')

        # commit in test repo where no CI is running at all
        commit_sha = '8456f867b03aa001fd5a6fe5a0c4300145c065dc'
        res = gh.det_commit_status('easybuilders', GITHUB_REPO, commit_sha, GITHUB_TEST_ACCOUNT)
        self.assertEqual(res, None)

    def test_github_check_pr_eligible_to_merge(self):
        """Test check_pr_eligible_to_merge function"""
        def run_check(expected_result=False):
            """Helper function to check result of check_pr_eligible_to_merge"""
            self.mock_stdout(True)
            self.mock_stderr(True)
            res = gh.check_pr_eligible_to_merge(pr_data)
            stdout = self.get_stdout()
            stderr = self.get_stderr()
            self.mock_stdout(False)
            self.mock_stderr(False)
            self.assertEqual(res, expected_result)
            self.assertEqual(stdout, expected_stdout)
            self.assertTrue(expected_warning in stderr, "Found '%s' in: %s" % (expected_warning, stderr))
            return stderr

        pr_data = {
            'base': {
                'ref': 'main',
                'repo': {
                    'name': 'easybuild-easyconfigs',
                    'owner': {'login': 'easybuilders'},
                },
            },
            'status_last_commit': None,
            'issue_comments': [],
            'milestone': None,
            'number': '1234',
            'merged': False,
            'mergeable_state': 'unknown',
            'reviews': [{'state': 'CHANGES_REQUESTED', 'user': {'login': 'boegel'}},
                        # to check that duplicates are filtered
                        {'state': 'CHANGES_REQUESTED', 'user': {'login': 'boegel'}}],
        }

        test_result_warning_template = "* test suite passes: %s => not eligible for merging!"

        expected_stdout = "Checking eligibility of easybuilders/easybuild-easyconfigs PR #1234 for merging...\n"

        # target branch for PR must be develop
        expected_warning = "* targets develop branch: FAILED; found 'main' => not eligible for merging!\n"
        run_check()

        pr_data['base']['ref'] = 'develop'
        expected_stdout += "* targets develop branch: OK\n"

        # test suite must PASS (not failed, pending or unknown) in Travis
        tests = [
            ('pending', 'pending...'),
            ('error', '(status: error)'),
            ('failure', '(status: failure)'),
            ('foobar', '(status: foobar)'),
            ('', '(status: )'),
        ]
        for status, test_result in tests:
            pr_data['status_last_commit'] = status
            expected_warning = test_result_warning_template % test_result
            run_check()

        pr_data['status_last_commit'] = 'success'
        expected_stdout += "* test suite passes: OK\n"
        expected_warning = ''
        run_check()

        # at least the last test report must be successful (and there must be one)
        expected_warning = "* last test report is successful: (no test reports found) => not eligible for merging!"
        run_check()

        pr_data['issue_comments'] = [
            {'body': "@easybuild-easyconfigs/maintainers: please review/merge?"},
            {'body': "Test report by @boegel\n**SUCCESS**\nit's all good!"},
            {'body': "Test report by @boegel\n**FAILED**\nnothing ever works..."},
            {'body': "this is just a regular comment"},
        ]
        expected_warning = "* last test report is successful: FAILED => not eligible for merging!"
        run_check()

        pr_data['issue_comments'].extend([
            {'body': "yet another comment"},
            {'body': "Test report by @boegel\n**SUCCESS**\nit's all good!"},
        ])
        expected_stdout += "* last test report is successful: OK\n"
        expected_warning = ''
        run_check()

        # approved style review by a human is required
        expected_warning = "* approved review: MISSING => not eligible for merging!"
        run_check()

        pr_data['issue_comments'].insert(2, {'body': 'lgtm'})
        run_check()

        expected_warning = "* no pending change requests: FAILED (changes requested by boegel)"
        expected_warning += " => not eligible for merging!"
        run_check()

        # if PR is approved by a different user that requested changes and that request has not been dismissed,
        # the PR is still not mergeable
        pr_data['reviews'].append({'state': 'APPROVED', 'user': {'login': 'not_boegel'}})
        expected_stdout_saved = expected_stdout
        expected_stdout += "* approved review: OK (by not_boegel)\n"
        run_check()

        # if the user that requested changes approves the PR, it's mergeable
        pr_data['reviews'].append({'state': 'APPROVED', 'user': {'login': 'boegel'}})
        expected_stdout = expected_stdout_saved + "* no pending change requests: OK\n"
        expected_stdout += "* approved review: OK (by not_boegel, boegel)\n"
        expected_warning = ''
        run_check()

        # milestone must be set
        expected_warning = "* milestone is set: no milestone found => not eligible for merging!"
        run_check()

        pr_data['milestone'] = {'title': '3.3.1'}
        expected_stdout += "* milestone is set: OK (3.3.1)\n"

        # mergeable state must be clean
        expected_warning = "* mergeable state is clean: FAILED (mergeable state is 'unknown')"
        run_check()

        pr_data['mergeable_state'] = GITHUB_MERGEABLE_STATE_CLEAN
        expected_stdout += "* mergeable state is clean: OK\n"

        # all checks pass, PR is eligible for merging
        expected_warning = ''
        self.assertEqual(run_check(True), '')

    def test_github_det_pr_labels(self):
        """Test for det_pr_labels function."""

        file_info = {'new_folder': [False], 'new_file_in_existing_folder': [True]}
        res = gh.det_pr_labels(file_info, GITHUB_EASYCONFIGS_REPO)
        self.assertEqual(res, ['update'])

        file_info = {'new_folder': [True], 'new_file_in_existing_folder': [False]}
        res = gh.det_pr_labels(file_info, GITHUB_EASYCONFIGS_REPO)
        self.assertEqual(res, ['new'])

        file_info = {'new_folder': [True, False], 'new_file_in_existing_folder': [False, True]}
        res = gh.det_pr_labels(file_info, GITHUB_EASYCONFIGS_REPO)
        self.assertTrue(sorted(res), ['new', 'update'])

        file_info = {'new': [True]}
        res = gh.det_pr_labels(file_info, GITHUB_EASYBLOCKS_REPO)
        self.assertEqual(res, ['new'])

    def test_github_det_patch_specs(self):
        """Test for det_patch_specs function."""

        patch_paths = [os.path.join(self.test_prefix, p) for p in ['1.patch', '2.patch', '3.patch']]
        file_info = {'ecs': []}

        rawtxt = textwrap.dedent("""
            easyblock = 'ConfigureMake'
            name = 'A'
            version = '42'
            homepage = 'http://foo.com/'
            description = ''
            toolchain = {"name":"GCC", "version": "4.6.3"}

            patches = ['1.patch']
        """)
        file_info['ecs'].append(EasyConfig(None, rawtxt=rawtxt))
        rawtxt = textwrap.dedent("""
            easyblock = 'ConfigureMake'
            name = 'B'
            version = '42'
            homepage = 'http://foo.com/'
            description = ''
            toolchain = {"name":"GCC", "version": "4.6.3"}
        """)
        file_info['ecs'].append(EasyConfig(None, rawtxt=rawtxt))

        error_pattern = "Failed to determine software name to which patch file .*/2.patch relates"
        self.mock_stdout(True)
        self.assertErrorRegex(EasyBuildError, error_pattern, gh.det_patch_specs, patch_paths, file_info, [])
        self.mock_stdout(False)

        rawtxt = textwrap.dedent("""
            easyblock = 'ConfigureMake'
            name = 'C'
            version = '42'
            homepage = 'http://foo.com/'
            description = ''
            toolchain = {"name":"GCC", "version": "4.6.3"}

            patches = [('3.patch', 'subdir'), '2.patch']
        """)
        file_info['ecs'].append(EasyConfig(None, rawtxt=rawtxt))
        self.mock_stdout(True)
        res = gh.det_patch_specs(patch_paths, file_info, [])
        self.mock_stdout(False)

        self.assertEqual([i[0] for i in res], patch_paths)
        self.assertEqual([i[1] for i in res], ['A', 'C', 'C'])

        # check if patches for extensions are found
        rawtxt = textwrap.dedent("""
            easyblock = 'ConfigureMake'
            name = 'patched_ext'
            version = '42'
            homepage = 'http://foo.com/'
            description = ''
            toolchain = {"name":"GCC", "version": "4.6.3"}

            exts_list = [
                'foo',
                ('bar', '1.2.3'),
                ('patched', '4.5.6', {
                    'patches': [('%(name)s-2.patch', 1), '%(name)s-3.patch'],
                }),
            ]
        """)
        patch_paths[1:3] = [os.path.join(self.test_prefix, p) for p in ['patched-2.patch', 'patched-3.patch']]
        file_info['ecs'][-1] = EasyConfig(None, rawtxt=rawtxt)

        self.mock_stdout(True)
        res = gh.det_patch_specs(patch_paths, file_info, [])
        self.mock_stdout(False)

        self.assertEqual([i[0] for i in res], patch_paths)
        self.assertEqual([i[1] for i in res], ['A', 'patched_ext', 'patched_ext'])

        # check if patches for components are found
        rawtxt = textwrap.dedent("""
            easyblock = 'PythonBundle'
            name = 'patched_bundle'
            version = '42'
            homepage = 'http://foo.com/'
            description = ''
            toolchain = {"name":"GCC", "version": "4.6.3"}

            components = [
                ('bar', '1.2.3'),
                ('patched', '4.5.6', {
                    'patches': [('%(name)s-2.patch', 1), '%(name)s-3.patch'],
                }),
            ]
        """)
        file_info['ecs'][-1] = EasyConfig(None, rawtxt=rawtxt)

        self.mock_stdout(True)
        res = gh.det_patch_specs(patch_paths, file_info, [])
        self.mock_stdout(False)

        self.assertEqual([i[0] for i in res], patch_paths)
        self.assertEqual([i[1] for i in res], ['A', 'patched_bundle', 'patched_bundle'])

    def test_github_restclient(self):
        """Test use of RestClient."""
        if self.skip_github_tests:
            print("Skipping test_restclient, no GitHub token available?")
            return

        client = RestClient('https://api.github.com', username=GITHUB_TEST_ACCOUNT, token=self.github_token)

        status, body = client.repos['easybuilders']['testrepository'].contents.a_directory['a_file.txt'].get()
        self.assertEqual(status, 200)
        # base64.b64encode requires & produces a 'bytes' value in Python 3,
        # but we need a string value hence the .decode() (also works in Python 2)
        self.assertEqual(body['content'].strip(), base64.b64encode(b'this is a line of text\n').decode())

        status, headers = client.head()
        self.assertEqual(status, 200)
        self.assertTrue(headers)
        self.assertTrue('X-GitHub-Media-Type' in headers)

        httperror_hit = False
        try:
            status, body = client.user.emails.post(body='test@example.com')
            self.assertTrue(False, 'posting to unauthorized endpoint did not throw a http error')
        except HTTPError:
            httperror_hit = True
        self.assertTrue(httperror_hit, "expected HTTPError not encountered")

        httperror_hit = False
        try:
            status, body = client.user.emails.delete(body='test@example.com')
            self.assertTrue(False, 'deleting to unauthorized endpoint did not throw a http error')
        except HTTPError:
            httperror_hit = True
        self.assertTrue(httperror_hit, "expected HTTPError not encountered")

    def test_github_create_delete_gist(self):
        """Test create_gist and delete_gist."""
        if self.skip_github_tests:
            print("Skipping test_restclient, no GitHub token available?")
            return

        test_txt = "This is just a test."

        gist_url = gh.create_gist(test_txt, 'test.txt', github_user=GITHUB_TEST_ACCOUNT, github_token=self.github_token)
        gist_id = gist_url.split('/')[-1]
        gh.delete_gist(gist_id, github_user=GITHUB_TEST_ACCOUNT, github_token=self.github_token)

    def test_github_det_account_branch_for_pr(self):
        """Test det_account_branch_for_pr."""
        if self.skip_github_tests:
            print("Skipping test_det_account_branch_for_pr, no GitHub token available?")
            return

        init_config(build_options={
            'pr_target_account': 'easybuilders',
            'pr_target_repo': 'easybuild-easyconfigs',
        })

        # see https://github.com/easybuilders/easybuild-easyconfigs/pull/9149
        self.mock_stdout(True)
        account, branch = gh.det_account_branch_for_pr(9149, github_user=GITHUB_TEST_ACCOUNT)
        self.mock_stdout(False)
        self.assertEqual(account, 'boegel')
        self.assertEqual(branch, '20191017070734_new_pr_EasyBuild401')

        init_config(build_options={
            'pr_target_account': 'easybuilders',
            'pr_target_repo': 'easybuild-framework',
        })

        # see https://github.com/easybuilders/easybuild-framework/pull/3069
        self.mock_stdout(True)
        account, branch = gh.det_account_branch_for_pr(3069, github_user=GITHUB_TEST_ACCOUNT)
        self.mock_stdout(False)
        self.assertEqual(account, 'migueldiascosta')
        self.assertEqual(branch, 'fix_inject_checksums')

    def test_github_det_pr_target_repo(self):
        """Test det_pr_target_repo."""

        self.assertEqual(build_option('pr_target_repo'), None)

        # no files => return default target repo (None)
        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type([])), None)

        test_dir = os.path.dirname(os.path.abspath(__file__))

        # easyconfigs/patches (incl. files to delete) => easyconfigs repo
        # this is solely based on filenames, actual files are not opened, except for the patch file which must exist
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        toy_patch = os.path.join(test_dir, 'sandbox', 'sources', 'toy', toy_patch_fn)
        test_cases = [
            ['toy.eb'],
            [toy_patch],
            ['toy.eb', toy_patch],
            [':toy.eb'],  # deleting toy.eb
            ['one.eb', 'two.eb'],
            ['one.eb', 'two.eb', toy_patch, ':todelete.eb'],
        ]
        for test_case in test_cases:
            self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type(test_case)), 'easybuild-easyconfigs')

        # if only Python files are involved, result is easyblocks or framework repo;
        # all Python files are easyblocks => easyblocks repo, otherwise => framework repo;
        # files are opened and inspected here to discriminate between easyblocks & other Python files, so must exist!
        github_py = os.path.join(test_dir, 'github.py')

        configuremake = os.path.join(test_dir, 'sandbox', 'easybuild', 'easyblocks', 'generic', 'configuremake.py')
        self.assertTrue(os.path.exists(configuremake))
        toy_eb = os.path.join(test_dir, 'sandbox', 'easybuild', 'easyblocks', 't', 'toy.py')
        self.assertTrue(os.path.exists(toy_eb))

        self.assertEqual(build_option('pr_target_repo'), None)
        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type([github_py])), 'easybuild-framework')
        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type([configuremake])), 'easybuild-easyblocks')
        py_files = [github_py, configuremake]
        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type(py_files)), 'easybuild-framework')
        py_files[0] = toy_eb
        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type(py_files)), 'easybuild-easyblocks')
        py_files.append(github_py)
        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type(py_files)), 'easybuild-framework')

        # as soon as an easyconfig file or patch files is involved => result is easybuild-easyconfigs repo
        for fn in ['toy.eb', toy_patch]:
            self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type(py_files + [fn])), 'easybuild-easyconfigs')

        # if --pr-target-repo is specified, we always get this value (no guessing anymore)
        init_config(build_options={'pr_target_repo': 'thisisjustatest'})

        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type([])), 'thisisjustatest')
        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type(['toy.eb', toy_patch])), 'thisisjustatest')
        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type(py_files)), 'thisisjustatest')
        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type([configuremake])), 'thisisjustatest')
        self.assertEqual(gh.det_pr_target_repo(categorize_files_by_type([toy_eb])), 'thisisjustatest')

    def test_push_branch_to_github(self):
        """Test push_branch_to_github."""

        build_options = {'dry_run': True}
        init_config(build_options=build_options)

        git_repo = gh.init_repo(self.test_prefix, GITHUB_REPO)
        branch = 'test123'

        self.mock_stderr(True)
        self.mock_stdout(True)
        gh.setup_repo(git_repo, GITHUB_USER, GITHUB_REPO, 'main')
        git_repo.create_head(branch, force=True)
        gh.push_branch_to_github(git_repo, GITHUB_USER, GITHUB_REPO, branch)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(True)
        self.mock_stdout(True)

        self.assertEqual(stderr, '')

        github_path = '%s/%s.git' % (GITHUB_USER, GITHUB_REPO)
        pattern = r'^' + '\n'.join([
            r"== fetching branch 'main' from https://github.com/%s\.\.\." % github_path,
            r"== pushing branch 'test123' to remote 'github_.*' \(git@github.com:%s\) \[DRY RUN\]" % github_path,
        ]) + r'$'
        regex = re.compile(pattern)
        self.assertTrue(regex.match(stdout.strip()), "Pattern '%s' doesn't match: %s" % (regex.pattern, stdout))

    def test_github_pr_test_report(self):
        """Test for post_pr_test_report function."""
        if self.skip_github_tests:
            print("Skipping test_post_pr_test_report, no GitHub token available?")
            return

        init_config(build_options={
            'dry_run': True,
            'github_user': GITHUB_TEST_ACCOUNT,
        })

        test_report = {'full': "This is a test report!"}

        init_session_state = session_state()

        self.mock_stderr(True)
        self.mock_stdout(True)
        post_pr_test_report('1234', gh.GITHUB_EASYCONFIGS_REPO, test_report, "OK!", init_session_state, True)
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertEqual(stderr, '')

        patterns = [
            r"^\[DRY RUN\] Adding comment to easybuild-easyconfigs issue #1234: 'Test report by @easybuild_test",
            r"^See https://gist.github.com/DRY_RUN for a full test report.'",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

        self.mock_stderr(True)
        self.mock_stdout(True)
        post_pr_test_report('1234', gh.GITHUB_EASYBLOCKS_REPO, test_report, "OK!", init_session_state, True)
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertEqual(stderr, '')

        patterns = [
            r"^\[DRY RUN\] Adding comment to easybuild-easyblocks issue #1234: 'Test report by @easybuild_test",
            r"^See https://gist.github.com/DRY_RUN for a full test report.'",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

        # also test combination of --from-pr and --include-easyblocks-from-pr
        update_build_option('include_easyblocks_from_pr', ['6789'])

        self.mock_stderr(True)
        self.mock_stdout(True)
        post_pr_test_report('1234', gh.GITHUB_EASYCONFIGS_REPO, test_report, "OK!", init_session_state, True)
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertEqual(stderr, '')

        patterns = [
            r"^\[DRY RUN\] Adding comment to easybuild-easyconfigs issue #1234: 'Test report by @easybuild_test",
            r"^See https://gist.github.com/DRY_RUN for a full test report.'",
            r"Using easyblocks from PR\(s\) https://github.com/easybuilders/easybuild-easyblocks/pull/6789",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

    def test_github_create_test_report(self):
        """Test create_test_report function."""
        logfile = os.path.join(self.test_prefix, 'log.txt')
        write_file(logfile, "Bazel failed with: error")
        ecs_with_res = [
            ({'spec': 'test.eb'}, {'success': True}),
            ({'spec': 'fail.eb'}, {
                'success': False,
                'err': EasyBuildError("error: bazel"),
                'traceback': "in bazel",
                'log_file': logfile,
            }),
        ]
        init_session_state = {
            'easybuild_configuration': ['EASYBUILD_DEBUG=1'],
            'environment': {'USER': 'test'},
            'module_list': [{'mod_name': 'test'}],
            'system_info': {'name': 'test'},
            'time': gmtime(0),
        }
        res = create_test_report("just a test", ecs_with_res, init_session_state)
        patterns = [
            "**SUCCESS** _test.eb_",
            "**FAIL (build issue)** _fail.eb_",
            "01 Jan 1970 00:00:00",
            "EASYBUILD_DEBUG=1",
        ]
        for pattern in patterns:
            self.assertTrue(pattern in res['full'], "Pattern '%s' found in: %s" % (pattern, res['full']))

        for pattern in patterns[:2]:
            self.assertTrue(pattern in res['full'], "Pattern '%s' found in: %s" % (pattern, res['overview']))

        # mock create_gist function, we don't want to actually create a gist every time we run this test...
        def fake_create_gist(*args, **kwargs):
            return 'https://gist.github.com/test'

        easybuild.tools.testing.create_gist = fake_create_gist

        res = create_test_report("just a test", ecs_with_res, init_session_state, pr_nrs=[123], gist_log=True)

        patterns.insert(2, "https://gist.github.com/test")
        patterns.extend([
            "https://github.com/easybuilders/easybuild-easyconfigs/pull/123",
        ])
        for pattern in patterns:
            self.assertTrue(pattern in res['full'], "Pattern '%s' found in: %s" % (pattern, res['full']))

        for pattern in patterns[:3]:
            self.assertTrue(pattern in res['full'], "Pattern '%s' found in: %s" % (pattern, res['overview']))

        self.assertTrue("**SUCCESS** _test.eb_" in res['overview'])


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(GithubTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
