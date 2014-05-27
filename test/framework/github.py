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
Unit tests for talking to GitHub.

@author: Jens Timmerman (Ghent University)
"""

import os
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main

from easybuild.tools.github import Githubfs, fetch_github_token


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
        github_user = 'easybuild_test'
        github_token = fetch_github_token(github_user)
        if github_token is None:
            self.ghfs = None
        else:
            self.ghfs = Githubfs(GITHUB_USER, GITHUB_REPO, GITHUB_BRANCH, github_user, None, github_token)

    def test_walk(self):
        """test the gitubfs walk function"""
        # TODO: this will not work when rate limited, so we should have a test account token here
        if self.ghfs is not None:
            try:
                expected = [(None, ['a_directory', 'second_dir'], ['README.md']),
                            ('a_directory', ['a_subdirectory'], ['a_file.txt']), ('a_directory/a_subdirectory', [],
                            ['a_file.txt']), ('second_dir', [], ['a_file.txt'])]
                self.assertEquals([x for x in self.ghfs.walk(None)], expected)
            except IOError:
                pass
        else:
            print "Skipping test_walk, no GitHub token available?"

    def test_read_api(self):
        """Test the githubfs read function"""
        if self.ghfs is not None:
            try:
                self.assertEquals(self.ghfs.read("a_directory/a_file.txt").strip(), "this is a line of text")
            except IOError:
                pass
        else:
            print "Skipping test_read_api, no GitHub token available?"

    def test_read(self):
        """Test the githubfs read function without using the api"""
        if self.ghfs is not None:
            try:
                fp = self.ghfs.read("a_directory/a_file.txt", api=False)
                self.assertEquals(open(fp, 'r').read().strip(), "this is a line of text")
                os.remove(fp)
            except (IOError, OSError):
                pass
        else:
            print "Skipping test_read, no GitHub token available?"

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(GithubTest)

if __name__ == '__main__':
    main()
