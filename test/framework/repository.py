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
Unit tests for repository.py.

@author: Toon Willems (Ghent University)
"""

import shutil
import tempfile
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main

from easybuild.tools.repository import FileRepository, init_repository


class RepositoryTest(EnhancedTestCase):
    """ very basis FileRepository test, we don't want git / svn dependency """

    def setUp(self):
        """Set up test."""
        super(RepositoryTest, self).setUp()

        self.path = tempfile.mkdtemp(prefix='easybuild-repo-')
        shutil.rmtree(self.path, True)

    def test_filerepository(self):
        """Test creating instance of FileRepository."""
        repo = FileRepository(self.path)
        repo.init()
        self.assertEqual(repo.wc, self.path)

        subdir = 'sub/dir'
        repo = FileRepository(self.path, subdir)
        repo.init()
        self.assertEqual(repo.wc, self.path)
        self.assertEqual(repo.subdir, subdir)

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

    def tearDown(self):
        """Clean up after test."""
        super(RepositoryTest, self).tearDown()

        shutil.rmtree(self.path, True)

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(RepositoryTest)


if __name__ == '__main__':
    main()
