# #
# Copyright 2015-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
from easybuild.framework.easyconfig.types import as_hashable, check_element_types, check_key_types, check_known_keys
from easybuild.framework.easyconfig.types import check_required_keys, check_type_of_param_value, convert_value_type
from easybuild.framework.easyconfig.types import DEPENDENCIES, DEPENDENCY_DICT, NAME_VERSION_DICT
from easybuild.framework.easyconfig.types import is_value_of_type, to_name_version_dict, to_dependencies, to_dependency


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

        # complex types
        dep = [{'GCC': '1.2.3', 'versionsuffix': 'foo'}]
        converted_dep = [{'name': 'GCC', 'version': '1.2.3', 'versionsuffix': 'foo'}]
        self.assertEqual(convert_value_type(dep, DEPENDENCIES), converted_dep)

        # no conversion function available for specific type
        class Foo():
            pass
        self.assertErrorRegex(EasyBuildError, "No conversion function available", convert_value_type, None, Foo)

    def test_to_name_version_dict(self):
        """ Test toolchain string to dict conversion """
        # normal cases
        self.assertEqual(to_name_version_dict("intel, 2015a"), {'name': 'intel', 'version': '2015a'})
        self.assertEqual(to_name_version_dict(('intel', '2015a')), {'name': 'intel', 'version': '2015a'})
        self.assertEqual(to_name_version_dict(['gcc', '4.7']), {'name': 'gcc', 'version': '4.7'})
        tc = {'name': 'intel', 'version': '2015a'}
        self.assertEqual(to_name_version_dict(tc), tc)

        # wrong type
        self.assertErrorRegex(EasyBuildError, r"Conversion of .* \(type .*\) to name and version dict is not supported",
                              to_name_version_dict, 1000)

        # wrong number of elements
        errstr = "Can not convert .* to name and version .*. Expected 2 elements"
        self.assertErrorRegex(EasyBuildError, errstr, to_name_version_dict, "intel, 2015, a")
        self.assertErrorRegex(EasyBuildError, errstr, to_name_version_dict, "intel")
        self.assertErrorRegex(EasyBuildError, errstr, to_name_version_dict, ['gcc', '4', '7'])

        # missing keys
        self.assertErrorRegex(EasyBuildError, "Incorrect set of keys", to_name_version_dict, {'name': 'intel'})

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
        lib_dict.update({'versionsuffix': ''})

        # to_dependency doesn't touch values of non-dict type
        self.assertEqual(to_dependency(('foo', '1.3')), ('foo','1.3'))
        self.assertEqual(to_dependency(('foo', '1.3', '-suff', ('GCC', '4.8.2'))), ('foo', '1.3', '-suff', ('GCC','4.8.2')))
        self.assertEqual(to_dependency('foo/1.3'), 'foo/1.3')

        self.assertEqual(to_dependency({'name':'fftw/3.3.4.2', 'external_module': True}),
            {
                'external_module': True,
                'full_mod_name': 'fftw/3.3.4.2',
                'name': None,
                'short_mod_name': 'fftw/3.3.4.2',
                'version': None,
            })

        foo_dict = {
            'name': 'foo',
            'version': '1.3',
            'versionsuffix': '-bar',
        }
        self.assertEqual(to_dependency({'foo': '1.3', 'versionsuffix': '-bar'}), foo_dict)

        foo_dict.update({'toolchain': {'name': 'GCC', 'version': '4.8.2'}})
        self.assertEqual(to_dependency({'foo': '1.3', 'versionsuffix': '-bar', 'toolchain': 'GCC, 4.8.2'}), foo_dict)

        # using 'name' and 'version' in dictionary being passed yields the expected result
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

    def test_to_dependencies(self):
        """Test to_dependencies function."""
        self.assertEqual(to_dependencies([]), [])
        deps = [
            'foo/1.2.3',
            ('foo', '1.2.3'),
            ('bar', '4.5.6', '-test'),
            ('foobar', '1.3.5', '', ('GCC', '4.7.2')),
            {'toy': '0.0'},
            {'toy': '0.0', 'versionsuffix': '-bleh'},
            {'toy': '0.0', 'toolchain': 'gompi, 2015a'},
            {'gzip': '1.5', 'versionsuffix': '', 'toolchain': 'foss, 2014b'},
            {'name': 'toy', 'version': '0.0', 'versionsuffix': '-bleh',
             'toolchain': {'name': 'gompi', 'version': '2015a'}},
        ]
        self.assertEqual(to_dependencies(deps), [
            'foo/1.2.3',
            ('foo', '1.2.3'),
            ('bar', '4.5.6', '-test'),
            ('foobar', '1.3.5', '', ('GCC','4.7.2')),
            {'name': 'toy', 'version': '0.0'},
            {'name': 'toy', 'version': '0.0', 'versionsuffix': '-bleh'},
            {'name': 'toy', 'version': '0.0', 'toolchain': {'name': 'gompi', 'version': '2015a'}},
            {'name': 'gzip', 'version': '1.5', 'versionsuffix': '',
             'toolchain': {'name': 'foss', 'version': '2014b'}},
            {'name': 'toy', 'version': '0.0', 'versionsuffix': '-bleh',
             'toolchain': {'name': 'gompi', 'version': '2015a'}},
        ])

    def test_is_value_of_type(self):
        """Test is_value_of_type function."""
        self.assertTrue(is_value_of_type({'one': 1}, dict))
        self.assertTrue(is_value_of_type(1, int))
        self.assertTrue(is_value_of_type("foo", str))
        self.assertTrue(is_value_of_type(['a', 'b'], list))
        self.assertTrue(is_value_of_type(('a', 'b'), tuple))

        self.assertFalse(is_value_of_type({'one': 1}, list))
        self.assertFalse(is_value_of_type(1, str))
        self.assertFalse(is_value_of_type("foo", int))

        # toolchain type check
        self.assertTrue(is_value_of_type({'name': 'intel', 'version': '2015a'}, NAME_VERSION_DICT))
        # version value should be string, not int
        self.assertFalse(is_value_of_type({'name': 'intel', 'version': 100}, NAME_VERSION_DICT))
        # missing version key
        self.assertFalse(is_value_of_type({'name': 'intel', 'foo': 'bar'}, NAME_VERSION_DICT))
        # extra key, shouldn't be there
        self.assertFalse(is_value_of_type({'name': 'intel', 'version': '2015a', 'foo': 'bar'}, NAME_VERSION_DICT))

        # dependency type check
        self.assertTrue(is_value_of_type({'name': 'intel', 'version': '2015a'}, DEPENDENCY_DICT))
        self.assertTrue(is_value_of_type({
            'name': 'intel',
            'version': '2015a',
            'toolchain': {'name': 'intel', 'version': '2015a'},
            'versionsuffix': 'foo',
        }, DEPENDENCY_DICT))
        # no version key
        self.assertFalse(is_value_of_type({'name': 'intel'}, NAME_VERSION_DICT))
        # too many keys
        self.assertFalse(is_value_of_type({
            'name': 'intel',
            'version': '2015a',
            'toolchain': 'intel, 2015a',
            'versionsuffix': 'foo',
            'extra': 'bar',
        }, DEPENDENCY_DICT))

        # list of dependencies type check
        dependencies = [
            {'name': 'intel', 'version': '2015a'},
            {'name': 'gcc', 'version': '4.1.3'},
            {'name': 'dummy', 'version': 'dummy', 'versionsuffix': 'foo',
             'toolchain': {'name': 'intel', 'version': '2015a'}},
        ]
        self.assertTrue(is_value_of_type(dependencies, DEPENDENCIES))

        # string value for toolchain key is not OK
        dependencies.append({'name': 'foo', 'version': '1.2.3', 'toolchain': 'intel, 2015a'})
        self.assertFalse(is_value_of_type(dependencies, DEPENDENCIES))

        # wrong keys (name/version is strictly required)
        self.assertFalse(is_value_of_type([{'a':'b', 'c':'d'}], DEPENDENCIES))

        # not a list
        self.assertFalse(is_value_of_type({'name': 'intel', 'version': '2015a'}, DEPENDENCIES))

        # no extra keys allowed, only name/version/versionsuffix/toolchain
        self.assertFalse(is_value_of_type({'name': 'intel', 'version': '2015a', 'foo': 'bar'}, DEPENDENCIES))

    def test_as_hashable(self):
        """Test as_hashable function."""
        hashable_value = (
            ('one', (1,)),
            ('two', (1,2)),
        )
        self.assertEqual(as_hashable({'one': [1], 'two': [1, 2]}), hashable_value)

        hashable_value = (
            ('one', (
                ('two', (1, 2)),
            ),),
        )
        self.assertEqual(as_hashable({'one': {'two': [1, 2]}}), hashable_value)

    def test_check_key_types(self):
        """Test check_key_types function."""
        self.assertTrue(check_key_types({'name': 'intel', 'version': '2015a'}, [str]))
        self.assertTrue(check_key_types({'one': 1, 2: 'two'}, (int, str)))

        self.assertFalse(check_key_types({'name': 'intel', 'version': '2015a'}, []))
        self.assertFalse(check_key_types({'name': 'intel', 'version': '2015a'}, (int,)))
        self.assertFalse(check_key_types({'one': 1, 2: 'two'}, [str]))

    def test_check_known_keys(self):
        """Test check_known_keys function."""
        self.assertTrue(check_known_keys({'one': 1, 'two': 2}, ['one', 'two']))
        self.assertTrue(check_known_keys({'one': 1, 'two': 2}, ('one', 'two', 'three')))
        self.assertFalse(check_known_keys({'one': 1, 'two': 2}, ['one']))

        known_keys = ['name', 'toolchain', 'version', 'versionsuffix']
        self.assertTrue(check_known_keys({'name': 'intel', 'version': '2015a'}, known_keys))
        self.assertTrue(check_known_keys({'name': 'intel', 'version': '2015a', 'versionsuffix': '-test'}, known_keys))
        self.assertFalse(check_known_keys({'name': 'intel', 'version': '2015a', 'foo': 'bar'}, known_keys))

    def test_check_required_keys(self):
        """Test check_required_keys function."""
        self.assertTrue(check_required_keys({'one': 1, 'two': 2}, ['one', 'two']))
        self.assertFalse(check_required_keys({'one': 1, 'two': 2}, ('one', 'two', 'three')))
        self.assertTrue(check_required_keys({'one': 1, 'two': 2}, ['one']))

        req_keys = ['name', 'version']
        self.assertTrue(check_required_keys({'name': 'intel', 'version': '2015a'}, req_keys))
        self.assertFalse(check_required_keys({'name': 'intel'}, req_keys))
        self.assertTrue(check_required_keys({'name': 'foo', 'version': '1.2.3', 'versionsuffix': '-test'}, req_keys))
        self.assertFalse(check_required_keys({'name': 'foo', 'versionsuffix': '-test'}, req_keys))

    def test_check_element_types(self):
        """Test check_element_types function."""
        # checking types of list elements
        self.assertTrue(check_element_types(['one', 'two'], [str]))
        self.assertTrue(check_element_types(['one', 'two'], [int, str]))
        self.assertTrue(check_element_types(['one', 2], [int, str]))
        self.assertFalse(check_element_types(['one', 2], [int]))

        # checking types of dict values (simple list of allowed types)
        self.assertTrue(check_element_types({'one': 1, 2: 'two'}, [int, str]))
        self.assertFalse(check_element_types({'one': 1, 2: 'two'}, [str]))
        self.assertFalse(check_element_types({'one': 1, 'two': None}, [str]))

        # checking types of dict values (dict of allowed types)
        self.assertTrue(check_element_types({'one': 1, 2: 'two'}, {'one': [int], 2: [str]}))
        self.assertFalse(check_element_types({'one': 1, 2: 'two'}, {'one': [str], 2: [str]}))

        self.assertTrue(check_element_types([], []))
        self.assertTrue(check_element_types({}, []))
        self.assertTrue(check_element_types({}, {}))
        # if no (matching) allowed types are listed, check returns False
        self.assertFalse(check_element_types({'one': 1}, []))
        self.assertFalse(check_element_types({'one': 1}, {}))
        self.assertFalse(check_element_types({'one': 1}, {'two': int}))

        # errors
        self.assertErrorRegex(EasyBuildError, "Don't know how to check element types .*", check_element_types, 1, [])


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(TypeCheckingTest)


if __name__ == '__main__':
    main()
