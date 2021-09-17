##
# Copyright 2012-2021 Ghent University
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


def suite():
    """ return all the tests in this file """
    return TestLoaderFiltered().loadTestsFromTestCase(UtilitiesTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
