##
# Copyright 2012-2023 Ghent University
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
##
"""
Unit tests for utilities.py

@author: Jens Timmerman (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Alexander Grund (TU Dresden)
"""
import os
import random
import sys
import tempfile
from datetime import datetime
from unittest import TextTestRunner

from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from easybuild.tools import LooseVersion
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.utilities import time2str, natural_keys


class UtilitiesTest(EnhancedTestCase):
    """Class for utilities testcases """

    def setUp(self):
        """ setup """
        super(UtilitiesTest, self).setUp()

        self.test_tmp_logdir = tempfile.mkdtemp()
        os.environ['EASYBUILD_TMP_LOGDIR'] = self.test_tmp_logdir

    def test_time2str(self):
        """Test time2str function."""

        start = datetime(2019, 7, 30, 5, 14, 23)

        test_cases = [
            (start, "0 secs"),
            (datetime(2019, 7, 30, 5, 14, 37), "14 secs"),
            (datetime(2019, 7, 30, 5, 15, 22), "59 secs"),
            (datetime(2019, 7, 30, 5, 15, 23), "1 min 0 secs"),
            (datetime(2019, 7, 30, 5, 16, 22), "1 min 59 secs"),
            (datetime(2019, 7, 30, 5, 16, 24), "2 mins 1 sec"),
            (datetime(2019, 7, 30, 5, 37, 26), "23 mins 3 secs"),
            (datetime(2019, 7, 30, 6, 14, 22), "59 mins 59 secs"),
            (datetime(2019, 7, 30, 6, 14, 23), "1 hour 0 mins 0 secs"),
            (datetime(2019, 7, 30, 6, 49, 14), "1 hour 34 mins 51 secs"),
            (datetime(2019, 7, 30, 7, 14, 23), "2 hours 0 mins 0 secs"),
            (datetime(2019, 7, 30, 8, 35, 59), "3 hours 21 mins 36 secs"),
            (datetime(2019, 7, 30, 16, 29, 24), "11 hours 15 mins 1 sec"),
            (datetime(2019, 7, 31, 5, 14, 22), "23 hours 59 mins 59 secs"),
            (datetime(2019, 7, 31, 5, 14, 23), "24 hours 0 mins 0 secs"),
            (datetime(2019, 7, 31, 5, 15, 24), "24 hours 1 min 1 sec"),
            (datetime(2019, 8, 5, 20, 39, 44), "159 hours 25 mins 21 secs"),
        ]
        for end, expected in test_cases:
            self.assertEqual(time2str(end - start), expected)

        error_pattern = "Incorrect value type provided to time2str, should be datetime.timedelta: <.* 'int'>"
        self.assertErrorRegex(EasyBuildError, error_pattern, time2str, 123)

    def test_natural_keys(self):
        """Test the natural_keys function"""
        sorted_items = [
            'ACoolSw-1.0',
            'ACoolSw-2.1',
            'ACoolSw-11.0',
            'ACoolSw-23.0',
            'ACoolSw-30.0',
            'ACoolSw-30.1',
            'BigNumber-1234567890',
            'BigNumber-1234567891',
            'NoNumbers',
            'VeryLastEntry-10'
        ]
        shuffled_items = sorted_items[:]
        random.shuffle(shuffled_items)
        shuffled_items.sort(key=natural_keys)
        self.assertEqual(shuffled_items, sorted_items)

    def test_LooseVersion(self):
        """Test ordering of LooseVersion instances"""
        # Simply check for the 6 comparison operators
        self.assertEqual(LooseVersion('8.02'), LooseVersion('8.02'))
        self.assertGreater(LooseVersion('2.02'), LooseVersion('2.01'))
        self.assertGreaterEqual(LooseVersion('2.02'), LooseVersion('2.01'))
        self.assertNotEqual(LooseVersion('2.02'), LooseVersion('2.01'))
        self.assertLess(LooseVersion('1.02'), LooseVersion('2.01'))
        self.assertLessEqual(LooseVersion('1.02'), LooseVersion('2.01'))
        # Same as above but either side is a string
        self.assertEqual('8.02', LooseVersion('8.02'))
        self.assertEqual(LooseVersion('8.02'), '8.02')
        self.assertGreater('2.02', LooseVersion('2.01'))
        self.assertGreater(LooseVersion('2.02'), '2.01')
        self.assertGreaterEqual('2.02', LooseVersion('2.01'))
        self.assertGreaterEqual(LooseVersion('2.02'), '2.01')
        self.assertNotEqual('2.02', LooseVersion('2.01'))
        self.assertNotEqual(LooseVersion('2.02'), '2.01')
        self.assertLess('1.02', LooseVersion('2.01'))
        self.assertLess(LooseVersion('1.02'), '2.01')
        self.assertLessEqual('1.02', LooseVersion('2.01'))
        self.assertLessEqual(LooseVersion('1.02'), '2.01')

        # Some comparisons we might do: Full version on left hand side, shorter on right
        self.assertGreater(LooseVersion('2.1.5'), LooseVersion('2.1'))
        self.assertGreater(LooseVersion('2.1.3'), LooseVersion('2'))
        self.assertGreaterEqual(LooseVersion('2.1.0'), LooseVersion('2.1'))
        self.assertLess(LooseVersion('2.1.5'), LooseVersion('2.2'))
        self.assertLess(LooseVersion('2.1.3'), LooseVersion('3'))
        self.assertLessEqual(LooseVersion('2.1.0'), LooseVersion('2.2'))
        # Careful here: 1.0 > 1 !!!
        self.assertGreater(LooseVersion('1.0'), LooseVersion('1'))
        self.assertLess(LooseVersion('1'), LooseVersion('1.0'))

        # The following test is taken from Python disutils tests
        # licensed under the Python Software Foundation License Version 2
        versions = (('1.5.1', '1.5.2b2', -1),
                    ('161', '3.10a', 1),
                    ('8.02', '8.02', 0),
                    ('3.4j', '1996.07.12', -1),
                    ('3.2.pl0', '3.1.1.6', 1),
                    ('2g6', '11g', -1),
                    ('0.960923', '2.2beta29', -1),
                    ('1.13++', '5.5.kw', -1),
                    # Added from https://bugs.python.org/issue14894
                    ('a.12.b.c', 'a.b.3', -1),
                    ('1.0', '1', 1),
                    ('1', '1.0', -1))

        for v1, v2, wanted in versions:
            res = LooseVersion(v1)._cmp(LooseVersion(v2))
            self.assertEqual(res, wanted,
                             'cmp(%s, %s) should be %s, got %s' %
                             (v1, v2, wanted, res))
            # vstring is the unparsed version
            self.assertEqual(LooseVersion(v1).vstring, v1)

        # Default/None LooseVersion cannot be compared
        none_version = LooseVersion(None)
        self.assertErrorRegex(TypeError, '', lambda c: none_version == LooseVersion('1'))
        self.assertErrorRegex(TypeError, '', lambda c: none_version < LooseVersion(''))
        self.assertErrorRegex(TypeError, '', lambda c: none_version < LooseVersion('0'))
        self.assertErrorRegex(TypeError, '', lambda c: none_version > LooseVersion(''))
        self.assertErrorRegex(TypeError, '', lambda c: none_version > LooseVersion('0'))
        self.assertErrorRegex(TypeError, '', lambda c: none_version == '1')
        self.assertErrorRegex(TypeError, '', lambda c: none_version != '1')
        self.assertErrorRegex(TypeError, '', lambda c: none_version < '1')
        self.assertErrorRegex(TypeError, '', lambda c: none_version > '1')
        # You can check for None .version or .vstring
        self.assertIsNone(none_version.version)
        self.assertIsNone(none_version.vstring)
        # version is the parsed version
        self.assertEqual(LooseVersion('2.5').version, [2, 5])
        self.assertEqual(LooseVersion('2.a.5').version, [2, 'a', 5])
        self.assertEqual(LooseVersion('2.a').version, [2, 'a'])
        self.assertEqual(LooseVersion('2.a5').version, [2, 'a', 5])


def suite():
    """ return all the tests in this file """
    return TestLoaderFiltered().loadTestsFromTestCase(UtilitiesTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
