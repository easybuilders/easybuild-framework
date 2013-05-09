"""
Unit tests for easyconfig/format/format.py

@author: Stijn De Weirdt (Ghent University)
"""
import os

from easybuild.framework.easyconfig.format.format import FORMAT_VERSION_HEADER_TEMPLATE, FORMAT_VERSION_REGEXP
from easybuild.framework.easyconfig.format.two import ConfigObjVersion
from easybuild.tools.toolchain.utilities import search_toolchain
from unittest import TestCase, TestSuite, main

from vsc.utils.fancylogger import setLogLevelDebug, logToScreen


class EasyConfigFormatTest(TestCase):
    """Test the parser"""

    def runTest(self):
        self.test_parser_version_regex()

    def test_parser_version_regex(self):
        """Trivial parser test"""
        version = {'major':1, 'minor':0}
        txt = FORMAT_VERSION_HEADER_TEMPLATE % version
        res = FORMAT_VERSION_REGEXP.search(txt).groupdict()
        self.assertEqual(version['major'], int(res['major']))
        self.assertEqual(version['minor'], int(res['minor']))


class ConfigObjTest(TestCase):
    """Test the 2.0 format"""

    def runTest(self):
        self.test_parser_version_regex()
        self.test_parser_toolchain_regex()
        self.test_parser_version_check()

    def test_parser_version_regex(self):
        """Test the version parser"""
        cov = ConfigObjVersion()
        # version tests
        self.assertTrue(cov.version_regexp.search('1.2.3_>='))
        self.assertTrue(cov.version_regexp.search('1.2.3'))
        self.assertFalse(cov.version_regexp.search('%s1.2.3' % cov.VERSION_SEPARATOR))

    def test_parser_toolchain_regex(self):
        """Test the toolchain parser"""
        cov = ConfigObjVersion()
        _, tcs = search_toolchain('')
        tc_names = [x.NAME for x in tcs]
        tc = tc_names[0]
        self.assertTrue(cov.toolchain_regexp.search("%s_1.2.3_>=" % (tc)))
        self.assertTrue(cov.toolchain_regexp.search("%s_1.2.3" % (tc)))
        self.assertTrue(cov.toolchain_regexp.search("%s" % (tc)))
        self.assertFalse(cov.toolchain_regexp.search("x%s_1.2.3_>=" % (tc)))
        self.assertFalse(cov.toolchain_regexp.search("%sx_1.2.3_>=" % (tc)))

    def test_parser_version_check(self):
        """Test version checker"""
        cov = ConfigObjVersion()
        check = cov._version_operator_check(**cov.version_regexp.search('1.2.3_>=').groupdict())
        self.assertTrue(check('1.2.3'))
        self.assertTrue(check('1.2.2'))  # righthand side: 1.2.3 >= 1.2.2 : True
        self.assertFalse(check('1.2.4'))  # righthand side: 1.2.3 >= 1.2.4 : False


def suite():
    """ returns all the testcases in this module """
    return TestSuite([EasyConfigFormatTest(), ConfigObjTest()])


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
