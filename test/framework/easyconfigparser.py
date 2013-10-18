"""
Unit tests for easyconfig/parser.py

@author: Stijn De Weirdt (Ghent University)
"""
import os

from easybuild.framework.easyconfig.parser import EasyConfigParser
from unittest import TestCase, TestLoader, main

from vsc.utils.fancylogger import setLogLevelDebug, logToScreen


TESTDIRBASE = os.path.join(os.path.dirname(__file__), 'easyconfigs')


class EasyConfigParserTest(TestCase):
    """Test the parser"""

    def test_v10(self):
        ecp = EasyConfigParser(os.path.join(TESTDIRBASE, 'v1.0', 'GCC-4.6.3.eb'))
        ec = ecp.get_config_dict()

    def test_v20(self):
        ecp = EasyConfigParser(os.path.join(TESTDIRBASE, 'v2.0', 'GCC.eb'))
        ec = ecp.get_config_dict()


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(EasyConfigParserTest)


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
