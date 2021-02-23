# #
# Copyright 2015-2021 Ghent University
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
Unit tests for environment.py

@author: Kenneth Hoste (Ghent University)
"""
import os
import sys
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

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
        self.assertEqual(txt, "  export FOO='foobaz'\n")

        # disabling verbose
        self.mock_stdout(True)
        env.setvar('FOO', 'barfoo', verbose=False)
        txt = self.get_stdout()
        self.mock_stdout(False)
        self.assertEqual(os.getenv('FOO'), 'barfoo')
        self.assertEqual(os.environ['FOO'], 'barfoo')
        self.assertEqual(txt, '')

    def test_modify_env(self):
        """Test for modify_env function."""

        old_env_vars = {
            'TEST_ENV_VAR_TO_UNSET1': 'foobar',
            'TEST_ENV_VAR_TO_UNSET2': 'value does not matter',
            'TEST_COMMON_ENV_VAR_CHANGED': 'old_value',
            'TEST_COMMON_ENV_VAR_SAME_VALUE': 'this_value_stays',
        }
        new_env_vars = {
            'TEST_COMMON_ENV_VAR_CHANGED': 'new_value',
            'TEST_NEW_ENV_VAR1': '1',
            'TEST_NEW_ENV_VAR2': 'two 2 two',
            'TEST_COMMON_ENV_VAR_SAME_VALUE': 'this_value_stays',
        }

        # prepare test environment first:
        # keys in new_env should not be set yet, keys in old_env are expected to be set
        for key in new_env_vars:
            if key in os.environ:
                del os.environ[key]
        for key in old_env_vars:
            os.environ[key] = old_env_vars[key]

        env.modify_env(os.environ, new_env_vars)

        self.assertEqual(os.environ.get('TEST_ENV_VAR_TO_UNSET1'), None)
        self.assertEqual(os.environ.get('TEST_ENV_VAR_TO_UNSET2'), None)
        self.assertEqual(os.environ.get('TEST_COMMON_ENV_VAR_CHANGED'), 'new_value')
        self.assertEqual(os.environ.get('TEST_COMMON_ENV_VAR_SAME_VALUE'), 'this_value_stays')
        self.assertEqual(os.environ.get('TEST_NEW_ENV_VAR1'), '1')
        self.assertEqual(os.environ.get('TEST_NEW_ENV_VAR2'), 'two 2 two')

        # extreme test case: empty entire environment (original env is restored for next tests)
        env.modify_env(os.environ, {})

    def test_unset_env_vars(self):
        """Test unset_env_vars function."""

        os.environ['TEST_ENV_VAR'] = 'test123'
        # it's fair to assume $HOME will always be set
        home = os.getenv('HOME')
        self.assertTrue(home)

        key_not_set = 'NO_SUCH_ENV_VAR'
        if key_not_set in os.environ:
            del os.environ[key_not_set]

        res = env.unset_env_vars(['HOME', 'NO_SUCH_ENV_VAR', 'TEST_ENV_VAR'])

        self.assertFalse('HOME' in os.environ)
        self.assertFalse('NO_SUCH_ENV_VAR' in os.environ)
        self.assertFalse('TEST_ENV_VAR' in os.environ)

        expected = {
            'HOME': home,
            'TEST_ENV_VAR': 'test123',
        }
        self.assertEqual(res, expected)

    def test_sanitize_env(self):
        """Test sanitize_env function."""

        # define $*PATH variable that include empty entries, those should get filtered out
        os.environ['PATH'] = '/bar::/foo:' + self.test_prefix  # middle empty entry
        os.environ['LD_LIBRARY_PATH'] = '/apps/slurm/default/lib:/usr/lib:'  # trailing empty entry
        os.environ['LIBRARY_PATH'] = self.test_prefix + ':' + os.environ['HOME']  # no empty entries here
        os.environ['CPATH'] = ':' + self.test_prefix  # leading empty entry
        os.environ['LD_PRELOAD'] = ':::'  # only empty entries (should get unset!)

        # define $PYTHON* environment variables, these should be unset by sanitize_env
        os.environ['PYTHONNOUSERSITE'] = '1'
        os.environ['PYTHONPATH'] = self.test_prefix
        os.environ['PYTHONOPTIMIZE'] = '1'

        env.sanitize_env()

        self.assertFalse(any(x for x in os.environ.keys() if x.startswith('PYTHON')))

        expected = {
            'CPATH': self.test_prefix,
            'LD_LIBRARY_PATH': '/apps/slurm/default/lib:/usr/lib',
            'LIBRARY_PATH': self.test_prefix + ':' + os.environ['HOME'],
            'PATH': '/bar:/foo:' + self.test_prefix,
        }
        for key in sorted(expected):
            self.assertEqual(os.getenv(key), expected[key])
            self.assertEqual(os.environ[key], expected[key])

        self.assertEqual(os.getenv('LD_PRELOAD'), None)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(EnvironmentTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
