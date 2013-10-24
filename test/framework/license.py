"""
Unit tests for easyconfig/format/format.py

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
