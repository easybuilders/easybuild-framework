##
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
##
"""
Unit tests for toolchain support.

@author: Kenneth Hoste (Ghent University)
"""

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from distutils.version import LooseVersion
from itertools import product
from unittest import TextTestRunner
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, find_full_path, init_config

import easybuild.tools.modules as modules
import easybuild.tools.toolchain.compiler
from easybuild.framework.easyconfig.easyconfig import EasyConfig, ActiveMNS
from easybuild.tools import systemtools as st
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.environment import setvar
from easybuild.tools.filetools import adjust_permissions, copy_dir, find_eb_script, mkdir, read_file, write_file, which
from easybuild.tools.run import run_cmd
from easybuild.tools.toolchain.utilities import get_toolchain, search_toolchain

easybuild.tools.toolchain.compiler.systemtools.get_compiler_family = lambda: st.POWER


class ToolchainTest(EnhancedTestCase):
    """ Baseclass for toolchain testcases """

    def setUp(self):
        """Set up toolchain test."""
        super(ToolchainTest, self).setUp()
        self.orig_get_cpu_architecture = st.get_cpu_architecture
        self.orig_get_cpu_family = st.get_cpu_family
        self.orig_get_cpu_model = st.get_cpu_model
        self.orig_get_cpu_vendor = st.get_cpu_vendor

    def tearDown(self):
        """Cleanup after toolchain test."""
        st.get_cpu_architecture = self.orig_get_cpu_architecture
        st.get_cpu_family = self.orig_get_cpu_family
        st.get_cpu_model = self.orig_get_cpu_model
        st.get_cpu_vendor = self.orig_get_cpu_vendor
        super(ToolchainTest, self).tearDown()

    def get_toolchain(self, name, version=None):
        """Get a toolchain object instance to test with."""
        tc_class, _ = search_toolchain(name)
        self.assertEqual(tc_class.NAME, name)
        tc = tc_class(version=version, mns=ActiveMNS(), modtool=self.modtool)
        return tc

    def test_toolchain(self):
        """Test whether toolchain is initialized correctly."""
        test_ecs = os.path.join('test', 'framework', 'easyconfigs', 'test_ecs')
        ec_file = find_full_path(os.path.join(test_ecs, 'g', 'gzip', 'gzip-1.4.eb'))
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
                    flags = tc.get_variable(var).split()
                    if enable:
                        self.assertTrue(flag in flags, "%s: True means %s in %s" % (opt, flag, flags))
                    else:
                        self.assertTrue(flag not in flags, "%s: False means no %s in %s" % (opt, flag, flags))
                self.modtool.purge()

    def test_misc_flags_unique(self):
        """Test whether unique compiler flags are set correctly."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']

        # setting option should result in corresponding flag to be set (unique options)
        for opt in ['unroll', 'optarch', 'openmp', 'vectorize']:
            for enable in [True, False]:
                tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
                tc.set_options({opt: enable})
                tc.prepare()
                if opt == 'optarch':
                    option = tc.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[(tc.arch, tc.cpu_family)]
                else:
                    option = tc.options.options_map[opt]
                if not isinstance(option, dict):
                    option = {True: option}
                for var in flag_vars:
                    flags = tc.get_variable(var)
                    for key, value in option.items():
                        flag = "-%s" % value
                        if enable == key:
                            self.assertTrue(flag in flags, "%s: %s means %s in %s" % (opt, enable, flag, flags))
                        else:
                            self.assertTrue(flag not in flags, "%s: %s means no %s in %s" % (opt, enable, flag, flags))
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
                    flag = tc.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[(tc.arch, tc.cpu_family)]

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

    def test_optarch_aarch64_heuristic(self):
        """Test whether AArch64 pre-GCC-6 optimal architecture flag heuristic works."""
        st.get_cpu_architecture = lambda: st.AARCH64
        st.get_cpu_family = lambda: st.ARM
        st.get_cpu_model = lambda: 'ARM Cortex-A53'
        st.get_cpu_vendor = lambda: st.ARM
        tc = self.get_toolchain("GCC", version="4.7.2")
        tc.set_options({})
        tc.prepare()
        self.assertEqual(tc.options.options_map['optarch'], 'mcpu=cortex-a53')
        self.assertTrue('-mcpu=cortex-a53' in os.environ['CFLAGS'])
        self.modtool.purge()

        tc = self.get_toolchain("GCCcore", version="6.2.0")
        tc.set_options({})
        tc.prepare()
        self.assertEqual(tc.options.options_map['optarch'], 'mcpu=native')
        self.assertTrue('-mcpu=native' in os.environ['CFLAGS'])
        self.modtool.purge()

        st.get_cpu_model = lambda: 'ARM Cortex-A53 + Cortex-A72'
        tc = self.get_toolchain("GCC", version="4.7.2")
        tc.set_options({})
        tc.prepare()
        self.assertEqual(tc.options.options_map['optarch'], 'mcpu=cortex-a72.cortex-a53')
        self.assertTrue('-mcpu=cortex-a72.cortex-a53' in os.environ['CFLAGS'])
        self.modtool.purge()

    def test_compiler_dependent_optarch(self):
        """Test whether specifying optarch on a per compiler basis works."""
        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']
        intel_options = [('intelflag', 'intelflag'), ('GENERIC', 'xSSE2'), ('', '')]
        gcc_options = [('gccflag', 'gccflag'), ('march=nocona', 'march=nocona'), ('', '')]
        gcccore_options = [('gcccoreflag', 'gcccoreflag'), ('GENERIC', 'march=x86-64 -mtune=generic'), ('', '')]
        toolchains = [('iccifort', '2011.13.367'), ('GCC', '4.7.2'), ('GCCcore', '6.2.0'), ('PGI', '16.7-GCC-5.4.0-2.26')]
        enabled = [True, False]

        test_cases = product(intel_options, gcc_options, gcccore_options, toolchains, enabled)

        for (intel_flags, intel_flags_exp), (gcc_flags, gcc_flags_exp), (gcccore_flags, gcccore_flags_exp), (toolchain, toolchain_ver), enable in test_cases:
            optarch_var = {}
            optarch_var['Intel'] = intel_flags
            optarch_var['GCC'] = gcc_flags
            optarch_var['GCCcore'] = gcccore_flags
            build_options = {'optarch': optarch_var}
            init_config(build_options=build_options)
            tc = self.get_toolchain(toolchain, version=toolchain_ver)
            tc.set_options({'optarch': enable})
            tc.prepare()
            flags = None
            if toolchain == 'iccifort':
                flags = intel_flags_exp
            elif toolchain == 'GCC':
                flags = gcc_flags_exp
            elif toolchain == 'GCCcore':
                flags = gcccore_flags_exp
            else: # PGI as an example of compiler not set
                # default optarch flag, should be the same as the one in
                # tc.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[(tc.arch,tc.cpu_family)]
                flags = ''

            optarch_flags = tc.options.options_map['optarch']

            self.assertEquals(flags, optarch_flags)

            # Also check that it is correctly passed to xFLAGS, honoring 'enable'
            if flags == '':
                blacklist = [
                    intel_options[0][1],
                    intel_options[1][1],
                    gcc_options[0][1],
                    gcc_options[1][1],
                    gcccore_options[0][1],
                    gcccore_options[1][1],
                    'xHost', # default optimal for Intel
                    'march=native', # default optimal for GCC
                ]
            else:
                blacklist = [flags]

            for var in flag_vars:
                 set_flags = tc.get_variable(var)

                 # Check that the correct flags are there
                 if enable and flags != '':
                     error_msg = "optarch: True means '%s' in '%s'" % (flags, set_flags)
                     self.assertTrue(flags in set_flags, "optarch: True means '%s' in '%s'")

                 # Check that there aren't any unexpected flags
                 else:
                     for blacklisted_flag in blacklist:
                         error_msg = "optarch: False means no '%s' in '%s'" % (blacklisted_flag, set_flags)
                         self.assertFalse(blacklisted_flag in set_flags, error_msg)

            self.modtool.purge()

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

        # check default precision: -fno-math-errno flag for GCC
        tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
        tc.set_options({})
        tc.prepare()
        for var in flag_vars:
            self.assertEqual(os.getenv(var), "-O2 -ftree-vectorize -march=native -fno-math-errno")

        # check other precision flags
        prec_flags = {
            'ieee': "-fno-math-errno -mieee-fp -fno-trapping-math",
            'strict': "-mieee-fp -mno-recip",
            'precise': "-mno-recip",
            'loose': "-fno-math-errno -mrecip -mno-ieee-fp",
            'veryloose': "-fno-math-errno -mrecip=all -mno-ieee-fp",
        }
        for prec in prec_flags:
            for enable in [True, False]:
                tc = self.get_toolchain("goalf", version="1.1.0-no-OFED")
                tc.set_options({prec: enable})
                tc.prepare()
                for var in flag_vars:
                    if enable:
                        self.assertEqual(os.getenv(var), "-O2 -ftree-vectorize -march=native %s" % prec_flags[prec])
                    else:
                        self.assertEqual(os.getenv(var), "-O2 -ftree-vectorize -march=native -fno-math-errno")
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

    def test_blas_lapack_family(self):
        """Test determining BLAS/LAPACK family."""
        # check compiler-only (sub)toolchain
        tc = self.get_toolchain("GCC", version="4.7.2")
        tc.prepare()
        self.assertEqual(tc.blas_family(), None)
        self.assertEqual(tc.lapack_family(), None)
        self.modtool.purge()

        # check compiler/MPI-only (sub)toolchain
        tc = self.get_toolchain('gompi', version='1.3.12')
        tc.prepare()
        self.assertEqual(tc.blas_family(), None)
        self.assertEqual(tc.lapack_family(), None)
        self.modtool.purge()

        # check full toolchain including BLAS/LAPACK
        tc = self.get_toolchain('goolfc', version='1.3.12')
        tc.prepare()
        self.assertEqual(tc.blas_family(), 'OpenBLAS')
        self.assertEqual(tc.lapack_family(), 'OpenBLAS')
        self.modtool.purge()

        # check another one
        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        self.modtool.prepend_module_path(self.test_prefix)
        tc = self.get_toolchain('ictce', version='4.1.13')
        tc.prepare()
        self.assertEqual(tc.blas_family(), 'IntelMKL')
        self.assertEqual(tc.lapack_family(), 'IntelMKL')

    def test_goolfc(self):
        """Test whether goolfc is handled properly."""
        tc = self.get_toolchain("goolfc", version="1.3.12")
        opts = {'cuda_gencode': ['arch=compute_35,code=sm_35', 'arch=compute_10,code=compute_10'], 'openmp': True}
        tc.set_options(opts)
        tc.prepare()

        archflags = tc.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[(tc.arch, tc.cpu_family)]
        optflags = "-O2 -ftree-vectorize -%s -fno-math-errno -fopenmp" % archflags
        nvcc_flags = r' '.join([
            r'-Xcompiler="%s"' % optflags,
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

        self.assertEqual(tc.get_variable('CC'), 'mpiicc')
        self.assertEqual(tc.get_variable('CXX'), 'mpiicpc')
        self.assertEqual(tc.get_variable('F77'), 'mpiifort')
        self.assertEqual(tc.get_variable('F90'), 'mpiifort')
        self.assertEqual(tc.get_variable('FC'), 'mpiifort')
        self.assertEqual(tc.get_variable('MPICC'), 'mpiicc')
        self.assertEqual(tc.get_variable('MPICXX'), 'mpiicpc')
        self.assertEqual(tc.get_variable('MPIF77'), 'mpiifort')
        self.assertEqual(tc.get_variable('MPIF90'), 'mpiifort')
        self.assertEqual(tc.get_variable('MPIFC'), 'mpiifort')
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

        self.assertEqual(tc.get_variable('CC'), 'mpiicc')
        self.assertEqual(tc.get_variable('CXX'), 'mpiicpc')
        self.assertEqual(tc.get_variable('F77'), 'mpiifort')
        self.assertEqual(tc.get_variable('F90'), 'mpiifort')
        self.assertEqual(tc.get_variable('FC'), 'mpiifort')
        self.assertEqual(tc.get_variable('MPICC'), 'mpiicc')
        self.assertEqual(tc.get_variable('MPICXX'), 'mpiicpc')
        self.assertEqual(tc.get_variable('MPIF77'), 'mpiifort')
        self.assertEqual(tc.get_variable('MPIF90'), 'mpiifort')
        self.assertEqual(tc.get_variable('MPIFC'), 'mpiifort')

        # different flag for OpenMP with old Intel compilers (11.x)
        modules.modules_tool().purge()
        self.setup_sandbox_for_intel_fftw(self.test_prefix, imklver='10.2.6.038')
        self.modtool.prepend_module_path(self.test_prefix)
        tc = self.get_toolchain('ictce', version='3.2.2.u3')
        opts = {'openmp': True}
        tc.set_options(opts)
        tc.prepare()
        self.assertEqual(tc.get_variable('MPIFC'), 'mpiifort')
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
        self.modtool.prepend_module_path(self.test_prefix)

        tc = self.get_toolchain('gompi', version='1.3.12')
        tc.prepare()
        self.assertEqual(tc.mpi_cmd_for('test123', 2), "mpirun -n 2 test123")
        self.modtool.purge()

        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        tc = self.get_toolchain('ictce', version='4.1.13')
        tc.prepare()
        self.assertEqual(tc.mpi_cmd_for('test123', 2), "mpirun -n 2 test123")
        self.modtool.purge()

        self.setup_sandbox_for_intel_fftw(self.test_prefix, imklver='10.2.6.038')
        tc = self.get_toolchain('ictce', version='3.2.2.u3')
        tc.prepare()

        mpi_cmd_for_re = re.compile("^mpirun --file=.*/mpdboot -machinefile .*/nodes -np 4 test$")
        self.assertTrue(mpi_cmd_for_re.match(tc.mpi_cmd_for('test', 4)))

        # test specifying custom template for MPI commands
        init_config(build_options={'mpi_cmd_template': "mpiexec -np %(nr_ranks)s -- %(cmd)s"})
        self.assertEqual(tc.mpi_cmd_for('test123', '7'), "mpiexec -np 7 -- test123")

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
                'build_only': False,
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
                'build_only': False,
            },
            # no metadata available
            {
                'name': None,
                'version': None,
                'full_mod_name': 'toy/0.0',
                'short_mod_name': 'toy/0.0',
                'external_module': True,
                'external_module_metadata': {},
                'build_only': False,
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
            },
            'build_only': False,
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
        libfft_mt_goolfc = "-lfftw3_omp -lfftw3 -lpthread"

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
        tc.set_options({'openmp': True})
        tc.prepare()
        self.assertEqual(os.environ['LIBBLAS_MT'], libblas_mt_goolfc)
        self.assertEqual(os.environ['LIBFFT_MT'], libfft_mt_goolfc)
        self.assertEqual(os.environ['LIBSCALAPACK'], libscalack_goolfc)

    def test_independence(self):
        """Test independency of toolchain instances."""

        # tweaking --optarch is required for Cray toolchains (craypre-<optarch> module must be available)
        init_config(build_options={'optarch': 'test'})

        tc_cflags = {
            'CrayCCE': "-O2 -homp -craype-verbose",
            'CrayGNU': "-O2 -fno-math-errno -fopenmp -craype-verbose",
            'CrayIntel': "-O2 -ftz -fp-speculation=safe -fp-model source -fopenmp -craype-verbose",
            'GCC': "-O2 -ftree-vectorize -test -fno-math-errno -fopenmp",
            'iccifort': "-O2 -test -ftz -fp-speculation=safe -fp-model source -fopenmp",
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
                # also check whether correct compiler flag for OpenMP is used while we're at it
                tc.set_options({'openmp': True})
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

    def test_compiler_cache(self):
        """Test ccache"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        eb_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        args = [
            eb_file,
            "--use-ccache=%s" % os.path.join(self.test_prefix, 'ccache'),
            "--force",
            "--debug",
            "--disable-cleanup-tmpdir",
        ]

        ccache = which('ccache')
        if ccache is None:
            msg = "ccache binary not found in \$PATH, required by --use-compiler-cache"
            self.assertErrorRegex(EasyBuildError, msg, self.eb_main, args, raise_error=True, do_build=True)

        # generate shell script to mock ccache/f90cache
        for cache_tool in ['ccache', 'f90cache']:
            path = os.path.join(self.test_prefix, 'scripts')

            txt = [
                "#!/bin/bash",
                "echo 'This is a %s wrapper'" % cache_tool,
                "NAME=${0##*/}",
                "comm=$(which -a $NAME | sed 1d)",
                "$comm $@",
                "exit 0"
            ]
            script = '\n'.join(txt)
            fn = os.path.join(path, cache_tool)
            write_file(fn, script)

            # make script executable
            st = os.stat(fn)
            os.chmod(fn, st.st_mode | stat.S_IEXEC)
            setvar('PATH', '%s:%s' % (path, os.getenv('PATH')))

        prepped_path_envvar = os.environ['PATH']

        ccache_dir = os.path.join(self.test_prefix, 'ccache')
        mkdir(ccache_dir, parents=True)

        out = self.eb_main(args, raise_error=True, do_build=True, reset_env=False)

        patterns = [
            "This is a ccache wrapper",
            "Command ccache found at .*%s" % os.path.dirname(path),
        ]
        for pattern in patterns:
            regex = re.compile(pattern)
            self.assertTrue(regex.search(out), "Pattern '%s' found in: %s" % (regex.pattern, out))

        # $CCACHE_DIR is defined by toolchain.prepare(), and should still be defined after running 'eb'
        self.assertTrue(os.path.samefile(os.environ['CCACHE_DIR'], ccache_dir))
        for comp in ['gcc', 'g++', 'gfortran']:
            self.assertTrue(os.path.samefile(which(comp), os.path.join(self.test_prefix, 'scripts', 'ccache')))

        # reset environment to get rid of ccache symlinks, but with ccache/f90cache mock scripts still in place
        os.environ['PATH'] = prepped_path_envvar

        # if both ccache and f90cache are used, Fortran compiler is symlinked to f90cache
        f90cache_dir = os.path.join(self.test_prefix, 'f90cache')
        mkdir(f90cache_dir, parents=True)
        args.append("--use-f90cache=%s" % f90cache_dir)

        out = self.eb_main(args, raise_error=True, do_build=True, reset_env=False)
        for pattern in patterns:
            regex = re.compile(pattern)
            self.assertTrue(regex.search(out), "Pattern '%s' found in: %s" % (regex.pattern, out))

        self.assertTrue(os.path.samefile(os.environ['CCACHE_DIR'], ccache_dir))
        self.assertTrue(os.path.samefile(os.environ['F90CACHE_DIR'], f90cache_dir))
        self.assertTrue(os.path.samefile(which('gcc'), os.path.join(self.test_prefix, 'scripts', 'ccache')))
        self.assertTrue(os.path.samefile(which('g++'), os.path.join(self.test_prefix, 'scripts', 'ccache')))
        self.assertTrue(os.path.samefile(which('gfortran'), os.path.join(self.test_prefix, 'scripts', 'f90cache')))

    def test_rpath_args_script(self):
        """Test rpath_args.py script"""
        script = find_eb_script('rpath_args.py')

        rpath_inc = ','.join([
            os.path.join(self.test_prefix, 'lib'),
            os.path.join(self.test_prefix, 'lib64'),
            '$ORIGIN',
            '$ORIGIN/../lib',
            '$ORIGIN/../lib64',
        ])

        # simplest possible compiler command
        out, ec = run_cmd("%s gcc '' '%s' -c foo.c" % (script, rpath_inc), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
            "'-c'",
            "'foo.c'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # linker command, --enable-new-dtags should be replaced with --disable-new-dtags
        out, ec = run_cmd("%s ld '' '%s' --enable-new-dtags foo.o" % (script, rpath_inc), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-rpath=%s/lib'" % self.test_prefix,
            "'-rpath=%s/lib64'" % self.test_prefix,
            "'-rpath=$ORIGIN'",
            "'-rpath=$ORIGIN/../lib'",
            "'-rpath=$ORIGIN/../lib64'",
            "'--disable-new-dtags'",
            "'--disable-new-dtags'",
            "'foo.o'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # test passing no arguments
        out, ec = run_cmd("%s gcc '' '%s'" % (script, rpath_inc), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # test passing a single empty argument
        out, ec = run_cmd("%s ld.gold '' '%s' ''" % (script, rpath_inc), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-rpath=%s/lib'" % self.test_prefix,
            "'-rpath=%s/lib64'" % self.test_prefix,
            "'-rpath=$ORIGIN'",
            "'-rpath=$ORIGIN/../lib'",
            "'-rpath=$ORIGIN/../lib64'",
            "'--disable-new-dtags'",
            "''",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # single -L argument
        out, ec = run_cmd("%s gcc '' '%s' foo.c -L/foo -lfoo" % (script, rpath_inc), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
            "'-Wl,-rpath=/foo'",
            "'foo.c'",
            "'-L/foo'",
            "'-lfoo'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # relative paths passed to -L are *not* RPATH'ed in
        out, ec = run_cmd("%s gcc '' '%s' foo.c -L../lib -lfoo" % (script, rpath_inc), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
            "'foo.c'",
            "'-L../lib'",
            "'-lfoo'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # single -L argument, with value separated by a space
        out, ec = run_cmd("%s gcc '' '%s' foo.c -L   /foo -lfoo" % (script, rpath_inc), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
            "'-Wl,-rpath=/foo'",
            "'foo.c'",
            "'-L/foo'",
            "'-lfoo'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # multiple -L arguments, order should be preserved
        out, ec = run_cmd("%s ld '' '%s' -L/foo foo.o -L/lib64 -lfoo -lbar -L/usr/lib -L/bar" % (script, rpath_inc), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-rpath=%s/lib'" % self.test_prefix,
            "'-rpath=%s/lib64'" % self.test_prefix,
            "'-rpath=$ORIGIN'",
            "'-rpath=$ORIGIN/../lib'",
            "'-rpath=$ORIGIN/../lib64'",
            "'--disable-new-dtags'",
            "'-rpath=/foo'",
            "'-rpath=/lib64'",
            "'-rpath=/usr/lib'",
            "'-rpath=/bar'",
            "'-L/foo'",
            "'foo.o'",
            "'-L/lib64'",
            "'-lfoo'",
            "'-lbar'",
            "'-L/usr/lib'",
            "'-L/bar'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # test specifying of custom rpath filter
        out, ec = run_cmd("%s ld '/fo.*,/bar.*' '%s' -L/foo foo.o -L/lib64 -lfoo -L/bar -lbar" % (script, rpath_inc), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-rpath=%s/lib'" % self.test_prefix,
            "'-rpath=%s/lib64'" % self.test_prefix,
            "'-rpath=$ORIGIN'",
            "'-rpath=$ORIGIN/../lib'",
            "'-rpath=$ORIGIN/../lib64'",
            "'--disable-new-dtags'",
            "'-rpath=/lib64'",
            "'-L/foo'",
            "'foo.o'",
            "'-L/lib64'",
            "'-lfoo'",
            "'-L/bar'",
            "'-lbar'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # slightly trimmed down real-life example (compilation of XZ)
        args = ' '.join([
            '-fvisibility=hidden',
            '-Wall',
            '-O2',
            '-xHost',
            '-o .libs/lzmainfo',
            'lzmainfo-lzmainfo.o lzmainfo-tuklib_progname.o lzmainfo-tuklib_exit.o',
            '-L/icc/lib/intel64',
            '-L/imkl/lib',
            '-L/imkl/mkl/lib/intel64',
            '-L/gettext/lib',
            '../../src/liblzma/.libs/liblzma.so',
            '-lrt -liomp5 -lpthread',
            '-Wl,-rpath',
            '-Wl,/example/software/XZ/5.2.2-intel-2016b/lib',
        ])
        out, ec = run_cmd("%s icc '' '%s' %s" % (script, rpath_inc, args), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
            "'-Wl,-rpath=/icc/lib/intel64'",
            "'-Wl,-rpath=/imkl/lib'",
            "'-Wl,-rpath=/imkl/mkl/lib/intel64'",
            "'-Wl,-rpath=/gettext/lib'",
            "'-fvisibility=hidden'",
            "'-Wall'",
            "'-O2'",
            "'-xHost'",
            "'-o' '.libs/lzmainfo'",
            "'lzmainfo-lzmainfo.o' 'lzmainfo-tuklib_progname.o' 'lzmainfo-tuklib_exit.o'",
            "'-L/icc/lib/intel64'",
            "'-L/imkl/lib'",
            "'-L/imkl/mkl/lib/intel64'",
            "'-L/gettext/lib'",
            "'../../src/liblzma/.libs/liblzma.so'",
            "'-lrt' '-liomp5' '-lpthread'",
            "'-Wl,-rpath'",
            "'-Wl,/example/software/XZ/5.2.2-intel-2016b/lib'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # trimmed down real-life example involving quotes and escaped quotes (compilation of GCC)
        args = [
            '-DHAVE_CONFIG_H',
            '-I.',
            '-Ibuild',
            '-I../../gcc',
            '-DBASEVER="\\"5.4.0\\""',
            '-DDATESTAMP="\\"\\""',
            '-DPKGVERSION="\\"(GCC) \\""',
            '-DBUGURL="\\"<http://gcc.gnu.org/bugs.html>\\""',
            '-o build/version.o',
            '../../gcc/version.c',
        ]
        cmd = "%s g++ '' '%s' %s" % (script, rpath_inc, ' '.join(args))
        out, ec = run_cmd(cmd, simple=False)
        self.assertEqual(ec, 0)

        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
            "'-DHAVE_CONFIG_H'",
            "'-I.'",
            "'-Ibuild'",
            "'-I../../gcc'",
            "'-DBASEVER=\"5.4.0\"'",
            "'-DDATESTAMP=\"\"'",
            "'-DPKGVERSION=\"(GCC) \"'",
            "'-DBUGURL=\"<http://gcc.gnu.org/bugs.html>\"'",
            "'-o' 'build/version.o'",
            "'../../gcc/version.c'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # verify that no -rpath arguments are injected when command is run in 'version check' mode
        cmd = "%s g++ '' '%s' -v" % (script, rpath_inc)
        out, ec = run_cmd(cmd, simple=False)
        self.assertEqual(ec, 0)
        self.assertEqual(out.strip(), "CMD_ARGS=('-v')")

    def test_toolchain_prepare_rpath(self):
        """Test toolchain.prepare under --rpath"""

        # put fake 'gcc' command in place that just echos its arguments
        fake_gcc = os.path.join(self.test_prefix, 'fake', 'gcc')
        write_file(fake_gcc, '#!/bin/bash\necho "$@"')
        adjust_permissions(fake_gcc, stat.S_IXUSR)
        os.environ['PATH'] = '%s:%s' % (os.path.join(self.test_prefix, 'fake'), os.getenv('PATH', ''))

        # enable --rpath and prepare toolchain
        init_config(build_options={'rpath': True, 'rpath_filter': ['/ba.*']})
        tc = self.get_toolchain('gompi', version='1.3.12')

        # preparing RPATH wrappers requires --experimental, need to bypass that here
        tc.log.experimental = lambda x: x

        # 'rpath' toolchain option gives control to disable use of RPATH wrappers
        tc.set_options({})
        self.assertTrue(tc.options['rpath'])  # enabled by default

        # setting 'rpath' toolchain option to false implies no RPATH wrappers being used
        tc.set_options({'rpath': False})
        tc.prepare()
        res = which('gcc', retain_all=True)
        self.assertTrue(len(res) >= 1)
        self.assertFalse(tc.is_rpath_wrapper(res[0]))
        self.assertFalse(any(tc.is_rpath_wrapper(x) for x in res[1:]))
        self.assertTrue(os.path.samefile(res[0], fake_gcc))

        # enable 'rpath' toolchain option again (equivalent to the default setting)
        tc.set_options({'rpath': True})
        tc.prepare()

        # check that wrapper is indeed in place
        res = which('gcc', retain_all=True)
        # there should be at least 2 hits: the RPATH wrapper, and our fake 'gcc' command (there may be real ones too)
        self.assertTrue(len(res) >= 2)
        self.assertTrue(tc.is_rpath_wrapper(res[0]))
        self.assertFalse(any(tc.is_rpath_wrapper(x) for x in res[1:]))
        self.assertTrue(os.path.samefile(res[1], fake_gcc))
        # any other available 'gcc' commands should not be a wrapper or our fake gcc
        self.assertFalse(any(os.path.samefile(x, fake_gcc) for x in res[2:]))

        # check whether fake gcc was wrapped and that arguments are what they should be
        # no -rpath for /bar because of rpath filter
        out, _ = run_cmd('gcc ${USER}.c -L/foo -L/bar \'$FOO\' -DX="\\"\\""')
        expected = ' '.join([
            '-Wl,--disable-new-dtags',
            '-Wl,-rpath=/foo',
            '%(user)s.c',
            '-L/foo',
            '-L/bar',
            '$FOO',
            '-DX=""',
        ])
        self.assertEqual(out.strip(), expected % {'user': os.getenv('USER')})

        # calling prepare() again should *not* result in wrapping the existing RPATH wrappers
        # this can happen when building extensions
        tc.prepare()
        res = which('gcc', retain_all=True)
        self.assertTrue(len(res) >= 2)
        self.assertTrue(tc.is_rpath_wrapper(res[0]))
        self.assertFalse(any(tc.is_rpath_wrapper(x) for x in res[1:]))
        self.assertTrue(os.path.samefile(res[1], fake_gcc))
        self.assertFalse(any(os.path.samefile(x, fake_gcc) for x in res[2:]))

    def test_prepare_openmpi_tmpdir(self):
        """Test handling of long $TMPDIR path for OpenMPI 2.x"""

        def prep():
            """Helper function: create & prepare toolchain"""
            self.modtool.unload(['gompi', 'OpenMPI', 'hwloc', 'GCC'])
            tc = self.get_toolchain('gompi', version='1.3.12')
            self.mock_stderr(True)
            self.mock_stdout(True)
            tc.prepare()
            stderr = self.get_stderr().strip()
            stdout = self.get_stdout().strip()
            self.mock_stderr(False)
            self.mock_stdout(False)

            return tc, stdout, stderr

        orig_tmpdir = os.environ.get('TMPDIR')
        if len(orig_tmpdir) > 40:
            # we need to make sure we have a short $TMPDIR for this test...
            orig_tmpdir = tempfile.mkdtemp(prefix='/tmp/')
            mkdir(orig_tmpdir)
            os.environ['TMPDIR'] = orig_tmpdir

        long_tmpdir = os.path.join(self.test_prefix, 'verylongdirectorythatmaycauseproblemswithopenmpi2')

        # $TMPDIR is left untouched with OpenMPI 1.6.4
        tc, stdout, stderr = prep()
        self.assertEqual(stdout, '')
        self.assertEqual(stderr, '')
        self.assertEqual(os.environ.get('TMPDIR'), orig_tmpdir)

        # ... even with long $TMPDIR
        os.environ['TMPDIR'] = long_tmpdir
        tc, stdout, stderr = prep()
        self.assertEqual(stdout, '')
        self.assertEqual(stderr, '')
        self.assertEqual(os.environ.get('TMPDIR'), long_tmpdir)
        os.environ['TMPDIR'] = orig_tmpdir

        # copy OpenMPI module used in gompi/1.3.12 to fiddle with it, i.e. to fake bump OpenMPI version used in it
        tmp_modules = os.path.join(self.test_prefix, 'modules')
        mkdir(tmp_modules)

        test_dir = os.path.abspath(os.path.dirname(__file__))
        copy_dir(os.path.join(test_dir, 'modules', 'OpenMPI'), os.path.join(tmp_modules, 'OpenMPI'))

        openmpi_module = os.path.join(tmp_modules, 'OpenMPI', '1.6.4-GCC-4.6.4')
        ompi_mod_txt = read_file(openmpi_module)
        write_file(openmpi_module, ompi_mod_txt.replace('1.6.4', '2.0.2'))

        self.modtool.use(tmp_modules)

        # $TMPDIR is left untouched with OpenMPI 2.x if $TMPDIR is sufficiently short
        os.environ['TMPDIR'] = orig_tmpdir
        tc, stdout, stderr = prep()
        self.assertEqual(stdout, '')
        self.assertEqual(stderr, '')
        self.assertEqual(os.environ.get('TMPDIR'), orig_tmpdir)

        # warning is printed and $TMPDIR is set to shorter path if existing $TMPDIR is too long
        os.environ['TMPDIR'] = long_tmpdir
        tc, stdout, stderr = prep()
        self.assertEqual(stdout, '')
        regex = re.compile("^WARNING: Long \$TMPDIR .* problems with OpenMPI 2.x, using shorter path: /tmp/.{6}$")
        self.assertTrue(regex.match(stderr), "Pattern '%s' found in: %s" % (regex.pattern, stderr))

        # new $TMPDIR should be /tmp/xxxxxx
        tmpdir = os.environ.get('TMPDIR')
        self.assertTrue(tmpdir.startswith('/tmp'))
        self.assertEqual(len(tmpdir), 11)

        # also test cleanup method to ensure short $TMPDIR is cleaned up properly
        self.assertTrue(os.path.exists(tmpdir))
        tc.cleanup()
        self.assertFalse(os.path.exists(tmpdir))

        # we may have created our own short tmpdir above, so make sure to clean things up...
        shutil.rmtree(orig_tmpdir)


def suite():
    """ return all the tests"""
    return TestLoaderFiltered().loadTestsFromTestCase(ToolchainTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
