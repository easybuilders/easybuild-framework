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
from easybuild.tools.toolchain.variables import ToolchainVariables


class ToolchainVariablesTest(TestCase):
    """ Baseclass for easyblock testcases """

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
        except error, err:
            self.assertTrue(re.search(regex, err.msg))

    def runTest(self):
        ## DEFAULTCLASS is FlagList
        tcv = ToolchainVariables()
        self.assertEqual(str(tcv), "{}")

        tcv['CC'] = 'gcc'
        self.assertEqual(str(tcv), "{'CC': [['gcc']]}")
        self.assertEqual(str(tcv['CC']), "gcc")

        tcv.join('MPICC', 'CC')
        self.assertEqual(str(tcv['MPICC']), "gcc")

        tcv['F90'] = ['gfortran', 'foo', 'bar']
        self.assertEqual(tcv['F90'].__repr__(), "[['gfortran', 'foo', 'bar']]")
        self.assertEqual(str(tcv['F90']), "gfortran -foo -bar")

        tcv.nappend('FLAGS', ['one', 'two'])
        x = tcv.nappend('FLAGS', ['three', 'four'])
        x.POSITION = -5 ## sanitize will reorder, default POSITION is 0
        self.assertEqual(tcv['FLAGS'].__repr__(), "[['one', 'two'], ['three', 'four']]")
        self.assertEqual(str(tcv['FLAGS']), "-three -four -one -two")


def suite():
    """ return all the tests"""
    return TestSuite([ToolchainVariablesTest()])
