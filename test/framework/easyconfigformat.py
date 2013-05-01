"""
Unit tests for easyconfig/format/format.py

@author: Stijn De Weirdt (Ghent University)
"""
import os

from easybuild.framework.easyconfig.format.format import FORMAT_VERSION_HEADER_TEMPLATE, FORMAT_VERSION_REGEXP
from unittest import TestCase, TestSuite, main


class EasyConfigParserTest(TestCase):
    """Test the parser"""

    def test_parser_version_regex(self):
        """Trivial parser test"""
        version = {'major':1, 'minor':0}
        txt = FORMAT_VERSION_HEADER_TEMPLATE % version
        res = FORMAT_VERSION_REGEXP.search(txt).groupdict()
        self.assertEqual(version['major'], int(res['major']))
        self.assertEqual(version['minor'], int(res['minor']))


if __name__ == '__main__':
    main()
