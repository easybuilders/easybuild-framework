"""
Unit tests for easyconfig/format/format.py

@author: Stijn De Weirdt (Ghent University)
"""
import os

from easybuild.framework.easyconfig.format.format import FORMAT_VERSION_HEADER_TEMPLATE, FORMAT_VERSION_REGEXP
from easybuild.tools.toolchain.utilities import search_toolchain
from unittest import TestCase, TestSuite, main

from vsc.utils.fancylogger import setLogLevelDebug, logToScreen


class EasyConfigFormatTest(TestCase):
    """Test the parser"""

    def runTest(self):
        self.test_parser_version_regex()

    def test_parser_version_regex(self):
        """Trivial parser test"""
        version = {'major': 1, 'minor': 0}
        txt = FORMAT_VERSION_HEADER_TEMPLATE % version
        res = FORMAT_VERSION_REGEXP.search(txt).groupdict()
        self.assertEqual(version['major'], int(res['major']))
        self.assertEqual(version['minor'], int(res['minor']))


def suite():
    """ returns all the testcases in this module """
    return TestSuite([EasyConfigFormatTest()])


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
