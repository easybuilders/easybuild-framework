# #
# Copyright 2016-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
Overrides TestLoader to filter single tests

@author Caroline De Brouwer (Ghent University)
"""
import sys
import unittest

class TestLoaderFiltered(unittest.TestLoader):

    def loadTestsFromTestCase(self, testCaseClass, filters):
        """Return a suite of all tests cases contained in testCaseClass."""

        if issubclass(testCaseClass, unittest.TestSuite):
            raise TypeError("Test cases should not be derived from "\
                "TestSuite. Maybe you meant to derive from"\
                " TestCase?")
        test_case_names = self.getTestCaseNames(testCaseClass)
        test_cases = []
        if len(filters) > 0:
            for test_case_name in test_case_names:
                for filt in filters:
                    if filt in test_case_name:
                        test_cases.append(testCaseClass(test_case_name))
        else:
            test_cases = [testCaseClass(test_case_name) for test_case_name in test_case_names]

        loaded_suite = self.suiteClass(test_cases)

        return loaded_suite
