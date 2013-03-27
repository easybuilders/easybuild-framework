# #
# Copyright 2012-2013 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
# #
"""
Unit tests for tools/variables.py.

@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""

import re

from unittest import TestCase, TestSuite, main
from easybuild.tools.variables import CommaList, StrList, Variables
from easybuild.tools.toolchain.variables import CommandFlagList


class VariablesTest(TestCase):
    """ Baseclass for easyblock testcases """

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
        except error, err:
            self.assertTrue(re.search(regex, err.msg))

    def runTest(self):
        class TestVariables(Variables):
            MAP_CLASS = {'FOO':CommaList}

        v = TestVariables()
        self.assertEqual(str(v), "{}")

        # DEFAULTCLASS is StrList
        v['BAR'] = range(3)
        self.assertEqual(str(v), "{'BAR': [[0, 1, 2]]}")
        self.assertEqual(str(v['BAR']), "0 1 2")

        v['BAR'].append(StrList(range(10, 12)))
        self.assertEqual(str(v['BAR']), "0 1 2 10 11")

        v.nappend('BAR', 20)
        self.assertEqual(str(v['BAR']), "0 1 2 10 11 20")

        v.nappend_el('BAR', 30, idx= -2)
        self.assertEqual(str(v), "{'BAR': [[0, 1, 2], [10, 11, 30], [20]]}")
        self.assertEqual(str(v['BAR']), '0 1 2 10 11 30 20')

        v['FOO'] = range(3)
        self.assertEqual(str(v['FOO']), "0,1,2")

        v['BARSTR'] = 'XYZ'
        self.assertEqual(v['BARSTR'].__repr__(), "[['XYZ']]")

        v['BARINT'] = 0
        self.assertEqual(v['BARINT'].__repr__(), "[[0]]")

        v.join('BAR2', 'FOO', 'BARINT')
        self.assertEqual(str(v['BAR2']), "0,1,2 0")

        self.assertRaises(Exception, v.join, 'BAZ', 'DOESNOTEXIST')

        cmd = CommandFlagList(["gcc", "bar", "baz"])
        self.assertEqual(str(cmd), "gcc -bar -baz")

def suite():
    """ return all the tests"""
    return TestSuite([VariablesTest()])

if __name__ == '__main__':
    main()
