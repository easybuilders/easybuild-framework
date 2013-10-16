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
        self.assertTrue(vop.regex.search('!= 2.0dev'))
        self.assertTrue(vop.regex.search('1.2.3'))  # operator is optional, '==' is default
        self.assertFalse(vop.regex.search('%s1.2.3' % vop.SEPARATOR))  # no separator usage w/o something to separate
        self.assertFalse(vop.regex.search('1.2.3%s' % vop.SEPARATOR))  # no separator usage w/o something to separate
        self.assertFalse(vop.regex.search('>  2.4'))  # double space as separator is not allowed
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
        self.assertTrue(check('1.2.2'))  # 1.2.3 >= 1.2.2 : True
        self.assertFalse(check('1.2.4'))  # 1.2.3 >= 1.2.4 : False

        check = vop._operator_check(**vop.regex.search('< 1.2.3').groupdict())
        self.assertFalse(check('1.2.3'))  # 1.2.3 < 1.2.3: False
        self.assertFalse(check('1.2.2'))  # 1.2.3 < 1.2.2 : False
        self.assertTrue(check('1.2.4'))  # 1.2.3 < 1.2.4 : True

        self.assertTrue(check('2a'))  # 1.2.3 < 2a : True
        self.assertTrue(check('1.2.3dev'))  # 1.2.3 < 1.2.3dev : True (beware!)

    def test_find_best_match(self):
        """Given set of ranges, find best match"""
        vop = VersionOperator()
        first = '== 1.0.0'
        last = '< 3.0.0'
        vop.add_version_ordered('>= 2.0.0')
        vop.add_version_ordered(last)
        vop.add_version_ordered(first)
        vop.add_version_ordered('!= 2.5.0')

        self.assertTrue(vop.versions[0], last)
        self.assertTrue(vop.versions[-1], first)

    def test_parser_toolchain_regex(self):
        """Test the toolchain parser"""
        top = ToolchainOperator()
        _, tcs = search_toolchain('')
        tc_names = [x.NAME for x in tcs]
        for tc in tc_names:  # test all known toolchain names
            for txt in ["%s >= 1.2.3" % tc, "%s 1.2.3" % tc, tc]:  # string with optional version operator
                self.assertTrue(top.regex.search(txt), "%s matches toolchain section marker regex" % txt)
            for txt in ["x%s >= 1.2.3" % tc, "%sx >= 1.2.3" % tc, "foo"]:  # only recognized toolchain names
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
