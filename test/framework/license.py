# #
# Copyright 2013-2014 Ghent University
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
# #
"""
Unit tests for easyconfig/licenses.py

@author: Stijn De Weirdt (Ghent University)
"""
import os

from easybuild.framework.easyconfig.licenses import License, VeryRestrictive, what_licenses
from unittest import TestCase, TestLoader, main


class LicenseTest(TestCase):
    """Test the license"""

    def test_common_ones(self):
        """Check if a number of common licenses can be found"""
        lics = what_licenses()
        commonlicenses = ['VeryRestrictive', 'GPLv2', 'GPLv3']
        for lic in commonlicenses:
            self.assertTrue(lic in lics)

    def test_default_license(self):
        """Verify that the default License class is very restrictive"""
        self.assertFalse(License.DISTRIBUTE_SOURCE)
        self.assertTrue(License.GROUP_SOURCE)
        self.assertTrue(License.GROUP_BINARY)

    def test_veryrestrictive_license(self):
        """Verify that the very restrictive class is very restrictive"""
        self.assertFalse(VeryRestrictive.DISTRIBUTE_SOURCE)
        self.assertTrue(VeryRestrictive.GROUP_SOURCE)
        self.assertTrue(VeryRestrictive.GROUP_BINARY)

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(LicenseTest)


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
