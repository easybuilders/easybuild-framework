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
        self.assertTrue(vop.regexp.search('1.2.3_>='))
        self.assertTrue(vop.regexp.search('1.2.3'))
        self.assertFalse(vop.regexp.search('%s1.2.3' % vop.SEPARATOR))

    def test_parser_check(self):
        """Test version checker"""
        vop = VersionOperator()
        check = vop._operator_check(**vop.regexp.search('1.2.3_>=').groupdict())
        self.assertTrue(check('1.2.3'))
        self.assertTrue(check('1.2.2'))  # righthand side: 1.2.3 >= 1.2.2 : True
        self.assertFalse(check('1.2.4'))  # righthand side: 1.2.3 >= 1.2.4 : False

    def test_find_best_natch(self):
        """Given set of ranges, find best match"""
        vop = VersionOperator()
        vop.add('1.0.0_>=')
        vop.add('2.0.0_>=')
        vop.add('2.5.0_<=')
        vop.add('3.0.0_>=')

    def test_parser_toolchain_regex(self):
        """Test the toolchain parser"""
        top = ToolchainOperator()
        _, tcs = search_toolchain('')
        tc_names = [x.NAME for x in tcs]
        tc = tc_names[0]
        self.assertTrue(top.regexp.search("%s_1.2.3_>=" % (tc)))
        self.assertTrue(top.regexp.search("%s_1.2.3" % (tc)))
        self.assertTrue(top.regexp.search("%s" % (tc)))
        self.assertFalse(top.regexp.search("x%s_1.2.3_>=" % (tc)))
        self.assertFalse(top.regexp.search("%sx_1.2.3_>=" % (tc)))

    def test_configobj(self):
        """Test configobj sort"""
        _, tcs = search_toolchain('')
        tc_names = [x.NAME for x in tcs]
        tcmax = 3
        if len(tc_names) < tcmax:
            tcmax = len(tc_names)
        tc = tc_names[0]
        configobj_txt = [
            '[DEFAULT]',
            'version=1.2.3',
            'toolchain=%s_5.6.7' % tc,
            '[[SUPPORTED]]',
            'toolchains=%s_7.8.9_>=' % ','.join(tc_names[:tcmax]),
            'versions=1.2.3,2.3.4,3.4.5',
            '[2.3.4_>=]',
            '[3.4.5_>=]',
            '[%s_5.6.7_>=]' % tc,
            '[%s_7.8.9_>=]' % tc_names[tcmax - 1],
        ]

        co = ConfigObj(configobj_txt)
        cov = ConfigObjVersion()


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(EasyConfigVersion)


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
