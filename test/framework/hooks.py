# #
# Copyright 2017-2018 Ghent University
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
Unit tests for hooks.py

@author: Kenneth Hoste (Ghent University)
"""
import os
import sys
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import write_file
from easybuild.tools.hooks import find_hook, load_hooks, run_hook, verify_hooks


class HooksTest(EnhancedTestCase):
    """Tests for hooks support."""

    def setUp(self):
        """Set up for testing."""
        super(HooksTest, self).setUp()
        self.test_hooks_pymod = os.path.join(self.test_prefix, 'test_hooks.py')
        test_hooks_pymod_txt = '\n'.join([
            'def start_hook():',
            '    print("this is triggered at the very beginning")',
            '',
            'def foo():',
            '    print("running foo helper method")',
            '',
            'def post_configure_hook(self):',
            '    print("this is run after configure step")',
            '    foo()',
            '',
            'def pre_install_hook(self):',
            '    print("this is run before install step")',
        ])
        write_file(self.test_hooks_pymod, test_hooks_pymod_txt)

    def test_load_hooks(self):
        """Test for load_hooks function."""

        self.assertErrorRegex(EasyBuildError, "Specified path .* does not exist.*", load_hooks, '/no/such/hooks.py')

        hooks = load_hooks(self.test_hooks_pymod)

        self.assertEqual(len(hooks), 3)
        self.assertEqual(sorted(hooks.keys()), ['post_configure_hook', 'pre_install_hook', 'start_hook'])
        self.assertTrue(all(callable(h) for h in hooks.values()))

    def test_find_hook(self):
        """Test for find_hook function."""

        hooks = load_hooks(self.test_hooks_pymod)

        post_configure_hook = [hooks[k] for k in hooks if k == 'post_configure_hook'][0]
        pre_install_hook = [hooks[k] for k in hooks if k == 'pre_install_hook'][0]
        start_hook = [hooks[k] for k in hooks if k == 'start_hook'][0]

        self.assertEqual(find_hook('configure', hooks), None)
        self.assertEqual(find_hook('configure', hooks, pre_step_hook=True), None)
        self.assertEqual(find_hook('configure', hooks, post_step_hook=True), post_configure_hook)

        self.assertEqual(find_hook('install', hooks), None)
        self.assertEqual(find_hook('install', hooks, pre_step_hook=True), pre_install_hook)
        self.assertEqual(find_hook('install', hooks, post_step_hook=True), None)

        self.assertEqual(find_hook('build', hooks), None)
        self.assertEqual(find_hook('build', hooks, pre_step_hook=True), None)
        self.assertEqual(find_hook('build', hooks, post_step_hook=True), None)

        self.assertEqual(find_hook('start', hooks), start_hook)
        self.assertEqual(find_hook('start', hooks, pre_step_hook=True), None)
        self.assertEqual(find_hook('start', hooks, post_step_hook=True), None)

    def test_run_hook(self):
        """Test for run_hook function."""

        hooks = load_hooks(self.test_hooks_pymod)

        self.mock_stdout(True)
        self.mock_stderr(True)
        run_hook('start', hooks)
        run_hook('configure', hooks, pre_step_hook=True, args=[None])
        run_hook('configure', hooks, post_step_hook=True, args=[None])
        run_hook('build', hooks, pre_step_hook=True, args=[None])
        run_hook('build', hooks, post_step_hook=True, args=[None])
        run_hook('install', hooks, pre_step_hook=True, args=[None])
        run_hook('install', hooks, post_step_hook=True, args=[None])
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)

        expected_stdout = '\n'.join([
            "== Running start hook...",
            "this is triggered at the very beginning",
            "== Running post-configure hook...",
            "this is run after configure step",
            "running foo helper method",
            "== Running pre-install hook...",
            "this is run before install step",
        ])

        self.assertEqual(stdout.strip(), expected_stdout)
        self.assertEqual(stderr, '')

    def test_verify_hooks(self):
        """Test verify_hooks function."""

        hooks = load_hooks(self.test_hooks_pymod)
        # verify_hooks is actually already called by load_hooks, so this is a bit silly, but fine
        # if no unexpected hooks are found, verify_hooks just logs (no return value)
        self.assertEqual(verify_hooks(hooks), None)

        test_broken_hooks_pymod = os.path.join(self.test_prefix, 'test_broken_hooks.py')
        test_hooks_txt = '\n'.join([
            '',
            'def there_is_no_such_hook():',
            '    pass',
            'def stat_hook(self):',
            '    pass',
            'def post_source_hook(self):',
            '    pass',
            'def install_hook(self):',
            '    pass',
        ])

        write_file(test_broken_hooks_pymod, test_hooks_txt)

        error_msg_pattern = r"Found one or more unknown hooks:\n"
        error_msg_pattern += r"\* stat_hook \(did you mean 'start_hook'\?\)\n"
        error_msg_pattern += r"\* there_is_no_such_hook\n"
        error_msg_pattern += r"\* install_hook \(did you mean 'pre_install_hook', or 'post_install_hook'\?\)\n\n"
        error_msg_pattern += r"Run 'eb --avail-hooks' to get an overview of known hooks"
        self.assertErrorRegex(EasyBuildError, error_msg_pattern, load_hooks, test_broken_hooks_pymod)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(HooksTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
