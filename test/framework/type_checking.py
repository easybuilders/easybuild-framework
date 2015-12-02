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
from easybuild.framework.easyconfig.types import NAME_VERSION_DICT, check_type_of_param_value, convert_value_type
from easybuild.framework.easyconfig.types import is_value_of_type, to_name_version_dict, to_dependency


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

        # check type checking of toolchain (non-trivial type: dict with only name/version keys & string values)
        toolchain = {'name': 'goolf', 'version': '1.4.10'}
        self.assertEqual(check_type_of_param_value('toolchain', toolchain), (True, toolchain))
        # missing 'version' key
        self.assertEqual(check_type_of_param_value('toolchain', {'name': 'intel'}), (False, None))
        # non-string value for 'version'
        toolchain = {'name': 'goolf', 'version': 100}
        self.assertEqual(check_type_of_param_value('toolchain', toolchain), (False, None))

        # check auto-converting of toolchain value
        toolchain = {'name': 'intel', 'version': '2015a'}
        for tcspec in ["intel, 2015a", ['intel', '2015a'], toolchain]:
            self.assertEqual(check_type_of_param_value('toolchain', tcspec, auto_convert=True), (True, toolchain))

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

    def test_to_name_version_dict(self):
        """ Test toolchain string to dict conversion """
        # normal cases
        self.assertEqual(to_name_version_dict("intel, 2015a"), {'name': 'intel', 'version': '2015a'})
        self.assertEqual(to_name_version_dict(['gcc', '4.7']), {'name': 'gcc', 'version': '4.7'})

        # wrong type
        self.assertErrorRegex(EasyBuildError, r"Conversion of .* \(type .*\) to name and version dict is not supported",
            to_name_version_dict, ('intel', '2015a'))

        # wrong number of elements
        errstr = "Can not convert .* to name and version .*. Expected 2 elements"
        self.assertErrorRegex(EasyBuildError, errstr, to_name_version_dict, "intel, 2015, a")
        self.assertErrorRegex(EasyBuildError, errstr, to_name_version_dict, "intel")
        self.assertErrorRegex(EasyBuildError, errstr, to_name_version_dict, ['gcc', '4', '7'])

    def test_to_dependency(self):
        """ Test dependency dict to tuple conversion """
        # normal cases
        lib_dict = {
            'name': 'lib',
            'version': '1.2.8',
            'toolchain': {'name': 'GCC', 'version': '4.8.2'},
        }

        self.assertEqual(to_dependency({'lib': '1.2.8'}), {'name': 'lib', 'version': '1.2.8'})
        self.assertEqual(to_dependency({'lib': '1.2.8', 'toolchain': 'GCC, 4.8.2'}), lib_dict)
        self.assertEqual(to_dependency({'lib': '1.2.8', 'toolchain': ['GCC', '4.8.2']}), lib_dict)

        foo_dict = {
            'name': 'foo',
            'version': '1.3',
            'versionsuffix': '-bar',
        }
        self.assertEqual(to_dependency({'foo': '1.3', 'versionsuffix': '-bar'}), foo_dict)

        foo_dict.update({'toolchain': {'name': 'GCC', 'version': '4.8.2'}})
        self.assertEqual(to_dependency({'foo': '1.3', 'versionsuffix': '-bar', 'toolchain': 'GCC, 4.8.2'}), foo_dict)

        # using 'name' and 'version' is dictionary being passed yields the expected result
        foo_dict = {'name': 'foo', 'version': '1.2.3'}
        self.assertEqual(to_dependency(foo_dict), foo_dict)
        foo_dict.update({'toolchain': {'name': 'GCC', 'version': '4.8.2'}})
        self.assertEqual(to_dependency({'name': 'foo', 'version': '1.2.3', 'toolchain': ['GCC', '4.8.2']}), foo_dict)
        self.assertEqual(to_dependency(foo_dict), foo_dict)

        # extra keys ruin it
        foo_dict.update({'extra_key': 'bogus'})
        self.assertErrorRegex(EasyBuildError, "Found unexpected \(key, value\) pair: .*", to_dependency, foo_dict)

        # no name/version
        self.assertErrorRegex(EasyBuildError, "Can not parse dependency without name and version: .*",
            to_dependency, {'toolchain': 'lib, 1.2.8', 'versionsuffix': 'suff'})
        # too many values
        self.assertErrorRegex(EasyBuildError, "Found unexpected \(key, value\) pair: .*",
            to_dependency, {'lib': '1.2.8', 'foo':'1.3', 'toolchain': 'lib, 1.2.8', 'versionsuffix': 'suff'})

    def test_is_value_of_type(self):
        """Test is_value_of_type function."""
        self.assertTrue(is_value_of_type({'one': 1}, (dict, {})))
        self.assertTrue(is_value_of_type({'one': 1}, (dict, [('only_keys', ['one'])])))
        self.assertTrue(is_value_of_type({'one': 1}, (dict, [('value_types', [int])])))
        self.assertTrue(is_value_of_type({'one': 1}, (dict, [('key_types', [str])])))

        self.assertFalse(is_value_of_type({'one': 1}, (dict, [('only_keys', ['one', 'two'])])))
        self.assertFalse(is_value_of_type({'one': 'two'}, (dict, [('value_types', [int])])))
        self.assertFalse(is_value_of_type({'one': 1}, (dict, [('key_types', [int])])))

        # toolchain type check
        self.assertTrue(is_value_of_type({'name': 'intel', 'version': '2015a'}, NAME_VERSION_DICT))
        # version value should be string, not int
        self.assertFalse(is_value_of_type({'name': 'intel', 'version': 100}, NAME_VERSION_DICT))
        # missing version key
        self.assertFalse(is_value_of_type({'name': 'intel', 'foo': 'bar'}, NAME_VERSION_DICT))
        # extra key, shouldn't be there
        self.assertFalse(is_value_of_type({'name': 'intel', 'version': '2015a', 'foo': 'bar'}, NAME_VERSION_DICT))


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(TypeCheckingTest)


if __name__ == '__main__':
    main()
