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
Unit tests for easyconfig/licenses.py

@author: Stijn De Weirdt (Ghent University)
"""
import sys

from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

from easybuild.framework.easyconfig.licenses import License, LicenseVeryRestrictive, what_licenses


class LicenseTest(EnhancedTestCase):
    """Test the license"""

    def test_common_ones(self):
        """Check if a number of common licenses can be found"""
        lics = what_licenses()
        commonlicenses = ['LicenseVeryRestrictive', 'LicenseGPLv2', 'LicenseGPLv3']
        for lic in commonlicenses:
            self.assertTrue(lic in lics, "%s found in %s" % (lic, lics.keys()))

    def test_default_license(self):
        """Verify that the default License class is very restrictive"""
        self.assertFalse(License.DISTRIBUTE_SOURCE)
        self.assertTrue(License.GROUP_SOURCE)
        self.assertTrue(License.GROUP_BINARY)

    def test_veryrestrictive_license(self):
        """Verify that the very restrictive class is very restrictive"""
        self.assertFalse(LicenseVeryRestrictive.DISTRIBUTE_SOURCE)
        self.assertTrue(LicenseVeryRestrictive.GROUP_SOURCE)
        self.assertTrue(LicenseVeryRestrictive.GROUP_BINARY)

    def test_licenses(self):
        """Test format of available licenses."""
        lics = what_licenses()
        for lic in lics:
            self.assertTrue(isinstance(lic, basestring))
            self.assertTrue(lic.startswith('License'))
            self.assertTrue(issubclass(lics[lic], License))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(LicenseTest, sys.argv[1:])


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    TextTestRunner(verbosity=1).run(suite())
