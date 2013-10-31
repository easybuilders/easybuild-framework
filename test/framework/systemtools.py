##
# Copyright 2013 Ghent University
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
Unit tests for systemtools.py

@author: Kenneth hoste (Ghent University)
"""

from unittest import TestCase, TestLoader, main

from easybuild.tools.systemtools import AMD, ARM, DARWIN, INTEL, LINUX, UNKNOWN
from easybuild.tools.systemtools import get_avail_core_count, get_core_count
from easybuild.tools.systemtools import get_cpu_model, get_cpu_speed, get_cpu_vendor
from easybuild.tools.systemtools import get_os_type, get_shared_lib_ext, get_platform_name, get_os_name, get_os_version


class SystemToolsTest(TestCase):
    """ very basis FileRepository test, we don't want git / svn dependency """

    def test_core_count(self):
        """Test getting core count."""
        for core_count in [get_avail_core_count(), get_core_count()]:
            self.assertTrue(isinstance(core_count, int), "core_count has type int: %s, %s" % (core_count, type(core_count)))
            self.assertTrue(core_count > 0, "core_count %d > 0" % core_count)

    def test_cpu_model(self):
        """Test getting CPU model."""
        cpu_model = get_cpu_model()
        self.assertTrue(isinstance(cpu_model, basestring))

    def test_cpu_speed(self):
        """Test getting CPU speed."""
        cpu_speed = get_cpu_speed()
        self.assertTrue(isinstance(cpu_speed, float))
        self.assertTrue(cpu_speed > 0.0)

    def test_cpu_vendor(self):
        """Test getting CPU vendor."""
        cpu_vendor = get_cpu_vendor()
        self.assertTrue(cpu_vendor in [AMD, ARM, INTEL, UNKNOWN])

    def test_os_type(self):
        """Test getting OS type."""
        os_type = get_os_type()
        self.assertTrue(os_type in [DARWIN, LINUX])

    def test_shared_lib_ext(self):
        """Test getting extension for shared libraries."""
        ext = get_shared_lib_ext()
        self.assertTrue(ext in ['dylib', 'so'])

    def test_platform_name(self):
        """Test getting platform name."""
        platform_name_nover = get_platform_name()
        self.assertTrue(isinstance(platform_name_nover, basestring))
        len_nover = len(platform_name_nover.split('-'))
        self.assertTrue(len_nover >= 3)

        platform_name_ver = get_platform_name(withversion=True)
        self.assertTrue(isinstance(platform_name_ver, basestring))
        len_ver = len(platform_name_ver.split('-'))
        self.assertTrue(platform_name_ver.startswith(platform_name_ver))
        self.assertTrue(len_ver >= len_nover)

    def test_os_name(self):
        """Test getting OS name."""
        os_name = get_os_name()
        self.assertTrue(isinstance(os_name, basestring) or os_name == UNKNOWN)

    def test_os_version(self):
        """Test getting OS version."""
        os_version = get_os_version()
        self.assertTrue(isinstance(os_version, basestring) or os_version == UNKNOWN)

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(SystemToolsTest)

if __name__ == '__main__':
    main()
