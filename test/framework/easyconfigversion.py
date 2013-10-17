"""
Unit tests for easyconfig/format/version.py

@author: Stijn De Weirdt (Ghent University)
"""
import os

from easybuild.framework.easyconfig.format.version import ConfigObjVersion, VersionOperator, ToolchainOperator
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
        self.assertFalse(vop.regex.search('%s1.2.3' % vop.SEPARATOR))  # no separator usage w/o something to separate
        self.assertFalse(vop.regex.search('1.2.3%s' % vop.SEPARATOR))  # no separator usage w/o something to separate
        self.assertFalse(vop.regex.search('>%s2.4' % vop.SEPARATOR*2))  # double space as separator is not allowed
        self.assertFalse(vop.regex.search('>%s 2.4' % vop.SEPARATOR))  # double separator is not allowed
        self.assertTrue(vop.regex.search('>%sa2.4' % vop.SEPARATOR))  # version starts/ends with *any* word character
        self.assertTrue(vop.regex.search('>%s2.4_' % vop.SEPARATOR))  # version starts/ends with *any* word character
        self.assertTrue(vop.regex.search('>%sG2.4_' % vop.SEPARATOR))  # version starts/ends with *any* word character

    def test_parser_check(self):
        """Test version checker"""
        vop = VersionOperator()
        # FIXME: default operator is '=='?
        #check = vop._operator_check(**vop.regex.search('1.2.3').groupdict())
        #self.assertTrue(check('1.2.3'))  # 1.2.3 == 1.2.3: True

        check = vop._operator_check(**vop.regex.search('>= 1.2.3').groupdict())
        self.assertTrue(check('1.2.3'))  # 1.2.3 >= 1.2.3: True
        self.assertFalse(check('1.2.2'))  # 1.2.2 >= 1.2.3 : False
        self.assertTrue(check('1.2.4'))  # 1.2.4 >= 1.2.3 : True

        check = vop._operator_check(**vop.regex.search('< 1.2.3').groupdict())
        self.assertFalse(check('1.2.3'))  # 1.2.3 < 1.2.3: False
        self.assertTrue(check('1.2.2'))  # 1.2.2 < 1.2.3 : True
        self.assertFalse(check('1.2.4'))  # 1.2.4 < 1.2.3 : False

        self.assertFalse(check('2a'))  # 2a < 1.2.3 : False
        self.assertTrue(check('1.1a'))  # 1.1a < 1.2.3 : True
        self.assertFalse(check('1a'))  # 1a < 1.2.3 : False (beware!)
        self.assertFalse(check('1.2.3dev'))  # 1.2.3dev < 1.2.3 : False (beware!)

    def test_order_version_expressions(self):
        """Given set of ranges, order them according to version/operator (most recent/specific first)"""
        # simple version ordering, all different versions
        vop = VersionOperator()
        ver_exprs = [
            '> 3.0.0',
            '== 1.0.0',
            '>= 2.5.0',
            '> 2.0.0',
        ]
        # add version expressions out of order intentionally
        vop.add_version_ordered(ver_exprs[1])
        vop.add_version_ordered(ver_exprs[-1])
        vop.add_version_ordered(ver_exprs[0])
        vop.add_version_ordered(ver_exprs[2])
        # verify whether order is what we expect it to be
        self.assertEqual(map(lambda d: d['ver_str'], vop.versions), ver_exprs[::-1])

        # more complex version ordering, identical/overlapping vesions
        vop = VersionOperator()
        ver_exprs = [
            '> 1.0.0',
            '== 1.0.0',
            '<= 1.0.1',
            '< 1.0.1',
            '>= 1.0.0',
        ]
        # add version expressions out of order intentionally
        vop.add_version_ordered(ver_exprs[1])
        vop.add_version_ordered(ver_exprs[-1])
        vop.add_version_ordered(ver_exprs[3])
        vop.add_version_ordered(ver_exprs[0])
        vop.add_version_ordered(ver_exprs[2])
        # verify whether order is what we expect it to be
        self.assertEqual(map(lambda d: d['ver_str'], vop.versions), ver_exprs[::-1])

    def test_parser_toolchain_regex(self):
        """Test the toolchain parser"""
        top = ToolchainOperator()
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
            # only accept known toolchain names
            fail_tests = [
                "x%s >= 1.2.3" % tc,
                "%sx >= 1.2.3" % tc,
                "foo",
            ]
            for txt in fail_tests:
                self.assertFalse(top.regex.search(txt), "%s doesn't match toolchain section marker regex" % txt)

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
            'version=1.2.3',
            'toolchain=%s 5.6.7' % tc,
            '[[SUPPORTED]]',
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
