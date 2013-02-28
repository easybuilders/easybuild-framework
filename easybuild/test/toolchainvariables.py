##
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
##
"""
Unit tests for tools/toolchain/variables.py.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import re

from unittest import TestCase, TestSuite, main
from easybuild.tools.toolchain.variables import ToolchainVariables
from easybuild.tools.variables import CommandFlagList

class ToolchainVariablesTest(TestCase):
    """ Baseclass for toolchain variables testcases """

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
        except error, err:
            self.assertTrue(re.search(regex, err.msg))

    def runTest(self):
        ## DEFAULTCLASS is FlagList
        class TCV(ToolchainVariables):
            LINKER_TOGGLE_START_STOP_GROUP = {'start': '-Xstart',
                                              'stop':'-Xstop', }
        tcv = TCV()
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
        tcv['FLAGS'].sanitize() # sort on position, called by __str__ also
        self.assertEqual(tcv['FLAGS'].__repr__(), "[['three', 'four'], ['one', 'two']]")
        self.assertEqual(str(tcv['FLAGS']), "-three -four -one -two")

        ## LIBBLAS is a LibraryList
        lib = tcv.nappend('LIBBLAS', ['d', 'e', 'f'])
        lib.POSITION = 5 ## relative position after default
        lib = tcv.nappend('LIBBLAS', ['a', 'b', 'c'])
        tcv.add_begin_end_linkerflags(lib, toggle_startstopgroup=True)
        self.assertEqual(lib.BEGIN.__repr__(), "['-Xstart']")
        self.assertEqual(tcv['LIBBLAS'].__repr__(), "[['d', 'e', 'f'], ['a', 'b', 'c']]")
        ## str calls sanitize
        self.assertEqual(str(tcv['LIBBLAS']), "-Wl,-Xstart -la -lb -lc -Wl,-Xstop -ld -le -lf")
        ## sanitize is on self
        self.assertEqual(tcv['LIBBLAS'].__repr__(), "[['a', 'b', 'c'], ['d', 'e', 'f']]")

        ## packed_linker
        tcv.try_function_el('set_packed_linker_options') ## don't use it like this (this is internal)
        self.assertEqual(str(tcv['LIBBLAS']), "-Wl,-Xstart,-la,-lb,-lc,-Xstop -ld -le -lf")

        tcv.join('LIBLAPACK', 'LIBBLAS')
        self.assertEqual(tcv['LIBLAPACK'].__repr__(), "[['a', 'b', 'c'], ['d', 'e', 'f']]")
        lib = tcv.nappend('LIBLAPACK', ['g', 'h'])
        tcv.add_begin_end_linkerflags(lib, toggle_startstopgroup=True)
        self.assertEqual(tcv['LIBLAPACK'].__repr__(), "[['a', 'b', 'c'], ['d', 'e', 'f'], ['g', 'h']]")
        ## sanitize will reorder wrt POSISTION and join the start/stop group
        tcv['LIBLAPACK'].sanitize()
        self.assertEqual(tcv['LIBLAPACK'].__repr__(), "[['a', 'b', 'c', 'g', 'h'], ['d', 'e', 'f']]")
        self.assertEqual(str(tcv['LIBLAPACK']), "-Wl,-Xstart,-la,-lb,-lc,-lg,-lh,-Xstop -ld -le -lf")

        tcv.nappend('MPICH_CC', 'icc', var_class=CommandFlagList)
        self.assertEqual(str(tcv['MPICH_CC']), "icc")
        tcv.nappend('MPICH_CC', 'test')
        self.assertEqual(str(tcv['MPICH_CC']), "icc -test")

def suite():
    """ return all the tests"""
    return TestSuite([ToolchainVariablesTest()])

if __name__ == '__main__':
    main()
