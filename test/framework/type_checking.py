# #
# Copyright 2015-2025 Ghent University
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
Unit tests for easyconfig/types.py

@author: Kenneth Hoste (Ghent University)
"""
import sys
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

from easybuild.framework.easyconfig.types import as_hashable, check_element_types, check_key_types, check_known_keys
from easybuild.framework.easyconfig.types import check_required_keys, check_type_of_param_value, convert_value_type
from easybuild.framework.easyconfig.types import DEPENDENCIES, DEPENDENCY_DICT, ensure_iterable_license_specs
from easybuild.framework.easyconfig.types import LIST_OF_STRINGS, SANITY_CHECK_PATHS_DICT, STRING_OR_TUPLE_LIST
from easybuild.framework.easyconfig.types import TOOLCHAIN_DICT
from easybuild.framework.easyconfig.types import is_value_of_type, to_checksums, to_dependencies, to_dependency
from easybuild.framework.easyconfig.types import to_list_of_strings, to_list_of_strings_and_tuples
from easybuild.framework.easyconfig.types import to_list_of_strings_and_tuples_and_dicts
from easybuild.framework.easyconfig.types import to_sanity_check_paths_dict, to_toolchain_dict
from easybuild.tools.build_log import EasyBuildError


class TypeCheckingTest(EnhancedTestCase):
    """Tests for value type checking of easyconfig parameters."""

    def test_check_type_of_param_value_name_version(self):
        """Test check_type_of_param_value function for name/version."""
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

    def test_check_type_of_param_value_toolchain(self):
        """Test check_type_of_param_value function for toolchain."""

        # check type checking of toolchain (non-trivial type: dict with only name/version keys & string values)
        toolchain = {'name': 'foss', 'version': '2018a'}
        self.assertEqual(check_type_of_param_value('toolchain', toolchain), (True, toolchain))
        # check type checking of toolchain (non-trivial type: dict with name/version keys & string values + hidden spec)
        toolchain = {'name': 'foss', 'version': '2018a', 'hidden': True}
        self.assertEqual(check_type_of_param_value('toolchain', toolchain), (True, toolchain))
        toolchain = {'name': 'foss', 'version': '2018a', 'hidden': False}
        self.assertEqual(check_type_of_param_value('toolchain', toolchain), (True, toolchain))
        # missing 'version' key
        self.assertEqual(check_type_of_param_value('toolchain', {'name': 'intel'}), (False, None))
        # non-string value for 'version'
        toolchain = {'name': 'foss', 'version': 100}
        self.assertEqual(check_type_of_param_value('toolchain', toolchain), (False, None))

        # check auto-converting of toolchain value
        toolchain = {'name': 'intel', 'version': '2015a'}
        for tcspec in ["intel, 2015a", ['intel', '2015a'], toolchain]:
            self.assertEqual(check_type_of_param_value('toolchain', tcspec, auto_convert=True), (True, toolchain))
        toolchain = {'name': 'intel', 'version': '2015a', 'hidden': True}
        for tcspec in ["intel, 2015a, True", ['intel', '2015a', 'True'], toolchain]:
            self.assertEqual(check_type_of_param_value('toolchain', tcspec, auto_convert=True), (True, toolchain))

    def test_check_type_of_param_value_deps(self):
        """Test check_type_of_param_value function for *dependencies."""

        # dependencies (type check)
        inputs = [
            [],
            [{'name': 'foo', 'version': '1.2.3'}],
            [{'name': 'foo', 'version': '1.2.3', 'versionsuffix': ''}],
            [{'name': 'foo', 'version': '1.2.3', 'versionsuffix': '', 'toolchain': {'name': 'GCC', 'version': '4.7'}}],
            [{'name': 'foo', 'version': '1.2.3', 'toolchain': {'name': 'GCC', 'version': '4.7'}}],
            [{'name': 'foo', 'version': '1.2.3'}, {'name': 'bar', 'version': '3.4.5'}],
        ]
        for inp in inputs:
            self.assertEqual(check_type_of_param_value('dependencies', inp), (True, inp))

        inputs = [
            ['foo'],
            [{'name': 'foo'}],
            ['foo,1.2.3'],
            [{'foo': '1.2.3'}],
            [('foo', '1.2.3')],
            [{'name': 'foo', 'version': '1.2.3'}, ('bar', '3.4.5')],
            [{'name': 'foo', 'version': '1.2.3', 'somekey': 'wrong'}],
        ]
        for inp in inputs:
            self.assertEqual(check_type_of_param_value('dependencies', inp), (False, None))

        # dependencies (auto-convert)
        self.assertEqual(check_type_of_param_value('dependencies', [{'foo': '1.2.3'}], auto_convert=True),
                         (True, [{'name': 'foo', 'version': '1.2.3'}]))
        # tuple values pass through untouched (are handled later by EasyConfig._parse_dependency)
        inp = [('foo', '1.2.3')]
        self.assertEqual(check_type_of_param_value('dependencies', inp, auto_convert=True), (True, [('foo', '1.2.3')]))
        inp = [('foo', '1.2.3'), {'bar': '3.4.5'}, ('baz', '9.8.7')]
        out = (True, [('foo', '1.2.3'), {'name': 'bar', 'version': '3.4.5'}, ('baz', '9.8.7')])
        self.assertEqual(check_type_of_param_value('dependencies', inp, auto_convert=True), out)

        # osdependencies (type check)
        inputs = [
            ['zlib'],
            [('openssl-devel', 'libssl-dev', 'libopenssl-devel')],
            ['zlib', ('openssl-devel', 'libssl-dev', 'libopenssl-devel')],
        ]
        for inp in inputs:
            self.assertEqual(check_type_of_param_value('osdependencies', inp), (True, inp))

        inp = ['zlib', ['openssl-devel', 'libssl-dev', 'libopenssl-devel']]
        self.assertEqual(check_type_of_param_value('osdependencies', inp), (False, None))

        # osdependencies (auto-convert)
        out = ['zlib', ('openssl-devel', 'libssl-dev', 'libopenssl-devel')]
        self.assertEqual(check_type_of_param_value('osdependencies', inp, auto_convert=True), (True, out))

    def test_check_type_of_param_value_sanity_check_paths(self):
        """Test check_type_of_param_value function for sanity_check_paths."""

        # sanity_check_paths (type check)
        inputs = [
            {'files': [], 'dirs': []},
            {'files': ['bin/foo'], 'dirs': [('lib', 'lib64')]},
            {'files': ['bin/foo', ('bin/bar', 'bin/baz')], 'dirs': []},
        ]
        for inp in inputs:
            self.assertEqual(check_type_of_param_value('sanity_check_paths', inp), (True, inp))

        inputs = [
            {},
            {'files': []},
            {'files': [], 'dirs': [], 'somethingelse': []},
            {'files': [['bin/foo']], 'dirs': []},
            {'files': [], 'dirs': [1]},
            {'files': ['foo'], 'dirs': [(1, 2)]},
        ]
        for inp in inputs:
            self.assertEqual(check_type_of_param_value('sanity_check_paths', inp), (False, None))

        # sanity_check_paths (auto-convert)
        inp = {'files': ['bin/foo', ['bin/bar', 'bin/baz']], 'dirs': [['lib', 'lib64', 'lib32']]}
        out = {'files': ['bin/foo', ('bin/bar', 'bin/baz')], 'dirs': [('lib', 'lib64', 'lib32')]}
        self.assertEqual(check_type_of_param_value('sanity_check_paths', inp, auto_convert=True), (True, out))

    @staticmethod
    def get_valid_checksums_values():
        """Return list of values valid for the 'checksums' EC parameter"""

        # Using (actually invalid) prefix to better detect those in case of errors
        md5_checksum = 'md518be8435447a017fd1bf2c7ae9224'
        sha256_checksum1 = 'sha18be8435447a017fd1bf2c7ae922d0428056cfc7449f7a8641edf76b48265'
        sha256_checksum2 = 'sha2cb06105c1d2d30719db5ffb3ea67da60919fb68deaefa583deccd8813551'
        sha256_checksum3 = 'sha3e54514a03e255df75c5aee8f9e672f663f93abb723444caec8fe43437bde'
        filesize = 45617379
        # valid values for 'checksums' easyconfig parameters
        return [
            [],
            # single checksum (one file)
            [md5_checksum],
            [sha256_checksum1],
            # one checksum, for 3 files
            [sha256_checksum1, sha256_checksum2, sha256_checksum3],
            # one checksum of specific type (as 2-tuple)
            [('md5', md5_checksum)],
            [('sha256', sha256_checksum1)],
            [('size', filesize)],
            # alternative checksums for a single file (n-tuple)
            [(sha256_checksum1, sha256_checksum2)],
            [(sha256_checksum1, sha256_checksum2, sha256_checksum3)],
            [(sha256_checksum1, sha256_checksum2, sha256_checksum3, md5_checksum)],
            [(md5_checksum,)],
            # multiple checksums of specific type, one for each file
            [('md5', md5_checksum), ('sha256', sha256_checksum1)],
            # checksum as dict (file to checksum mapping)
            [{'foo.txt': sha256_checksum1, 'bar.txt': sha256_checksum2}],
            # list of checksums for a single file
            [[md5_checksum]],
            [[sha256_checksum1, sha256_checksum2, sha256_checksum3]],
            # in the mix (3 files, each a different kind of checksum spec)...
            [
                sha256_checksum1,
                ('md5', md5_checksum),
                {'foo.txt': sha256_checksum2, 'bar.txt': sha256_checksum3},
            ],
            # each item can be a list of checksums for a single file, which can be of different types...
            [
                # two checksums for a single file, *both* should match
                [sha256_checksum1, md5_checksum],
                # three checksums for a single file, *all* should match
                [sha256_checksum1, ('md5', md5_checksum), ('size', filesize)],
                # single checksum for a single file
                sha256_checksum1,
                # filename-to-checksum mapping
                {'foo.txt': sha256_checksum1, 'bar.txt': sha256_checksum2, 'baz.txt': ('size', filesize)},
                # 3 alternative checksums for a single file, one match is sufficient
                (sha256_checksum1, sha256_checksum2, sha256_checksum3),
                # two alternative checksums for a single file (not to be confused by checksum-type & -value tuple)
                (sha256_checksum1, md5_checksum),
                # three alternative checksums for a single file of different types
                (sha256_checksum1, ('md5', md5_checksum), ('size', filesize)),
                # alternative checksums in dicts are also allowed
                {'foo.txt': (sha256_checksum2, sha256_checksum3), 'bar.txt': (sha256_checksum1, md5_checksum)},
                # Same but with lists -> all must match for each file
                {'foo.txt': [sha256_checksum2, sha256_checksum3], 'bar.txt': [sha256_checksum1, md5_checksum]},
            ],
            # None is allowed, meaning skip the checksum
            [
                None,
                # Also in mappings
                {'foo.txt': sha256_checksum1, 'bar.txt': None},
            ],
        ]

    def test_check_type_of_param_value_checksums(self):
        """Test check_type_of_param_value function for checksums."""

        for inp in TypeCheckingTest.get_valid_checksums_values():
            type_ok, newval = check_type_of_param_value('checksums', inp)
            self.assertIs(type_ok, True, 'Failed for ' + str(inp))
            self.assertEqual(newval, inp)

    def test_check_type_of_param_value_patches(self):
        """Test check_type_of_param_value function for patches."""

        # patches values that do not need to be converted
        inputs = (
            [],  # empty list of patches
            # single patch, different types
            ['foo.patch'],  # only filename
            [('foo.patch', '1')],  # filename + patch level
            [('foo.patch', 'subdir')],  # filename + subdir to apply patch in
            [{'name': 'foo.patch', 'level': '1'}],  # filename + patch level, as dict value
            # multiple patches, mix of different types
            ['1.patch', '2.patch', '3.patch'],
            ['1.patch', ('2.patch', '2'), {'name': '3.patch'}],
            ['1.patch', {'name': '2.patch', 'level': '2'}, ('3.patch', '3')],
        )
        for inp in inputs:
            self.assertEqual(check_type_of_param_value('patches', inp), (True, inp))

    def test_convert_value_type(self):
        """Test convert_value_type function."""
        # to string
        self.assertEqual(convert_value_type(100, str), '100')
        self.assertEqual(convert_value_type((100,), str), '(100,)')
        self.assertEqual(convert_value_type([100], str), '[100]')
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

        # to list of strings
        self.assertEqual(convert_value_type('foo', LIST_OF_STRINGS), ['foo'])
        self.assertEqual(convert_value_type(('foo', 'bar'), LIST_OF_STRINGS), ['foo', 'bar'])
        self.assertEqual(convert_value_type((), LIST_OF_STRINGS), [])

        # idempotency
        self.assertEqual(convert_value_type('foo', str), 'foo')
        self.assertEqual(convert_value_type('foo', str), 'foo')
        self.assertEqual(convert_value_type(100, int), 100)
        self.assertEqual(convert_value_type(1.6, float), 1.6)
        self.assertEqual(convert_value_type(['foo', 'bar'], LIST_OF_STRINGS), ['foo', 'bar'])
        self.assertEqual(convert_value_type([], LIST_OF_STRINGS), [])

        # complex types
        dep = [{'GCC': '1.2.3', 'versionsuffix': 'foo'}]
        converted_dep = [{'name': 'GCC', 'version': '1.2.3', 'versionsuffix': 'foo'}]
        self.assertEqual(convert_value_type(dep, DEPENDENCIES), converted_dep)

        # no conversion function available for specific type
        class Foo():
            pass
        self.assertErrorRegex(EasyBuildError, "No conversion function available", convert_value_type, None, Foo)

    def test_to_toolchain_dict(self):
        """ Test toolchain string to dict conversion """
        # normal cases
        self.assertEqual(to_toolchain_dict(('intel', '2015a')), {'name': 'intel', 'version': '2015a'})
        self.assertEqual(to_toolchain_dict("intel, 2015a"), {'name': 'intel', 'version': '2015a'})
        self.assertEqual(to_toolchain_dict(['gcc', '4.7']), {'name': 'gcc', 'version': '4.7'})

        # incl. hidden spec
        expected = {'name': 'intel', 'version': '2015a', 'hidden': True}
        self.assertEqual(to_toolchain_dict("intel, 2015a, True"), expected)
        expected = {'name': 'intel', 'version': '2015a', 'hidden': False}
        self.assertEqual(to_toolchain_dict(('intel', '2015a', 'False')), expected)
        expected = {'name': 'gcc', 'version': '4.7', 'hidden': True}
        self.assertEqual(to_toolchain_dict(['gcc', '4.7', 'True']), expected)

        tc = {'name': 'intel', 'version': '2015a'}
        self.assertEqual(to_toolchain_dict(tc), tc)

        tc = {'name': 'intel', 'version': '2015a', 'hidden': True}
        self.assertEqual(to_toolchain_dict(tc), tc)

        # wrong type
        self.assertErrorRegex(EasyBuildError, r"Conversion of .* \(type .*\) to toolchain dict is not supported",
                              to_toolchain_dict, 1000)

        # wrong number of elements
        errstr = "Can not convert .* to toolchain dict. Expected 2 or 3 elements"
        self.assertErrorRegex(EasyBuildError, errstr, to_toolchain_dict, "intel, 2015, True, a")
        self.assertErrorRegex(EasyBuildError, errstr, to_toolchain_dict, "intel")
        self.assertErrorRegex(EasyBuildError, errstr, to_toolchain_dict, ['gcc', '4', 'False', '7'])

        # invalid truth value
        errstr = "Invalid truth value .*"
        self.assertErrorRegex(EasyBuildError, errstr, to_toolchain_dict, "intel, 2015, foo")
        self.assertErrorRegex(EasyBuildError, errstr, to_toolchain_dict, ['gcc', '4', '7'])

        # missing keys
        self.assertErrorRegex(EasyBuildError, "Incorrect set of keys", to_toolchain_dict, {'name': 'intel'})

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
        dep_specs = [
            ('foo', '1.3'),
            ('foo', '1.3', '-suff', ('GCC', '4.8.2')),
            'foo/1.3',
        ]
        for dep_spec in dep_specs:
            self.assertEqual(to_dependency(dep_spec), dep_spec)

        expected = {
            'external_module': True,
            'full_mod_name': 'fftw/3.3.4.2',
            'name': None,
            'short_mod_name': 'fftw/3.3.4.2',
            'version': None,
        }
        self.assertEqual(to_dependency({'name': 'fftw/3.3.4.2', 'external_module': True}), expected)

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
        self.assertErrorRegex(EasyBuildError, r"Found unexpected \(key, value\) pair: .*", to_dependency, foo_dict)

        # no name/version
        self.assertErrorRegex(EasyBuildError, "Can not parse dependency without name and version: .*",
                              to_dependency, {'toolchain': 'lib, 1.2.8', 'versionsuffix': 'suff'})
        # too many values
        dep_spec = {'lib': '1.2.8', 'foo': '1.3', 'toolchain': 'lib, 1.2.8', 'versionsuffix': 'suff'}
        self.assertErrorRegex(EasyBuildError, r"Found unexpected \(key, value\) pair: .*", to_dependency, dep_spec)

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
            ('foobar', '1.3.5', '', ('GCC', '4.7.2')),
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

        # list of strings check
        self.assertTrue(is_value_of_type([], LIST_OF_STRINGS))
        self.assertTrue(is_value_of_type(['foo', 'bar'], LIST_OF_STRINGS))
        self.assertTrue(is_value_of_type([''], LIST_OF_STRINGS))
        self.assertFalse(is_value_of_type(123, LIST_OF_STRINGS))
        self.assertFalse(is_value_of_type('foo', LIST_OF_STRINGS))
        self.assertFalse(is_value_of_type(('foo', 'bar'), LIST_OF_STRINGS))

        # toolchain type check
        self.assertTrue(is_value_of_type({'name': 'intel', 'version': '2015a'}, TOOLCHAIN_DICT))
        # version value should be string, not int
        self.assertFalse(is_value_of_type({'name': 'intel', 'version': 100}, TOOLCHAIN_DICT))
        # missing version key
        self.assertFalse(is_value_of_type({'name': 'intel', 'foo': 'bar'}, TOOLCHAIN_DICT))
        # extra key, shouldn't be there
        self.assertFalse(is_value_of_type({'name': 'intel', 'version': '2015a', 'foo': 'bar'}, TOOLCHAIN_DICT))

        # dependency type check
        self.assertTrue(is_value_of_type({'name': 'intel', 'version': '2015a'}, DEPENDENCY_DICT))
        self.assertTrue(is_value_of_type({
            'name': 'intel',
            'version': '2015a',
            'toolchain': {'name': 'intel', 'version': '2015a'},
            'versionsuffix': 'foo',
        }, DEPENDENCY_DICT))
        # no version key
        self.assertFalse(is_value_of_type({'name': 'intel'}, TOOLCHAIN_DICT))
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
        self.assertFalse(is_value_of_type([{'a': 'b', 'c': 'd'}], DEPENDENCIES))

        # not a list
        self.assertFalse(is_value_of_type({'name': 'intel', 'version': '2015a'}, DEPENDENCIES))

        # no extra keys allowed, only name/version/versionsuffix/toolchain
        self.assertFalse(is_value_of_type({'name': 'intel', 'version': '2015a', 'foo': 'bar'}, DEPENDENCIES))

        # list of strings and tuples test
        self.assertTrue(is_value_of_type(['foo', ('bar', 'bat')], STRING_OR_TUPLE_LIST))
        self.assertTrue(is_value_of_type(['foo', 'bar'], STRING_OR_TUPLE_LIST))
        self.assertTrue(is_value_of_type([('foo', 'fob'), ('bar', 'bat')], STRING_OR_TUPLE_LIST))
        self.assertTrue(is_value_of_type([], STRING_OR_TUPLE_LIST))

        # list element, not allowed (should be tuple or string)
        self.assertFalse(is_value_of_type(['foo', ['bar', 'bat']], STRING_OR_TUPLE_LIST))
        # int element, not allowed (should be tuple or string)
        self.assertFalse(is_value_of_type(['foo', 1], STRING_OR_TUPLE_LIST))

        # sanity_check_paths test
        self.assertTrue(is_value_of_type({'files': ['one', 'two'], 'dirs': ['dirA', 'dirB']}, SANITY_CHECK_PATHS_DICT))
        self.assertTrue(is_value_of_type({'files': ['f1', ('f2a', 'f2b')], 'dirs': []}, SANITY_CHECK_PATHS_DICT))
        self.assertTrue(is_value_of_type({'files': [], 'dirs': []}, SANITY_CHECK_PATHS_DICT))

        # list element for 'files', should be string or tuple
        self.assertFalse(is_value_of_type({'files': ['f1', ['f2a', 'f2b']], 'dirs': []}, SANITY_CHECK_PATHS_DICT))
        # missing 'dirs' key
        self.assertFalse(is_value_of_type({'files': ['f1', 'f2']}, SANITY_CHECK_PATHS_DICT))
        # tuple rather than list
        self.assertFalse(is_value_of_type({'files': (1, 2), 'dirs': []}, SANITY_CHECK_PATHS_DICT))
        # int elements rather than strings/tuples-of-strings
        self.assertFalse(is_value_of_type({'files': [1, 2], 'dirs': []}, SANITY_CHECK_PATHS_DICT))
        # one int element is not allowed either
        self.assertFalse(is_value_of_type({'files': ['foo', 2], 'dirs': []}, SANITY_CHECK_PATHS_DICT))
        # extra key is not allowed
        self.assertFalse(is_value_of_type({'files': [], 'dirs': [], 'foo': []}, SANITY_CHECK_PATHS_DICT))
        # no keys at all
        self.assertFalse(is_value_of_type({}, SANITY_CHECK_PATHS_DICT))

    def test_as_hashable(self):
        """Test as_hashable function."""
        hashable_value = (
            ('one', (1,)),
            ('two', (1, 2)),
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
        # checking types of list/tuple elements
        self.assertTrue(check_element_types(['one', 'two'], [str]))
        self.assertTrue(check_element_types(('one', 'two'), [str]))
        self.assertTrue(check_element_types(['one', 'two'], [int, str]))
        self.assertTrue(check_element_types(('one', 'two'), [int, str]))
        self.assertTrue(check_element_types(['one', 2], [int, str]))
        self.assertTrue(check_element_types(('one', 2), [int, str]))
        self.assertFalse(check_element_types(['one', 2], [int]))
        self.assertFalse(check_element_types(('one', 2), [int]))

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

    def test_to_list_of_strings(self):
        """Test to_list_of_strings function."""
        # no conversion if value type is already correct
        self.assertEqual(to_list_of_strings([]), [])
        self.assertEqual(to_list_of_strings(['foo']), ['foo'])
        self.assertEqual(to_list_of_strings(['foo', 'bar', 'baz']), ['foo', 'bar', 'baz'])

        # single string is converted to a single-element list
        self.assertEqual(to_list_of_strings('foo'), ['foo'])
        self.assertEqual(to_list_of_strings(''), [''])

        # tuple of strings is converted to list of strings
        self.assertEqual(to_list_of_strings(['foo', 'bar']), ['foo', 'bar'])
        self.assertEqual(to_list_of_strings(['foo']), ['foo'])
        self.assertEqual(to_list_of_strings(()), [])

        # proper error reporting for other values
        error_pattern = r"Don't know how to convert provided value to a list of strings: "
        self.assertErrorRegex(EasyBuildError, error_pattern + '123', to_list_of_strings, 123)
        self.assertErrorRegex(EasyBuildError, error_pattern + 'True', to_list_of_strings, True)
        self.assertErrorRegex(EasyBuildError, error_pattern, to_list_of_strings, [('foo', 'bar')])

    def test_to_list_of_strings_and_tuples(self):
        """Test to_list_of_strings_and_tuples function."""
        # no conversion, already right type
        self.assertEqual(to_list_of_strings_and_tuples([]), [])
        self.assertEqual(to_list_of_strings_and_tuples([()]), [()])
        self.assertEqual(to_list_of_strings_and_tuples(['foo']), ['foo'])
        self.assertEqual(to_list_of_strings_and_tuples([('foo', 'bar')]), [('foo', 'bar')])
        self.assertEqual(to_list_of_strings_and_tuples([('foo', 'bar'), 'baz']), [('foo', 'bar'), 'baz'])

        # actual conversion
        self.assertEqual(to_list_of_strings_and_tuples(()), [])
        self.assertEqual(to_list_of_strings_and_tuples(('foo',)), ['foo'])
        self.assertEqual(to_list_of_strings_and_tuples([['bar', 'baz']]), [('bar', 'baz')])
        self.assertEqual(to_list_of_strings_and_tuples((['bar', 'baz'],)), [('bar', 'baz')])
        self.assertEqual(to_list_of_strings_and_tuples(['foo', ['bar', 'baz']]), ['foo', ('bar', 'baz')])
        self.assertEqual(to_list_of_strings_and_tuples(('foo', ['bar', 'baz'])), ['foo', ('bar', 'baz')])

        # conversion failures
        error_regex = "Expected value to be a list"
        self.assertErrorRegex(EasyBuildError, error_regex, to_list_of_strings_and_tuples, 'foo')
        self.assertErrorRegex(EasyBuildError, error_regex, to_list_of_strings_and_tuples, 1)
        self.assertErrorRegex(EasyBuildError, error_regex, to_list_of_strings_and_tuples, {'foo': 'bar'})
        error_msg = "Expected elements to be of type string, tuple or list"
        self.assertErrorRegex(EasyBuildError, error_msg, to_list_of_strings_and_tuples, ['foo', 1])
        self.assertErrorRegex(EasyBuildError, error_msg, to_list_of_strings_and_tuples, (1,))

    def test_to_list_of_strings_and_tuples_and_dicts(self):
        """Test to_list_of_strings_and_tuples_and_dicts function."""

        # no conversion, already right type
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts([]), [])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts([()]), [()])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts(['foo']), ['foo'])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts([{}]), [{}])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts([('foo', 'bar')]), [('foo', 'bar')])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts([('foo', 'bar'), 'baz']), [('foo', 'bar'), 'baz'])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts([('x',), 'y', {'z': 1}]), [('x',), 'y', {'z': 1}])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts(['y', {'z': 1}]), ['y', {'z': 1}])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts([{'z': 1}, ('x',)]), [{'z': 1}, ('x',)])

        # actual conversion
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts(()), [])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts(('foo',)), ['foo'])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts([['bar', 'baz']]), [('bar', 'baz')])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts((['bar', 'baz'],)), [('bar', 'baz')])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts(['foo', ['bar', 'baz']]), ['foo', ('bar', 'baz')])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts(('foo', ['bar', 'baz'])), ['foo', ('bar', 'baz')])
        self.assertEqual(to_list_of_strings_and_tuples_and_dicts(('x', ['y'], {'z': 1})), ['x', ('y',), {'z': 1}])

        # conversion failures
        error_regex = "Expected value to be a list"
        self.assertErrorRegex(EasyBuildError, error_regex, to_list_of_strings_and_tuples_and_dicts, 'foo')
        self.assertErrorRegex(EasyBuildError, error_regex, to_list_of_strings_and_tuples_and_dicts, 1)
        self.assertErrorRegex(EasyBuildError, error_regex, to_list_of_strings_and_tuples_and_dicts, {'foo': 'bar'})
        error_msg = "Expected elements to be of type string, tuple, dict or list"
        self.assertErrorRegex(EasyBuildError, error_msg, to_list_of_strings_and_tuples_and_dicts, ['foo', 1])
        self.assertErrorRegex(EasyBuildError, error_msg, to_list_of_strings_and_tuples_and_dicts, (1,))
        self.assertErrorRegex(EasyBuildError, error_msg, to_list_of_strings_and_tuples_and_dicts, (1, {'foo': 'bar'}))

    def test_to_sanity_check_paths_dict(self):
        """Test to_sanity_check_paths_dict function."""
        # no conversion, already right type
        inputs = [
            {'files': [], 'dirs': []},
            {'files': ['foo', 'bar'], 'dirs': []},
            {'files': [], 'dirs': ['baz']},
            {'files': ['foo', ('bar', 'baz')], 'dirs': [('one', '2', 'three')]},
        ]
        for inp in inputs:
            self.assertEqual(to_sanity_check_paths_dict(inp), inp)

        # actual conversion
        inputs = [
            ({'files': ['foo'], 'dirs': [['bar', 'baz']]}, {'files': ['foo'], 'dirs': [('bar', 'baz')]}),
            ({'files': ['foo', ['bar', 'baz']], 'dirs': []}, {'files': ['foo', ('bar', 'baz')], 'dirs': []}),
            ({'files': (), 'dirs': [('f1', 'f2'), ['1', '2', '3'], 'x']},
             {'files': [], 'dirs': [('f1', 'f2'), ('1', '2', '3'), 'x']}),
        ]
        for inp, out in inputs:
            self.assertEqual(to_sanity_check_paths_dict(inp), out)

        # conversion failures
        self.assertErrorRegex(EasyBuildError, "Expected value to be a dict", to_sanity_check_paths_dict, [])
        error_msg = "Expected value to be a list"
        self.assertErrorRegex(EasyBuildError, error_msg, to_sanity_check_paths_dict, {'files': 'foo', 'dirs': []})
        error_msg = "Expected elements to be of type string, tuple/list or dict"
        self.assertErrorRegex(EasyBuildError, error_msg, to_sanity_check_paths_dict, {'files': [], 'dirs': [1]})

    def test_to_checksums(self):
        """Test to_checksums function."""
        # Some hand-crafted examples. Only the types are important, values are for easier verification
        test_inputs = [
            ['checksumvalue'],
            [('md5', 'md5checksumvalue')],
            ['file_1_checksum', ('md5', 'file_2_md5_checksum')],
            # One checksum per file, some with checksum type
            [
                'be662daa971a640e40be5c804d9d7d10',
                ('adler32', '0x998410035'),
                ('crc32', '0x1553842328'),
                ('md5', 'be662daa971a640e40be5c804d9d7d10'),
                ('sha1', 'f618096c52244539d0e89867405f573fdb0b55b0'),
                # int type as the 2nd value
                ('size', 273),
            ],
            # None values should not be filtered out, but left in place
            [None, 'checksum', None],
            # Alternative checksums, not to be confused with multiple checksums for a file
            [('main_checksum', 'alternative_checksum')],
            [('1st_of_3', '2nd_of_3', '3rd_of_3')],
            # Lists must be kept: This means all must match
            [['checksum_1_in_list']],
            [['checksum_must_match', 'this_must_also_match']],
            [['1st_of_3_list', '2nd_of_3_list', '3rd_of_3_list']],
            # Alternative checksums with types
            [
                (('adler32', '1st_adler'), ('crc32', '1st_crc')),
                (('adler32', '2nd_adler'), ('crc32', '2nd_crc'), ('sha1', '2nd_sha')),
            ],
            # Entries can be dicts even containing `None`
            [
                {
                    'src-arm.tgz': 'arm_checksum',
                    'src-x86.tgz': ('mainchecksum', 'altchecksum'),
                    'src-ppc.tgz': ('mainchecksum', ('md5', 'altchecksum')),
                    'git-clone.tgz': None,
                },
                {
                    'src': ['checksum_must_match', 'this_must_also_match']
                },
                # 2nd required checksum a dict
                ['first_checksum', {'src-arm': 'arm_checksum'}]
            ],
        ]
        for checksums in test_inputs:
            self.assertEqual(to_checksums(checksums), checksums)
        # Also reuse the checksums we use in test_check_type_of_param_value_checksums
        # When a checksum is valid it must not be modified
        for checksums in TypeCheckingTest.get_valid_checksums_values():
            self.assertEqual(to_checksums(checksums), checksums)

        # List in list converted to tuple -> alternatives or checksum with type
        checksums = [['1stchecksum', ['md5', 'md5sum']]]
        checksums_expected = [['1stchecksum', ('md5', 'md5sum')]]
        self.assertEqual(to_checksums(checksums), checksums_expected)

        # Error detection
        wrong_nesting = [('1stchecksum', ('md5', ('md5sum', 'altmd5sum')))]
        self.assertErrorRegex(EasyBuildError, 'Unexpected type.*md5', to_checksums, wrong_nesting)
        correct_nesting = [('1stchecksum', ('md5', 'md5sum'), ('md5', 'altmd5sum'))]
        self.assertEqual(to_checksums(correct_nesting), correct_nesting)
        # YEB (YAML EC) doesn't has tuples so it uses lists instead which need to get converted
        correct_nesting_yeb = [[['1stchecksum', ['md5', 'md5sum'], ['md5', 'altmd5sum']]]]
        correct_nesting_yeb_conv = [[('1stchecksum', ('md5', 'md5sum'), ('md5', 'altmd5sum'))]]
        self.assertEqual(to_checksums(correct_nesting_yeb), correct_nesting_yeb_conv)
        self.assertEqual(to_checksums(correct_nesting_yeb_conv), correct_nesting_yeb_conv)

        unexpected_set = [('1stchecksum', {'md5', 'md5sum'})]
        self.assertErrorRegex(EasyBuildError, 'Unexpected type.*md5', to_checksums, unexpected_set)
        unexpected_dict = [{'src': ('md5sum', {'src': 'shasum'})}]
        self.assertErrorRegex(EasyBuildError, 'Unexpected type.*shasum', to_checksums, unexpected_dict)
        correct_dict = [{'src': ('md5sum', 'shasum')}]
        self.assertEqual(to_checksums(correct_dict), correct_dict)
        correct_dict_1 = [{'src': [['md5', 'md5sum'], ['sha', 'shasum']]}]
        correct_dict_2 = [{'src': [('md5', 'md5sum'), ('sha', 'shasum')]}]
        self.assertEqual(to_checksums(correct_dict_2), correct_dict_2)
        self.assertEqual(to_checksums(correct_dict_1), correct_dict_2)  # inner lists to tuples

        unexpected_Nones = [
            [('1stchecksum', None)],
            [['1stchecksum', None]],
            [{'src': ('md5sum', None)}],
            [{'src': ['md5sum', None]}],
        ]
        self.assertErrorRegex(EasyBuildError, 'Unexpected None', to_checksums, unexpected_Nones[0])
        self.assertErrorRegex(EasyBuildError, 'Unexpected None', to_checksums, unexpected_Nones[1])
        self.assertErrorRegex(EasyBuildError, 'Unexpected None', to_checksums, unexpected_Nones[2])
        self.assertErrorRegex(EasyBuildError, 'Unexpected None', to_checksums, unexpected_Nones[3])

    def test_ensure_iterable_license_specs(self):
        """Test ensure_iterable_license_specs function."""
        # Test acceptable inputs
        self.assertEqual(ensure_iterable_license_specs(None), [None])
        self.assertEqual(ensure_iterable_license_specs('foo'), ['foo'])
        self.assertEqual(ensure_iterable_license_specs(['foo']), ['foo'])
        self.assertEqual(ensure_iterable_license_specs(['foo', 'bar']), ['foo', 'bar'])
        self.assertEqual(ensure_iterable_license_specs(('foo',)), ['foo'])
        self.assertEqual(ensure_iterable_license_specs(('foo', 'bar')), ['foo', 'bar'])

        # Test unacceptable inputs
        error_msg = "Unsupported type .* for easyconfig parameter 'license_file'!"
        self.assertErrorRegex(EasyBuildError, error_msg, ensure_iterable_license_specs, 42)
        self.assertErrorRegex(EasyBuildError, error_msg, ensure_iterable_license_specs, {'1': 'foo'})
        self.assertErrorRegex(EasyBuildError, error_msg, ensure_iterable_license_specs, [None])
        self.assertErrorRegex(EasyBuildError, error_msg, ensure_iterable_license_specs, [42])
        self.assertErrorRegex(EasyBuildError, error_msg, ensure_iterable_license_specs, [42, 'foo'])
        self.assertErrorRegex(EasyBuildError, error_msg, ensure_iterable_license_specs, [['foo']])
        self.assertErrorRegex(EasyBuildError, error_msg, ensure_iterable_license_specs, [(42, 'foo')])
        self.assertErrorRegex(EasyBuildError, error_msg, ensure_iterable_license_specs, (42,))
        self.assertErrorRegex(EasyBuildError, error_msg, ensure_iterable_license_specs, (42, 'foo'))


def suite(loader=None):
    """ returns all the testcases in this module """
    if loader:
        return loader.loadTestsFromTestCase(TypeCheckingTest)
    else:
        return TestLoaderFiltered().loadTestsFromTestCase(TypeCheckingTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
