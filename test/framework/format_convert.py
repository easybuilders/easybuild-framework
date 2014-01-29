"""
Unit tests for easyconfig/format/convert.py

@author: Stijn De Weirdt (Ghent University)
"""
from easybuild.framework.easyconfig.format.convert import get_convert_class, Convert, ListStr
from unittest import TestCase, TestLoader, main


class ConvertTest(TestCase):
    """Test the license"""

    def test_subclasses(self):
        """Check if a number of common convertmethods can be found"""
        self.assertEqual(get_convert_class('ListStr'), ListStr)

    def test_liststr(self):
        """Test list of strings"""
        txt = 'a,b'
        self.assertEqual(txt.split(Convert.SEPARATOR_LIST), ListStr(txt).data)

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(ConvertTest)


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
