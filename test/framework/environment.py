# #
# Copyright 2015-2016 Ghent University
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
Unit tests for environment.py

@author: Kenneth Hoste (Ghent University)
"""
import os
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader, main

import easybuild.tools.environment as env


class EnvironmentTest(EnhancedTestCase):
    """ Testcase for run module """

    def test_setvar(self):
        """Test setvar function."""
        self.mock_stdout(True)
        env.setvar('FOO', 'bar')
        txt = self.get_stdout()
        self.mock_stdout(False)
        self.assertEqual(os.getenv('FOO'), 'bar')
        self.assertEqual(os.environ['FOO'], 'bar')
        # no printing if dry run is not enabled
        self.assertEqual(txt, '')

        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)
        self.mock_stdout(True)
        env.setvar('FOO', 'foobaz')
        txt = self.get_stdout()
        self.mock_stdout(False)
        self.assertEqual(os.getenv('FOO'), 'foobaz')
        self.assertEqual(os.environ['FOO'], 'foobaz')
        self.assertEqual(txt, "  export FOO=\"foobaz\"\n")

        # disabling verbose
        self.mock_stdout(True)
        env.setvar('FOO', 'barfoo', verbose=False)
        txt = self.get_stdout()
        self.mock_stdout(False)
        self.assertEqual(os.getenv('FOO'), 'barfoo')
        self.assertEqual(os.environ['FOO'], 'barfoo')
        self.assertEqual(txt, '')


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(EnvironmentTest)

if __name__ == '__main__':
    main()
