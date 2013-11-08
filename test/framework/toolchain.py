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
Unit tests for toolchain support.

@author: Kenneth Hoste (Ghent University)
"""

import os
import re
from unittest import TestCase, TestLoader, main

import easybuild.tools.config as config
import easybuild.tools.modules as modules
import easybuild.tools.options as eboptions
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.tools.toolchain.utilities import search_toolchain
from test.framework.utilities import find_full_path

class ToolchainTest(TestCase):
    """ Baseclass for toolchain testcases """

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
        except error, err:
            self.assertTrue(re.search(regex, err.msg))

    def setUp(self):
        """Set up everything for a unit test."""
        # initialize configuration so config.get_modules_tool function works
        eb_go = eboptions.parse_options()
        config.init(eb_go.options, eb_go.get_options_by_section('config'))

        # start with a clean slate
        modules.modules_tool().purge()

        # make sure path with modules for testing is added to MODULEPATH
        self.orig_modpath = os.environ.get('MODULEPATH', '')
        os.environ['MODULEPATH'] = find_full_path(os.path.join('test', 'framework', 'modules'))

    def test_toolchain(self):
        """Test whether toolchain is initialized correctly."""
        ec_file = find_full_path(os.path.join('test', 'framework', 'easyconfigs', 'gzip-1.4.eb'))
        ec = EasyConfig(ec_file, validate=False)
        tc = ec.toolchain
        self.assertTrue('debug' in tc.options)

    def test_unknown_toolchain(self):
        """Test search_toolchain function for not available toolchains."""
        tc, all_tcs = search_toolchain("NOSUCHTOOLKIT")
        self.assertEqual(tc, None)
        self.assertTrue(len(all_tcs) > 0)  # list of available toolchains

    def test_goalf_toolchain(self):
        """Test for goalf toolchain."""
        name = "goalf"
        tc, _ = search_toolchain(name)
        self.assertEqual(tc.NAME, name)
        self.tc = tc(version="1.1.0-no-OFED")

    def test_get_variable_compilers(self):
        """Test get_variable function to obtain compiler variables."""
        tc_class, _ = search_toolchain("goalf")
        tc = tc_class(version="1.1.0-no-OFED")
        tc.prepare()

        cc = tc.get_variable('CC')
        self.assertEqual(cc, "gcc")
        cxx = tc.get_variable('CXX')
        self.assertEqual(cxx, "g++")
        f77 = tc.get_variable('F77')
        self.assertEqual(f77, "gfortran")
        f90 = tc.get_variable('F90')
        self.assertEqual(f90, "gfortran")
        mpicc = tc.get_variable('MPICC')
        self.assertEqual(mpicc, "mpicc")
        mpicxx = tc.get_variable('MPICXX')
        self.assertEqual(mpicxx, "mpicxx")
        mpif77 = tc.get_variable('MPIF77')
        self.assertEqual(mpif77, "mpif77")
        mpif90 = tc.get_variable('MPIF90')
        self.assertEqual(mpif90, "mpif90")

        ompi_cc = tc.get_variable('OMPI_CC')
        self.assertEqual(ompi_cc, "gcc")
        ompi_cxx = tc.get_variable('OMPI_CXX')
        self.assertEqual(ompi_cxx, "g++")
        ompi_f77 = tc.get_variable('OMPI_F77')
        self.assertEqual(ompi_f77, "gfortran")
        ompi_fc = tc.get_variable('OMPI_FC')
        self.assertEqual(ompi_fc, "gfortran")

    def test_get_variable_mpi_compilers(self):
        """Test get_variable function to obtain compiler variables."""
        tc_class, _ = search_toolchain("goalf")
        tc = tc_class(version="1.1.0-no-OFED")
        tc.set_options({'usempi': True})
        tc.prepare()

        cc = tc.get_variable('CC')
        self.assertEqual(cc, "mpicc")
        cxx = tc.get_variable('CXX')
        self.assertEqual(cxx, "mpicxx")
        f77 = tc.get_variable('F77')
        self.assertEqual(f77, "mpif77")
        f90 = tc.get_variable('F90')
        self.assertEqual(f90, "mpif90")

        mpicc = tc.get_variable('MPICC')
        self.assertEqual(mpicc, "mpicc")
        mpicxx = tc.get_variable('MPICXX')
        self.assertEqual(mpicxx, "mpicxx")
        mpif77 = tc.get_variable('MPIF77')
        self.assertEqual(mpif77, "mpif77")
        mpif90 = tc.get_variable('MPIF90')
        self.assertEqual(mpif90, "mpif90")

        ompi_cc = tc.get_variable('OMPI_CC')
        self.assertEqual(ompi_cc, "gcc")
        ompi_cxx = tc.get_variable('OMPI_CXX')
        self.assertEqual(ompi_cxx, "g++")
        ompi_f77 = tc.get_variable('OMPI_F77')
        self.assertEqual(ompi_f77, "gfortran")
        ompi_fc = tc.get_variable('OMPI_FC')
        self.assertEqual(ompi_fc, "gfortran")

    def test_get_variable_seq_compilers(self):
        """Test get_variable function to obtain compiler variables."""
        tc_class, _ = search_toolchain("goalf")
        tc = tc_class(version="1.1.0-no-OFED")
        tc.set_options({'usempi': True})
        tc.prepare()

        cc_seq = tc.get_variable('CC_SEQ')
        self.assertEqual(cc_seq, "gcc")
        cxx_seq = tc.get_variable('CXX_SEQ')
        self.assertEqual(cxx_seq, "g++")
        f77_seq = tc.get_variable('F77_SEQ')
        self.assertEqual(f77_seq, "gfortran")
        f90_seq = tc.get_variable('F90_SEQ')
        self.assertEqual(f90_seq, "gfortran")

    def test_get_variable_libs_list(self):
        """Test get_variable function to obtain list of libraries."""
        tc_class, _ = search_toolchain("goalf")
        tc = tc_class(version="1.1.0-no-OFED")
        tc.prepare()

        ldflags = tc.get_variable('LDFLAGS', typ=list)
        self.assertTrue(isinstance(ldflags, list))
        if len(ldflags) > 0:
            self.assertTrue(isinstance(ldflags[0], basestring))

    def test_validate_pass_by_value(self):
        """
        Check that elements of variables are passed by value, not by reference,
        which is required to ensure correctness.
        """
        tc_class, _ = search_toolchain("goalf")
        tc = tc_class(version="1.1.0-no-OFED")
        tc.prepare()

        pass_by_value = True
        ids = []
        for k, v in tc.variables.items():
            for x in v:
                idx = id(x)
                if not idx in ids:
                    ids.append(idx)
                else:
                    pass_by_value = False
                    break
            if not pass_by_value:
                break

        self.assertTrue(pass_by_value)

    def test_optimization_flags(self):
        """Test whether optimization flags are being set correctly."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FFLAGS', 'F90FLAGS']
        tc_class, _ = search_toolchain("goalf")

        # check default optimization flag (e.g. -O2)
        tc = tc_class(version="1.1.0-no-OFED")
        tc.set_options({})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            self.assertTrue(tc.COMPILER_SHARED_OPTION_MAP['defaultopt'] in flags)

        # check other optimization flags
        for opt in ['noopt', 'lowopt', 'opt']:
            tc = tc_class(version="1.1.0-no-OFED")
            for enable in [True, False]:
                tc.set_options({opt: enable})
                tc.prepare()
                for var in flag_vars:
                    flags = tc.get_variable(var)
                    if enable:
                        self.assertTrue(tc.COMPILER_SHARED_OPTION_MAP[opt] in flags)
                    else:
                        self.assertTrue(tc.COMPILER_SHARED_OPTION_MAP[opt] in flags)

    def test_optimization_flags_combos(self):
        """Test whether combining optimization levels works as expected."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FFLAGS', 'F90FLAGS']
        tc_class, _ = search_toolchain("goalf")

        # check combining of optimization flags (doesn't make much sense)
        # lowest optimization should always be picked
        tc = tc_class(version="1.1.0-no-OFED")
        tc.set_options({'lowopt': True, 'opt':True})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            flag = '-%s' % tc.COMPILER_SHARED_OPTION_MAP['lowopt']
            self.assertTrue(flag in flags)

        tc = tc_class(version="1.1.0-no-OFED")
        tc.set_options({'noopt': True, 'lowopt':True})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            flag = '-%s' % tc.COMPILER_SHARED_OPTION_MAP['noopt']
            self.assertTrue(flag in flags)

        tc = tc_class(version="1.1.0-no-OFED")
        tc.set_options({'noopt':True, 'lowopt': True, 'opt':True})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            flag = '-%s' % tc.COMPILER_SHARED_OPTION_MAP['noopt']
            self.assertTrue(flag in flags)

    def test_misc_flags_shared(self):
        """Test whether shared compiler flags are set correctly."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FFLAGS', 'F90FLAGS']
        tc_class, _ = search_toolchain("goalf")

        # setting option should result in corresponding flag to be set (shared options)
        for opt in ['pic', 'verbose', 'debug', 'static', 'shared']:
            for enable in [True, False]:
                tc = tc_class(version="1.1.0-no-OFED")
                tc.set_options({opt: enable})
                tc.prepare()
                # we need to make sure we check for flags, not letter (e.g. 'v' vs '-v')
                flag = '-%s' % tc.COMPILER_SHARED_OPTION_MAP[opt]
                for var in flag_vars:
                    flags = tc.get_variable(var)
                    if enable:
                        self.assertTrue(flag in flags, "%s: True means %s in %s" % (opt, flag, flags))
                    else:
                        self.assertTrue(flag not in flags, "%s: False means no %s in %s" % (opt, flag, flags))

    def test_misc_flags_unique(self):
        """Test whether unique compiler flags are set correctly."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FFLAGS', 'F90FLAGS']
        tc_class, _ = search_toolchain("goalf")

        # setting option should result in corresponding flag to be set (unique options)
        for opt in ['unroll', 'optarch', 'openmp']:
            for enable in [True, False]:
                tc = tc_class(version="1.1.0-no-OFED")
                tc.set_options({opt: enable})
                tc.prepare()
                flag = '-%s' % tc.COMPILER_UNIQUE_OPTION_MAP[opt]
                for var in flag_vars:
                    flags = tc.get_variable(var)
                    if enable:
                        self.assertTrue(flag in flags, "%s: True means %s in %s" % (opt, flag, flags))
                    else:
                        self.assertTrue(flag not in flags, "%s: False means no %s in %s" % (opt, flag, flags))

    def test_misc_flags_unique_fortran(self):
        """Test whether unique Fortran compiler flags are set correctly."""

        flag_vars = ['FFLAGS', 'F90FLAGS']
        tc_class, _ = search_toolchain("goalf")

        # setting option should result in corresponding flag to be set (Fortran unique options)
        for opt in ['i8', 'r8']:
            for enable in [True, False]:
                tc = tc_class(version="1.1.0-no-OFED")
                tc.set_options({opt: enable})
                tc.prepare()
                flag = '-%s' % tc.COMPILER_UNIQUE_OPTION_MAP[opt]
                for var in flag_vars:
                    flags = tc.get_variable(var)
                    if enable:
                        self.assertTrue(flag in flags, "%s: True means %s in %s" % (opt, flag, flags))
                    else:
                        self.assertTrue(flag not in flags, "%s: False means no %s in %s" % (opt, flag, flags))

    def test_precision_flags(self):
        """Test whether precision flags are being set correctly."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FFLAGS', 'F90FLAGS']
        tc_class, _ = search_toolchain("goalf")

        # check default precision flag
        tc = tc_class(version="1.1.0-no-OFED")
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            val = ' '.join(['-%s' % f for f in tc.COMPILER_UNIQUE_OPTION_MAP['defaultprec']])
            self.assertTrue(val in flags)

        # check other precision flags
        for opt in ['strict', 'precise', 'loose', 'veryloose']:
            for enable in [True, False]:
                tc = tc_class(version="1.1.0-no-OFED")
                tc.set_options({opt: enable})
                tc.prepare()
                val = ' '.join(['-%s' % f for f in tc.COMPILER_UNIQUE_OPTION_MAP[opt]])
                for var in flag_vars:
                    flags = tc.get_variable(var)
                    if enable:
                        self.assertTrue(val in flags)
                    else:
                        self.assertTrue(val not in flags)

    def test_cgoolf_toolchain(self):
        """Test for cgoolf toolchain."""
        name = "cgoolf"
        tc_class, _ = search_toolchain(name)
        self.assertEqual(tc_class.NAME, name)
        tc = tc_class(version="1.1.6")
        tc.prepare()

        self.assertEqual(tc.get_variable('CC'), 'clang')
        self.assertEqual(tc.get_variable('CXX'), 'clang++')
        self.assertEqual(tc.get_variable('F77'), 'gfortran')
        self.assertEqual(tc.get_variable('F90'), 'gfortran')

    def test_comp_family(self):
        """Test determining compiler family."""

        tc_class, _ = search_toolchain("goalf")
        tc = tc_class(version="1.1.0-no-OFED")
        tc.prepare()

        self.assertEqual(tc.comp_family(), "GCC")

    def test_goolfc(self):
        """Test whether goolfc is handled properly."""

        tc_class, _ = search_toolchain("goolfc")
        tc = tc_class(version="1.3.12")
        opts = {'cuda_gencode': ['arch=compute_35,code=sm_35', 'arch=compute_10,code=compute_10']}
        tc.set_options(opts)
        tc.prepare()

        nvcc_flags = r' '.join([
            r'-Xcompiler="-O2 -march=native"',
            # the use of -lcudart in -Xlinker is a bit silly but hard to avoid
            r'-Xlinker=".* -lm -lcudart -lpthread"',
            r' '.join(["-gencode %s" % x for x in opts['cuda_gencode']]),
        ])

        self.assertEqual(tc.get_variable('CUDA_CC'), 'nvcc -ccbin="g++"')
        self.assertEqual(tc.get_variable('CUDA_CXX'), 'nvcc -ccbin="g++"')
        # -L/path flags will not be there if the software installations are not available
        val = tc.get_variable('CUDA_CFLAGS')
        self.assertTrue(re.compile(nvcc_flags).match(val), "'%s' matches '%s'" % (val, nvcc_flags))
        val = tc.get_variable('CUDA_CXXFLAGS')
        self.assertTrue(re.compile(nvcc_flags).match(val), "'%s' matches '%s'" % (val, nvcc_flags))

        # check compiler prefixes
        self.assertEqual(tc.comp_family(prefix='CUDA'), "CUDA")

        # check CUDA runtime lib
        self.assertTrue("-lcudart" in tc.get_variable('LIBS'))

    def tearDown(self):
        """Cleanup."""
        # purge any loaded modules, restore $MODULEPATH
        modules.modules_tool().purge()
        os.environ['MODULEPATH'] = self.orig_modpath
        # reinitialize modules tool after touching $MODULEPATH
        modules.modules_tool()

def suite():
    """ return all the tests"""
    return TestLoader().loadTestsFromTestCase(ToolchainTest)

if __name__ == '__main__':
    main()
