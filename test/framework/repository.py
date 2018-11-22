##
# Copyright 2012-2018 Ghent University
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
Unit tests for repository.py.

@author: Toon Willems (Ghent University)
"""
import os
import re
import shutil
import sys
import tempfile
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

import easybuild.tools.build_log
from easybuild.framework.easyconfig.parser import EasyConfigParser
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file
from easybuild.tools.repository.filerepo import FileRepository
from easybuild.tools.repository.gitrepo import GitRepository
from easybuild.tools.repository.hgrepo import HgRepository
from easybuild.tools.repository.svnrepo import SvnRepository
from easybuild.tools.repository.repository import init_repository
from easybuild.tools.run import run_cmd
from easybuild.tools.version import VERSION


class RepositoryTest(EnhancedTestCase):
    """ very basis FileRepository test, we don't want git / svn dependency """

    def setUp(self):
        """Set up test."""
        super(RepositoryTest, self).setUp()

        self.path = tempfile.mkdtemp(prefix='easybuild-repo-')
        shutil.rmtree(self.path, True)

    def test_filerepo(self):
        """Test using FileRepository."""
        repo = FileRepository(self.path)
        repo.init()
        self.assertEqual(repo.wc, self.path)

        subdir = 'sub/dir'
        repo = FileRepository(self.path, subdir)
        repo.init()
        self.assertEqual(repo.wc, self.path)
        self.assertEqual(repo.subdir, subdir)

    def test_gitrepo(self):
        """Test using GitRepository."""
        # only run this test if git Python module is available
        try:
            from git import GitCommandError
        except ImportError:
            print "(skipping GitRepository test)"
            return

        test_repo_url = 'https://github.com/hpcugent/testrepository'

        # URL
        repo = GitRepository(test_repo_url)
        try:
            repo.init()
            self.assertEqual(os.path.basename(repo.wc), 'testrepository')
            self.assertTrue(os.path.exists(os.path.join(repo.wc, 'README.md')))
            shutil.rmtree(repo.wc)
        except EasyBuildError, err:
            print "ignoring failed subtest in test_gitrepo, testing offline?"
            self.assertTrue(re.search("pull in working copy .* went wrong", str(err)))

        # filepath
        tmpdir = tempfile.mkdtemp()
        cmd = "cd %s && git clone --bare %s" % (tmpdir, test_repo_url)
        _, ec = run_cmd(cmd, simple=False, log_all=False, log_ok=False)

        # skip remainder of test if creating bare git repo didn't work
        if ec == 0:
            repo = GitRepository(os.path.join(tmpdir, 'testrepository.git'))
            repo.init()
            toy_ec_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
            repo.add_easyconfig(toy_ec_file, 'test', '1.0', {}, None)
            repo.commit("toy/0.0")

            log_regex = re.compile(r"toy/0.0 with EasyBuild v%s @ .* \(time: .*, user: .*\)" % VERSION, re.M)
            logmsg = repo.client.log('HEAD^!')
            self.assertTrue(log_regex.search(logmsg), "Pattern '%s' found in %s" % (log_regex.pattern, logmsg))

            shutil.rmtree(repo.wc)
            shutil.rmtree(tmpdir)

    def test_svnrepo(self):
        """Test using SvnRepository."""
        # only run this test if pysvn Python module is available
        try:
            from pysvn import ClientError
        except ImportError:
            print "(skipping SvnRepository test)"
            return

        # GitHub also supports SVN
        test_repo_url = 'https://github.com/hpcugent/testrepository'

        repo = SvnRepository(test_repo_url)
        repo.init()
        self.assertTrue(os.path.exists(os.path.join(repo.wc, 'trunk', 'README.md')))
        shutil.rmtree(repo.wc)

    def test_hgrepo(self):
        """Test using HgRepository."""
        # only run this test if pysvn Python module is available
        try:
            import hglib
        except ImportError:
            print "(skipping HgRepository test)"
            return

        # GitHub also supports SVN
        test_repo_url = 'https://kehoste@bitbucket.org/kehoste/testrepository'

        repo = HgRepository(test_repo_url)
        repo.init()
        self.assertTrue(os.path.exists(os.path.join(repo.wc, 'README')))
        shutil.rmtree(repo.wc)

    def test_init_repository(self):
        """Test use of init_repository function."""
        repo = init_repository('FileRepository', self.path)
        self.assertEqual(repo.wc, self.path)

        repo = init_repository('FileRepository', [self.path])
        self.assertEqual(repo.wc, self.path)

        subdir = 'sub/dir'
        repo = init_repository('FileRepository', [self.path, subdir])
        self.assertEqual(repo.wc, self.path)
        self.assertEqual(repo.subdir, subdir)

    def test_add_easyconfig(self):
        """Test use of add_easyconfig method"""
        repo = init_repository('FileRepository', self.path)
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')

        def check_ec(path, expected_buildstats):
            """Check easyconfig at specified path"""
            self.assertTrue(os.path.exists(path))
            ectxt = read_file(path)
            self.assertTrue(ectxt.startswith("# Built with EasyBuild version"))
            self.assertTrue("# Build statistics" in ectxt)
            ecdict = EasyConfigParser(path).get_config_dict()
            self.assertEqual(ecdict['buildstats'], expected_buildstats)

        toy_eb_file = os.path.join(test_easyconfigs, 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        path = repo.add_easyconfig(toy_eb_file, 'test', '1.0', {'time': 1.23}, None)
        check_ec(path, [{'time': 1.23}])

        path = repo.add_easyconfig(toy_eb_file, 'test', '1.0', {'time': 1.23, 'size': 123}, [{'time': 0.9, 'size': 2}])
        check_ec(path, [{'time': 0.9, 'size': 2}, {'time': 1.23, 'size': 123}])

        orig_experimental = easybuild.tools.build_log.EXPERIMENTAL
        easybuild.tools.build_log.EXPERIMENTAL = True

        if 'yaml' in sys.modules:
            toy_yeb_file = os.path.join(test_easyconfigs, 'yeb', 'toy-0.0.yeb')
            path = repo.add_easyconfig(toy_yeb_file, 'test', '1.0', {'time': 1.23}, None)
            check_ec(path, [{'time': 1.23}])

            path = repo.add_easyconfig(toy_yeb_file, 'test', '1.0', {'time': 1.23, 'size': 123}, [{'time': 0.9, 'size': 2}])
            check_ec(path, [{'time': 0.9, 'size': 2}, {'time': 1.23, 'size': 123}])

            easybuild.tools.build_log.EXPERIMENTAL = orig_experimental
        else:
            print "Skipping .yeb part of test_add_easyconfig (no PyYAML available)"

    def tearDown(self):
        """Clean up after test."""
        super(RepositoryTest, self).tearDown()

        shutil.rmtree(self.path, True)

def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(RepositoryTest, sys.argv[1:])


if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
