# #
# Copyright 2017-2024 Ghent University
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
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

import easybuild.tools.hooks  # so we can reset cached hooks
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import update_build_option
from easybuild.tools.filetools import remove_file, write_file
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
            'def parse_hook(ec):',
            '   print("Parse hook with argument %s" % ec)',
            '',
            'def pre_build_and_install_loop_hook(ecs):',
            '    print("About to start looping for %d easyconfigs!" % len(ecs))',
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
            '',
            'def pre_single_extension_hook(ext):',
            '    print("this is run before installing an extension")',
            '',
            'def pre_run_shell_cmd_hook(cmd, interactive=False):',
            '    if interactive:',
            '        print("this is run before running interactive command \'%s\'" % cmd)',
            '    else:',
            '        print("this is run before running command \'%s\'" % cmd)',
            '        if cmd == "make install":',
            '            return "sudo " + cmd',
            '',
            'def fail_hook(err):',
            '    print("EasyBuild FAIL: %s" % err)',
        ])
        write_file(self.test_hooks_pymod, test_hooks_pymod_txt)

    def tearDown(self):
        """Cleanup."""

        # reset cached hooks
        easybuild.tools.hooks._cached_hooks.clear()

        super(HooksTest, self).tearDown()

    def test_load_hooks(self):
        """Test for load_hooks function."""

        self.assertErrorRegex(EasyBuildError, "Specified path .* does not exist.*", load_hooks, '/no/such/hooks.py')

        hooks = load_hooks(self.test_hooks_pymod)

        self.assertEqual(len(hooks), 8)
        expected = [
            'fail_hook',
            'parse_hook',
            'post_configure_hook',
            'pre_build_and_install_loop_hook',
            'pre_install_hook',
            'pre_run_shell_cmd_hook',
            'pre_single_extension_hook',
            'start_hook',
        ]
        self.assertEqual(sorted(hooks.keys()), expected)
        self.assertTrue(all(callable(h) for h in hooks.values()))

        # test caching of hooks
        remove_file(self.test_hooks_pymod)
        cached_hooks = load_hooks(self.test_hooks_pymod)
        self.assertIs(cached_hooks, hooks)

        # hooks file can be empty
        empty_hooks_path = os.path.join(self.test_prefix, 'empty_hooks.py')
        write_file(empty_hooks_path, '')
        empty_hooks = load_hooks(empty_hooks_path)
        self.assertEqual(empty_hooks, {})

        # loading another hooks file doesn't affect cached hooks
        prev_hooks = load_hooks(self.test_hooks_pymod)
        self.assertIs(prev_hooks, hooks)

        # clearing cached hooks results in error because hooks file is not found
        easybuild.tools.hooks._cached_hooks = {}
        self.assertErrorRegex(EasyBuildError, "Specified path .* does not exist.*", load_hooks, self.test_hooks_pymod)

    def test_find_hook(self):
        """Test for find_hook function."""

        hooks = load_hooks(self.test_hooks_pymod)

        post_configure_hook = [hooks[k] for k in hooks if k == 'post_configure_hook'][0]
        pre_install_hook = [hooks[k] for k in hooks if k == 'pre_install_hook'][0]
        pre_single_extension_hook = [hooks[k] for k in hooks if k == 'pre_single_extension_hook'][0]
        start_hook = [hooks[k] for k in hooks if k == 'start_hook'][0]
        pre_run_shell_cmd_hook = [hooks[k] for k in hooks if k == 'pre_run_shell_cmd_hook'][0]
        fail_hook = [hooks[k] for k in hooks if k == 'fail_hook'][0]
        pre_build_and_install_loop_hook = [hooks[k] for k in hooks if k == 'pre_build_and_install_loop_hook'][0]

        self.assertEqual(find_hook('configure', hooks), None)
        self.assertEqual(find_hook('configure', hooks, pre_step_hook=True), None)
        self.assertEqual(find_hook('configure', hooks, post_step_hook=True), post_configure_hook)

        self.assertEqual(find_hook('install', hooks), None)
        self.assertEqual(find_hook('install', hooks, pre_step_hook=True), pre_install_hook)
        self.assertEqual(find_hook('install', hooks, post_step_hook=True), None)

        self.assertEqual(find_hook('single_extension', hooks), None)
        self.assertEqual(find_hook('single_extension', hooks, pre_step_hook=True), pre_single_extension_hook)
        self.assertEqual(find_hook('single_extension', hooks, post_step_hook=True), None)

        self.assertEqual(find_hook('extensions', hooks), None)
        self.assertEqual(find_hook('extensions', hooks, pre_step_hook=True), None)
        self.assertEqual(find_hook('extensions', hooks, post_step_hook=True), None)

        self.assertEqual(find_hook('build', hooks), None)
        self.assertEqual(find_hook('build', hooks, pre_step_hook=True), None)
        self.assertEqual(find_hook('build', hooks, post_step_hook=True), None)

        self.assertEqual(find_hook('start', hooks), start_hook)
        self.assertEqual(find_hook('start', hooks, pre_step_hook=True), None)
        self.assertEqual(find_hook('start', hooks, post_step_hook=True), None)

        self.assertEqual(find_hook('run_shell_cmd', hooks), None)
        self.assertEqual(find_hook('run_shell_cmd', hooks, pre_step_hook=True), pre_run_shell_cmd_hook)
        self.assertEqual(find_hook('run_shell_cmd', hooks, post_step_hook=True), None)

        self.assertEqual(find_hook('fail', hooks), fail_hook)
        self.assertEqual(find_hook('fail', hooks, pre_step_hook=True), None)
        self.assertEqual(find_hook('fail', hooks, post_step_hook=True), None)

        hook_name = 'build_and_install_loop'
        self.assertEqual(find_hook(hook_name, hooks), None)
        self.assertEqual(find_hook(hook_name, hooks, pre_step_hook=True), pre_build_and_install_loop_hook)
        self.assertEqual(find_hook(hook_name, hooks, post_step_hook=True), None)

    def test_run_hook(self):
        """Test for run_hook function."""

        hooks = load_hooks(self.test_hooks_pymod)

        init_config(build_options={'debug': True})

        def run_hooks():
            self.mock_stdout(True)
            self.mock_stderr(True)
            run_hook('start', hooks)
            run_hook('parse', hooks, args=['<EasyConfig instance>'], msg="Running parse hook for example.eb...")
            run_hook('build_and_install_loop', hooks, args=[['ec1', 'ec2']], pre_step_hook=True)
            run_hook('configure', hooks, pre_step_hook=True, args=[None])
            run_hook('run_shell_cmd', hooks, pre_step_hook=True, args=["configure.sh"], kwargs={'interactive': True})
            run_hook('configure', hooks, post_step_hook=True, args=[None])
            run_hook('build', hooks, pre_step_hook=True, args=[None])
            run_hook('run_shell_cmd', hooks, pre_step_hook=True, args=["make -j 3"])
            run_hook('build', hooks, post_step_hook=True, args=[None])
            run_hook('install', hooks, pre_step_hook=True, args=[None])
            res = run_hook('run_shell_cmd', hooks, pre_step_hook=True, args=["make install"], kwargs={})
            self.assertEqual(res, "sudo make install")
            run_hook('install', hooks, post_step_hook=True, args=[None])
            run_hook('extensions', hooks, pre_step_hook=True, args=[None])
            for _ in range(3):
                run_hook('single_extension', hooks, pre_step_hook=True, args=[None])
                run_hook('single_extension', hooks, post_step_hook=True, args=[None])
            run_hook('extensions', hooks, post_step_hook=True, args=[None])
            run_hook('fail', hooks, args=[EasyBuildError('oops')])
            stdout = self.get_stdout()
            stderr = self.get_stderr()
            self.mock_stdout(False)
            self.mock_stderr(False)

            return stdout, stderr

        stdout, stderr = run_hooks()

        expected_stdout_lines = [
            "== Running start hook...",
            "this is triggered at the very beginning",
            "== Running parse hook for example.eb...",
            "Parse hook with argument <EasyConfig instance>",
            "== Running pre-build_and_install_loop hook...",
            "About to start looping for 2 easyconfigs!",
            "== Running pre-run_shell_cmd hook...",
            "this is run before running interactive command 'configure.sh'",
            "== Running post-configure hook...",
            "this is run after configure step",
            "running foo helper method",
            "== Running pre-run_shell_cmd hook...",
            "this is run before running command 'make -j 3'",
            "== Running pre-install hook...",
            "this is run before install step",
            "== Running pre-run_shell_cmd hook...",
            "this is run before running command 'make install'",
            "== Running pre-single_extension hook...",
            "this is run before installing an extension",
            "== Running pre-single_extension hook...",
            "this is run before installing an extension",
            "== Running pre-single_extension hook...",
            "this is run before installing an extension",
            "== Running fail hook...",
            "EasyBuild FAIL: 'oops'",
        ]
        expected_stdout = '\n'.join(expected_stdout_lines)

        self.assertEqual(stdout.strip(), expected_stdout)
        self.assertEqual(stderr, '')

        # test silencing of hook trigger
        update_build_option('silence_hook_trigger', True)
        stdout, stderr = run_hooks()

        expected_stdout = '\n'.join(x for x in expected_stdout_lines if not x.startswith('== Running'))

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
        error_msg_pattern += r"\* install_hook \(did you mean 'pre_install_hook', or 'post_install_hook'\?\)\n"
        error_msg_pattern += r"\* stat_hook \(did you mean 'start_hook'\?\)\n"
        error_msg_pattern += r"\* there_is_no_such_hook\n\n"
        error_msg_pattern += r"Run 'eb --avail-hooks' to get an overview of known hooks"
        self.assertErrorRegex(EasyBuildError, error_msg_pattern, load_hooks, test_broken_hooks_pymod)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(HooksTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
