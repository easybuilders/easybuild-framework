# #
# Copyright 2012-2018 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
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
Unit tests for tools/toolchain/variables.py.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import sys

from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

from easybuild.tools.toolchain.toolchainvariables import ToolchainVariables
from easybuild.tools.toolchain.variables import CommandFlagList


class ToolchainVariablesTest(EnhancedTestCase):
    """ Baseclass for toolchain variables testcases """

    def test_toolchainvariables(self):
        # DEFAULTCLASS is FlagList
        class TCV(ToolchainVariables):
            LINKER_TOGGLE_START_STOP_GROUP = {
                'start': '-Xstart',
                'stop': '-Xstop',
            }
            LINKER_TOGGLE_STATIC_DYNAMIC = {
                'static': '-Bstatic',
                'dynamic': '-Bdynamic',
            }

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
        x.POSITION = -5  # sanitize will reorder, default POSITION is 0
        self.assertEqual(tcv['FLAGS'].__repr__(), "[['one', 'two'], ['three', 'four']]")
        tcv['FLAGS'].sanitize()  # sort on position, called by __str__ also
        self.assertEqual(tcv['FLAGS'].__repr__(), "[['three', 'four'], ['one', 'two']]")
        self.assertEqual(str(tcv['FLAGS']), "-three -four -one -two")

        # LIBBLAS is a LibraryList
        lib = tcv.nappend('LIBBLAS', ['d', 'e', 'f'])
        lib.POSITION = 5  # relative position after default
        lib = tcv.nappend('LIBBLAS', ['a', 'b', 'c'])
        tcv.add_begin_end_linkerflags(lib, toggle_startstopgroup=True, toggle_staticdynamic=True)
        self.assertEqual(lib.BEGIN.__repr__(), "['-Bstatic', '-Xstart']")
        self.assertEqual(tcv['LIBBLAS'].__repr__(), "[['d', 'e', 'f'], ['a', 'b', 'c']]")
        # str calls sanitize
        self.assertEqual(str(tcv['LIBBLAS']),
                         "-Wl,-Bstatic -Wl,-Xstart -la -lb -lc -Wl,-Xstop -Wl,-Bdynamic -ld -le -lf")
        # sanitize is on self
        self.assertEqual(tcv['LIBBLAS'].__repr__(), "[['a', 'b', 'c'], ['d', 'e', 'f']]")

        # make copies for later
        copy_blas = tcv['LIBBLAS'].copy()
        copy_blas_2 = tcv['LIBBLAS'].copy()
        self.assertEqual(str(tcv['LIBBLAS']), str(copy_blas))

        # packed_linker
        tcv.try_function_on_element('set_packed_linker_options')  # don't use it like this (this is internal)
        new_res = "-Wl,-Bstatic,-Xstart,-la,-lb,-lc,-Xstop,-Bdynamic -ld -le -lf"
        self.assertEqual(str(tcv['LIBBLAS']), new_res)

        # run it directly on copy of LIBBLAS, not through the tcv instance
        copy_blas.try_function_on_element('set_packed_linker_options')
        self.assertEqual(str(copy_blas), new_res)

        # arbitrary example
        kwargs = {
            'prefix': '_P_',
            'prefix_begin_end': '_p_',
            'separator': ':',
            'separator_begin_end': ';',
        }
        copy_blas.try_function_on_element('set_packed_linker_options', kwargs=kwargs)
        self.assertEqual(str(copy_blas),
                         '_p_;-Bstatic;-Xstart:_P_a:_P_b:_P_c:-Xstop;-Bdynamic -ld -le -lf')

        kwargs = {
            'prefix': '_P_',
            'prefix_begin_end': '_p_',
            'separator': ':',
            'separator_begin_end': ';',
        }
        copy_blas.try_function_on_element('change', kwargs=kwargs)
        self.assertEqual(str(copy_blas),
                         '_p_;_p_-Bstatic;_p_-Xstart:_P_a:_P_b:_P_c:_p_-Xstop;_p_-Bdynamic _P_d:_P_e:_P_f')

        # e.g. numpy and mkl blas
        # -Wl:-Bstatic,-Wl:--start-group,mkl_intel_lp64,mkl_intel_thread,mkl_core,-Wl:--end-group,-Wl:-Bdynamic,iomp5
        kwargs = {
                  'prefix':'',
                  'prefix_begin_end':'-Wl:',
                  'separator':',',
                  'separator_begin_end':',',
                  }
        copy_blas_2.try_function_on_element('change', kwargs=kwargs)
        copy_blas_2.SEPARATOR = ','

        self.assertEqual(str(copy_blas_2),
                         '-Wl:-Bstatic,-Wl:-Xstart,a,b,c,-Wl:-Xstop,-Wl:-Bdynamic,d,e,f')

        # test try remove
        copy_blas.try_remove(['a', 'f'])
        self.assertEqual(copy_blas.__repr__(), "[['b', 'c'], ['d', 'e']]")

        # test join
        tcv.join('LIBLAPACK', 'LIBBLAS')
        self.assertEqual(tcv['LIBLAPACK'].__repr__(), "[['a', 'b', 'c'], ['d', 'e', 'f']]")
        lib = tcv.nappend('LIBLAPACK', ['g', 'h'])
        tcv.add_begin_end_linkerflags(lib, toggle_startstopgroup=True)
        self.assertEqual(tcv['LIBLAPACK'].__repr__(), "[['a', 'b', 'c'], ['d', 'e', 'f'], ['g', 'h']]")
        # sanitize will reorder wrt POSISTION but not join the start/stop group (blas has also statc/dynamic)
        tcv['LIBLAPACK'].sanitize()
        self.assertEqual(tcv['LIBLAPACK'].__repr__(), "[['a', 'b', 'c'], ['g', 'h'], ['d', 'e', 'f']]")

        # run both toggle, not just static/dynamic one.
        tcv.add_begin_end_linkerflags(lib, toggle_startstopgroup=True, toggle_staticdynamic=True)
        # sanitize will reorder wrt POSISTION and join the start/stop group
        tcv['LIBLAPACK'].sanitize()
        self.assertEqual(tcv['LIBLAPACK'].__repr__(), "[['a', 'b', 'c', 'g', 'h'], ['d', 'e', 'f']]")
        self.assertEqual(str(tcv['LIBLAPACK']), "-Wl,-Bstatic,-Xstart,-la,-lb,-lc,-lg,-lh,-Xstop,-Bdynamic -ld -le -lf")

        tcv.nappend('MPICH_CC', 'icc', var_class=CommandFlagList)
        self.assertEqual(str(tcv['MPICH_CC']), "icc")
        tcv.nappend('MPICH_CC', 'test')
        self.assertEqual(str(tcv['MPICH_CC']), "icc -test")


def suite():
    """ return all the tests"""
    return TestLoaderFiltered().loadTestsFromTestCase(ToolchainVariablesTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
