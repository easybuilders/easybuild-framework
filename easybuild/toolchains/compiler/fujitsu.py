##
# Copyright 2014-2021 Ghent University
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
Support for the Fujitsu compiler drivers (aka fcc, frt).

The basic concept is the same as for the Cray Programming Environment.

:author: Miguel Dias Costa (National University of Singapore)
"""
import os
import re

import easybuild.tools.environment as env
import easybuild.tools.systemtools as systemtools
from easybuild.tools.toolchain.compiler import Compiler, DEFAULT_OPT_LEVEL

TC_CONSTANT_FUJITSU = 'Fujitsu'
TC_CONSTANT_MODULE_NAME = 'lang'
TC_CONSTANT_MODULE_VAR = 'FJSVXTCLANGA'


class FujitsuCompiler(Compiler):
    """Generic support for using Fujitsu compiler drivers."""
    TOOLCHAIN_FAMILY = TC_CONSTANT_FUJITSU

    COMPILER_MODULE_NAME = [TC_CONSTANT_MODULE_NAME]
    COMPILER_FAMILY = TC_CONSTANT_FUJITSU

    COMPILER_CC = 'fcc'
    COMPILER_CXX = 'FCC'

    COMPILER_F77 = 'frt'
    COMPILER_F90 = 'frt'
    COMPILER_FC = 'frt'

    COMPILER_UNIQUE_OPTION_MAP = {
        DEFAULT_OPT_LEVEL: 'O2',
        'lowopt': 'O1',
        'noopt': 'O0',
        'opt': 'Kfast',  # -O3 -Keval,fast_matmul,fp_contract,fp_relaxed,fz,ilfunc,mfunc,omitfp,simd_packed_promotion
        'optarch': '',  # Fujitsu compiler by default generates code for the arch it is running on
        'openmp': 'Kopenmp',
        'unroll': 'funroll-loops',
        # apparently the -Kfp_precision flag doesn't work in clang mode, will need to look into these later
        # also at strict vs precise and loose vs veryloose
        'strict': ['Knoeval,nofast_matmul,nofp_contract,nofp_relaxed,noilfunc'],  # ['Kfp_precision'],
        'precise': ['Knoeval,nofast_matmul,nofp_contract,nofp_relaxed,noilfunc'],  # ['Kfp_precision'],
        'defaultprec': [],
        'loose': ['Kfp_relaxed'],
        'veryloose': ['Kfp_relaxed'],
        # apparently the -K[NO]SVE flags don't work in clang mode
        # SVE is enabled by default, -Knosimd seems to disable it
        'vectorize': {False: 'Knosimd', True: ''},
    }

    # used when 'optarch' toolchain option is enabled (and --optarch is not specified)
    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        # -march=archi[+features]. At least on Fugaku, these are set by default (-march=armv8.3-a+sve and -mcpu=a64fx)
        (systemtools.AARCH64, systemtools.ARM): '',
    }

    # used with --optarch=GENERIC
    COMPILER_GENERIC_OPTION = {
        (systemtools.AARCH64, systemtools.ARM): '-mcpu=generic -mtune=generic',
    }

    def prepare(self, *args, **kwargs):
        super(FujitsuCompiler, self).prepare(*args, **kwargs)

        # fcc doesn't accept e.g. -std=c++11 or -std=gnu++11, only -std=c11 or -std=gnu11
        pattern = r'-std=(gnu|c)\+\+(\d+)'
        if re.search(pattern, self.vars['CFLAGS']):
            self.log.debug("Found '-std=(gnu|c)++' in CFLAGS, fcc doesn't accept '++' here, removing it")
            self.vars['CFLAGS'] = re.sub(pattern, r'-std=\1\2', self.vars['CFLAGS'])
            self._setenv_variables()

        # make sure the fujitsu module libraries are found (and added to rpath by wrapper)
        library_path = os.getenv('LIBRARY_PATH', '')
        libdir = os.path.join(os.getenv(TC_CONSTANT_MODULE_VAR), 'lib64')
        if libdir not in library_path:
            self.log.debug("Adding %s to $LIBRARY_PATH" % libdir)
            env.setvar('LIBRARY_PATH', os.pathsep.join([library_path, libdir]))

    def _set_compiler_vars(self):
        super(FujitsuCompiler, self)._set_compiler_vars()

        # enable clang compatibility mode
        self.variables.nappend('CFLAGS', ['Nclang'])
        self.variables.nappend('CXXFLAGS', ['Nclang'])

        # also add fujitsu module library path to LDFLAGS
        libdir = os.path.join(os.getenv(TC_CONSTANT_MODULE_VAR), 'lib64')
        self.log.debug("Adding %s to $LDFLAGS" % libdir)
        self.variables.nappend('LDFLAGS', [libdir])
