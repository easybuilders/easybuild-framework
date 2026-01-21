# Copyright 2024 Ghent University
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
#

"""
Easyconfig module that provides tools for extensions for EasyBuild easyconfigs.

Authors:

* Victor Machado (Do IT Now)
* Danilo Gonzalez (Do IT Now)
"""

from io import StringIO
import os
import sys
from unittest import TextTestRunner
from unittest.mock import patch
from easybuild.framework.easyconfig.exttools.ext_tools import ExtTools
from easybuild.framework.easyconfig.parser import EasyConfigParser
from easybuild.tools.build_log import EasyBuildError
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered

TESTDIRBASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')


class ExttoolsTest(EnhancedTestCase):
    """ Baseclass for exttols testcases """

    def setUp(self):
        """ setup """
        super(ExttoolsTest, self).setUp()

        self.ec_path = os.path.join(TESTDIRBASE, 'test_ecs', 'r', 'R',
                                    'R-4.3.3-gfbf-2023b_reduced_1_ext.eb')

        self.ec_parsed = EasyConfigParser(self.ec_path)
        self.ec_dict = self.ec_parsed.get_config_dict()

    def test_no_init_param(self):
        """Test that ExtTools class raises an exception when no argument is provided"""

        self.assertRaises(TypeError, ExtTools)

    def test_wrong_init_param(self):
        """Test that ExtTools class raises an exception when no argument is provided"""

        self.assertRaises(EasyBuildError, ExtTools, "wrong init param")

    def test_exttools_update_exts_list(self):
        """Test that ExtTools updates the extensions list without errors."""

        try:
            exttools = ExtTools(self.ec_path)
        except Exception as e:
            self.fail(f"ExtTools initialization failed with exception: {e}")

        # check that exttools class instance is created
        self.assertIsNotNone(exttools)

        # check that extension list is not empty
        self.assertIsNotNone(exttools.exts_list)

        with patch('sys.stdout', new=StringIO()):
            try:
                exttools.update_exts_list()
            except Exception as e:
                self.fail(f"ExtTools initialization failed with exception: {e}")

        # check that updated extension list is not empty
        self.assertIsNotNone(exttools.exts_list_updated)

        # check that updated extension list is the same length as the original extension list
        self.assertEqual(len(exttools.exts_list), len(exttools.exts_list_updated))

        # check first extension parameters

        # check that the name is the same in both lists
        self.assertEqual(exttools.exts_list[0][0], exttools.exts_list_updated[0][0])

        # check that the version is different in both lists, as the version is updated
        self.assertNotEqual(exttools.exts_list[0][1], exttools.exts_list_updated[0][1])


def suite():
    """ return all the tests in this file """
    return TestLoaderFiltered().loadTestsFromTestCase(ExttoolsTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
