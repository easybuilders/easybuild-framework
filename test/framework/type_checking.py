# #
# Copyright 2015-2015 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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
Unit tests for easyconfig/types.py

@author: Kenneth Hoste (Ghent University)
"""
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main

from easybuild.tools.build_log import EasyBuildError
from easybuild.framework.easyconfig.types import check_type_of_param_value, convert_value_type


class TypeCheckingTest(EnhancedTestCase):
    """Tests for value type checking of easyconfig parameters."""

    def test_check_type_of_param_value(self):
        """Test check_type_of_param_value function."""
        # check selected values that should be strings
        for key in ['name', 'version']:
            self.assertEqual(check_type_of_param_value(key, 'foo'), (True, 'foo'))
            for not_a_string in [100, 1.5, ('bar',), ['baz'], None]:
                self.assertEqual(check_type_of_param_value(key, not_a_string), (False, None))
            # value doesn't matter, only type does
            self.assertEqual(check_type_of_param_value(key, ''), (True, ''))

        # parameters with no type specification always pass the check
        key = 'nosucheasyconfigparametereverhopefully'
        for val in ['foo', 100, 1.5, ('bar',), ['baz'], '', None]:
            self.assertEqual(check_type_of_param_value(key, val), (True, val))

        # check use of auto_convert
        self.assertEqual(check_type_of_param_value('version', 1.5), (False, None))
        self.assertEqual(check_type_of_param_value('version', 1.5, auto_convert=True), (True, '1.5'))

    def test_convert_value_type(self):
        """Test convert_value_type function."""
        # to string
        self.assertEqual(convert_value_type(100, basestring), '100')
        self.assertEqual(convert_value_type((100,), str), '(100,)')
        self.assertEqual(convert_value_type([100], basestring), '[100]')
        self.assertEqual(convert_value_type(None, str), 'None')

        # to int/float
        self.assertEqual(convert_value_type('100', int), 100)
        self.assertEqual(convert_value_type('0', int), 0)
        self.assertEqual(convert_value_type('-123', int), -123)
        self.assertEqual(convert_value_type('1.6', float), 1.6)
        self.assertEqual(convert_value_type('5', float), 5.0)
        self.assertErrorRegex(EasyBuildError, "Converting type of .* failed", convert_value_type, '', int)
        # 1.6 can't be parsed as an int (yields "invalid literal for int() with base 10" error)
        self.assertErrorRegex(EasyBuildError, "Converting type of .* failed", convert_value_type, '1.6', int)

        # idempotency
        self.assertEqual(convert_value_type('foo', basestring), 'foo')
        self.assertEqual(convert_value_type('foo', str), 'foo')
        self.assertEqual(convert_value_type(100, int), 100)
        self.assertEqual(convert_value_type(1.6, float), 1.6)

        # no conversion function available for specific type
        class Foo():
            pass
        self.assertErrorRegex(EasyBuildError, "No conversion function available", convert_value_type, None, Foo)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(TypeCheckingTest)


if __name__ == '__main__':
    main()
