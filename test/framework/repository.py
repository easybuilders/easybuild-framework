##
# Copyright 2012-2013 Ghent University
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

import os
import shutil
import tempfile
from unittest import TestCase, TestSuite, main

from easybuild.tools.repository import FileRepository


class RepositoryTest(TestCase):
    """ very basis FileRepository test, we don't want git / svn dependency """

    def setUp(self):
        """ make sure temporary path does not exist """
        self.path = tempfile.mkdtemp(prefix='easybuild-repo-')
        shutil.rmtree(self.path, True)
        self.cwd = os.getcwd()

    def runTest(self):
        """ after initialization it should be the working copy """
        repo = FileRepository(self.path)
        self.assertEqual(repo.wc, self.path)

    def tearDown(self):
        """ clean up after myself """
        shutil.rmtree(self.path, True)
        os.chdir(self.cwd)

def suite():
    """ returns all the testcases in this module """
    return TestSuite([RepositoryTest()])

if __name__ == '__main__':
    main()
