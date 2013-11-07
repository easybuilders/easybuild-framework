"""
Unit tests for easyconfig/parser.py

@author: Stijn De Weirdt (Ghent University)
"""
import os

from unittest import TestCase, TestLoader, main

from easybuild.framework.easyconfig.format.version import EasyVersion
from easybuild.framework.easyconfig.parser import EasyConfigParser

from vsc.utils.fancylogger import setLogLevelDebug, logToScreen


TESTDIRBASE = os.path.join(os.path.dirname(__file__), 'easyconfigs')


class EasyConfigParserTest(TestCase):
    """Test the parser"""

    def test_v10(self):
        ecp = EasyConfigParser(os.path.join(TESTDIRBASE, 'v1.0', 'GCC-4.6.3.eb'))

        self.assertEqual(ecp._formatter.VERSION, EasyVersion('1.0'))

        ec = ecp.get_config_dict()

        self.assertEqual(ec['toolchain'], {'name': 'dummy', 'version': 'dummy'})
        self.assertEqual(ec['name'], 'GCC')
        self.assertEqual(ec['version'], '4.6.3')

    def test_v20(self):
        fn = os.path.join(TESTDIRBASE, 'v2.0', 'GCC.eb')
        ecp = EasyConfigParser(fn)

        formatter = ecp._formatter
        self.assertEqual(formatter.VERSION, EasyVersion('2.0'))

        self.assertTrue('name' in formatter.pyheader_localvars)
        self.assertFalse('version' in formatter.pyheader_localvars)
        self.assertFalse('toolchain' in formatter.pyheader_localvars)

        self.assertRaises(NotImplementedError, ecp.get_config_dict)

        # this should be ok: ie the default values
        # self.assertEqual(ec['toolchain'], {'name': 'dummy', 'version': 'dummy'})
        # self.assertEqual(ec['name'], 'GCC')
        # self.assertEqual(ec['version'], '4.6.3')

    def test_v20_extra(self):
        fn = os.path.join(TESTDIRBASE, 'v2.0', 'doesnotexist.eb')
        ecp = EasyConfigParser(fn)

        formatter = ecp._formatter
        self.assertEqual(formatter.VERSION, EasyVersion('2.0'))

        self.assertTrue('name' in formatter.pyheader_localvars)
        self.assertFalse('version' in formatter.pyheader_localvars)
        self.assertFalse('toolchain' in formatter.pyheader_localvars)

        self.assertRaises(NotImplementedError, ecp.get_config_dict)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(EasyConfigParserTest)


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
