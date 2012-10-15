##
# Copyright 2012 Kenneth Hoste
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
##
import os
import re

from unittest import TestCase, TestSuite
from easybuild.tools.variables import CommaList, CommandFlagList, FlagList, ListOfLists, StrList, Variables
from easybuild.tools.variables import get_linker_endgroup, get_linker_startgroup


class VariablesTest(TestCase):
    """ Baseclass for easyblock testcases """

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
        except error, err:
            self.assertTrue(re.search(regex, err.msg))

    def runTest(self):

        class TestListOfLists(ListOfLists):
            MAP_CLASS = {'FOO':CommaList}

        class TestVariables(Variables):
            MAP_LISTCLASS = {TestListOfLists : ['FOO']}

        v = TestVariables()
        self.assertEqual(str(v), "{}")

        ## DEFAULTCLASS is StrList
        v['BAR'] = range(3)
        self.assertEqual(str(v), "{'BAR': [[], [0, 1, 2]]}")
        self.assertEqual(str(v['BAR']), "0 1 2")

        v['BAR'].append(StrList(range(10, 12)))
        self.assertEqual(str(v['BAR']), "0 1 2 10 11")

        v.nappend('BAR', 20)
        self.assertEqual(str(v['BAR']), "0 1 2 10 11 20")

        v.nappend_el('BAR', 30, idx= -2)
        self.assertEqual(str(v), "{'BAR': [[], [0, 1, 2], [10, 11, 30], [20]]}")
        self.assertEqual(str(v['BAR']), '0 1 2 10 11 30 20')

        v['FOO'] = range(3)
        self.assertEqual(str(v['FOO']), "0,1,2")

        v['BARSTR'] = 'XYZ'
        self.assertEqual(v['BARSTR'].__repr__(), "[[], ['XYZ']]")

        v['BARINT'] = 0
        self.assertEqual(v['BARINT'].__repr__(), "[[], [0]]")

        le = get_linker_endgroup()
        self.assertEqual(str(le), "-Wl,--end-group")

        static_dynamic = {
                          'static': '-Bstatic',
                          'dynamic': '-Bdynamic'
                         }

        ls = get_linker_startgroup(static_dynamic)
        ls.toggle_static()
        self.assertEqual(str(ls), "-Wl,--start-group -Wl,-Bstatic")

        fs = FlagList(["foo", "bar"])
        le.set_static_dynamic(static_dynamic)
        le.toggle_dynamic()
        all_flags = ListOfLists([ls, fs, le])
        self.assertEqual(str(all_flags), "-Wl,--start-group -Wl,-Bstatic -foo -bar -Wl,--end-group -Wl,-Bdynamic")

        cmd = CommandFlagList(["gcc", "bar", "baz"])
        self.assertEqual(str(cmd), "gcc -bar -baz")

def suite():
    """ return all the tests"""
    return TestSuite([VariablesTest()])
