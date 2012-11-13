##
# Copyright 2012 Ghent University
# Copyright 2012 Kenneth Hoste
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
import os
import re
from unittest import TestCase, TestLoader

from easybuild.test.utilities import find_full_path
from easybuild.tools.toolchain.utilities import search_toolchain

class ToolchainTest(TestCase):
    """ Baseclass for toolchain testcases """

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
        except error, err:
            self.assertTrue(re.search(regex, err.msg))

    def setUp(self):
        """Setup for tests."""
        # make sure path with modules for testing is added to MODULEPATH
        self.orig_modpath = os.environ.get('MODULEPATH', '')
        os.environ['MODULEPATH'] = find_full_path(os.path.join('easybuild', 'test', 'modules'))

    def test_unknown_toolchain(self):
        """Test search_toolchain function for not available toolchains."""
        tc, all_tcs = search_toolchain("NOSUCHTOOLKIT")
        self.assertEqual(tc, None)
        self.assertTrue(len(all_tcs) > 0)  # list of available toolchains

    def test_goalf_toolchain(self):
        """Test for goalf toolchain."""
        name = "goalf"
        tc, _ = search_toolchain(name)
        self.assertEqual(tc.NAME, name)
        self.tc = tc(version="1.1.0-no-OFED")

    def test_get_variable_compilers(self):
        """Test get_variable function to obtain compiler variables."""
        tc_class, _ = search_toolchain("goalf")
        tc = tc_class(version="1.1.0-no-OFED")
        tc.prepare()

        cc = tc.get_variable('CC')
        self.assertEqual(cc, "gcc")
        cxx = tc.get_variable('CXX')
        self.assertEqual(cxx, "g++")
        f77 = tc.get_variable('F77')
        self.assertEqual(f77, "gfortran")
        f90 = tc.get_variable('F90')
        self.assertEqual(f90, "gfortran")

    def test_get_variable_libs_list(self):
        """Test get_variable function to obtain list of libraries."""
        tc_class, _ = search_toolchain("goalf")
        tc = tc_class(version="1.1.0-no-OFED")
        tc.prepare()

        ldflags = tc.get_variable('LDFLAGS', typ=list)
        self.assertTrue(isinstance(ldflags, list))
        if len(ldflags) > 0:
            self.assertTrue(isinstance(ldflags[0], basestring))

    def tearDown(self):
        """Cleanup."""
        os.environ['MODULEPATH'] = self.orig_modpath

def suite():
    """ return all the tests"""
    return TestLoader().loadTestsFromTestCase(ToolchainTest)
