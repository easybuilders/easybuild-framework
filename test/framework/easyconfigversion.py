"""
Unit tests for easyconfig/format/version.py

@author: Stijn De Weirdt (Ghent University)
"""
import os

from easybuild.framework.easyconfig.format.version import VersionOperator, ToolchainVersionOperator
from easybuild.framework.easyconfig.format.version import OrderedVersionOperators
from easybuild.framework.easyconfig.format.version import ConfigObjVersion
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.toolchain.utilities import search_toolchain
from unittest import TestCase, TestLoader, main

from vsc.utils.fancylogger import setLogLevelDebug, logToScreen


class EasyConfigVersion(TestCase):
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

        self.assertFalse(VersionOperator('<='))

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
                "%s >= 1.2.3" % tc,
                "%s 1.2.3" % tc,
                tc,
            ]
            for txt in ok_tests:
                self.assertTrue(top.regex.search(txt), "%s matches toolchain section marker regex" % txt)
                self.assertTrue(ToolchainVersionOperator(txt))

            # only accept known toolchain names
            fail_tests = [
                "x%s >= 1.2.3" % tc,
                "%sx >= 1.2.3" % tc,
                "foo",
                ">= 1.2.3",
            ]
            for txt in fail_tests:
                self.assertFalse(top.regex.search(txt), "%s doesn't match toolchain section marker regex" % txt)
                self.assertFalse(ToolchainVersionOperator(txt))

    def test_configobj(self):
        """Test configobj sort"""
        _, tcs = search_toolchain('')
        tc_names = [x.NAME for x in tcs]
        tcmax = min(len(tc_names), 3)
        if len(tc_names) < tcmax:
            tcmax = len(tc_names)
        tc = tc_names[0]
        configobj_txt = [
            '[DEFAULT]',
            'toolchains=%s >= 7.8.9' % ','.join(tc_names[:tcmax]),
            'versions=1.2.3,2.3.4,3.4.5',
            '[>= 2.3.4]',
            'foo=bar',
            '[== 3.4.5]',
            'baz=biz',
            '[!= %s 5.6.7]' % tc,
            '[%s > 7.8.9]' % tc_names[tcmax - 1],
        ]

        co = ConfigObj(configobj_txt)
        cov = ConfigObjVersion()
        # FIXME: actually check something


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(EasyConfigVersion)


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
