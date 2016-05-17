##
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
import shutil
import tempfile
from distutils.version import LooseVersion
from unittest import TestLoader, main
from test.framework.utilities import EnhancedTestCase, find_full_path, init_config

import easybuild.tools.build_log
import easybuild.tools.modules as modules
import easybuild.tools.toolchain.compiler
from easybuild.framework.easyconfig.easyconfig import EasyConfig, ActiveMNS
from easybuild.tools import systemtools as st
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import write_file
from easybuild.tools.toolchain.utilities import get_toolchain, search_toolchain

easybuild.tools.toolchain.compiler.systemtools.get_compiler_family = lambda: st.POWER


class ToolchainTest(EnhancedTestCase):
    """ Baseclass for toolchain testcases """

    def get_toolchain(self, name, version=None):
        """Get a toolchain object instance to test with."""
        tc_class, _ = search_toolchain(name)
        self.assertEqual(tc_class.NAME, name)
        tc = tc_class(version=version, mns=ActiveMNS(), modtool=self.modtool)
        return tc

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
        self.get_toolchain("goalf", version="1.1.0-no-OFED")

    def test_get_variable_dummy_toolchain(self):
        """Test get_variable on dummy toolchain"""
        tc = self.get_toolchain('dummy', version='dummy')
        tc.prepare()
        self.assertEqual(tc.get_variable('CC'), '')
        self.assertEqual(tc.get_variable('CXX', typ=str), '')
        self.assertEqual(tc.get_variable('CFLAGS', typ=list), [])

        tc = self.get_toolchain('dummy', version='')
        tc.prepare()
        self.assertEqual(tc.get_variable('CC'), '')
        self.assertEqual(tc.get_variable('CXX', typ=str), '')
        self.assertEqual(tc.get_variable('CFLAGS', typ=list), [])

    def test_get_variable_compilers(self):
        """Test get_variable function to obtain compiler variables."""
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.prepare()

        self.assertEqual(tc.get_variable('CC'), 'gcc')
        self.assertEqual(tc.get_variable('CXX'), 'g++')
        self.assertEqual(tc.get_variable('F77'), 'gfortran')
        self.assertEqual(tc.get_variable('F90'), 'gfortran')
        self.assertEqual(tc.get_variable('FC'), 'gfortran')

        self.assertEqual(tc.get_variable('MPICC'), 'mpicc')
        self.assertEqual(tc.get_variable('MPICXX'), 'mpicxx')
        # OpenMPI 1.4.5, so old MPI compiler wrappers for Fortran
        self.assertEqual(tc.get_variable('MPIF77'), 'mpif77')
        self.assertEqual(tc.get_variable('MPIF90'), 'mpif90')
        self.assertEqual(tc.get_variable('MPIFC'), 'mpif90')

        self.assertEqual(tc.get_variable('OMPI_CC'), 'gcc')
        self.assertEqual(tc.get_variable('OMPI_CXX'), 'g++')
        self.assertEqual(tc.get_variable('OMPI_F77'), 'gfortran')
        self.assertEqual(tc.get_variable('OMPI_FC'), 'gfortran')

    def test_get_variable_mpi_compilers(self):
        """Test get_variable function to obtain compiler variables."""
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.set_options({'usempi': True})
        tc.prepare()

        self.assertEqual(tc.get_variable('CC'), 'mpicc')
        self.assertEqual(tc.get_variable('CXX'), 'mpicxx')
        # OpenMPI 1.4.5, so old MPI compiler wrappers for Fortran
        self.assertEqual(tc.get_variable('F77'), 'mpif77')
        self.assertEqual(tc.get_variable('F90'), 'mpif90')
        self.assertEqual(tc.get_variable('FC'), 'mpif90')

        self.assertEqual(tc.get_variable('MPICC'), 'mpicc')
        self.assertEqual(tc.get_variable('MPICXX'), 'mpicxx')
        self.assertEqual(tc.get_variable('MPIF77'), 'mpif77')
        self.assertEqual(tc.get_variable('MPIF90'), 'mpif90')
        self.assertEqual(tc.get_variable('MPIFC'), 'mpif90')

        self.assertEqual(tc.get_variable('OMPI_CC'), 'gcc')
        self.assertEqual(tc.get_variable('OMPI_CXX'), 'g++')
        self.assertEqual(tc.get_variable('OMPI_F77'), 'gfortran')
        self.assertEqual(tc.get_variable('OMPI_FC'), 'gfortran')

    def test_get_variable_seq_compilers(self):
        """Test get_variable function to obtain compiler variables."""
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.set_options({'usempi': True})
        tc.prepare()

        self.assertEqual(tc.get_variable('CC_SEQ'), 'gcc')
        self.assertEqual(tc.get_variable('CXX_SEQ'), 'g++')
        self.assertEqual(tc.get_variable('F77_SEQ'), 'gfortran')
        self.assertEqual(tc.get_variable('F90_SEQ'), 'gfortran')
        self.assertEqual(tc.get_variable('FC_SEQ'), 'gfortran')

    def test_get_variable_libs_list(self):
        """Test get_variable function to obtain list of libraries."""
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
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
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
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

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']

        # check default optimization flag (e.g. -O2)
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.set_options({})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            self.assertTrue(tc.COMPILER_SHARED_OPTION_MAP['defaultopt'] in flags)

        # check other optimization flags
        for opt in ['noopt', 'lowopt', 'opt']:
            tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
            for enable in [True, False]:
                tc.set_options({opt: enable})
                tc.prepare()
                for var in flag_vars:
                    flags = tc.get_variable(var)
                    if enable:
                        self.assertTrue(tc.COMPILER_SHARED_OPTION_MAP[opt] in flags)
                    else:
                        self.assertTrue(tc.COMPILER_SHARED_OPTION_MAP[opt] in flags)
                self.modtool.purge()

    def test_optimization_flags_combos(self):
        """Test whether combining optimization levels works as expected."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']

        # check combining of optimization flags (doesn't make much sense)
        # lowest optimization should always be picked
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.set_options({'lowopt': True, 'opt':True})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            flag = '-%s' % tc.COMPILER_SHARED_OPTION_MAP['lowopt']
            self.assertTrue(flag in flags)
        self.modtool.purge()

        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.set_options({'noopt': True, 'lowopt':True})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            flag = '-%s' % tc.COMPILER_SHARED_OPTION_MAP['noopt']
            self.assertTrue(flag in flags)
        self.modtool.purge()

        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.set_options({'noopt':True, 'lowopt': True, 'opt':True})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            flag = '-%s' % tc.COMPILER_SHARED_OPTION_MAP['noopt']
            self.assertTrue(flag in flags)

    def test_misc_flags_shared(self):
        """Test whether shared compiler flags are set correctly."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']

        # setting option should result in corresponding flag to be set (shared options)
        for opt in ['pic', 'verbose', 'debug', 'static', 'shared']:
            for enable in [True, False]:
                tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
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
                self.modtool.purge()

    def test_misc_flags_unique(self):
        """Test whether unique compiler flags are set correctly."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']

        # setting option should result in corresponding flag to be set (unique options)
        for opt in ['unroll', 'optarch', 'openmp']:
            for enable in [True, False]:
                tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
                tc.set_options({opt: enable})
                tc.prepare()
                if opt == 'optarch':
                    flag = '-%s' % tc.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[tc.arch]
                else:
                    flag = '-%s' % tc.COMPILER_UNIQUE_OPTION_MAP[opt]
                for var in flag_vars:
                    flags = tc.get_variable(var)
                    if enable:
                        self.assertTrue(flag in flags, "%s: True means %s in %s" % (opt, flag, flags))
                    else:
                        self.assertTrue(flag not in flags, "%s: False means no %s in %s" % (opt, flag, flags))
                self.modtool.purge()

    def test_override_optarch(self):
        """Test whether overriding the optarch flag works."""
        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']
        for optarch_var in ['march=lovelylovelysandybridge', None]:
            build_options = {'optarch': optarch_var}
            init_config(build_options=build_options)
            for enable in [True, False]:
                tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
                tc.set_options({'optarch': enable})
                tc.prepare()
                flag = None
                if optarch_var is not None:
                    flag = '-%s' % optarch_var
                else:
                    # default optarch flag
                    flag = tc.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[tc.arch]

                for var in flag_vars:
                    flags = tc.get_variable(var)
                    if enable:
                        self.assertTrue(flag in flags, "optarch: True means %s in %s" % (flag, flags))
                    else:
                        self.assertFalse(flag in flags, "optarch: False means no %s in %s" % (flag, flags))
                self.modtool.purge()

    def test_optarch_generic(self):
        """Test whether --optarch=GENERIC works as intended."""
        for generic in [False, True]:
            if generic:
                build_options = {'optarch': 'GENERIC'}
                init_config(build_options=build_options)
            flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']
            tcs = {
                'gompi': ('1.3.12', "-march=x86-64 -mtune=generic"),
                'iccifort': ('2011.13.367', "-xSSE2 -ftz -fp-speculation=safe -fp-model source"),
            }
            for tcopt_optarch in [False, True]:
                for tcname in tcs:
                    tcversion, generic_flags = tcs[tcname]
                    tc = self.get_toolchain(tcname, version=tcversion)
                    tc.set_options({'optarch': tcopt_optarch})
                    tc.prepare()
                    for var in flag_vars:
                        if generic:
                            self.assertTrue(generic_flags in tc.get_variable(var))
                        else:
                            self.assertFalse(generic_flags in tc.get_variable(var))

    def test_misc_flags_unique_fortran(self):
        """Test whether unique Fortran compiler flags are set correctly."""

        flag_vars = ['FCFLAGS', 'FFLAGS', 'F90FLAGS']

        # setting option should result in corresponding flag to be set (Fortran unique options)
        for opt in ['i8', 'r8']:
            for enable in [True, False]:
                tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
                tc.set_options({opt: enable})
                tc.prepare()
                flag = '-%s' % tc.COMPILER_UNIQUE_OPTION_MAP[opt]
                for var in flag_vars:
                    flags = tc.get_variable(var)
                    if enable:
                        self.assertTrue(flag in flags, "%s: True means %s in %s" % (opt, flag, flags))
                    else:
                        self.assertTrue(flag not in flags, "%s: False means no %s in %s" % (opt, flag, flags))
                self.modtool.purge()

    def test_precision_flags(self):
        """Test whether precision flags are being set correctly."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']

        # check default precision flag
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            val = ' '.join(['-%s' % f for f in tc.COMPILER_UNIQUE_OPTION_MAP['defaultprec']])
            self.assertTrue(val in flags)

        # check other precision flags
        for opt in ['strict', 'precise', 'loose', 'veryloose']:
            for enable in [True, False]:
                tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
                tc.set_options({opt: enable})
                tc.prepare()
                val = ' '.join(['-%s' % f for f in tc.COMPILER_UNIQUE_OPTION_MAP[opt]])
                for var in flag_vars:
                    flags = tc.get_variable(var)
                    if enable:
                        self.assertTrue(val in flags)
                    else:
                        self.assertTrue(val not in flags)
                self.modtool.purge()

    def test_cgoolf_toolchain(self):
        """Test for cgoolf toolchain."""
        tc = self.get_toolchain("cgoolf", version="1.1.6")
        tc.prepare()

        self.assertEqual(tc.get_variable('CC'), 'clang')
        self.assertEqual(tc.get_variable('CXX'), 'clang++')
        self.assertEqual(tc.get_variable('F77'), 'gfortran')
        self.assertEqual(tc.get_variable('F90'), 'gfortran')
        self.assertEqual(tc.get_variable('FC'), 'gfortran')

    def test_comp_family(self):
        """Test determining compiler family."""
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.prepare()
        self.assertEqual(tc.comp_family(), "GCC")

    def test_mpi_family(self):
        """Test determining MPI family."""
        # check subtoolchain w/o MPI
        tc = self.get_toolchain("GCC", version="4.7.2")
        tc.prepare()
        self.assertEqual(tc.mpi_family(), None)
        self.modtool.purge()

        # check full toolchain including MPI
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.prepare()
        self.assertEqual(tc.mpi_family(), "OpenMPI")
        self.modtool.purge()

        # check another one
        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        self.modtool.prepend_module_path(self.test_prefix)
        tc = self.get_toolchain("ictce", version="4.1.13")
        tc.prepare()
        self.assertEqual(tc.mpi_family(), "IntelMPI")

    def test_goolfc(self):
        """Test whether goolfc is handled properly."""
        tc = self.get_toolchain("goolfc", version="1.3.12")
        opts = {'cuda_gencode': ['arch=compute_35,code=sm_35', 'arch=compute_10,code=compute_10']}
        tc.set_options(opts)
        tc.prepare()

        nvcc_flags = r' '.join([
            r'-Xcompiler="-O2 -%s"' % tc.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[tc.arch],
            # the use of -lcudart in -Xlinker is a bit silly but hard to avoid
            r'-Xlinker=".* -lm -lrt -lcudart -lpthread"',
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
        self.assertTrue("-lrt -lcudart" in tc.get_variable('LIBS'))

    def setup_sandbox_for_intel_fftw(self, moddir, imklver='10.3.12.361'):
        """Set up sandbox for Intel FFTW"""
        # hack to make Intel FFTW lib check pass
        # create dummy imkl module and put required lib*.a files in place

        imkl_module_path = os.path.join(moddir, 'imkl', imklver)
        imkl_dir = os.path.join(self.test_prefix, 'software', 'imkl', imklver)

        imkl_mod_txt = '\n'.join([
            "#%Module",
            "setenv EBROOTIMKL %s" % imkl_dir,
            "setenv EBVERSIONIMKL %s" % imklver,
        ])
        write_file(imkl_module_path, imkl_mod_txt)

        fftw_libs = ['fftw3xc_intel', 'fftw3xc_pgi', 'mkl_cdft_core', 'mkl_blacs_intelmpi_lp64']
        fftw_libs += ['mkl_intel_lp64', 'mkl_sequential', 'mkl_core', 'mkl_intel_ilp64']
        if LooseVersion(imklver) >= LooseVersion('11'):
            fftw_libs.extend(['fftw3x_cdft_ilp64', 'fftw3x_cdft_lp64'])
        else:
            fftw_libs.append('fftw3x_cdft')

        for subdir in ['mkl/lib/intel64', 'compiler/lib/intel64', 'lib/em64t']:
            os.makedirs(os.path.join(imkl_dir, subdir))
            for fftlib in fftw_libs:
                write_file(os.path.join(imkl_dir, subdir, 'lib%s.a' % fftlib), 'foo')

    def test_ictce_toolchain(self):
        """Test for ictce toolchain."""
        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        self.modtool.prepend_module_path(self.test_prefix)

        tc = self.get_toolchain("ictce", version="4.1.13")
        tc.prepare()

        self.assertEqual(tc.get_variable('CC'), 'icc')
        self.assertEqual(tc.get_variable('CXX'), 'icpc')
        self.assertEqual(tc.get_variable('F77'), 'ifort')
        self.assertEqual(tc.get_variable('F90'), 'ifort')
        self.assertEqual(tc.get_variable('FC'), 'ifort')
        self.modtool.purge()

        tc = self.get_toolchain("ictce", version="4.1.13")
        opts = {'usempi': True}
        tc.set_options(opts)
        tc.prepare()

        self.assertEqual(tc.get_variable('CC'), 'mpicc')
        self.assertEqual(tc.get_variable('CXX'), 'mpicxx')
        self.assertEqual(tc.get_variable('F77'), 'mpif77')
        self.assertEqual(tc.get_variable('F90'), 'mpif90')
        self.assertEqual(tc.get_variable('FC'), 'mpif90')
        self.assertEqual(tc.get_variable('MPICC'), 'mpicc')
        self.assertEqual(tc.get_variable('MPICXX'), 'mpicxx')
        self.assertEqual(tc.get_variable('MPIF77'), 'mpif77')
        self.assertEqual(tc.get_variable('MPIF90'), 'mpif90')
        self.assertEqual(tc.get_variable('MPIFC'), 'mpif90')
        self.modtool.purge()

        tc = self.get_toolchain("ictce", version="4.1.13")
        opts = {'usempi': True, 'openmp': True}
        tc.set_options(opts)
        tc.prepare()

        for flag in ['-mt_mpi', '-fopenmp']:
            for var in ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']:
                self.assertTrue(flag in tc.get_variable(var))

        # -openmp is deprecated for new Intel compiler versions
        self.assertFalse('-openmp' in tc.get_variable('CFLAGS'))
        self.assertFalse('-openmp' in tc.get_variable('CXXFLAGS'))
        self.assertFalse('-openmp' in tc.get_variable('FFLAGS'))

        self.assertEqual(tc.get_variable('CC'), 'mpicc')
        self.assertEqual(tc.get_variable('CXX'), 'mpicxx')
        self.assertEqual(tc.get_variable('F77'), 'mpif77')
        self.assertEqual(tc.get_variable('F90'), 'mpif90')
        self.assertEqual(tc.get_variable('FC'), 'mpif90')
        self.assertEqual(tc.get_variable('MPICC'), 'mpicc')
        self.assertEqual(tc.get_variable('MPICXX'), 'mpicxx')
        self.assertEqual(tc.get_variable('MPIF77'), 'mpif77')
        self.assertEqual(tc.get_variable('MPIF90'), 'mpif90')

        # different flag for OpenMP with old Intel compilers (11.x)
        modules.modules_tool().purge()
        self.setup_sandbox_for_intel_fftw(self.test_prefix, imklver='10.2.6.038')
        self.modtool.prepend_module_path(self.test_prefix)
        tc = self.get_toolchain('ictce', version='3.2.2.u3')
        opts = {'openmp': True}
        tc.set_options(opts)
        tc.prepare()
        self.assertEqual(tc.get_variable('MPIFC'), 'mpif90')
        for var in ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']:
            self.assertTrue('-openmp' in tc.get_variable(var))

    def test_toolchain_verification(self):
        """Test verification of toolchain definition."""
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.prepare()
        self.modtool.purge()

        # toolchain modules missing a toolchain element should fail verification
        error_msg = "List of toolchain dependency modules and toolchain definition do not match"
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED-brokenFFTW")
        self.assertErrorRegex(EasyBuildError, error_msg, tc.prepare)
        self.modtool.purge()

        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED-brokenBLACS")
        self.assertErrorRegex(EasyBuildError, error_msg, tc.prepare)
        self.modtool.purge()

        # missing optional toolchain elements are fine
        tc = self.get_toolchain('goolfc', version='1.3.12')
        opts = {'cuda_gencode': ['arch=compute_35,code=sm_35', 'arch=compute_10,code=compute_10']}
        tc.set_options(opts)
        tc.prepare()

    def test_nosuchtoolchain(self):
        """Test preparing for a toolchain for which no module is available."""
        tc = self.get_toolchain('intel', version='1970.01')
        self.assertErrorRegex(EasyBuildError, "No module found for toolchain", tc.prepare)

    def test_mpi_cmd_for(self):
        """Test mpi_cmd_for function."""
        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        self.modtool.prepend_module_path(self.test_prefix)

        tc = self.get_toolchain('ictce', version='4.1.13')
        tc.prepare()

        mpi_cmd_for_re = re.compile("^mpirun --file=.*/mpdboot -machinefile .*/nodes -np 4 test$")
        self.assertTrue(mpi_cmd_for_re.match(tc.mpi_cmd_for('test', 4)))

    def test_prepare_deps(self):
        """Test preparing for a toolchain when dependencies are involved."""
        tc = self.get_toolchain('GCC', version='4.6.4')
        deps = [
            {
                'name': 'OpenMPI',
                'version': '1.6.4',
                'full_mod_name': 'OpenMPI/1.6.4-GCC-4.6.4',
                'short_mod_name': 'OpenMPI/1.6.4-GCC-4.6.4',
                'external_module': False,
            },
        ]
        tc.add_dependencies(deps)
        tc.prepare()
        mods = ['GCC/4.6.4', 'hwloc/1.6.2-GCC-4.6.4', 'OpenMPI/1.6.4-GCC-4.6.4']
        self.assertTrue([m['mod_name'] for m in self.modtool.list()], mods)

    def test_prepare_deps_external(self):
        """Test preparing for a toolchain when dependencies and external modules are involved."""
        deps = [
            {
                'name': 'OpenMPI',
                'version': '1.6.4',
                'full_mod_name': 'OpenMPI/1.6.4-GCC-4.6.4',
                'short_mod_name': 'OpenMPI/1.6.4-GCC-4.6.4',
                'external_module': False,
                'external_module_metadata': {},
            },
            # no metadata available
            {
                'name': None,
                'version': None,
                'full_mod_name': 'toy/0.0',
                'short_mod_name': 'toy/0.0',
                'external_module': True,
                'external_module_metadata': {},
            }
        ]
        tc = self.get_toolchain('GCC', version='4.6.4')
        tc.add_dependencies(deps)
        tc.prepare()
        mods = ['GCC/4.6.4', 'hwloc/1.6.2-GCC-4.6.4', 'OpenMPI/1.6.4-GCC-4.6.4', 'toy/0.0']
        self.assertTrue([m['mod_name'] for m in self.modtool.list()], mods)
        self.assertTrue(os.environ['EBROOTTOY'].endswith('software/toy/0.0'))
        self.assertEqual(os.environ['EBVERSIONTOY'], '0.0')
        self.assertFalse('EBROOTFOOBAR' in os.environ)

        # with metadata
        deps[1] = {
            'full_mod_name': 'toy/0.0',
            'short_mod_name': 'toy/0.0',
            'external_module': True,
            'external_module_metadata': {
                'name': ['toy', 'foobar'],
                'version': ['1.2.3', '4.5'],
                'prefix': 'FOOBAR_PREFIX',
            }
        }
        tc = self.get_toolchain('GCC', version='4.6.4')
        tc.add_dependencies(deps)
        os.environ['FOOBAR_PREFIX'] = '/foo/bar'
        tc.prepare()
        mods = ['GCC/4.6.4', 'hwloc/1.6.2-GCC-4.6.4', 'OpenMPI/1.6.4-GCC-4.6.4', 'toy/0.0']
        self.assertTrue([m['mod_name'] for m in self.modtool.list()], mods)
        self.assertEqual(os.environ['EBROOTTOY'], '/foo/bar')
        self.assertEqual(os.environ['EBVERSIONTOY'], '1.2.3')
        self.assertEqual(os.environ['EBROOTFOOBAR'], '/foo/bar')
        self.assertEqual(os.environ['EBVERSIONFOOBAR'], '4.5')

        self.assertEqual(modules.get_software_root('foobar'), '/foo/bar')
        self.assertEqual(modules.get_software_version('toy'), '1.2.3')

    def test_old_new_iccifort(self):
        """Test whether preparing for old/new Intel compilers works correctly."""
        self.setup_sandbox_for_intel_fftw(self.test_prefix, imklver='10.3.12.361')
        self.setup_sandbox_for_intel_fftw(self.test_prefix, imklver='10.2.6.038')
        self.modtool.prepend_module_path(self.test_prefix)

        # incl. -lguide
        libblas_mt_ictce3 = "-Wl,-Bstatic -Wl,--start-group -lmkl_intel_lp64 -lmkl_intel_thread -lmkl_core"
        libblas_mt_ictce3 += " -Wl,--end-group -Wl,-Bdynamic -liomp5 -lguide -lpthread"

        # no -lguide
        libblas_mt_ictce4 = "-Wl,-Bstatic -Wl,--start-group -lmkl_intel_lp64 -lmkl_intel_thread -lmkl_core"
        libblas_mt_ictce4 += " -Wl,--end-group -Wl,-Bdynamic -liomp5 -lpthread"

        # incl. -lmkl_solver*
        libscalack_ictce3 = "-lmkl_scalapack_lp64 -lmkl_solver_lp64_sequential -lmkl_blacs_intelmpi_lp64"
        libscalack_ictce3 += " -lmkl_intel_lp64 -lmkl_sequential -lmkl_core"

        # no -lmkl_solver*
        libscalack_ictce4 = "-lmkl_scalapack_lp64 -lmkl_blacs_intelmpi_lp64 -lmkl_intel_lp64 -lmkl_sequential -lmkl_core"

        libblas_mt_goolfc = "-lopenblas -lgfortran"
        libscalack_goolfc = "-lscalapack -lopenblas -lgfortran"

        tc = self.get_toolchain('goolfc', version='1.3.12')
        tc.prepare()
        self.assertEqual(os.environ['LIBBLAS_MT'], libblas_mt_goolfc)
        self.assertEqual(os.environ['LIBSCALAPACK'], libscalack_goolfc)
        self.modtool.purge()

        tc = self.get_toolchain('ictce', version='4.1.13')
        tc.prepare()
        self.assertEqual(os.environ.get('LIBBLAS_MT', "(not set)"), libblas_mt_ictce4)
        self.assertTrue(libscalack_ictce4 in os.environ['LIBSCALAPACK'])
        self.modtool.purge()

        tc = self.get_toolchain('ictce', version='3.2.2.u3')
        tc.prepare()
        self.assertEqual(os.environ.get('LIBBLAS_MT', "(not set)"), libblas_mt_ictce3)
        self.assertTrue(libscalack_ictce3 in os.environ['LIBSCALAPACK'])
        self.modtool.purge()

        tc = self.get_toolchain('ictce', version='4.1.13')
        tc.prepare()
        self.assertEqual(os.environ.get('LIBBLAS_MT', "(not set)"), libblas_mt_ictce4)
        self.assertTrue(libscalack_ictce4 in os.environ['LIBSCALAPACK'])
        self.modtool.purge()

        tc = self.get_toolchain('ictce', version='3.2.2.u3')
        tc.prepare()
        self.assertEqual(os.environ.get('LIBBLAS_MT', "(not set)"), libblas_mt_ictce3)
        self.assertTrue(libscalack_ictce3 in os.environ['LIBSCALAPACK'])
        self.modtool.purge()

        libscalack_ictce4 = libscalack_ictce4.replace('_lp64', '_ilp64')
        tc = self.get_toolchain('ictce', version='4.1.13')
        opts = {'i8': True}
        tc.set_options(opts)
        tc.prepare()
        self.assertTrue(libscalack_ictce4 in os.environ['LIBSCALAPACK'])
        self.modtool.purge()

        tc = self.get_toolchain('goolfc', version='1.3.12')
        tc.prepare()
        self.assertEqual(os.environ['LIBBLAS_MT'], libblas_mt_goolfc)
        self.assertEqual(os.environ['LIBSCALAPACK'], libscalack_goolfc)

    def test_independence(self):
        """Test independency of toolchain instances."""

        # tweaking --optarch is required for Cray toolchains (craypre-<optarch> module must be available)
        init_config(build_options={'optarch': 'test'})

        tc_cflags = {
            'CrayCCE': "-craype-verbose -O2",
            'CrayGNU': "-craype-verbose -O2",
            'CrayIntel': "-craype-verbose -O2 -ftz -fp-speculation=safe -fp-model source",
            'GCC': "-O2 -test",
            'iccifort': "-O2 -test -ftz -fp-speculation=safe -fp-model source",
        }

        toolchains = [
            ('CrayCCE', '2015.06-XC'),
            ('CrayGNU', '2015.06-XC'),
            ('CrayIntel', '2015.06-XC'),
            ('GCC', '4.7.2'),
            ('iccifort', '2011.13.367'),
        ]

        # purposely obtain toolchains several times in a row, value for $CFLAGS should not change
        for _ in range(3):
            for tcname, tcversion in toolchains:
                tc = get_toolchain({'name': tcname, 'version': tcversion}, {},
                                   mns=ActiveMNS(), modtool=self.modtool)
                tc.set_options({})
                tc.prepare()
                expected_cflags = tc_cflags[tcname]
                msg = "Expected $CFLAGS found for toolchain %s: %s" % (tcname, expected_cflags)
                self.assertEqual(str(tc.variables['CFLAGS']), expected_cflags, msg)
                self.assertEqual(os.environ['CFLAGS'], expected_cflags, msg)

    def test_pgi_toolchain(self):
        """Tests for PGI toolchain."""
        # add dummy PGI modules to play with
        write_file(os.path.join(self.test_prefix, 'PGI', '14.9'), '#%Module\nsetenv EBVERSIONPGI 14.9')
        write_file(os.path.join(self.test_prefix, 'PGI', '14.10'), '#%Module\nsetenv EBVERSIONPGI 14.10')
        write_file(os.path.join(self.test_prefix, 'PGI', '16.3'), '#%Module\nsetenv EBVERSIONPGI 16.3')
        self.modtool.prepend_module_path(self.test_prefix)

        tc = self.get_toolchain('PGI', version='14.9')
        tc.prepare()

        self.assertEqual(tc.get_variable('CC'), 'pgcc')
        self.assertEqual(tc.get_variable('CXX'), 'pgCC')
        self.assertEqual(tc.get_variable('F77'), 'pgf77')
        self.assertEqual(tc.get_variable('F90'), 'pgfortran')
        self.assertEqual(tc.get_variable('FC'), 'pgfortran')
        self.modtool.purge()

        for pgi_ver in ['14.10', '16.3']:
            tc = self.get_toolchain('PGI', version=pgi_ver)
            tc.prepare()

            self.assertEqual(tc.get_variable('CC'), 'pgcc')
            self.assertEqual(tc.get_variable('CXX'), 'pgc++')
            self.assertEqual(tc.get_variable('F77'), 'pgf77')
            self.assertEqual(tc.get_variable('F90'), 'pgfortran')
            self.assertEqual(tc.get_variable('FC'), 'pgfortran')

    def test_pgi_imkl(self):
        """Test setup of build environment for toolchain with PGI and Intel MKL."""
        pomkl_mod_txt = '\n'.join([
            '#%Module',
            "module load PGI/16.3",
            "module load OpenMPI/1.10.2-PGI-16.3",
            "module load imkl/11.3.2.181",
        ])
        write_file(os.path.join(self.test_prefix, 'pomkl', '2016.03'), pomkl_mod_txt)
        pgi_mod_txt = '\n'.join([
            '#%Module',
            "setenv EBROOTPGI %s" % self.test_prefix,
            "setenv EBVERSIONPGI 16.3",
        ])
        write_file(os.path.join(self.test_prefix, 'PGI', '16.3'), pgi_mod_txt)
        ompi_mod_txt = '\n'.join([
            '#%Module',
            "setenv EBROOTOPENMPI %s" % self.test_prefix,
            "setenv EBVERSIONOPENMPI 1.10.2",
        ])
        write_file(os.path.join(self.test_prefix, 'OpenMPI', '1.10.2-PGI-16.3'), ompi_mod_txt)
        self.setup_sandbox_for_intel_fftw(self.test_prefix, imklver='11.3.2.181')
        self.modtool.prepend_module_path(self.test_prefix)

        tc = self.get_toolchain('pomkl', version='2016.03')
        tc.prepare()

        liblapack = "-Wl,-Bstatic -Wl,--start-group -lmkl_intel_lp64 -lmkl_sequential -lmkl_core "
        liblapack += "-Wl,--end-group -Wl,-Bdynamic -ldl"
        self.assertEqual(os.environ.get('LIBLAPACK', '(not set)'), liblapack)


def suite():
    """ return all the tests"""
    return TestLoader().loadTestsFromTestCase(ToolchainTest)

if __name__ == '__main__':
    main()
