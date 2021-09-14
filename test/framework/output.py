# #
# Copyright 2021-2021 Ghent University
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

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, get_output_style, update_build_option
from easybuild.tools.output import DummyProgress, create_progress_bar, use_rich

try:
    import rich.progress
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False


class OutputTest(EnhancedTestCase):
    """Tests for functions controlling terminal output."""

    def test_create_progress_bar(self):
        """Test create_progress_bar function."""

        progress_bar = create_progress_bar()
        if HAVE_RICH:
            progress_bar_class = rich.progress.ProgressBar
        else:
            progress_bar_class = DummyProgress
        self.assertTrue(isinstance(progress_bar, progress_bar_class))

        update_build_option('output_style', 'basic')
        self.assertTrue(isinstance(progress_bar, DummyProgress))

        update_build_option('output_style', 'rich')
        self.assertTrue(isinstance(progress_bar, progress_bar_class))

        update_build_option('show_progress_bar', False)
        self.assertTrue(isinstance(progress_bar, DummyProgress))

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

    def test_use_rich(self):
        """Test use_rich function."""
        try:
            import rich  # noqa
            self.assertTrue(use_rich())
        except ImportError:
            self.assertFalse(use_rich())


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(OutputTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
