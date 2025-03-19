# #
# Copyright 2021-2025 Ghent University
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
Unit tests for functionality in easybuild.tools.output

@author: Kenneth Hoste (Ghent University)
"""
import sys
from unittest import TextTestRunner
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered

import easybuild.tools.output
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, get_output_style, update_build_option
from easybuild.tools.output import PROGRESS_BAR_EXTENSIONS, PROGRESS_BAR_TYPES
from easybuild.tools.output import DummyRich, colorize, get_progress_bar, print_error, show_progress_bars
from easybuild.tools.output import start_progress_bar, status_bar, stop_progress_bar, update_progress_bar, use_rich

try:
    import rich.progress
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False


class OutputTest(EnhancedTestCase):
    """Tests for functions controlling terminal output."""

    def test_status_bar(self):
        """Test status_bar function."""

        # restore default (was disabled in EnhancedTestCase.setUp to avoid messing up test output)
        update_build_option('show_progress_bar', True)

        if HAVE_RICH:
            expected_progress_bar_class = rich.progress.Progress
        else:
            expected_progress_bar_class = DummyRich

        progress_bar = status_bar(ignore_cache=True)
        self.assertIsInstance(progress_bar, expected_progress_bar_class)

        update_build_option('output_style', 'basic')
        progress_bar = status_bar(ignore_cache=True)
        self.assertIsInstance(progress_bar, DummyRich)

        if HAVE_RICH:
            update_build_option('output_style', 'rich')
            progress_bar = status_bar(ignore_cache=True)
            self.assertIsInstance(progress_bar, expected_progress_bar_class)

        update_build_option('show_progress_bar', False)
        progress_bar = status_bar(ignore_cache=True)
        self.assertIsInstance(progress_bar, DummyRich)

    def test_get_output_style(self):
        """Test get_output_style function."""

        self.assertEqual(build_option('output_style'), 'auto')

        for style in (None, 'auto'):
            if style:
                update_build_option('output_style', style)

            if HAVE_RICH:
                self.assertEqual(get_output_style(), 'rich')
            else:
                self.assertEqual(get_output_style(), 'basic')

        test_styles = ['basic', 'no_color']
        if HAVE_RICH:
            test_styles.append('rich')

        for style in test_styles:
            update_build_option('output_style', style)
            self.assertEqual(get_output_style(), style)

        if not HAVE_RICH:
            update_build_option('output_style', 'rich')
            error_pattern = "Can't use 'rich' output style, Rich Python package is not available!"
            self.assertErrorRegex(EasyBuildError, error_pattern, get_output_style)

    def test_use_rich_show_progress_bars(self):
        """Test use_rich and show_progress_bar functions."""

        # restore default configuration to show progress bars (disabled to avoid mangled test output)
        update_build_option('show_progress_bar', True)

        self.assertEqual(build_option('output_style'), 'auto')

        if HAVE_RICH:
            self.assertTrue(use_rich())
            self.assertTrue(show_progress_bars())

            update_build_option('output_style', 'rich')
            self.assertTrue(use_rich())
            self.assertTrue(show_progress_bars())
        else:
            self.assertFalse(use_rich())
            self.assertFalse(show_progress_bars())

        update_build_option('output_style', 'basic')
        self.assertFalse(use_rich())
        self.assertFalse(show_progress_bars())

    def test_colorize(self):
        """
        Test colorize function
        """
        if HAVE_RICH:
            for color in ('green', 'red', 'yellow'):
                self.assertEqual(colorize('test', color), '[bold %s]test[/bold %s]' % (color, color))
        else:
            self.assertEqual(colorize('test', 'green'), '\x1b[0;32mtest\x1b[0m')
            self.assertEqual(colorize('test', 'red'), '\x1b[0;31mtest\x1b[0m')
            self.assertEqual(colorize('test', 'yellow'), '\x1b[1;33mtest\x1b[0m')

        self.assertErrorRegex(EasyBuildError, "Unknown color: nosuchcolor", colorize, 'test', 'nosuchcolor')

    def test_print_error(self):
        """
        Test print_error function
        """
        msg = "This is yellow: " + colorize("a banana", color='yellow')
        self.mock_stderr(True)
        self.mock_stdout(True)
        print_error(msg)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stdout, '')
        if HAVE_RICH:
            # when using Rich, message printed to stderr won't have funny terminal escape characters for the color
            expected = '\n\nThis is yellow: a banana\n\n'
        else:
            expected = '\nThis is yellow: \x1b[1;33ma banana\x1b[0m\n\n'
        self.assertEqual(stderr, expected)

    def test_get_progress_bar(self):
        """
        Test get_progress_bar.
        """
        # restore default configuration to show progress bars (disabled to avoid mangled test output),
        # to ensure we'll get actual Progress instances when Rich is available
        update_build_option('show_progress_bar', True)

        for pbar_type in PROGRESS_BAR_TYPES:
            pbar = get_progress_bar(pbar_type, ignore_cache=True)
            if HAVE_RICH:
                self.assertIsInstance(pbar, rich.progress.Progress)
            else:
                self.assertIsInstance(pbar, DummyRich)

    def test_get_start_update_stop_progress_bar(self):
        """
        Test starting/updating/stopping of progress bars.
        """
        # clear progress bar cache first, this test assumes we start with a clean slate
        easybuild.tools.output._progress_bar_cache.clear()

        # restore default configuration to show progress bars (disabled to avoid mangled test output)
        update_build_option('show_progress_bar', True)

        # stopping a progress bar that never was started results in an error
        error_pattern = "Failed to stop extensions progress bar, since it was never started"
        self.assertErrorRegex(EasyBuildError, error_pattern, stop_progress_bar, PROGRESS_BAR_EXTENSIONS)

        # updating a progress bar that never was started is silently ignored on purpose
        update_progress_bar(PROGRESS_BAR_EXTENSIONS)
        update_progress_bar(PROGRESS_BAR_EXTENSIONS, label="foo")
        update_progress_bar(PROGRESS_BAR_EXTENSIONS, progress_size=100)

        # also test normal cycle: start, update, stop
        start_progress_bar(PROGRESS_BAR_EXTENSIONS, 100)
        update_progress_bar(PROGRESS_BAR_EXTENSIONS)  # single step progress
        update_progress_bar(PROGRESS_BAR_EXTENSIONS, total=50)
        update_progress_bar(PROGRESS_BAR_EXTENSIONS, label="test123", progress_size=5)
        stop_progress_bar(PROGRESS_BAR_EXTENSIONS)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(OutputTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
