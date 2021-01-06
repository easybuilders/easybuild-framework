# #
# Copyright 2014-2021 Ghent University
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
# #
"""
Unit tests for easyconfig/format/convert.py

@author: Stijn De Weirdt (Ghent University)
"""
import sys

from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

from easybuild.framework.easyconfig.format.convert import Dependency
from easybuild.framework.easyconfig.format.version import VersionOperator, ToolchainVersionOperator


class ConvertTest(EnhancedTestCase):
    """Test the license"""

    def test_dependency(self):
        """Test Dependency class"""
        versop_str = '>= 1.5'
        tc_versop_str = 'GCC >= 3.0'

        versop = VersionOperator(versop_str)
        tc_versop = ToolchainVersionOperator(tc_versop_str)

        txt = Dependency.SEPARATOR_DEP.join([versop_str])
        dest = {'versop': versop}
        res = Dependency(txt)
        self.assertEqual(dest, res)
        self.assertEqual(str(res), txt)

        txt = Dependency.SEPARATOR_DEP.join([versop_str, tc_versop_str])
        dest = {'versop': versop, 'tc_versop': tc_versop}
        res = Dependency(txt)
        self.assertEqual(dest, res)
        self.assertEqual(str(res), txt)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(ConvertTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
