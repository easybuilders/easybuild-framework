##
# Copyright 2012-2021 Ghent University
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
import sys
import tempfile
from distutils.version import LooseVersion
from itertools import product
from unittest import TextTestRunner
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, find_full_path, init_config

import easybuild.tools.modules as modules
import easybuild.tools.toolchain as toolchain
import easybuild.tools.toolchain.compiler
from easybuild.framework.easyconfig.easyconfig import EasyConfig, ActiveMNS
from easybuild.toolchains.system import SystemToolchain
from easybuild.tools import systemtools as st
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.environment import setvar
from easybuild.tools.filetools import adjust_permissions, copy_dir, find_eb_script, mkdir
from easybuild.tools.filetools import read_file, symlink, write_file, which
from easybuild.tools.py2vs3 import string_type
from easybuild.tools.run import run_cmd
from easybuild.tools.systemtools import get_shared_lib_ext
from easybuild.tools.toolchain.mpi import get_mpi_cmd_template
from easybuild.tools.toolchain.toolchain import env_vars_external_module
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

        init_config(build_options={'silent': True})

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

    def test_system_toolchain(self):
        """Test for system toolchain."""
        for ver in ['system', '']:
            tc = self.get_toolchain('system', version=ver)
            self.assertTrue(isinstance(tc, SystemToolchain))

    def test_foss_toolchain(self):
        """Test for foss toolchain."""
        self.get_toolchain("foss", version="2018a")

    def test_get_variable_system_toolchain(self):
        """Test get_variable on system/dummy toolchain"""

        # system toolchain version doesn't really matter, but fine...
        for ver in ['system', '']:
            tc = self.get_toolchain('system', version=ver)
            tc.prepare()
            self.assertEqual(tc.get_variable('CC'), '')
            self.assertEqual(tc.get_variable('CXX', typ=str), '')
            self.assertEqual(tc.get_variable('CFLAGS', typ=list), [])

        # dummy toolchain is deprecated, so we need to allow for it (and catch the warnings that get printed)
        self.allow_deprecated_behaviour()

        for ver in ['dummy', '']:
            self.mock_stderr(True)
            tc = self.get_toolchain('dummy', version=ver)
            self.mock_stderr(False)
            tc.prepare()
            self.assertEqual(tc.get_variable('CC'), '')
            self.assertEqual(tc.get_variable('CXX', typ=str), '')
            self.assertEqual(tc.get_variable('CFLAGS', typ=list), [])

    def test_is_system_toolchain(self):
        """Test is_system_toolchain method."""

        init_config()

        for ver in ['system', '']:
            tc = self.get_toolchain('system', version=ver)
            self.assertTrue(tc.is_system_toolchain())

        tc = self.get_toolchain('foss', version='2018a')
        self.assertFalse(tc.is_system_toolchain())

        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        self.modtool.prepend_module_path(self.test_prefix)
        tc = self.get_toolchain('intel', version='2018a')
        self.assertFalse(tc.is_system_toolchain())

        # using dummy toolchain is deprecated, so to test for that we need to explicitely allow using deprecated stuff
        error_pattern = "Use of 'dummy' toolchain is deprecated"
        for ver in ['dummy', '']:
            self.assertErrorRegex(EasyBuildError, error_pattern, self.get_toolchain, 'dummy', version=ver)

        dummy_depr_warning = "WARNING: Deprecated functionality, will no longer work in v5.0: Use of 'dummy' toolchain"

        self.allow_deprecated_behaviour()

        for ver in ['dummy', '']:
            self.mock_stderr(True)
            tc = self.get_toolchain('dummy', version=ver)
            stderr = self.get_stderr()
            self.mock_stderr(False)
            self.assertTrue(tc.is_system_toolchain())
            self.assertTrue(dummy_depr_warning in stderr, "Found '%s' in: %s" % (dummy_depr_warning, stderr))

    def test_toolchain_prepare_sysroot(self):
        """Test build environment setup done by Toolchain.prepare in case --sysroot is specified."""

        sysroot = os.path.join(self.test_prefix, 'test', 'alternate', 'sysroot')
        sysroot_pkgconfig = os.path.join(sysroot, 'usr', 'lib', 'pkgconfig')
        mkdir(sysroot_pkgconfig, parents=True)
        init_config(build_options={'sysroot': sysroot})

        # clean environment
        self.unset_compiler_env_vars()

        if 'PKG_CONFIG_PATH' in os.environ:
            del os.environ['PKG_CONFIG_PATH']

        self.assertEqual(os.getenv('PKG_CONFIG_PATH'), None)

        tc = self.get_toolchain('system', version='system')
        tc.prepare()
        self.assertEqual(os.getenv('PKG_CONFIG_PATH'), sysroot_pkgconfig)

        # usr/lib64/pkgconfig is also picked up
        sysroot = sysroot.replace('usr/lib/pkgconfig', 'usr/lib64/pkgconfig')
        mkdir(sysroot_pkgconfig, parents=True)
        init_config(build_options={'sysroot': sysroot})

        del os.environ['PKG_CONFIG_PATH']
        tc.prepare()
        self.assertEqual(os.getenv('PKG_CONFIG_PATH'), sysroot_pkgconfig)

        # existing $PKG_CONFIG_PATH value is retained
        test_pkg_config_path = os.pathsep.join([self.test_prefix, '/foo/bar'])
        os.environ['PKG_CONFIG_PATH'] = test_pkg_config_path
        tc.prepare()
        self.assertEqual(os.getenv('PKG_CONFIG_PATH'), test_pkg_config_path + os.pathsep + sysroot_pkgconfig)

        # no duplicate paths are added
        test_pkg_config_path = os.pathsep.join([self.test_prefix, sysroot_pkgconfig, '/foo/bar'])
        os.environ['PKG_CONFIG_PATH'] = test_pkg_config_path
        tc.prepare()
        self.assertEqual(os.getenv('PKG_CONFIG_PATH'), test_pkg_config_path)

        # if no usr/lib*/pkgconfig subdirectory is present in sysroot, then $PKG_CONFIG_PATH is not touched
        del os.environ['PKG_CONFIG_PATH']
        init_config(build_options={'sysroot': self.test_prefix})
        tc.prepare()
        self.assertEqual(os.getenv('PKG_CONFIG_PATH'), None)

    def unset_compiler_env_vars(self):
        """Unset environment variables before checking whether they're set by the toolchain prep mechanism."""

        comp_env_vars = ['CC', 'CXX', 'F77', 'F90', 'FC']

        env_vars = ['CFLAGS', 'CXXFLAGS', 'F90FLAGS', 'FCFLAGS', 'FFLAGS'] + comp_env_vars[:]
        env_vars.extend(['MPI%s' % x for x in comp_env_vars])
        env_vars.extend(['OMPI_%s' % x for x in comp_env_vars])

        for key in env_vars:
            if key in os.environ:
                del os.environ[key]

    def test_toolchain_compiler_env_vars(self):
        """Test whether environment variables for compilers are defined by toolchain mechanism."""

        # clean environment
        self.unset_compiler_env_vars()
        for key in ['CC', 'CXX', 'F77', 'F90', 'FC']:
            self.assertEqual(os.getenv(key), None)

        # install dummy 'gcc' and 'g++' commands, to make sure they're available
        # (required since Toolchain.set_minimal_build_env checks whether these commands exist)
        for cmd in ['gcc', 'g++']:
            fake_cmd = os.path.join(self.test_prefix, cmd)
            write_file(fake_cmd, '#!/bin/bash')
            adjust_permissions(fake_cmd, stat.S_IRUSR | stat.S_IXUSR)
        os.environ['PATH'] = self.test_prefix + ':' + os.environ['PATH']

        # first try with system compiler: only minimal build environment is set up
        tc = self.get_toolchain('system', version='system')
        tc.set_options({})

        # no warning about redefining if $CC/$CXX are not defined
        self.mock_stderr(True)
        self.mock_stdout(True)
        tc.prepare()
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertEqual(stderr, '')
        self.assertEqual(stdout, '')

        # only $CC and $CXX are set, no point is setting environment variables for Fortran
        # since gfortran is often not installed on the system
        self.assertEqual(os.getenv('CC'), 'gcc')
        self.assertEqual(os.getenv('CXX'), 'g++')
        for key in ['F77', 'F90', 'FC']:
            self.assertEqual(os.getenv(key), None)

        # env vars for compiler flags and MPI compiler commands are not set for system toolchain
        flags_keys = ['CFLAGS', 'CXXFLAGS', 'F90FLAGS', 'FCFLAGS', 'FFLAGS']
        mpi_keys = ['MPICC', 'MPICXX', 'MPIFC', 'OMPI_CC', 'OMPI_CXX', 'OMPI_FC']
        for key in flags_keys + mpi_keys:
            self.assertEqual(os.getenv(key), None)

        self.unset_compiler_env_vars()
        for key in ['CC', 'CXX', 'F77', 'F90', 'FC']:
            self.assertEqual(os.getenv(key), None)

        # warning is printed when EasyBuild redefines environment variables in minimal build environment
        os.environ['CC'] = 'foo'
        os.environ['CXX'] = 'bar'

        self.mock_stderr(True)
        self.mock_stdout(True)
        tc.prepare()
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertEqual(stdout, '')

        for key, prev_val, new_val in [('CC', 'foo', 'gcc'), ('CXX', 'bar', 'g++')]:
            warning_msg = "WARNING: $%s was defined as '%s', " % (key, prev_val)
            warning_msg += "but is now set to '%s' in minimal build environment" % new_val
            self.assertTrue(warning_msg in stderr)

        self.assertEqual(os.getenv('CC'), 'gcc')
        self.assertEqual(os.getenv('CXX'), 'g++')

        # no warning if the values are identical to the ones used in the minimal build environment
        self.mock_stderr(True)
        self.mock_stdout(True)
        tc.prepare()
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertEqual(stderr, '')
        self.assertEqual(stdout, '')

        del os.environ['CC']
        del os.environ['CXX']

        # check whether specification in --minimal-build-env is picked up
        init_config(build_options={'minimal_build_env': 'CC:g++'})

        tc.prepare()
        self.assertEqual(os.getenv('CC'), 'g++')
        self.assertEqual(os.getenv('CXX'), None)

        del os.environ['CC']

        # check whether a warning is printed when a value specified for $CC or $CXX is not found
        init_config(build_options={'minimal_build_env': 'CC:nosuchcommand,CXX:gcc'})

        self.mock_stderr(True)
        self.mock_stdout(True)
        tc.prepare()
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        warning_msg = "WARNING: 'nosuchcommand' command not found in $PATH, "
        warning_msg += "not setting $CC in minimal build environment"
        self.assertTrue(warning_msg in stderr)
        self.assertEqual(stdout, '')

        self.assertEqual(os.getenv('CC'), None)
        self.assertEqual(os.getenv('CXX'), 'gcc')

        # no warning for defining environment variable that was previously undefined,
        # only warning on redefining, other values can be whatever (and can include spaces)
        init_config(build_options={'minimal_build_env': 'CC:gcc,CXX:g++,CFLAGS:-O2,CXXFLAGS:-O3 -g,FC:gfortan'})

        for key in ['CFLAGS', 'CXXFLAGS', 'FC']:
            if key in os.environ:
                del os.environ[key]

        self.mock_stderr(True)
        self.mock_stdout(True)
        tc.prepare()
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertEqual(os.getenv('CC'), 'gcc')
        self.assertEqual(os.getenv('CXX'), 'g++')
        self.assertEqual(os.getenv('CFLAGS'), '-O2')
        self.assertEqual(os.getenv('CXXFLAGS'), '-O3 -g')
        self.assertEqual(os.getenv('FC'), 'gfortan')

        # incorrect spec in minimal_build_env results in an error
        init_config(build_options={'minimal_build_env': 'CC=gcc'})
        error_pattern = "Incorrect mapping in --minimal-build-env value: 'CC=gcc'"
        self.assertErrorRegex(EasyBuildError, error_pattern, tc.prepare)

        init_config(build_options={'minimal_build_env': 'foo:bar:baz'})
        error_pattern = "Incorrect mapping in --minimal-build-env value: 'foo:bar:baz'"
        self.assertErrorRegex(EasyBuildError, error_pattern, tc.prepare)

        init_config(build_options={'minimal_build_env': 'CC:gcc,foo'})
        error_pattern = "Incorrect mapping in --minimal-build-env value: 'foo'"
        self.assertErrorRegex(EasyBuildError, error_pattern, tc.prepare)

        init_config(build_options={'minimal_build_env': 'foo:bar:baz,CC:gcc'})
        error_pattern = "Incorrect mapping in --minimal-build-env value: 'foo:bar:baz'"
        self.assertErrorRegex(EasyBuildError, error_pattern, tc.prepare)

        init_config(build_options={'minimal_build_env': 'CC:gcc,'})
        error_pattern = "Incorrect mapping in --minimal-build-env value: ''"
        self.assertErrorRegex(EasyBuildError, error_pattern, tc.prepare)

        # for a full toolchain, a more extensive build environment is set up (incl. $CFLAGS & co),
        # and the specs in --minimal-build-env are ignored
        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({})

        # catch potential warning about too long $TMPDIR value that causes trouble for Open MPI (irrelevant here)
        self.mock_stderr(True)
        tc.prepare()
        self.mock_stderr(False)

        self.assertEqual(os.getenv('CC'), 'gcc')
        self.assertEqual(os.getenv('CXX'), 'g++')
        self.assertEqual(os.getenv('F77'), 'gfortran')
        self.assertEqual(os.getenv('F90'), 'gfortran')
        self.assertEqual(os.getenv('FC'), 'gfortran')

        self.assertEqual(os.getenv('MPICC'), 'mpicc')
        self.assertEqual(os.getenv('MPICXX'), 'mpicxx')
        self.assertEqual(os.getenv('MPIF77'), 'mpifort')
        self.assertEqual(os.getenv('MPIF90'), 'mpifort')
        self.assertEqual(os.getenv('MPIFC'), 'mpifort')

        self.assertEqual(os.getenv('OMPI_CC'), 'gcc')
        self.assertEqual(os.getenv('OMPI_CXX'), 'g++')
        self.assertEqual(os.getenv('OMPI_F77'), 'gfortran')
        self.assertEqual(os.getenv('OMPI_FC'), 'gfortran')

        for key in ['CFLAGS', 'CXXFLAGS', 'F90FLAGS', 'FCFLAGS', 'FFLAGS']:
            self.assertEqual(os.getenv(key), "-O2 -ftree-vectorize -march=native -fno-math-errno")

    def test_get_variable_compilers(self):
        """Test get_variable function to obtain compiler variables."""

        tc = self.get_toolchain('foss', version='2018a')
        tc.prepare()

        self.assertEqual(tc.get_variable('CC'), 'gcc')
        self.assertEqual(tc.get_variable('CXX'), 'g++')
        self.assertEqual(tc.get_variable('F77'), 'gfortran')
        self.assertEqual(tc.get_variable('F90'), 'gfortran')
        self.assertEqual(tc.get_variable('FC'), 'gfortran')

        self.assertEqual(tc.get_variable('MPICC'), 'mpicc')
        self.assertEqual(tc.get_variable('MPICXX'), 'mpicxx')
        self.assertEqual(tc.get_variable('MPIF77'), 'mpifort')
        self.assertEqual(tc.get_variable('MPIF90'), 'mpifort')
        self.assertEqual(tc.get_variable('MPIFC'), 'mpifort')

        self.assertEqual(tc.get_variable('OMPI_CC'), 'gcc')
        self.assertEqual(tc.get_variable('OMPI_CXX'), 'g++')
        self.assertEqual(tc.get_variable('OMPI_F77'), 'gfortran')
        self.assertEqual(tc.get_variable('OMPI_FC'), 'gfortran')

    def check_vars_foss_usempi(self, tc):
        """Utility function to check compiler variables for foss toolchain with usempi enabled."""

        self.assertEqual(tc.get_variable('CC'), 'mpicc')
        self.assertEqual(tc.get_variable('CXX'), 'mpicxx')
        self.assertEqual(tc.get_variable('F77'), 'mpifort')
        self.assertEqual(tc.get_variable('F90'), 'mpifort')
        self.assertEqual(tc.get_variable('FC'), 'mpifort')

        self.assertEqual(tc.get_variable('MPICC'), 'mpicc')
        self.assertEqual(tc.get_variable('MPICXX'), 'mpicxx')
        self.assertEqual(tc.get_variable('MPIF77'), 'mpifort')
        self.assertEqual(tc.get_variable('MPIF90'), 'mpifort')
        self.assertEqual(tc.get_variable('MPIFC'), 'mpifort')

        self.assertEqual(tc.get_variable('OMPI_CC'), 'gcc')
        self.assertEqual(tc.get_variable('OMPI_CXX'), 'g++')
        self.assertEqual(tc.get_variable('OMPI_F77'), 'gfortran')
        self.assertEqual(tc.get_variable('OMPI_FC'), 'gfortran')

    def test_get_variable_mpi_compilers(self):
        """Test get_variable function to obtain compiler variables."""
        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({'usempi': True})
        tc.prepare()

        self.check_vars_foss_usempi(tc)

    def test_prepare_iterate(self):
        """Test preparing of toolchain in iterative context."""
        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({'usempi': True})

        tc.prepare()
        self.check_vars_foss_usempi(tc)

        # without a reset, the value is wrong...
        tc.prepare()
        self.assertFalse(tc.get_variable('MPICC') == 'mpicc')

        tc.reset()
        tc.prepare()
        self.check_vars_foss_usempi(tc)

    def test_cray_reset(self):
        """Test toolchain preparation after reset for Cray* toolchain."""
        # cfr. https://github.com/easybuilders/easybuild-framework/issues/2911
        init_config(build_options={'optarch': 'test', 'silent': True})

        for tcname in ['CrayGNU', 'CrayCCE', 'CrayIntel']:
            tc = self.get_toolchain(tcname, version='2015.06-XC')
            tc.set_options({'dynamic': True})
            tc.prepare()
            self.assertEqual(os.environ.get('LIBBLAS'), '')
            tc.reset()
            tc.prepare()
            self.assertEqual(os.environ.get('LIBBLAS'), '')
            tc.reset()
            tc.prepare()
            self.assertEqual(os.environ.get('LIBBLAS'), '')
            tc.reset()
            tc.prepare()
            self.assertEqual(os.environ.get('LIBBLAS'), '')

    def test_get_variable_seq_compilers(self):
        """Test get_variable function to obtain compiler variables."""
        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({'usempi': True})
        tc.prepare()

        self.assertEqual(tc.get_variable('CC_SEQ'), 'gcc')
        self.assertEqual(tc.get_variable('CXX_SEQ'), 'g++')
        self.assertEqual(tc.get_variable('F77_SEQ'), 'gfortran')
        self.assertEqual(tc.get_variable('F90_SEQ'), 'gfortran')
        self.assertEqual(tc.get_variable('FC_SEQ'), 'gfortran')

    def test_get_variable_libs_list(self):
        """Test get_variable function to obtain list of libraries."""
        tc = self.get_toolchain('foss', version='2018a')
        tc.prepare()

        ldflags = tc.get_variable('LDFLAGS', typ=list)
        self.assertTrue(isinstance(ldflags, list))
        if len(ldflags) > 0:
            self.assertTrue(isinstance(ldflags[0], string_type))

    def test_validate_pass_by_value(self):
        """
        Check that elements of variables are passed by value, not by reference,
        which is required to ensure correctness.
        """
        tc = self.get_toolchain('foss', version='2018a')
        tc.prepare()

        pass_by_value = True
        ids = []
        for k, v in tc.variables.items():
            for x in v:
                idx = id(x)
                if idx not in ids:
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
        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            self.assertTrue(tc.COMPILER_SHARED_OPTION_MAP['defaultopt'] in flags)

        # check other optimization flags
        for opt in ['noopt', 'lowopt', 'opt']:
            tc = self.get_toolchain('foss', version='2018a')
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
        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({'lowopt': True, 'opt': True})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            flag = '-%s' % tc.COMPILER_SHARED_OPTION_MAP['lowopt']
            self.assertTrue(flag in flags)
        self.modtool.purge()

        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({'noopt': True, 'lowopt': True})
        tc.prepare()
        for var in flag_vars:
            flags = tc.get_variable(var)
            flag = '-%s' % tc.COMPILER_SHARED_OPTION_MAP['noopt']
            self.assertTrue(flag in flags)
        self.modtool.purge()

        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({'noopt': True, 'lowopt': True, 'opt': True})
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
                tc = self.get_toolchain('foss', version='2018a')
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

        value = '--see-if-this-propagates'
        for var in flag_vars:
            opt = 'extra_' + var.lower()
            tc = self.get_toolchain('foss', version='2018a')
            tc.set_options({opt: value})
            tc.prepare()
            self.assertTrue(tc.get_variable(var).endswith(' ' + value))
            self.modtool.purge()

        value = '--only-in-cxxflags'
        flag_vars.remove('CXXFLAGS')
        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({'extra_cxxflags': value})
        tc.prepare()
        self.assertTrue(tc.get_variable('CXXFLAGS').endswith(' ' + value))
        for var in flag_vars:
            self.assertTrue(value not in tc.get_variable(var))
            # https://github.com/easybuilders/easybuild-framework/pull/3571
            # catch variable resued inside loop
            self.assertTrue("-o -n -l -y" not in tc.get_variable(var))
        self.modtool.purge()

    def test_misc_flags_unique(self):
        """Test whether unique compiler flags are set correctly."""

        flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']

        # setting option should result in corresponding flag to be set (unique options)
        for opt in ['unroll', 'optarch', 'openmp', 'vectorize']:
            for enable in [True, False]:
                tc = self.get_toolchain('foss', version='2018a')
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
            init_config(build_options={'optarch': optarch_var, 'silent': True})
            for enable in [True, False]:
                tc = self.get_toolchain('foss', version='2018a')
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
                init_config(build_options={'optarch': 'GENERIC', 'silent': True})
            flag_vars = ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']
            tcs = {
                'gompi': ('2018a', "-march=x86-64 -mtune=generic"),
                'iccifort': ('2018.1.163', "-xSSE2 -ftz -fp-speculation=safe -fp-model source"),
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
        tc = self.get_toolchain("GCC", version="4.6.4")
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
        tc = self.get_toolchain("GCC", version="4.6.4")
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

        tc_intel = ('iccifort', '2018.1.163')
        tc_gcc = ('GCC', '6.4.0-2.28')
        tc_gcccore = ('GCCcore', '6.2.0')
        tc_pgi = ('PGI', '16.7-GCC-5.4.0-2.26')
        enabled = [True, False]

        test_cases = []
        for i, (tc, options) in enumerate(zip((tc_intel, tc_gcc, tc_gcccore),
                                              (intel_options, gcc_options, gcccore_options))):
            # Vary only the compiler specific option
            for opt in options:
                new_value = [intel_options[0], gcc_options[0], gcccore_options[0], tc]
                new_value[i] = opt
                test_cases.append(new_value)
        # Add one case for PGI
        test_cases.append((intel_options[0], gcc_options[0], gcccore_options[0], tc_pgi))

        # Run each for enabled and disabled
        test_cases = list(product(test_cases, enabled))

        for (intel_flags, gcc_flags, gcccore_flags, (toolchain_name, toolchain_ver)), enable in test_cases:

            intel_flags, intel_flags_exp = intel_flags
            gcc_flags, gcc_flags_exp = gcc_flags
            gcccore_flags, gcccore_flags_exp = gcccore_flags

            optarch_var = {}
            optarch_var['Intel'] = intel_flags
            optarch_var['GCC'] = gcc_flags
            optarch_var['GCCcore'] = gcccore_flags
            init_config(build_options={'optarch': optarch_var, 'silent': True})
            tc = self.get_toolchain(toolchain_name, version=toolchain_ver)
            tc.set_options({'optarch': enable})
            tc.prepare()
            flags = None
            if toolchain_name == 'iccifort':
                flags = intel_flags_exp
            elif toolchain_name == 'GCC':
                flags = gcc_flags_exp
            elif toolchain_name == 'GCCcore':
                flags = gcccore_flags_exp
            else:  # PGI as an example of compiler not set
                # default optarch flag, should be the same as the one in
                # tc.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[(tc.arch,tc.cpu_family)]
                flags = ''

            optarch_flags = tc.options.options_map['optarch']

            self.assertEqual(flags, optarch_flags)

            # Also check that it is correctly passed to xFLAGS, honoring 'enable'
            if flags == '':
                blacklist = [
                    intel_options[0][1],
                    intel_options[1][1],
                    gcc_options[0][1],
                    gcc_options[1][1],
                    gcccore_options[0][1],
                    gcccore_options[1][1],
                    'xHost',  # default optimal for Intel
                    'march=native',  # default optimal for GCC
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

    def test_easyconfig_optarch_flags(self):
        """Test whether specifying optarch flags in the easyconfigs works."""
        topdir = os.path.dirname(os.path.abspath(__file__))
        eb_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-2018a.eb')

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        toy_txt = read_file(eb_file)

        # check that an optarch map raises an error
        write_file(test_ec, toy_txt + "\ntoolchainopts = {'optarch': 'GCC:march=sandrybridge;Intel:xAVX'}")
        msg = "syntax is not allowed"
        self.assertErrorRegex(EasyBuildError, msg, self.eb_main, [test_ec], raise_error=True, do_build=True)

        # check that setting optarch flags work
        write_file(test_ec, toy_txt + "\ntoolchainopts = {'optarch': 'march=sandybridge'}")
        out = self.eb_main([test_ec], raise_error=True, do_build=True)
        regex = re.compile("_set_optimal_architecture: using march=sandybridge as optarch for x86_64")
        self.assertTrue(regex.search(out), "Pattern '%s' found in: %s" % (regex.pattern, out))

    def test_misc_flags_unique_fortran(self):
        """Test whether unique Fortran compiler flags are set correctly."""

        flag_vars = ['FCFLAGS', 'FFLAGS', 'F90FLAGS']

        # setting option should result in corresponding flag to be set (Fortran unique options)
        for opt in ['i8', 'r8']:
            for enable in [True, False]:
                tc = self.get_toolchain('foss', version='2018a')
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
        tc = self.get_toolchain('foss', version='2018a')
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
                tc = self.get_toolchain('foss', version='2018a')
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
        tc = self.get_toolchain('foss', version='2018a')
        tc.prepare()
        self.assertEqual(tc.comp_family(), "GCC")

    def test_mpi_family(self):
        """Test determining MPI family."""
        # check subtoolchain w/o MPI
        tc = self.get_toolchain("GCC", version="6.4.0-2.28")
        tc.prepare()
        self.assertEqual(tc.mpi_family(), None)
        self.modtool.purge()

        # check full toolchain including MPI
        tc = self.get_toolchain('foss', version='2018a')
        tc.prepare()
        self.assertEqual(tc.mpi_family(), "OpenMPI")
        self.modtool.purge()

        # check another one
        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        self.modtool.prepend_module_path(self.test_prefix)
        tc = self.get_toolchain("intel", version="2018a")
        tc.prepare()
        self.assertEqual(tc.mpi_family(), "IntelMPI")

    def test_blas_lapack_family(self):
        """Test determining BLAS/LAPACK family."""
        # check compiler-only (sub)toolchain
        tc = self.get_toolchain("GCC", version="6.4.0-2.28")
        tc.prepare()
        self.assertEqual(tc.blas_family(), None)
        self.assertEqual(tc.lapack_family(), None)
        self.modtool.purge()

        # check compiler/MPI-only (sub)toolchain
        tc = self.get_toolchain('gompi', version='2018a')
        tc.prepare()
        self.assertEqual(tc.blas_family(), None)
        self.assertEqual(tc.lapack_family(), None)
        self.modtool.purge()

        # check full toolchain including BLAS/LAPACK
        tc = self.get_toolchain('fosscuda', version='2018a')
        tc.prepare()
        self.assertEqual(tc.blas_family(), 'OpenBLAS')
        self.assertEqual(tc.lapack_family(), 'OpenBLAS')
        self.modtool.purge()

        # check another one
        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        self.modtool.prepend_module_path(self.test_prefix)
        tc = self.get_toolchain('intel', version='2018a')
        tc.prepare()
        self.assertEqual(tc.blas_family(), 'IntelMKL')
        self.assertEqual(tc.lapack_family(), 'IntelMKL')

    def test_fft_env_vars_foss(self):
        """Test setting of $FFT* environment variables using foss toolchain."""
        tc = self.get_toolchain('foss', version='2018a')
        tc.prepare()

        fft_static_libs = 'libfftw3.a'
        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS'), fft_static_libs)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS'), fft_static_libs)

        fft_static_libs_mt = 'libfftw3.a,libpthread.a'
        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS_MT'), fft_static_libs_mt)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS_MT'), fft_static_libs_mt)

        self.assertEqual(tc.get_variable('LIBFFT'), '-lfftw3')
        self.assertEqual(tc.get_variable('LIBFFT_MT'), '-lfftw3 -lpthread')

        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({'openmp': True})
        tc.prepare()

        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS'), fft_static_libs)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS'), fft_static_libs)

        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS_MT'), 'libfftw3_omp.a,' + fft_static_libs_mt)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS_MT'), 'libfftw3_omp.a,' + fft_static_libs_mt)

        self.assertEqual(tc.get_variable('LIBFFT'), '-lfftw3')
        self.assertEqual(tc.get_variable('LIBFFT_MT'), '-lfftw3_omp -lfftw3 -lpthread')

        tc = self.get_toolchain('foss', version='2018a')
        tc.set_options({'usempi': True})
        tc.prepare()

        fft_static_libs = 'libfftw3_mpi.a,libfftw3.a'
        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS'), fft_static_libs)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS'), fft_static_libs)

        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS_MT'), fft_static_libs_mt)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS_MT'), fft_static_libs_mt)

        self.assertEqual(tc.get_variable('LIBFFT'), '-lfftw3_mpi -lfftw3')
        self.assertEqual(tc.get_variable('LIBFFT_MT'), '-lfftw3 -lpthread')

    def test_fft_env_vars_intel(self):
        """Test setting of $FFT* environment variables using intel toolchain."""

        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        self.modtool.prepend_module_path(self.test_prefix)

        tc = self.get_toolchain('intel', version='2018a')
        tc.prepare()

        fft_static_libs = 'libfftw3xc_intel.a,libmkl_intel_lp64.a,libmkl_sequential.a,libmkl_core.a'
        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS'), fft_static_libs)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS'), fft_static_libs)

        fft_static_libs_mt = 'libfftw3xc_intel.a,libmkl_intel_lp64.a,libmkl_intel_thread.a,libmkl_core.a,'
        fft_static_libs_mt += 'libiomp5.a,libpthread.a'
        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS_MT'), fft_static_libs_mt)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS_MT'), fft_static_libs_mt)

        libfft = "-Wl,-Bstatic -Wl,--start-group -lfftw3xc_intel -lmkl_intel_lp64 -lmkl_sequential -lmkl_core "
        libfft += "-Wl,--end-group -Wl,-Bdynamic"
        self.assertEqual(tc.get_variable('LIBFFT'), libfft)

        libfft_mt = "-Wl,-Bstatic -Wl,--start-group -lfftw3xc_intel -lmkl_intel_lp64 -lmkl_intel_thread -lmkl_core "
        libfft_mt += "-Wl,--end-group -Wl,-Bdynamic -liomp5 -lpthread"
        self.assertEqual(tc.get_variable('LIBFFT_MT'), libfft_mt)

        tc = self.get_toolchain('intel', version='2018a')
        tc.set_options({'openmp': True})
        tc.prepare()

        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS'), fft_static_libs)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS'), fft_static_libs)

        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS_MT'), fft_static_libs_mt)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS_MT'), fft_static_libs_mt)

        self.assertEqual(tc.get_variable('LIBFFT'), libfft)
        self.assertEqual(tc.get_variable('LIBFFT_MT'), libfft_mt)

        tc = self.get_toolchain('intel', version='2018a')
        tc.set_options({'usempi': True})
        tc.prepare()

        fft_static_libs = 'libfftw3xc_intel.a,libfftw3x_cdft_lp64.a,libmkl_cdft_core.a,libmkl_blacs_intelmpi_lp64.a,'
        fft_static_libs += 'libmkl_intel_lp64.a,libmkl_sequential.a,libmkl_core.a'
        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS'), fft_static_libs)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS'), fft_static_libs)

        fft_static_libs_mt = 'libfftw3xc_intel.a,libfftw3x_cdft_lp64.a,libmkl_cdft_core.a,libmkl_blacs_intelmpi_lp64.a,'
        fft_static_libs_mt += 'libmkl_intel_lp64.a,libmkl_intel_thread.a,libmkl_core.a,libiomp5.a,libpthread.a'
        self.assertEqual(tc.get_variable('FFT_STATIC_LIBS_MT'), fft_static_libs_mt)
        self.assertEqual(tc.get_variable('FFTW_STATIC_LIBS_MT'), fft_static_libs_mt)

        libfft = '-Wl,-Bstatic -Wl,--start-group -lfftw3xc_intel -lfftw3x_cdft_lp64 -lmkl_cdft_core '
        libfft += '-lmkl_blacs_intelmpi_lp64 -lmkl_intel_lp64 -lmkl_sequential -lmkl_core -Wl,--end-group -Wl,-Bdynamic'
        self.assertEqual(tc.get_variable('LIBFFT'), libfft)

        libfft_mt = '-Wl,-Bstatic -Wl,--start-group -lfftw3xc_intel -lfftw3x_cdft_lp64 -lmkl_cdft_core '
        libfft_mt += '-lmkl_blacs_intelmpi_lp64 -lmkl_intel_lp64 -lmkl_intel_thread -lmkl_core -Wl,--end-group '
        libfft_mt += '-Wl,-Bdynamic -liomp5 -lpthread'
        self.assertEqual(tc.get_variable('LIBFFT_MT'), libfft_mt)

    def test_fosscuda(self):
        """Test whether fosscuda is handled properly."""
        tc = self.get_toolchain("fosscuda", version="2018a")
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

    def setup_sandbox_for_intel_fftw(self, moddir, imklver='2018.1.163'):
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

    def test_intel_toolchain(self):
        """Test for intel toolchain."""
        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        self.modtool.prepend_module_path(self.test_prefix)

        tc = self.get_toolchain("intel", version="2018a")
        tc.prepare()

        self.assertEqual(tc.get_variable('CC'), 'icc')
        self.assertEqual(tc.get_variable('CXX'), 'icpc')
        self.assertEqual(tc.get_variable('F77'), 'ifort')
        self.assertEqual(tc.get_variable('F90'), 'ifort')
        self.assertEqual(tc.get_variable('FC'), 'ifort')
        self.modtool.purge()

        tc = self.get_toolchain("intel", version="2018a")
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

        tc = self.get_toolchain("intel", version="2018a")
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
        tc = self.get_toolchain('intel', version='2012a')
        opts = {'openmp': True}
        tc.set_options(opts)
        tc.prepare()
        self.assertEqual(tc.get_variable('MPIFC'), 'mpiifort')
        for var in ['CFLAGS', 'CXXFLAGS', 'FCFLAGS', 'FFLAGS', 'F90FLAGS']:
            self.assertTrue('-openmp' in tc.get_variable(var))

    def test_toolchain_verification(self):
        """Test verification of toolchain definition."""
        tc = self.get_toolchain('foss', version='2018a')
        tc.prepare()
        self.modtool.purge()

        # toolchain modules missing a toolchain element should fail verification
        error_msg = "List of toolchain dependency modules and toolchain definition do not match"
        tc = self.get_toolchain('foss', version='2018a-brokenFFTW')
        self.assertErrorRegex(EasyBuildError, error_msg, tc.prepare)
        self.modtool.purge()

        # missing optional toolchain elements are fine
        tc = self.get_toolchain('fosscuda', version='2018a')
        opts = {'cuda_gencode': ['arch=compute_35,code=sm_35', 'arch=compute_10,code=compute_10']}
        tc.set_options(opts)
        tc.prepare()

    def test_nosuchtoolchain(self):
        """Test preparing for a toolchain for which no module is available."""
        tc = self.get_toolchain('intel', version='1970.01')
        self.assertErrorRegex(EasyBuildError, "No module found for toolchain", tc.prepare)

    def test_mpi_cmd_prefix(self):
        """Test mpi_exec_nranks function."""
        self.modtool.prepend_module_path(self.test_prefix)

        # first try calling mpi_cmd_prefix without having any modules loaded, should not cause trouble

        # for toolchain with Intel MPI we get None as result in this cause (because impi version can
        # not be determined)
        tc = self.get_toolchain('intel', version='2018a')
        self.assertEqual(tc.mpi_cmd_prefix(nr_ranks=2), None)

        tc = self.get_toolchain('gompi', version='2018a')
        self.assertEqual(tc.mpi_cmd_prefix(nr_ranks=2), "mpirun -n 2")

        tc = self.get_toolchain('gompi', version='2018a')
        tc.prepare()
        self.assertEqual(tc.mpi_cmd_prefix(nr_ranks=2), "mpirun -n 2")
        self.assertEqual(tc.mpi_cmd_prefix(nr_ranks='2'), "mpirun -n 2")
        self.assertEqual(tc.mpi_cmd_prefix(), "mpirun -n 1")
        self.modtool.purge()

        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        tc = self.get_toolchain('intel', version='2018a')
        tc.prepare()
        self.assertEqual(tc.mpi_cmd_prefix(nr_ranks=2), "mpirun -n 2")
        self.assertEqual(tc.mpi_cmd_prefix(nr_ranks='2'), "mpirun -n 2")
        self.assertEqual(tc.mpi_cmd_prefix(), "mpirun -n 1")
        self.modtool.purge()

        self.setup_sandbox_for_intel_fftw(self.test_prefix, imklver='10.2.6.038')
        tc = self.get_toolchain('intel', version='2012a')
        tc.prepare()

        mpi_exec_nranks_re = re.compile("^mpirun --file=.*/mpdboot -machinefile .*/nodes -np 4")
        self.assertTrue(mpi_exec_nranks_re.match(tc.mpi_cmd_prefix(nr_ranks=4)))
        mpi_exec_nranks_re = re.compile("^mpirun --file=.*/mpdboot -machinefile .*/nodes -np 1")
        self.assertTrue(mpi_exec_nranks_re.match(tc.mpi_cmd_prefix()))

        # test specifying custom template for MPI commands
        init_config(build_options={'mpi_cmd_template': "mpiexec -np %(nr_ranks)s -- %(cmd)s", 'silent': True})
        self.assertEqual(tc.mpi_cmd_prefix(nr_ranks="7"), "mpiexec -np 7 --")
        self.assertEqual(tc.mpi_cmd_prefix(), "mpiexec -np 1 --")

        # check that we return None when command does not appear at the end of the template
        init_config(build_options={'mpi_cmd_template': "mpiexec -np %(nr_ranks)s -- %(cmd)s option", 'silent': True})
        self.assertEqual(tc.mpi_cmd_prefix(nr_ranks="7"), None)
        self.assertEqual(tc.mpi_cmd_prefix(), None)

        # template with extra spaces at the end if fine though
        init_config(build_options={'mpi_cmd_template': "mpirun -np %(nr_ranks)s %(cmd)s  ", 'silent': True})
        self.assertEqual(tc.mpi_cmd_prefix(), "mpirun -np 1")

    def test_mpi_cmd_for(self):
        """Test mpi_cmd_for function."""
        self.modtool.prepend_module_path(self.test_prefix)

        # if mpi_cmd_for is called too early when using toolchain that includes impi,
        # we get None as result because Intel MPI version can not be determined
        tc = self.get_toolchain('intel', version='2018a')
        self.assertEqual(tc.mpi_cmd_for('test123', 2), None)

        # no problem for OpenMPI-based toolchain, because OpenMPI version is not required
        # to determine MPI command template
        tc = self.get_toolchain('gompi', version='2018a')
        self.assertEqual(tc.mpi_cmd_for('test123', 2), "mpirun -n 2 test123")

        tc = self.get_toolchain('gompi', version='2018a')
        tc.prepare()
        self.assertEqual(tc.mpi_cmd_for('test123', 2), "mpirun -n 2 test123")
        self.modtool.purge()

        self.setup_sandbox_for_intel_fftw(self.test_prefix)
        tc = self.get_toolchain('intel', version='2018a')
        tc.prepare()
        self.assertEqual(tc.mpi_cmd_for('test123', 2), "mpirun -n 2 test123")
        self.modtool.purge()

        self.setup_sandbox_for_intel_fftw(self.test_prefix, imklver='10.2.6.038')
        tc = self.get_toolchain('intel', version='2012a')
        tc.prepare()

        mpi_cmd_for_re = re.compile("^mpirun --file=.*/mpdboot -machinefile .*/nodes -np 4 test$")
        self.assertTrue(mpi_cmd_for_re.match(tc.mpi_cmd_for('test', 4)))

        # test specifying custom template for MPI commands
        init_config(build_options={'mpi_cmd_template': "mpiexec -np %(nr_ranks)s -- %(cmd)s", 'silent': True})
        self.assertEqual(tc.mpi_cmd_for('test123', '7'), "mpiexec -np 7 -- test123")

        # check whether expected error is raised when a template with missing keys is used;
        # %(ranks)s should be %(nr_ranks)s
        init_config(build_options={'mpi_cmd_template': "mpiexec -np %(ranks)s -- %(cmd)s", 'silent': True})
        error_pattern = \
            r"Missing templates in mpi-cmd-template value 'mpiexec -np %\(ranks\)s -- %\(cmd\)s': %\(nr_ranks\)s"
        self.assertErrorRegex(EasyBuildError, error_pattern, tc.mpi_cmd_for, 'test', 1)

        init_config(build_options={'mpi_cmd_template': "mpirun %(foo)s -np %(nr_ranks)s %(cmd)s", 'silent': True})
        error_pattern = "Failed to complete MPI cmd template .* with .*: KeyError 'foo'"
        self.assertErrorRegex(EasyBuildError, error_pattern, tc.mpi_cmd_for, 'test', 1)

    def test_get_mpi_cmd_template(self):
        """Test get_mpi_cmd_template function."""

        # search_toolchain needs to be called once to make sure constants like toolchain.OPENMPI are in place
        search_toolchain('')

        input_params = {'nr_ranks': 123, 'cmd': 'this_is_just_a_test'}

        for mpi_fam in [toolchain.OPENMPI, toolchain.MPICH, toolchain.MPICH2, toolchain.MVAPICH2]:
            mpi_cmd_tmpl, params = get_mpi_cmd_template(mpi_fam, input_params)
            self.assertEqual(mpi_cmd_tmpl, "mpirun -n %(nr_ranks)s %(cmd)s")
            self.assertEqual(params, input_params)

        # Intel MPI is a special case, also requires MPI version to be known
        impi = toolchain.INTELMPI
        error_pattern = "Intel MPI version unknown, can't determine MPI command template!"
        self.assertErrorRegex(EasyBuildError, error_pattern, get_mpi_cmd_template, impi, {})

        mpi_cmd_tmpl, params = get_mpi_cmd_template(toolchain.INTELMPI, input_params, mpi_version='1.0')
        self.assertEqual(mpi_cmd_tmpl, "mpirun %(mpdbf)s %(nodesfile)s -np %(nr_ranks)s %(cmd)s")
        self.assertEqual(sorted(params.keys()), ['cmd', 'mpdbf', 'nodesfile', 'nr_ranks'])
        self.assertEqual(params['cmd'], 'this_is_just_a_test')
        self.assertEqual(params['nr_ranks'], 123)

        mpdbf = params['mpdbf']
        regex = re.compile('^--file=.*/mpdboot$')
        self.assertTrue(regex.match(mpdbf), "'%s' should match pattern '%s'" % (mpdbf, regex.pattern))
        self.assertTrue(os.path.exists(mpdbf.split('=')[1]))

        nodesfile = params['nodesfile']
        regex = re.compile('^-machinefile /.*/nodes$')
        self.assertTrue(regex.match(nodesfile), "'%s' should match pattern '%s'" % (nodesfile, regex.pattern))
        self.assertTrue(os.path.exists(nodesfile.split(' ')[1]))

    def test_prepare_deps(self):
        """Test preparing for a toolchain when dependencies are involved."""
        tc = self.get_toolchain('GCC', version='6.4.0-2.28')
        deps = [
            {
                'name': 'OpenMPI',
                'version': '2.1.2',
                'full_mod_name': 'OpenMPI/2.1.2-GCC-6.4.0-2.28',
                'short_mod_name': 'OpenMPI/2.1.2-GCC-6.4.0-2.28',
                'external_module': False,
                'build_only': False,
            },
        ]
        tc.prepare(deps=deps)
        mods = ['GCC/6.4.0-2.28', 'hwloc/1.11.8-GCC-6.4.0-2.28', 'OpenMPI/2.1.2-GCC-6.4.0-2.28']
        self.assertTrue([m['mod_name'] for m in self.modtool.list()], mods)

    def test_prepare_deps_external(self):
        """Test preparing for a toolchain when dependencies and external modules are involved."""
        deps = [
            {
                'name': 'OpenMPI',
                'version': '2.1.2',
                'full_mod_name': 'OpenMPI/2.1.2-GCC-6.4.0-2.28',
                'short_mod_name': 'OpenMPI/2.1.2-GCC-6.4.0-2.28',
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
        tc = self.get_toolchain('GCC', version='6.4.0-2.28')
        tc.prepare(deps=deps)
        mods = ['GCC/6.4.0-2.28', 'hwloc/1.11.8-GCC-6.4.0-2.28', 'OpenMPI/2.1.2-GCC-6.4.0-2.28', 'toy/0.0']
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
        tc = self.get_toolchain('GCC', version='6.4.0-2.28')
        os.environ['FOOBAR_PREFIX'] = '/foo/bar'
        tc.prepare(deps=deps)
        mods = ['GCC/6.4.0-2.28', 'hwloc/1.11.8-GCC-6.4.0-2.28', 'OpenMPI/2.1.2-GCC-6.4.0-2.28', 'toy/0.0']
        self.assertTrue([m['mod_name'] for m in self.modtool.list()], mods)
        self.assertEqual(os.environ['EBROOTTOY'], '/foo/bar')
        self.assertEqual(os.environ['EBVERSIONTOY'], '1.2.3')
        self.assertEqual(os.environ['EBROOTFOOBAR'], '/foo/bar')
        self.assertEqual(os.environ['EBVERSIONFOOBAR'], '4.5')

        self.assertEqual(modules.get_software_root('foobar'), '/foo/bar')
        self.assertEqual(modules.get_software_version('toy'), '1.2.3')

    def test_get_software_version(self):
        """Test that get_software_version works"""
        os.environ['EBROOTTOY'] = '/foo/bar'
        os.environ['EBVERSIONTOY'] = '1.2.3'
        os.environ['EBROOTFOOBAR'] = '/foo/bar'
        os.environ['EBVERSIONFOOBAR'] = '4.5'
        tc = self.get_toolchain('GCC', version='6.4.0-2.28')
        self.assertEqual(tc.get_software_version('toy'), ['1.2.3'])
        self.assertEqual(tc.get_software_version(['toy']), ['1.2.3'])
        self.assertEqual(tc.get_software_version(['toy', 'foobar']), ['1.2.3', '4.5'])
        # Non existing modules raise an error
        self.assertErrorRegex(EasyBuildError, 'non-existing was not found',
                              tc.get_software_version, 'non-existing')
        self.assertErrorRegex(EasyBuildError, 'non-existing was not found',
                              tc.get_software_version, ['toy', 'non-existing', 'foobar'])
        # Can use required=False to avoid
        self.assertEqual(tc.get_software_version('non-existing', required=False), [None])
        self.assertEqual(tc.get_software_version(['toy', 'non-existing', 'foobar'], required=False),
                         ['1.2.3', None, '4.5'])

    def test_old_new_iccifort(self):
        """Test whether preparing for old/new Intel compilers works correctly."""
        self.setup_sandbox_for_intel_fftw(self.test_prefix, imklver='2018.1.163')
        self.setup_sandbox_for_intel_fftw(self.test_prefix, imklver='10.2.6.038')
        self.modtool.prepend_module_path(self.test_prefix)

        shlib_ext = get_shared_lib_ext()

        # incl. -lguide
        libblas_mt_intel3 = "-Wl,-Bstatic -Wl,--start-group -lmkl_intel_lp64 -lmkl_intel_thread -lmkl_core"
        libblas_mt_intel3 += " -Wl,--end-group -Wl,-Bdynamic -liomp5 -lguide -lpthread"

        # no -lguide
        blas_static_libs_intel4 = 'libmkl_intel_lp64.a,libmkl_sequential.a,libmkl_core.a'
        blas_shared_libs_intel4 = blas_static_libs_intel4.replace('.a', '.' + shlib_ext)
        libblas_intel4 = "-Wl,-Bstatic -Wl,--start-group -lmkl_intel_lp64 -lmkl_sequential -lmkl_core"
        libblas_intel4 += " -Wl,--end-group -Wl,-Bdynamic"
        libblas_mt_intel4 = "-Wl,-Bstatic -Wl,--start-group -lmkl_intel_lp64 -lmkl_intel_thread -lmkl_core"
        libblas_mt_intel4 += " -Wl,--end-group -Wl,-Bdynamic -liomp5 -lpthread"

        libfft_intel4 = libblas_intel4.replace('-lmkl_intel_lp64', '-lfftw3xc_intel -lmkl_intel_lp64')
        libfft_mt_intel4 = libblas_mt_intel4.replace('-lmkl_intel_lp64', '-lfftw3xc_intel -lmkl_intel_lp64')

        # incl. -lmkl_solver*
        libscalack_intel3 = "-lmkl_scalapack_lp64 -lmkl_solver_lp64_sequential -lmkl_blacs_intelmpi_lp64"
        libscalack_intel3 += " -lmkl_intel_lp64 -lmkl_sequential -lmkl_core"

        # no -lmkl_solver*
        libscalack_intel4 = "-lmkl_scalapack_lp64 -lmkl_blacs_intelmpi_lp64 -lmkl_intel_lp64 -lmkl_sequential "
        libscalack_intel4 += "-lmkl_core"

        blas_static_libs_fosscuda = "libopenblas.a,libgfortran.a"
        blas_shared_libs_fosscuda = blas_static_libs_fosscuda.replace('.a', '.' + shlib_ext)
        blas_mt_static_libs_fosscuda = blas_static_libs_fosscuda + ",libpthread.a"
        blas_mt_shared_libs_fosscuda = blas_mt_static_libs_fosscuda.replace('.a', '.' + shlib_ext)
        libblas_fosscuda = "-lopenblas -lgfortran"
        libblas_mt_fosscuda = libblas_fosscuda + " -lpthread"

        fft_static_libs_fosscuda = "libfftw3.a"
        fft_shared_libs_fosscuda = fft_static_libs_fosscuda.replace('.a', '.' + shlib_ext)
        fft_mt_static_libs_fosscuda = "libfftw3.a,libpthread.a"
        fft_mt_shared_libs_fosscuda = fft_mt_static_libs_fosscuda.replace('.a', '.' + shlib_ext)
        fft_mt_static_libs_fosscuda_omp = "libfftw3_omp.a,libfftw3.a,libpthread.a"
        fft_mt_shared_libs_fosscuda_omp = fft_mt_static_libs_fosscuda_omp.replace('.a', '.' + shlib_ext)
        libfft_fosscuda = "-lfftw3"
        libfft_mt_fosscuda = libfft_fosscuda + " -lpthread"
        libfft_mt_fosscuda_omp = "-lfftw3_omp " + libfft_fosscuda + " -lpthread"

        lapack_static_libs_fosscuda = "libopenblas.a,libgfortran.a"
        lapack_shared_libs_fosscuda = lapack_static_libs_fosscuda.replace('.a', '.' + shlib_ext)
        lapack_mt_static_libs_fosscuda = lapack_static_libs_fosscuda + ",libpthread.a"
        lapack_mt_shared_libs_fosscuda = lapack_mt_static_libs_fosscuda.replace('.a', '.' + shlib_ext)
        liblapack_fosscuda = "-lopenblas -lgfortran"
        liblapack_mt_fosscuda = liblapack_fosscuda + " -lpthread"

        libscalack_fosscuda = "-lscalapack -lopenblas -lgfortran"
        libscalack_mt_fosscuda = libscalack_fosscuda + " -lpthread"
        scalapack_static_libs_fosscuda = "libscalapack.a,libopenblas.a,libgfortran.a"
        scalapack_shared_libs_fosscuda = scalapack_static_libs_fosscuda.replace('.a', '.' + shlib_ext)
        scalapack_mt_static_libs_fosscuda = "libscalapack.a,libopenblas.a,libgfortran.a,libpthread.a"
        scalapack_mt_shared_libs_fosscuda = scalapack_mt_static_libs_fosscuda.replace('.a', '.' + shlib_ext)

        tc = self.get_toolchain('fosscuda', version='2018a')
        tc.prepare()
        self.assertEqual(os.environ['BLAS_SHARED_LIBS'], blas_shared_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_STATIC_LIBS'], blas_static_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_MT_SHARED_LIBS'], blas_mt_shared_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_MT_STATIC_LIBS'], blas_mt_static_libs_fosscuda)
        self.assertEqual(os.environ['LIBBLAS'], libblas_fosscuda)
        self.assertEqual(os.environ['LIBBLAS_MT'], libblas_mt_fosscuda)

        self.assertEqual(os.environ['LAPACK_SHARED_LIBS'], lapack_shared_libs_fosscuda)
        self.assertEqual(os.environ['LAPACK_STATIC_LIBS'], lapack_static_libs_fosscuda)
        self.assertEqual(os.environ['LAPACK_MT_SHARED_LIBS'], lapack_mt_shared_libs_fosscuda)
        self.assertEqual(os.environ['LAPACK_MT_STATIC_LIBS'], lapack_mt_static_libs_fosscuda)
        self.assertEqual(os.environ['LIBLAPACK'], liblapack_fosscuda)
        self.assertEqual(os.environ['LIBLAPACK_MT'], liblapack_mt_fosscuda)

        self.assertEqual(os.environ['BLAS_LAPACK_SHARED_LIBS'], blas_shared_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_LAPACK_STATIC_LIBS'], blas_static_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_LAPACK_MT_SHARED_LIBS'], blas_mt_shared_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_LAPACK_MT_STATIC_LIBS'], blas_mt_static_libs_fosscuda)

        self.assertEqual(os.environ['FFT_SHARED_LIBS'], fft_shared_libs_fosscuda)
        self.assertEqual(os.environ['FFT_STATIC_LIBS'], fft_static_libs_fosscuda)
        self.assertEqual(os.environ['FFT_SHARED_LIBS_MT'], fft_mt_shared_libs_fosscuda)
        self.assertEqual(os.environ['FFT_STATIC_LIBS_MT'], fft_mt_static_libs_fosscuda)
        self.assertEqual(os.environ['FFTW_SHARED_LIBS'], fft_shared_libs_fosscuda)
        self.assertEqual(os.environ['FFTW_STATIC_LIBS'], fft_static_libs_fosscuda)
        self.assertEqual(os.environ['FFTW_SHARED_LIBS_MT'], fft_mt_shared_libs_fosscuda)
        self.assertEqual(os.environ['FFTW_STATIC_LIBS_MT'], fft_mt_static_libs_fosscuda)
        self.assertEqual(os.environ['LIBFFT'], libfft_fosscuda)
        self.assertEqual(os.environ['LIBFFT_MT'], libfft_mt_fosscuda)

        self.assertEqual(os.environ['LIBSCALAPACK'], libscalack_fosscuda)
        self.assertEqual(os.environ['LIBSCALAPACK_MT'], libscalack_mt_fosscuda)
        self.assertEqual(os.environ['SCALAPACK_SHARED_LIBS'], scalapack_shared_libs_fosscuda)
        self.assertEqual(os.environ['SCALAPACK_STATIC_LIBS'], scalapack_static_libs_fosscuda)
        self.assertEqual(os.environ['SCALAPACK_MT_SHARED_LIBS'], scalapack_mt_shared_libs_fosscuda)
        self.assertEqual(os.environ['SCALAPACK_MT_STATIC_LIBS'], scalapack_mt_static_libs_fosscuda)
        self.modtool.purge()

        tc = self.get_toolchain('intel', version='2018a')
        tc.prepare()
        self.assertEqual(os.environ.get('BLAS_SHARED_LIBS', "(not set)"), blas_shared_libs_intel4)
        self.assertEqual(os.environ.get('BLAS_STATIC_LIBS', "(not set)"), blas_static_libs_intel4)
        self.assertEqual(os.environ.get('LAPACK_SHARED_LIBS', "(not set)"), blas_shared_libs_intel4)
        self.assertEqual(os.environ.get('LAPACK_STATIC_LIBS', "(not set)"), blas_static_libs_intel4)
        self.assertEqual(os.environ.get('LIBBLAS', "(not set)"), libblas_intel4)
        self.assertEqual(os.environ.get('LIBBLAS_MT', "(not set)"), libblas_mt_intel4)
        self.assertEqual(os.environ.get('LIBFFT', "(not set)"), libfft_intel4)
        self.assertEqual(os.environ.get('LIBFFT_MT', "(not set)"), libfft_mt_intel4)
        self.assertTrue(libscalack_intel4 in os.environ['LIBSCALAPACK'])
        self.modtool.purge()

        tc = self.get_toolchain('intel', version='2012a')
        tc.prepare()
        self.assertEqual(os.environ.get('LIBBLAS_MT', "(not set)"), libblas_mt_intel3)
        self.assertTrue(libscalack_intel3 in os.environ['LIBSCALAPACK'])
        self.modtool.purge()

        tc = self.get_toolchain('intel', version='2018a')
        tc.prepare()
        self.assertEqual(os.environ.get('LIBBLAS_MT', "(not set)"), libblas_mt_intel4)
        self.assertTrue(libscalack_intel4 in os.environ['LIBSCALAPACK'])
        self.modtool.purge()

        tc = self.get_toolchain('intel', version='2012a')
        tc.prepare()
        self.assertEqual(os.environ.get('LIBBLAS_MT', "(not set)"), libblas_mt_intel3)
        self.assertTrue(libscalack_intel3 in os.environ['LIBSCALAPACK'])
        self.modtool.purge()

        libscalack_intel4 = libscalack_intel4.replace('_lp64', '_ilp64')
        tc = self.get_toolchain('intel', version='2018a')
        opts = {'i8': True}
        tc.set_options(opts)
        tc.prepare()
        self.assertTrue(libscalack_intel4 in os.environ['LIBSCALAPACK'])
        self.modtool.purge()

        tc = self.get_toolchain('fosscuda', version='2018a')
        tc.set_options({'openmp': True})
        tc.prepare()
        self.assertEqual(os.environ['BLAS_SHARED_LIBS'], blas_shared_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_STATIC_LIBS'], blas_static_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_MT_SHARED_LIBS'], blas_mt_shared_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_MT_STATIC_LIBS'], blas_mt_static_libs_fosscuda)
        self.assertEqual(os.environ['LIBBLAS'], libblas_fosscuda)
        self.assertEqual(os.environ['LIBBLAS_MT'], libblas_mt_fosscuda)

        self.assertEqual(os.environ['LAPACK_SHARED_LIBS'], lapack_shared_libs_fosscuda)
        self.assertEqual(os.environ['LAPACK_STATIC_LIBS'], lapack_static_libs_fosscuda)
        self.assertEqual(os.environ['LAPACK_MT_SHARED_LIBS'], lapack_mt_shared_libs_fosscuda)
        self.assertEqual(os.environ['LAPACK_MT_STATIC_LIBS'], lapack_mt_static_libs_fosscuda)
        self.assertEqual(os.environ['LIBLAPACK'], liblapack_fosscuda)
        self.assertEqual(os.environ['LIBLAPACK_MT'], liblapack_mt_fosscuda)

        self.assertEqual(os.environ['BLAS_LAPACK_SHARED_LIBS'], blas_shared_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_LAPACK_STATIC_LIBS'], blas_static_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_LAPACK_MT_SHARED_LIBS'], blas_mt_shared_libs_fosscuda)
        self.assertEqual(os.environ['BLAS_LAPACK_MT_STATIC_LIBS'], blas_mt_static_libs_fosscuda)

        self.assertEqual(os.environ['FFT_SHARED_LIBS'], fft_shared_libs_fosscuda)
        self.assertEqual(os.environ['FFT_STATIC_LIBS'], fft_static_libs_fosscuda)
        self.assertEqual(os.environ['FFT_SHARED_LIBS_MT'], fft_mt_shared_libs_fosscuda_omp)
        self.assertEqual(os.environ['FFT_STATIC_LIBS_MT'], fft_mt_static_libs_fosscuda_omp)
        self.assertEqual(os.environ['FFTW_SHARED_LIBS'], fft_shared_libs_fosscuda)
        self.assertEqual(os.environ['FFTW_STATIC_LIBS'], fft_static_libs_fosscuda)
        self.assertEqual(os.environ['FFTW_SHARED_LIBS_MT'], fft_mt_shared_libs_fosscuda_omp)
        self.assertEqual(os.environ['FFTW_STATIC_LIBS_MT'], fft_mt_static_libs_fosscuda_omp)
        self.assertEqual(os.environ['LIBFFT'], libfft_fosscuda)
        self.assertEqual(os.environ['LIBFFT_MT'], libfft_mt_fosscuda_omp)

        self.assertEqual(os.environ['LIBSCALAPACK'], libscalack_fosscuda)
        self.assertEqual(os.environ['LIBSCALAPACK_MT'], libscalack_mt_fosscuda)
        self.assertEqual(os.environ['SCALAPACK_SHARED_LIBS'], scalapack_shared_libs_fosscuda)
        self.assertEqual(os.environ['SCALAPACK_STATIC_LIBS'], scalapack_static_libs_fosscuda)
        self.assertEqual(os.environ['SCALAPACK_MT_SHARED_LIBS'], scalapack_mt_shared_libs_fosscuda)
        self.assertEqual(os.environ['SCALAPACK_MT_STATIC_LIBS'], scalapack_mt_static_libs_fosscuda)

    def test_standalone_iccifort(self):
        """Test whether standalone installation of iccifort matches the iccifort toolchain definition."""

        tc = self.get_toolchain('iccifort', version='2018.1.163')
        tc.prepare()
        self.assertEqual(tc.toolchain_dep_mods, ['icc/2018.1.163', 'ifort/2018.1.163'])
        self.modtool.purge()

        for key in ['EBROOTICC', 'EBROOTIFORT', 'EBVERSIONICC', 'EBVERSIONIFORT']:
            self.assertTrue(os.getenv(key) is None)

        # install fake iccifort module with no dependencies
        fake_iccifort = os.path.join(self.test_prefix, 'iccifort', '2018.1.163')
        write_file(fake_iccifort, "#%Module")
        self.modtool.use(self.test_prefix)

        # toolchain verification fails because icc/ifort are not dependencies of iccifort modules,
        # and corresponding environment variables are not set
        error_pattern = "List of toolchain dependency modules and toolchain definition do not match"
        self.assertErrorRegex(EasyBuildError, error_pattern, tc.prepare)
        self.modtool.purge()

        # make iccifort module set $EBROOT* and $EBVERSION* to pass toolchain verification
        fake_iccifort_txt = '\n'.join([
            "#%Module",
            'setenv EBROOTICC "%s"' % self.test_prefix,
            'setenv EBROOTIFORT "%s"' % self.test_prefix,
            'setenv EBVERSIONICC "2018.1.163"',
            'setenv EBVERSIONIFORT "2018.1.163"',
        ])
        write_file(fake_iccifort, fake_iccifort_txt)
        # toolchain preparation (which includes verification) works fine now
        tc.prepare()
        # no dependencies found in iccifort module
        self.assertEqual(tc.toolchain_dep_mods, [])

    def test_standalone_iccifortcuda(self):
        """Test whether standalone installation of iccifortcuda matches the iccifortcuda toolchain definition."""

        tc = self.get_toolchain('iccifortcuda', version='2018b')
        tc.prepare()
        self.assertEqual(tc.toolchain_dep_mods, ['icc/2018.1.163', 'ifort/2018.1.163', 'CUDA/9.1.85'])
        self.modtool.purge()

        for key in ['EBROOTICC', 'EBROOTIFORT', 'EBVERSIONICC', 'EBVERSIONIFORT', 'EBROOTCUDA', 'EBVERSIONCUDA']:
            self.assertTrue(os.getenv(key) is None)

        # install fake iccifortcuda module with no dependencies
        fake_iccifortcuda = os.path.join(self.test_prefix, 'iccifortcuda', '2018b')
        write_file(fake_iccifortcuda, "#%Module")
        self.modtool.use(self.test_prefix)

        # toolchain verification fails because icc/ifort are not dependencies of iccifortcuda modules,
        # and corresponding environment variables are not set
        error_pattern = "List of toolchain dependency modules and toolchain definition do not match"
        self.assertErrorRegex(EasyBuildError, error_pattern, tc.prepare)
        self.modtool.purge()

        # Verify that it works loading a module that contains a combined iccifort module
        tc = self.get_toolchain('iccifortcuda', version='2019a')
        # toolchain preparation (which includes verification) works fine now
        tc.prepare()
        # dependencies found in iccifortcuda module
        self.assertEqual(tc.toolchain_dep_mods, ['iccifort/2019.5.281', 'CUDA/9.1.85'])

    def test_independence(self):
        """Test independency of toolchain instances."""

        # tweaking --optarch is required for Cray toolchains (craypre-<optarch> module must be available)
        init_config(build_options={'optarch': 'test', 'silent': True})

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
            ('GCC', '6.4.0-2.28'),
            ('iccifort', '2018.1.163'),
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
        write_file(os.path.join(self.test_prefix, 'PGI', '19.1'), '#%Module\nsetenv EBVERSIONPGI 19.1')
        self.modtool.prepend_module_path(self.test_prefix)

        tc = self.get_toolchain('PGI', version='14.9')
        tc.prepare()

        self.assertEqual(tc.get_variable('CC'), 'pgcc')
        self.assertEqual(tc.get_variable('CXX'), 'pgCC')
        self.assertEqual(tc.get_variable('F77'), 'pgf77')
        self.assertEqual(tc.get_variable('F90'), 'pgf90')
        self.assertEqual(tc.get_variable('FC'), 'pgfortran')
        self.modtool.purge()

        for pgi_ver in ['14.10', '16.3', '19.1']:
            tc = self.get_toolchain('PGI', version=pgi_ver)
            tc.prepare()

            self.assertEqual(tc.get_variable('CC'), 'pgcc')
            self.assertEqual(tc.get_variable('CXX'), 'pgc++')
            if pgi_ver == '19.1':
                self.assertEqual(tc.get_variable('F77'), 'pgfortran')
            else:
                self.assertEqual(tc.get_variable('F77'), 'pgf77')
            self.assertEqual(tc.get_variable('F90'), 'pgf90')
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
            msg = r"ccache binary not found in \$PATH, required by --use-ccache"
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
        ccache_path = os.path.join(self.test_prefix, 'scripts', 'ccache')
        self.assertTrue(os.path.samefile(os.environ['CCACHE_DIR'], ccache_dir))
        for comp in ['gcc', 'g++']:
            comp_path = which(comp)
            self.assertTrue(comp_path)
            self.assertTrue(os.path.samefile(comp_path, ccache_path))

        # no ccache wrapper for gfortran when using ccache
        # (ccache either doesn't support Fortran anymore, or support is spotty (trouble with Fortran modules))
        gfortran_path = which('gfortran')
        self.assertTrue(gfortran_path is None or not os.path.samefile(gfortran_path, ccache_path))

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

        # $LIBRARY_PATH affects result of rpath_args.py, so make sure it's not set
        if 'LIBRARY_PATH' in os.environ:
            del os.environ['LIBRARY_PATH']

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

        # compiler command, -Wl,--enable-new-dtags should be replaced with -Wl,--disable-new-dtags
        out, ec = run_cmd("%s gcc '' '%s' -Wl,--enable-new-dtags foo.c" % (script, rpath_inc), simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
            "'-Wl,--disable-new-dtags'",
            "'foo.c'",
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

        # single -L argument, but non-existing path => not used in RPATH, but -L option is retained
        cmd = "%s gcc '' '%s' foo.c -L%s/foo -lfoo" % (script, rpath_inc, self.test_prefix)
        out, ec = run_cmd(cmd, simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
            "'foo.c'",
            "'-L%s/foo'" % self.test_prefix,
            "'-lfoo'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # single -L argument again, with existing path
        mkdir(os.path.join(self.test_prefix, 'foo'))
        out, ec = run_cmd(cmd, simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
            "'-Wl,-rpath=%s/foo'" % self.test_prefix,
            "'foo.c'",
            "'-L%s/foo'" % self.test_prefix,
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
        cmd = "%s gcc '' '%s' foo.c -L   %s/foo -lfoo" % (script, rpath_inc, self.test_prefix)
        out, ec = run_cmd(cmd, simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
            "'-Wl,-rpath=%s/foo'" % self.test_prefix,
            "'foo.c'",
            "'-L%s/foo'" % self.test_prefix,
            "'-lfoo'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        mkdir(os.path.join(self.test_prefix, 'bar'))
        mkdir(os.path.join(self.test_prefix, 'lib64'))

        # multiple -L arguments, order should be preserved;
        # duplicate paths are only used once for RPATH (but -L flags are always retained)
        cmd = ' '.join([
            script,
            'ld',
            "''",
            "'%s'" % rpath_inc,
            '-L%s/foo' % self.test_prefix,
            'foo.o',
            '-L%s/lib64' % self.test_prefix,
            '-L%s/foo' % self.test_prefix,
            '-lfoo',
            '-lbar',
            '-L/usr/lib',
            '-L%s/bar' % self.test_prefix,
        ])
        out, ec = run_cmd(cmd, simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-rpath=%s/lib'" % self.test_prefix,
            "'-rpath=%s/lib64'" % self.test_prefix,
            "'-rpath=$ORIGIN'",
            "'-rpath=$ORIGIN/../lib'",
            "'-rpath=$ORIGIN/../lib64'",
            "'--disable-new-dtags'",
            "'-rpath=%s/foo'" % self.test_prefix,
            "'-rpath=%s/lib64'" % self.test_prefix,
            "'-rpath=/usr/lib'",
            "'-rpath=%s/bar'" % self.test_prefix,
            "'-L%s/foo'" % self.test_prefix,
            "'foo.o'",
            "'-L%s/lib64'" % self.test_prefix,
            "'-L%s/foo'" % self.test_prefix,
            "'-lfoo'",
            "'-lbar'",
            "'-L/usr/lib'",
            "'-L%s/bar'" % self.test_prefix,
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # test specifying of custom rpath filter
        cmd = ' '.join([
            script,
            'ld',
            '/fo.*,/bar.*',
            "'%s'" % rpath_inc,
            '-L/foo',
            'foo.o',
            '-L%s/lib64' % self.test_prefix,
            '-lfoo',
            '-L/bar',
            '-lbar',
        ])
        out, ec = run_cmd(cmd, simple=False)
        self.assertEqual(ec, 0)
        cmd_args = [
            "'-rpath=%s/lib'" % self.test_prefix,
            "'-rpath=%s/lib64'" % self.test_prefix,
            "'-rpath=$ORIGIN'",
            "'-rpath=$ORIGIN/../lib'",
            "'-rpath=$ORIGIN/../lib64'",
            "'--disable-new-dtags'",
            "'-rpath=%s/lib64'" % self.test_prefix,
            "'-L/foo'",
            "'foo.o'",
            "'-L%s/lib64'" % self.test_prefix,
            "'-lfoo'",
            "'-L/bar'",
            "'-lbar'",
        ]
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # slightly trimmed down real-life example (compilation of XZ)
        for subdir in ['icc/lib/intel64', 'imkl/lib', 'imkl/mkl/lib/intel64', 'gettext/lib']:
            mkdir(os.path.join(self.test_prefix, subdir), parents=True)

        args = ' '.join([
            '-fvisibility=hidden',
            '-Wall',
            '-O2',
            '-xHost',
            '-o .libs/lzmainfo',
            'lzmainfo-lzmainfo.o lzmainfo-tuklib_progname.o lzmainfo-tuklib_exit.o',
            '-L%s/icc/lib/intel64' % self.test_prefix,
            '-L%s/imkl/lib' % self.test_prefix,
            '-L%s/imkl/mkl/lib/intel64' % self.test_prefix,
            '-L%s/gettext/lib' % self.test_prefix,
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
            "'-Wl,-rpath=%s/icc/lib/intel64'" % self.test_prefix,
            "'-Wl,-rpath=%s/imkl/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/imkl/mkl/lib/intel64'" % self.test_prefix,
            "'-Wl,-rpath=%s/gettext/lib'" % self.test_prefix,
            "'-fvisibility=hidden'",
            "'-Wall'",
            "'-O2'",
            "'-xHost'",
            "'-o' '.libs/lzmainfo'",
            "'lzmainfo-lzmainfo.o' 'lzmainfo-tuklib_progname.o' 'lzmainfo-tuklib_exit.o'",
            "'-L%s/icc/lib/intel64'" % self.test_prefix,
            "'-L%s/imkl/lib'" % self.test_prefix,
            "'-L%s/imkl/mkl/lib/intel64'" % self.test_prefix,
            "'-L%s/gettext/lib'" % self.test_prefix,
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
        for extra_args in ["-v", "-V", "--version", "-dumpversion", "-v -L/test/lib"]:
            cmd = "%s g++ '' '%s' %s" % (script, rpath_inc, extra_args)
            out, ec = run_cmd(cmd, simple=False)
            self.assertEqual(ec, 0)
            self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(["'%s'" % x for x in extra_args.split(' ')]))

        # if a compiler command includes "-x c++-header" or "-x c-header" (which imply no linking is done),
        # we should *not* inject -Wl,-rpath options, since those enable linking as a side-effect;
        # see https://github.com/easybuilders/easybuild-framework/issues/3371
        test_cases = [
            "-x c++-header",
            "-x c-header",
            "-L/test/lib -x c++-header",
        ]
        for extra_args in test_cases:
            cmd = "%s g++ '' '%s' foo.c -O2 %s" % (script, rpath_inc, extra_args)
            out, ec = run_cmd(cmd, simple=False)
            self.assertEqual(ec, 0)
            cmd_args = ["'foo.c'", "'-O2'"] + ["'%s'" % x for x in extra_args.split(' ')]
            self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # check whether $LIBRARY_PATH is taken into account
        test_cmd_gcc = "%s gcc '' '%s' -c foo.c" % (script, rpath_inc)
        pre_cmd_args_gcc = [
            "'-Wl,-rpath=%s/lib'" % self.test_prefix,
            "'-Wl,-rpath=%s/lib64'" % self.test_prefix,
            "'-Wl,-rpath=$ORIGIN'",
            "'-Wl,-rpath=$ORIGIN/../lib'",
            "'-Wl,-rpath=$ORIGIN/../lib64'",
            "'-Wl,--disable-new-dtags'",
        ]
        post_cmd_args_gcc = [
            "'-c'",
            "'foo.c'",
        ]

        test_cmd_ld = ' '.join([
            script,
            'ld',
            "''",
            "'%s'" % rpath_inc,
            '-L%s/foo' % self.test_prefix,
            'foo.o',
            '-L%s/lib64' % self.test_prefix,
            '-lfoo',
            '-lbar',
            '-L/usr/lib',
            '-L%s/bar' % self.test_prefix,
        ])
        pre_cmd_args_ld = [
            "'-rpath=%s/lib'" % self.test_prefix,
            "'-rpath=%s/lib64'" % self.test_prefix,
            "'-rpath=$ORIGIN'",
            "'-rpath=$ORIGIN/../lib'",
            "'-rpath=$ORIGIN/../lib64'",
            "'--disable-new-dtags'",
            "'-rpath=%s/foo'" % self.test_prefix,
            "'-rpath=%s/lib64'" % self.test_prefix,
            "'-rpath=/usr/lib'",
            "'-rpath=%s/bar'" % self.test_prefix,
        ]
        post_cmd_args_ld = [
            "'-L%s/foo'" % self.test_prefix,
            "'foo.o'",
            "'-L%s/lib64'" % self.test_prefix,
            "'-lfoo'",
            "'-lbar'",
            "'-L/usr/lib'",
            "'-L%s/bar'" % self.test_prefix,
        ]

        library_paths = [
            ('',),  # special case: empty value
            ('path/to/lib',),
            ('path/to/lib', 'another/path/to/lib64'),
            ('path/to/lib', 'another/path/to/lib64', 'yet-another/path/to/libraries'),
        ]
        for library_path in library_paths:
            library_path = [os.path.join(self.test_prefix, x) for x in library_path]
            for path in library_path:
                mkdir(path, parents=True)

            os.environ['LIBRARY_PATH'] = ':'.join(library_path)

            out, ec = run_cmd(test_cmd_gcc, simple=False)
            self.assertEqual(ec, 0)
            cmd_args = pre_cmd_args_gcc + ["'-Wl,-rpath=%s'" % x for x in library_path if x] + post_cmd_args_gcc
            self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

            out, ec = run_cmd(test_cmd_ld, simple=False)
            self.assertEqual(ec, 0)
            cmd_args = pre_cmd_args_ld + ["'-rpath=%s'" % x for x in library_path if x] + post_cmd_args_ld
            self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        # paths already listed via -L don't get included again as RPATH option
        new_lib64 = os.path.join(self.test_prefix, 'new', 'lib64')
        mkdir(new_lib64, parents=True)

        lib64_subdir = os.path.join(self.test_prefix, 'lib64')
        lib_symlink = os.path.join(self.test_prefix, 'lib')
        symlink(lib64_subdir, lib_symlink)

        library_path = [
            lib64_subdir,
            new_lib64,
            os.path.join(self.test_prefix, 'bar'),
            lib_symlink,
        ]
        os.environ['LIBRARY_PATH'] = ':'.join(library_path)

        out, ec = run_cmd(test_cmd_gcc, simple=False)
        self.assertEqual(ec, 0)
        # no -L options in GCC command, so all $LIBRARY_PATH entries are retained except for last one (lib symlink)
        cmd_args = pre_cmd_args_gcc + ["'-Wl,-rpath=%s'" % x for x in library_path[:-1] if x] + post_cmd_args_gcc
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

        out, ec = run_cmd(test_cmd_ld, simple=False)
        self.assertEqual(ec, 0)
        # only new path from $LIBRARY_PATH is included as -rpath option,
        # since others are already included via corresponding -L flag
        cmd_args = pre_cmd_args_ld + ["'-rpath=%s'" % new_lib64] + post_cmd_args_ld
        self.assertEqual(out.strip(), "CMD_ARGS=(%s)" % ' '.join(cmd_args))

    def test_toolchain_prepare_rpath(self):
        """Test toolchain.prepare under --rpath"""

        # put fake 'g++' command in place that just echos its arguments
        fake_gxx = os.path.join(self.test_prefix, 'fake', 'g++')
        write_file(fake_gxx, '#!/bin/bash\necho "$@"')
        adjust_permissions(fake_gxx, stat.S_IXUSR)
        os.environ['PATH'] = '%s:%s' % (os.path.join(self.test_prefix, 'fake'), os.getenv('PATH', ''))

        # enable --rpath and prepare toolchain
        init_config(build_options={'rpath': True, 'rpath_filter': ['/ba.*'], 'silent': True})
        tc = self.get_toolchain('gompi', version='2018a')

        # preparing RPATH wrappers requires --experimental, need to bypass that here
        tc.log.experimental = lambda x: x

        # 'rpath' toolchain option gives control to disable use of RPATH wrappers
        tc.set_options({})
        self.assertTrue(tc.options['rpath'])  # enabled by default

        # setting 'rpath' toolchain option to false implies no RPATH wrappers being used
        tc.set_options({'rpath': False})
        tc.prepare()
        res = which('g++', retain_all=True)
        self.assertTrue(len(res) >= 1)
        self.assertFalse(tc.is_rpath_wrapper(res[0]))
        self.assertFalse(any(tc.is_rpath_wrapper(x) for x in res[1:]))
        self.assertTrue(os.path.samefile(res[0], fake_gxx))

        # enable 'rpath' toolchain option again (equivalent to the default setting)
        tc.set_options({'rpath': True})
        tc.prepare()

        # check that wrapper is indeed in place
        res = which('g++', retain_all=True)
        # there should be at least 2 hits: the RPATH wrapper, and our fake 'g++' command (there may be real ones too)
        self.assertTrue(len(res) >= 2)
        self.assertTrue(tc.is_rpath_wrapper(res[0]))
        self.assertEqual(os.path.basename(res[0]), 'g++')
        self.assertEqual(os.path.basename(os.path.dirname(res[0])), 'gxx_wrapper')
        self.assertFalse(any(tc.is_rpath_wrapper(x) for x in res[1:]))
        self.assertTrue(os.path.samefile(res[1], fake_gxx))
        # any other available 'g++' commands should not be a wrapper or our fake g++
        self.assertFalse(any(os.path.samefile(x, fake_gxx) for x in res[2:]))

        # RPATH wrapper should be robust against Python environment variables & site-packages magic,
        # so we set up a weird environment here to verify that
        # (see https://github.com/easybuilders/easybuild-framework/issues/3421)

        # redefine $HOME so we can put up a fake $HOME/.local/lib/python*/site-packages,
        # which is picked up automatically (even without setting $PYTHONPATH)
        home = os.path.join(self.test_prefix, 'home')
        os.environ['HOME'] = home

        # also set $PYTHONUSERBASE (default is $HOME/.local when this is not set)
        # see https://docs.python.org/3/library/site.html#site.USER_BASE
        os.environ['PYTHONUSERBASE'] = home

        # add directory to $PYTHONPATH where we can inject broken Python modules
        pythonpath = os.getenv('PYTHONPATH')
        if pythonpath:
            os.environ['PYTHONPATH'] = self.test_prefix + ':' + pythonpath
        else:
            os.environ['PYTHONPATH'] = self.test_prefix

        site_pkgs_dir = os.path.join(home, '.local', 'lib', 'python%s.%s' % sys.version_info[:2], 'site-packages')
        mkdir(site_pkgs_dir, parents=True)

        # add site.py that imports imp (which on Python 3 triggers an 'import enum')
        # when running with Python 3 (since then 'import imp' triggers 'import enum')
        write_file(os.path.join(site_pkgs_dir, 'site.py'), 'import imp')

        # also include an empty enum.py both in $PYTHONUSERBASE and a path listed in $PYTHONPATH;
        # combined with the site.py above, this combination is sufficient
        # to reproduce https://github.com/easybuilders/easybuild-framework/issues/3421
        write_file(os.path.join(site_pkgs_dir, 'enum.py'), 'import os')
        write_file(os.path.join(self.test_prefix, 'enum.py'), 'import os')

        # also add a broken re.py, which is sufficient to cause trouble in Python 2,
        # unless $PYTHONPATH is ignored by the RPATH wrapper
        write_file(os.path.join(self.test_prefix, 're.py'), 'import this_is_a_broken_re_module')

        # check whether fake g++ was wrapped and that arguments are what they should be
        # no -rpath for /bar because of rpath filter
        mkdir(os.path.join(self.test_prefix, 'foo'), parents=True)
        cmd = ' '.join([
            'g++',
            '${USER}.c',
            '-L%s/foo' % self.test_prefix,
            '-L/bar',
            "'$FOO'",
            '-DX="\\"\\""',
        ])
        out, ec = run_cmd(cmd)
        self.assertEqual(ec, 0)
        expected = ' '.join([
            '-Wl,--disable-new-dtags',
            '-Wl,-rpath=%s/foo' % self.test_prefix,
            '%(user)s.c',
            '-L%s/foo' % self.test_prefix,
            '-L/bar',
            '$FOO',
            '-DX=""',
        ])
        self.assertEqual(out.strip(), expected % {'user': os.getenv('USER')})

        # check whether 'stubs' library directory are correctly filtered out
        paths = [
            'prefix/software/CUDA/1.2.3/lib/stubs/',  # should be filtered (no -rpath)
            'tmp/foo/',
            'prefix/software/stubs/1.2.3/lib',  # should NOT be filtered
            'prefix/software/CUDA/1.2.3/lib/stubs',  # should be filtered (no -rpath)
            'prefix/software/CUDA/1.2.3/lib64/stubs/',  # should be filtered (no -rpath)
            'prefix/software/foobar/4.5/notreallystubs',  # should NOT be filtered
            'prefix/software/CUDA/1.2.3/lib64/stubs',  # should be filtered (no -rpath)
            'prefix/software/zlib/1.2.11/lib',
            'prefix/software/bleh/0/lib/stubs',  # should be filtered (no -rpath)
            'prefix/software/foobar/4.5/stubsbutnotreally',  # should NOT be filtered
        ]
        paths = [os.path.join(self.test_prefix, x) for x in paths]
        for path in paths:
            mkdir(path, parents=True)
        args = ['-L%s' % x for x in paths]

        cmd = "g++ ${USER}.c %s" % ' '.join(args)
        out, ec = run_cmd(cmd, simple=False)
        self.assertEqual(ec, 0)

        expected = ' '.join([
            '-Wl,--disable-new-dtags',
            '-Wl,-rpath=%s/tmp/foo/' % self.test_prefix,
            '-Wl,-rpath=%s/prefix/software/stubs/1.2.3/lib' % self.test_prefix,
            '-Wl,-rpath=%s/prefix/software/foobar/4.5/notreallystubs' % self.test_prefix,
            '-Wl,-rpath=%s/prefix/software/zlib/1.2.11/lib' % self.test_prefix,
            '-Wl,-rpath=%s/prefix/software/foobar/4.5/stubsbutnotreally' % self.test_prefix,
            '%(user)s.c',
            '-L%s/prefix/software/CUDA/1.2.3/lib/stubs/' % self.test_prefix,
            '-L%s/tmp/foo/' % self.test_prefix,
            '-L%s/prefix/software/stubs/1.2.3/lib' % self.test_prefix,
            '-L%s/prefix/software/CUDA/1.2.3/lib/stubs' % self.test_prefix,
            '-L%s/prefix/software/CUDA/1.2.3/lib64/stubs/' % self.test_prefix,
            '-L%s/prefix/software/foobar/4.5/notreallystubs' % self.test_prefix,
            '-L%s/prefix/software/CUDA/1.2.3/lib64/stubs' % self.test_prefix,
            '-L%s/prefix/software/zlib/1.2.11/lib' % self.test_prefix,
            '-L%s/prefix/software/bleh/0/lib/stubs' % self.test_prefix,
            '-L%s/prefix/software/foobar/4.5/stubsbutnotreally' % self.test_prefix,
        ])
        self.assertEqual(out.strip(), expected % {'user': os.getenv('USER')})

        # calling prepare() again should *not* result in wrapping the existing RPATH wrappers
        # this can happen when building extensions
        tc.prepare()
        res = which('g++', retain_all=True)
        self.assertTrue(len(res) >= 2)
        self.assertTrue(tc.is_rpath_wrapper(res[0]))
        self.assertFalse(any(tc.is_rpath_wrapper(x) for x in res[1:]))
        self.assertTrue(os.path.samefile(res[1], fake_gxx))
        self.assertFalse(any(os.path.samefile(x, fake_gxx) for x in res[2:]))

    def test_prepare_openmpi_tmpdir(self):
        """Test handling of long $TMPDIR path for OpenMPI 2.x"""

        # this test relies on warnings being printed
        init_config(build_options={'silent': False})

        def prep():
            """Helper function: create & prepare toolchain"""
            self.modtool.unload(['gompi', 'OpenMPI', 'hwloc', 'GCC'])
            tc = self.get_toolchain('gompi', version='2018a')
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
        # basename of tmpdir will be 6 chars in Python 2, 8 chars in Python 3
        regex = re.compile(r"^WARNING: Long \$TMPDIR .* problems with OpenMPI 2.x, using shorter path: /tmp/.{6,8}$")
        self.assertTrue(regex.match(stderr), "Pattern '%s' found in: %s" % (regex.pattern, stderr))

        # new $TMPDIR should be /tmp/xxxxxx
        tmpdir = os.environ.get('TMPDIR')
        self.assertTrue(tmpdir.startswith('/tmp'))
        self.assertTrue(len(tmpdir) in (11, 13))

        # also test cleanup method to ensure short $TMPDIR is cleaned up properly
        self.assertTrue(os.path.exists(tmpdir))
        tc.cleanup()
        self.assertFalse(os.path.exists(tmpdir))

        os.environ['TMPDIR'] = orig_tmpdir

        # copy OpenMPI module used in gompi/2018a to fiddle with it, i.e. to fake bump OpenMPI version used in it
        tmp_modules = os.path.join(self.test_prefix, 'modules')
        mkdir(tmp_modules)

        test_dir = os.path.abspath(os.path.dirname(__file__))
        copy_dir(os.path.join(test_dir, 'modules', 'OpenMPI'), os.path.join(tmp_modules, 'OpenMPI'))

        openmpi_module = os.path.join(tmp_modules, 'OpenMPI', '2.1.2-GCC-6.4.0-2.28')
        ompi_mod_txt = read_file(openmpi_module)
        write_file(openmpi_module, ompi_mod_txt.replace('2.1.2', '1.6.4'))

        self.modtool.use(tmp_modules)

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

        # we may have created our own short tmpdir above, so make sure to clean things up...
        shutil.rmtree(orig_tmpdir)

    def test_env_vars_external_module(self):
        """Test env_vars_external_module function."""

        res = env_vars_external_module('test', '1.2.3', {'prefix': '/software/test/1.2.3'})
        expected = {'EBVERSIONTEST': '1.2.3', 'EBROOTTEST': '/software/test/1.2.3'}
        self.assertEqual(res, expected)

        res = env_vars_external_module('test-test', '1.2.3', {})
        expected = {'EBVERSIONTESTMINTEST': '1.2.3'}
        self.assertEqual(res, expected)

        res = env_vars_external_module('test', None, {'prefix': '/software/test/1.2.3'})
        expected = {'EBROOTTEST': '/software/test/1.2.3'}
        self.assertEqual(res, expected)

        res = env_vars_external_module('test', None, {})
        expected = {}
        self.assertEqual(res, expected)


def suite():
    """ return all the tests"""
    return TestLoaderFiltered().loadTestsFromTestCase(ToolchainTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
