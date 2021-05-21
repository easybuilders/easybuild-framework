# #
# Copyright 2013-2021 Ghent University
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
Unit tests for easystack files

@author: Denis Kristak (Inuits)
@author: Kenneth Hoste (Ghent University)
"""
import os
import sys
from unittest import TextTestRunner

import easybuild.tools.build_log
from easybuild.framework.easystack import parse_easystack
from easybuild.tools.build_log import EasyBuildError
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered


class EasyStackTest(EnhancedTestCase):
    """Testcases for easystack files."""

    logfile = None

    def setUp(self):
        """Set up test."""
        super(EasyStackTest, self).setUp()
        self.orig_experimental = easybuild.tools.build_log.EXPERIMENTAL

    def tearDown(self):
        """Clean up after test."""
        easybuild.tools.build_log.EXPERIMENTAL = self.orig_experimental
        super(EasyStackTest, self).tearDown()

    def test_easystack_wrong_structure(self):
        """Test for --easystack <easystack.yaml> when yaml easystack has wrong structure"""
        easybuild.tools.build_log.EXPERIMENTAL = True
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_wrong_structure.yaml')

        expected_err = r"[\S\s]*An error occurred when interpreting the data for software Bioconductor:"
        expected_err += r"( 'float' object is not subscriptable[\S\s]*"
        expected_err += r"| 'float' object is unsubscriptable"
        expected_err += r"| 'float' object has no attribute '__getitem__'[\S\s]*)"
        self.assertErrorRegex(EasyBuildError, expected_err, parse_easystack, test_easystack)

    def test_easystack_asterisk(self):
        """Test for --easystack <easystack.yaml> when yaml easystack contains asterisk (wildcard)"""
        easybuild.tools.build_log.EXPERIMENTAL = True
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_asterisk.yaml')

        expected_err = "EasyStack specifications of 'binutils' in .*/test_easystack_asterisk.yaml contain asterisk. "
        expected_err += "Wildcard feature is not supported yet."

        self.assertErrorRegex(EasyBuildError, expected_err, parse_easystack, test_easystack)

    def test_easystack_labels(self):
        """Test for --easystack <easystack.yaml> when yaml easystack contains exclude-labels / include-labels"""
        easybuild.tools.build_log.EXPERIMENTAL = True
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easystack = os.path.join(topdir, 'easystacks', 'test_easystack_labels.yaml')

        error_msg = "EasyStack specifications of 'binutils' in .*/test_easystack_labels.yaml contain labels. "
        error_msg += "Labels aren't supported yet."
        self.assertErrorRegex(EasyBuildError, error_msg, parse_easystack, test_easystack)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(EasyStackTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
