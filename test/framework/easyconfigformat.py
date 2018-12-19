# #
# Copyright 2013-2018 Ghent University
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
Unit tests for easyconfig/format/format.py

@author: Stijn De Weirdt (Ghent University)
"""
import sys

from easybuild.framework.easyconfig.format.format import FORMAT_VERSION_HEADER_TEMPLATE, FORMAT_VERSION_REGEXP
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

from vsc.utils.fancylogger import setLogLevelDebug, logToScreen


class EasyConfigFormatTest(EnhancedTestCase):
    """Test the parser"""

    def test_parser_version_regex(self):
        """Trivial parser test"""
        version = {'major': 1, 'minor': 0}
        txt = FORMAT_VERSION_HEADER_TEMPLATE % version
        res = FORMAT_VERSION_REGEXP.search(txt).groupdict()
        self.assertEqual(version['major'], int(res['major']))
        self.assertEqual(version['minor'], int(res['minor']))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(EasyConfigFormatTest, sys.argv[1:])


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    TextTestRunner(verbosity=1).run(suite())
