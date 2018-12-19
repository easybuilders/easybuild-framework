# #
# Copyright 2018-2018 Ghent University
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
Unit tests for using EasyBuild as a library.

@author: Kenneth Hoste (Ghent University)
"""
import os
import shutil
import sys
import tempfile
from unittest import TextTestRunner

from test.framework.utilities import TestLoaderFiltered

# deliberately *not* using EnhancedTestCase from test.framework.utilities to avoid automatic configuration via setUp
from vsc.utils.testing import EnhancedTestCase

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import BuildOptions
from easybuild.tools.options import set_up_configuration
from easybuild.tools.filetools import mkdir
from easybuild.tools.modules import modules_tool
from easybuild.tools.run import run_cmd


class EasyBuildLibTest(EnhancedTestCase):
    """Test cases for using EasyBuild as a library."""

    def setUp(self):
        """Prepare for running test."""
        super(EasyBuildLibTest, self).setUp()

        # make sure BuildOptions instance is re-created
        del BuildOptions._instances[BuildOptions]

        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        """Cleanup after running test."""
        super(EasyBuildLibTest, self).tearDown()

        shutil.rmtree(self.tmpdir)

    def configure(self):
        """Utility function to set up EasyBuild configuration."""

        # wipe BuildOption singleton instance, so it gets re-created when set_up_configuration is called
        del BuildOptions._instances[BuildOptions]

        self.assertFalse(BuildOptions in BuildOptions._instances)
        set_up_configuration(silent=True)
        self.assertTrue(BuildOptions in BuildOptions._instances)

    def test_run_cmd(self):
        """Test use of run_cmd function in the context of using EasyBuild framework as a library."""

        error_pattern = "Undefined build option: .*"
        error_pattern += " Make sure you have set up the EasyBuild configuration using set_up_configuration\(\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, run_cmd, "echo hello")

        self.configure()

        # run_cmd works fine if set_up_configuration was called first
        (out, ec) = run_cmd("echo hello")
        self.assertEqual(ec, 0)
        self.assertEqual(out, 'hello\n')

    def test_mkdir(self):
        """Test use of run_cmd function in the context of using EasyBuild framework as a library."""

        test_dir = os.path.join(self.tmpdir, 'test123')

        error_pattern = "Undefined build option: .*"
        error_pattern += " Make sure you have set up the EasyBuild configuration using set_up_configuration\(\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, mkdir, test_dir)

        self.configure()

        # mkdir works fine if set_up_configuration was called first
        self.assertFalse(os.path.exists(test_dir))
        mkdir(test_dir)
        self.assertTrue(os.path.exists(test_dir))

    def test_modules_tool(self):
        """Test use of modules_tool function in the context of using EasyBuild framework as a library."""

        error_pattern = "Undefined build option: .*"
        error_pattern += " Make sure you have set up the EasyBuild configuration using set_up_configuration\(\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, modules_tool)

        self.configure()

        test_mods_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modules')

        modtool = modules_tool()
        modtool.use(test_mods_path)
        self.assertTrue('GCC/6.4.0-2.28' in modtool.available())
        modtool.load(['GCC/6.4.0-2.28'])
        self.assertEqual(modtool.list(), [{'default': None, 'mod_name': 'GCC/6.4.0-2.28'}])


def suite():
    return TestLoaderFiltered().loadTestsFromTestCase(EasyBuildLibTest, sys.argv[1:])


if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
