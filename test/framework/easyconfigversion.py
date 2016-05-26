# #
# Copyright 2014-2016 Ghent University
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
Unit tests for easyconfig/format/version.py

@author: Stijn De Weirdt (Ghent University)
"""
import copy

from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen

from easybuild.framework.easyconfig.format.version import VersionOperator, ToolchainVersionOperator
from easybuild.framework.easyconfig.format.version import OrderedVersionOperators
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.utilities import search_toolchain


class EasyConfigVersion(EnhancedTestCase):
    """Unit tests for format.version module."""

    def test_parser_regex(self):
        """Test the version parser"""
        vop = VersionOperator()
        # version tests
        self.assertTrue(vop.regex.search('< 4'))
        self.assertTrue(vop.regex.search('>= 20131016'))
        self.assertTrue(vop.regex.search('<= 1.2.3'))
        self.assertTrue(vop.regex.search('> 2.4'))
        self.assertTrue(vop.regex.search('== 1.2b'))
        self.assertTrue(vop.regex.search('< 2.0dev'))
        self.assertTrue(vop.regex.search('1.2.3'))  # operator is optional, '==' is default
        self.assertFalse(vop.regex.search('>='))  # version is mandatory (even if DEFAULT_UNDEFINED_VERSION exists)
        self.assertFalse(vop.regex.search('%s1.2.3' % vop.SEPARATOR))  # no separator usage w/o something to separate
        self.assertFalse(vop.regex.search('1.2.3%s' % vop.SEPARATOR))  # no separator usage w/o something to separate
        self.assertFalse(vop.regex.search('>%s2.4' % vop.SEPARATOR * 2))  # double space as separator is not allowed
        self.assertFalse(vop.regex.search('>%s 2.4' % vop.SEPARATOR))  # double separator is not allowed
        self.assertTrue(vop.regex.search('>%sa2.4' % vop.SEPARATOR))  # version starts/ends with *any* word character
        self.assertTrue(vop.regex.search('>%s2.4_' % vop.SEPARATOR))  # version starts/ends with *any* word character
        self.assertTrue(vop.regex.search('>%sG2.4_' % vop.SEPARATOR))  # version starts/ends with *any* word character

    def test_boolean(self):
        """Test boolean test"""
        self.assertTrue(VersionOperator('>= 123'))
        self.assertTrue(VersionOperator('123'))

        error_msg = "Failed to parse '<=' as a version operator string"
        self.assertErrorRegex(EasyBuildError, error_msg, VersionOperator, '<=')

    def test_vop_test(self):
        """Test version checker"""
        vop = VersionOperator('1.2.3')
        self.assertTrue(vop.operator == vop.DEFAULT_UNDEFINED_OPERATOR)

        vop = VersionOperator('>= 1.2.3')
        self.assertTrue(vop.test('1.2.3'))  # 1.2.3 >= 1.2.3: True
        self.assertFalse(vop.test('1.2.2'))  # 1.2.2 >= 1.2.3 : False
        self.assertTrue(vop.test('1.2.4'))  # 1.2.4 >= 1.2.3 : True

        vop = VersionOperator('< 1.2.3')
        self.assertFalse(vop.test('1.2.3'))  # 1.2.3 < 1.2.3: False
        self.assertTrue(vop.test('1.2.2'))  # 1.2.2 < 1.2.3 : True
        self.assertFalse(vop.test('1.2.4'))  # 1.2.4 < 1.2.3 : False

        self.assertFalse(vop.test('2a'))  # 2a < 1.2.3 : False
        self.assertTrue(vop.test('1.1a'))  # 1.1a < 1.2.3 : True
        self.assertFalse(vop.test('1a'))  # 1a < 1.2.3 : False (beware!)
        self.assertFalse(vop.test('1.2.3dev'))  # 1.2.3dev < 1.2.3 : False (beware!)

    def test_versop_overlap_conflict(self):
        """Test overlap/conflicts"""
        overlap_conflict = [
            ('> 3', '> 3', (True, False)),  # equal, and thus overlap. no conflict
            ('> 3', '< 2', (False, False)),  # no overlap
            ('> 3', '== 3', (False, False)),  # no overlap
            ('< 3', '> 2', (True, True)),  # overlap, and conflict (region between 2 and 3 is ambiguous)
            ('>= 3', '== 3' , (True, True)),  # overlap, and conflict (boundary 3 is ambigous)
            ('> 3', '>= 3' , (True, False)),  # overlap, no conflict ('> 3' is more strict then '>= 3')

            # suffix
            ('> 2', '> 1', (True, False)),  # suffix both equal (both None), ordering like above
            ('> 2 suffix:-x1', '> 1 suffix:-x1', (True, False)),  # suffix both equal (both -x1), ordering like above
            ('> 2 suffix:-x1', '> 1 suffix:-x2', (True, True)),  # suffix not equal, conflict (and overlap)
            ('> 2 suffix:-x1', '< 1 suffix:-x2', (False, True)),  # suffix not equal, conflict (and no overlap)
            ('> 2 suffix:-x1', '< 1 suffix:-x1', (False, False)),  # suffix equal, no conflict (and no overlap)
        ]

        for l, r, res in overlap_conflict:
            vl = VersionOperator(l)
            vr = VersionOperator(r)
            self.assertEqual(vl.test_overlap_and_conflict(vr), res)

    def test_versop_gt(self):
        """Test strict greater then ordering"""
        left_gt_right = [
            ('> 2', '> 1'),  # True, order by strictness equals order by boundaries for gt/ge
            ('< 8' , '< 10'),  # True, order by strictness equals inversed order by boundaries for lt/le
            ('== 4' , '> 3'),  # equality is more strict then inequality, but this order by boundaries
            ('> 3', '== 2'),  # there is no overlap, so just order the intervals according their boundaries
            ('== 1', '> 1'),  # no overlap, same boundaries, order by operator
            ('== 1', '< 1'),  # no overlap, same boundaries, order by operator
            ('> 1', '>= 1'),  # no overlap, same boundaries, order by operator (order by strictness)
            ('< 1', '<= 1'),  # no overlap, same boundaries, order by operator (order by strictness)
            ('> 1', '< 1'),  # no overlap, same boundaries, order by operator (quite arbitrary in this case)

            # suffix
            ('> 2 suffix:-x1', '> 1 suffix:-x1'),  # equal suffixes, regular ordering
        ]
        for l, r in left_gt_right:
            self.assertTrue(VersionOperator(l) > VersionOperator(r), "%s gt %s" % (l, r))

    def test_ordered_versop_expressions(self):
        """Given set of ranges, order them according to version/operator (most recent/specific first)"""
        # simple version ordering, all different versions
        ovop = OrderedVersionOperators()
        versop_exprs = [
            '> 3.0.0',
            '>= 2.5.0',
            '> 2.0.0',
            '== 1.0.0',
        ]
        # add version expressions out of order intentionally
        ovop.add(versop_exprs[1])
        ovop.add(versop_exprs[-1])
        ovop.add(versop_exprs[0])
        ovop.add(versop_exprs[2])

        # verify whether order is what we expect it to be
        self.assertEqual(ovop.versops, [VersionOperator(x) for x in versop_exprs])

        # more complex version ordering, identical/overlapping vesions
        ovop = OrderedVersionOperators()
        versop_exprs = [
            '== 1.0.0',
            '> 1.0.0',
            '< 1.0.0',
        ]
        # add version expressions out of order intentionally
        ovop.add(versop_exprs[-1])
        ovop.add(versop_exprs[1])
        ovop.add(versop_exprs[0])
        # verify whether order is what we expect it to be
        self.assertEqual(ovop.versops, [VersionOperator(x) for x in versop_exprs])

    def test_parser_toolchain_regex(self):
        """Test the ToolchainVersionOperator parser"""
        top = ToolchainVersionOperator()
        _, tcs = search_toolchain('')
        tc_names = [x.NAME for x in tcs]
        for tc in tc_names:  # test all known toolchain names
            # test version expressions with optional version operator
            ok_tests = [
                ("%s >= 1.2.3" % tc, None),  # only dict repr for == operator
                ("%s == 1.2.3" % tc, {'name': tc, 'version': '1.2.3'}),
                (tc, None),  # only toolchain name, no dict repr (default operator is >=, version is 0.0.0)
            ]
            for txt, as_dict in ok_tests:
                self.assertTrue(top.regex.search(txt), "%s matches toolchain section marker regex" % txt)
                tcversop = ToolchainVersionOperator(txt)
                self.assertTrue(tcversop)
                self.assertEqual(tcversop.as_dict(), as_dict)

            # only accept known toolchain names
            fail_tests = [
                "x%s >= 1.2.3" % tc,
                "%sx >= 1.2.3" % tc,
                "foo",
                ">= 1.2.3",
            ]
            for txt in fail_tests:
                self.assertFalse(top.regex.search(txt), "%s doesn't match toolchain section marker regex" % txt)
                tcv = ToolchainVersionOperator(txt)
                self.assertEqual(tcv.tc_name, None)
                self.assertEqual(tcv.tcversop_str, None)

    def test_toolchain_versop_test(self):
        """Test the ToolchainVersionOperator test"""
        top = ToolchainVersionOperator()
        _, tcs = search_toolchain('')
        tc_names = [x.NAME for x in tcs]
        for tc in tc_names:  # test all known toolchain names
            # test version expressions with optional version operator
            tests = [
                ("%s >= 1.2.3" % tc, (
                    (tc, '1.2.3', True),  # version ok, name ok
                    (tc, '1.2.4', True),  # version ok, name ok
                    (tc, '1.2.2', False),  # version not ok, name ok
                    ('x' + tc, '1.2.3', False),  # version ok, name not ok
                    ('x' + tc, '1.2.2', False),  # version not ok, name not ok
                    )),
            ]
            for txt, subtests in tests:
                tcversop = ToolchainVersionOperator(txt)
                for name, version, res in subtests:
                    self.assertEqual(tcversop.test(name, version), res)

    def test_ordered_versop_add_data(self):
        """Test the add and data handling"""
        ovop = OrderedVersionOperators()
        tests = [
            ('> 1', '5'),
            ('> 2', {'x': 3}),
        ]
        for versop_txt, data in tests:
            versop = VersionOperator(versop_txt)
            ovop.add(versop)
            # no data was added, this is a new entry, mapper is initialised with None
            self.assertEqual(ovop.get_data(versop), None)
            ovop.add(versop, data)
            # test data
            self.assertEqual(ovop.get_data(versop), data)

        # new data for same versops
        tests = [
            ('> 1', '6'),
            ('> 2', {'x': 4}),
        ]
        for versop_txt, data in tests:
            versop = VersionOperator(versop_txt)
            ovop.add(versop, data)
            # test updated data
            self.assertEqual(ovop.get_data(versop), data)

        # 'update' a value
        # the data for '> 1' has no .update()
        extra_data = {'y': 4}
        tests = [
            ('> 2', extra_data),
        ]
        for versop_txt, data in tests:
            versop = VersionOperator(versop_txt)
            prevdata = copy.deepcopy(ovop.get_data(versop))
            prevdata.update(extra_data)

            ovop.add(versop, data, update=True)
            # test updated data
            self.assertEqual(ovop.get_data(versop), prevdata)

        # use update=True on new element
        versop = VersionOperator('> 10000')
        new_data = {'new': 5}
        ovop.add(versop, new_data, update=True)
        # test updated data
        self.assertEqual(ovop.get_data(versop), new_data)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(EasyConfigVersion)


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
