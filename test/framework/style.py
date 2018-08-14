##
# Copyright 2016-2018 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
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
##
"""
Style tests for easyconfig files.

:author: Ward Poelmans (Ghent University)
"""

import glob
import os
import sys
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner
from vsc.utils import fancylogger
from easybuild.framework.easyconfig.style import _eb_check_trailing_whitespace, _eb_check_order_grouping_params
from easybuild.framework.easyconfig.style import check_easyconfigs_style

try:
    import pycodestyle
except ImportError:
    try:
        import pep8
    except ImportError:
        pass


class StyleTest(EnhancedTestCase):
    log = fancylogger.getLogger("StyleTest", fname=False)

    def test_style_conformance(self):
        """Check the easyconfigs for style"""
        if not ('pycodestyle' in sys.modules or 'pep8' in sys.modules):
            print "Skipping style checks (no pycodestyle or pep8 available)"
            return

        # all available easyconfig files
        test_easyconfigs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        specs = glob.glob('%s/*.eb' % test_easyconfigs_path)
        specs = sorted(specs)

        result = check_easyconfigs_style(specs)

        self.assertEqual(result, 0, "No code style errors (and/or warnings) found.")

    def test_check_trailing_whitespace(self):
        """Test for trailing whitespace check."""
        if not ('pycodestyle' in sys.modules or 'pep8' in sys.modules):
            print "Skipping trailing whitespace checks (no pycodestyle or pep8 available)"
            return

        lines = [
            "name = 'foo'",  # no trailing whitespace
            "version = '1.2.3'  ",  # trailing whitespace
            "   ",  # blank line with whitespace included
            '''description = """start of long description, ''',  # trailing whitespace, but allowed in description
            ''' continuation of long description ''',  # trailing whitespace, but allowed in continued description
            ''' end of long description"""''',
            "moduleclass = 'tools'   ",  # trailing whitespace
            '',
        ]
        line_numbers = range(1, len(lines) + 1)
        state = {}
        test_cases = [
            None,
            (17, "W299 trailing whitespace"),
            (0, "W293 blank line contains whitespace"),
            None,
            None,
            None,
            (21, "W299 trailing whitespace"),
        ]

        for (line, line_number, expected_result) in zip(lines, line_numbers, test_cases):
            result = _eb_check_trailing_whitespace(line, lines, line_number, state)
            self.assertEqual(result, expected_result)

    def test_check_order_grouping_params_head(self):
        """Test for check on order/grouping of parameters in head of easyconfig file."""

        def run_test(fail_idx):
            """Helper function to run the actual test"""
            state = {}
            for idx in range(total_lines):
                # error state should be detected at specified line
                if idx == fail_idx:
                    expected = (0, "W001 " + ', '.join(expected_errors))
                else:
                    expected = None

                res = _eb_check_order_grouping_params(lines[idx], lines, idx+1, total_lines, state)
                self.assertEqual(res, expected)


        # easyblock shouldn't be in same group as name/version
        # name/version are out of order
        keys = ['easyblock', 'version', 'name']
        lines = ["%s = '...'" % k for k in keys]
        total_lines = len(lines)

        expected_errors = [
            "easyblock parameter definition is not isolated",
            "name/version parameter definitions are not isolated",
            "name/version parameter definitions are out of order",
        ]

        # failure should occur at index 2 (3rd line)
        run_test(2)

        # error state detected as soon as group ends, not necessary at end of file
        lines.append('')
        total_lines += 1

        # failure should still occur at index 2 (3rd line)
        run_test(2)

        # switch name/version lines, inject empty line after easyblock line
        lines[1], lines[2] = lines[2], lines[1]
        lines.insert(1, '')
        total_lines += 1

        # no failures
        run_test(-1)

        # add homepage/description out of order
        lines.extend([
            '',
            'description = """..."""',
            'homepage = "..."',
        ])

        # add unexpected parameter definition in head of easyconfig
        lines.append("moduleclass = '...'")
        total_lines = len(lines)

        expected_errors = [
            "homepage/description parameter definitions are not isolated",
            "homepage/description parameter definitions are out of order",
            "found unexpected parameter definitions in head of easyconfig: moduleclass",
        ]
        run_test(8)


def suite():
    """Return all style tests for easyconfigs."""
    return TestLoaderFiltered().loadTestsFromTestCase(StyleTest, sys.argv[1:])


if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
