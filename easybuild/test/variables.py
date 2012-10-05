##
# Copyright 2012 Toon Willems
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
from easybuild.tools.variables import CommaList, CommandFlagList, ListOfLists, StrList, Variables
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

        v['BAR'] = range(3)
        self.assertEqual(str(v), "{'BAR': [[], [0, 1, 2]]}")
        self.assertEqual(str(v['BAR']), " 0 1 2")

        v['BAR'].append(StrList(range(10, 12)))
        self.assertEqual(str(v['BAR']), " 0 1 2 10 11")

        v.append_el('BAR', 20)
        self.assertEqual(str(v['BAR']), " 0 1 2 10 11 20")

        v['FOO'] = range(3)
        self.assertEqual(str(v['FOO']), " 0,1,2")   

        l = get_linker_endgroup()
        self.assertEqual(str(l), "-Wl,--end-group")

        l2 = get_linker_startgroup({'static':'-Bstatic',
                                    'dynamic':'-Bdynamic',
                                   })
        l2.toggle_static()
        self.assertEqual(str(l2), "-Wl,--start-group -Wl,-Bstatic")

        l2.append("foo")
        l2.toggle_dynamic()
        self.assertEqual(str(l2), "-Wl,--start-group -Wl,-Bstatic -foo -Wl,-Bdynamic")

        cmd = CommandFlagList(["foo", "bar", "baz"])
        self.assertEqual(str(cmd), "-foo -bar -baz")

def suite():
    """ return all the tests"""
    return TestSuite([VariablesTest()])
