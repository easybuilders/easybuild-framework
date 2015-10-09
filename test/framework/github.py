##
# Copyright 2012-2015 Ghent University
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
Unit tests for talking to GitHub.

@author: Jens Timmerman (Ghent University)
"""

import os
import re
import shutil
import tempfile
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main
from urllib2 import URLError

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file, write_file
import easybuild.tools.github as gh


# test account, for which a token is available
GITHUB_TEST_ACCOUNT = 'easybuild_test'
# the user who's repo to test
GITHUB_USER = "hpcugent"
# the repo of this user to use in this test
GITHUB_REPO = "testrepository"
# branch to test
GITHUB_BRANCH = 'master'

class GithubTest(EnhancedTestCase):
    """ small test for The github package
    This should not be to much, since there is an hourly limit of request
    for non authenticated users of 50"""

    def setUp(self):
        """setup"""
        super(GithubTest, self).setUp()
        self.github_token = gh.fetch_github_token(GITHUB_TEST_ACCOUNT)
        if self.github_token is None:
            self.ghfs = None
        else:
            self.ghfs = gh.Githubfs(GITHUB_USER, GITHUB_REPO, GITHUB_BRANCH, GITHUB_TEST_ACCOUNT, None, self.github_token)

    def test_walk(self):
        """test the gitubfs walk function"""
        if self.github_token is None:
            print "Skipping test_walk, no GitHub token available?"
            return

        try:
            expected = [(None, ['a_directory', 'second_dir'], ['README.md']),
                        ('a_directory', ['a_subdirectory'], ['a_file.txt']), ('a_directory/a_subdirectory', [],
                        ['a_file.txt']), ('second_dir', [], ['a_file.txt'])]
            self.assertEquals([x for x in self.ghfs.walk(None)], expected)
        except IOError:
            pass

    def test_read_api(self):
        """Test the githubfs read function"""
        if self.github_token is None:
            print "Skipping test_read_api, no GitHub token available?"
            return

        try:
            self.assertEquals(self.ghfs.read("a_directory/a_file.txt").strip(), "this is a line of text")
        except IOError:
            pass

    def test_read(self):
        """Test the githubfs read function without using the api"""
        if self.github_token is None:
            print "Skipping test_read, no GitHub token available?"
            return

        try:
            fp = self.ghfs.read("a_directory/a_file.txt", api=False)
            self.assertEquals(open(fp, 'r').read().strip(), "this is a line of text")
            os.remove(fp)
        except (IOError, OSError):
            pass

    def test_fetch_easyconfigs_from_pr(self):
        """Test fetch_easyconfigs_from_pr function."""
        if self.github_token is None:
            print "Skipping test_fetch_easyconfigs_from_pr, no GitHub token available?"
            return

        tmpdir = tempfile.mkdtemp()
        # PR for ictce/6.2.5, see https://github.com/hpcugent/easybuild-easyconfigs/pull/726/files
        all_ecs = ['gzip-1.6-ictce-6.2.5.eb', 'icc-2013_sp1.2.144.eb', 'ictce-6.2.5.eb', 'ifort-2013_sp1.2.144.eb',
                   'imkl-11.1.2.144.eb', 'impi-4.1.3.049.eb']
        try:
            ec_files = gh.fetch_easyconfigs_from_pr(726, path=tmpdir, github_user=GITHUB_TEST_ACCOUNT)
            self.assertEqual(all_ecs, sorted([os.path.basename(f) for f in ec_files]))
            self.assertEqual(all_ecs, sorted(os.listdir(tmpdir)))

            # PR for EasyBuild v1.13.0 release (250+ commits, 218 files changed)
            err_msg = "PR #897 contains more than .* commits, can't obtain last commit"
            self.assertErrorRegex(EasyBuildError, err_msg, gh.fetch_easyconfigs_from_pr, 897,
                                  github_user=GITHUB_TEST_ACCOUNT)

        except URLError, err:
            print "Ignoring URLError '%s' in test_fetch_easyconfigs_from_pr" % err

        shutil.rmtree(tmpdir)

    def test_fetch_latest_commit_sha(self):
        """Test fetch_latest_commit_sha function."""
        sha = gh.fetch_latest_commit_sha('easybuild-framework', 'hpcugent')
        self.assertTrue(re.match('^[0-9a-f]{40}$', sha))
        sha = gh.fetch_latest_commit_sha('easybuild-easyblocks', 'hpcugent', branch='develop')
        self.assertTrue(re.match('^[0-9a-f]{40}$', sha))

    def test_download_repo(self):
        """Test download_repo function."""
        # default: download tarball for master branch of hpcugent/easybuild-easyconfigs repo
        path = gh.download_repo(path=self.test_prefix)
        repodir = os.path.join(self.test_prefix, 'hpcugent', 'easybuild-easyconfigs-master')
        self.assertTrue(os.path.samefile(path, repodir))
        self.assertTrue(os.path.exists(repodir))
        shafile = os.path.join(repodir, 'latest-sha')
        self.assertTrue(re.match('^[0-9a-f]{40}$', read_file(shafile)))
        self.assertTrue(os.path.exists(os.path.join(repodir, 'easybuild', 'easyconfigs', 'f', 'foss', 'foss-2015a.eb')))

        # existing downloaded repo is not reperformed, except if SHA is different
        account, repo, branch = 'boegel', 'easybuild-easyblocks', 'develop'
        repodir = os.path.join(self.test_prefix, account, '%s-%s' % (repo, branch))
        latest_sha = gh.fetch_latest_commit_sha(repo, account, branch=branch)

        # put 'latest-sha' fail in place, check whether repo was (re)downloaded (should not)
        shafile = os.path.join(repodir, 'latest-sha')
        write_file(shafile, latest_sha)
        path = gh.download_repo(repo=repo, branch=branch, account=account, path=self.test_prefix)
        self.assertTrue(os.path.samefile(path, repodir))
        self.assertEqual(os.listdir(repodir), ['latest-sha'])

        # remove 'latest-sha' file and verify that download was performed
        os.remove(shafile)
        path = gh.download_repo(repo=repo, branch=branch, account=account, path=self.test_prefix)
        self.assertTrue(os.path.samefile(path, repodir))
        self.assertTrue('easybuild' in os.listdir(repodir))
        self.assertTrue(re.match('^[0-9a-f]{40}$', read_file(shafile)))
        self.assertTrue(os.path.exists(os.path.join(repodir, 'easybuild', 'easyblocks', '__init__.py')))


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(GithubTest)

if __name__ == '__main__':
    main()
