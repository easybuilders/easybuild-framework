##
# Copyright 2013-2018 Ghent University
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
Support for CUDA compilers as toolchain (co-)compiler.

:author: Kenneth Hoste (Ghent University)
"""

from distutils.version import LooseVersion

import easybuild.tools.systemtools as systemtools
from easybuild.tools.toolchain.compiler import Compiler
from easybuild.tools.toolchain.variables import FlagList


TC_CONSTANT_CUDA = "CUDA"


class Cuda(Compiler):
    """CUDA compiler class."""

    COMPILER_CUDA_MODULE_NAME = ['CUDA']
    COMPILER_CUDA_FAMILY = TC_CONSTANT_CUDA

    COMPILER_CUDA_UNIQUE_OPTS = {
        # handle '-gencode arch=X,code=Y' nvcc options (also -arch, -code) 
        # -arch always needs to be specified, -code is optional (defaults to -arch if missing)
        # -gencode is syntactic sugar for combining -arch/-code
        # multiple values can be specified
        # examples:
        # * target v1.3 features, generate both object code and PTX for v1.3: -gencode arch=compute_13,code=compute_13 -gencode arch=compute_13,code=sm_13
        # * target v3.5 features, only generate object code for v3.5: -gencode arch=compute_35,code=sm_35
        # * target v2.0 features, generate object code for v2.0 and v3.5: -gencode arch=compute_20,code=sm_20 -gencode arch=compute_20,code=sm_35
        'cuda_gencode': ([], ("List of arguments for nvcc -gencode command line option, e.g., "
                              "['arch=compute_20,code=sm_20', 'arch=compute_35,code=compute_35']")),
    }

    # always C++ compiler command, even for C!
    COMPILER_CUDA_UNIQUE_OPTION_MAP = {
        '_opt_CUDA_CC': 'ccbin="%(CXX_base)s"',
        '_opt_CUDA_CXX': 'ccbin="%(CXX_base)s"',
    }

    COMPILER_CUDA_CC = 'nvcc'
    COMPILER_CUDA_CXX = 'nvcc'
    LIB_CUDA_RUNTIME = ['rt', 'cudart']

    def __init__(self, *args, **kwargs):
        """Constructor, with settings custom to CUDA."""
        super(Cuda, self).__init__(*args, **kwargs)
        # append CUDA prefix to list of compiler prefixes
        self.prefixes.append(TC_CONSTANT_CUDA)

    def _set_compiler_vars(self):
        """Set the compiler variables"""
        # append lib dir paths to LDFLAGS (only if the paths are actually there)
        root = self.get_software_root('CUDA')[0]
        self.variables.append_subdirs("LDFLAGS", root, subdirs=["lib64", "lib"])
        super(Cuda, self)._set_compiler_vars()

    def _set_compiler_flags(self):
        """Collect flags to set, and add them as variables."""

        super(Cuda, self)._set_compiler_flags()

        # always C++ compiler flags, even for C!
        # note: using $LIBS will yield the use of -lcudart in Xlinker, which is silly, but fine
        
        cuda_flags = [
            'Xcompiler="%s"' % str(self.variables['CXXFLAGS']),
            'Xlinker="%s %s"' % (str(self.variables['LDFLAGS']), str(self.variables['LIBS'])),
        ]
        self.variables.nextend('CUDA_CFLAGS', cuda_flags)
        self.variables.nextend('CUDA_CXXFLAGS', cuda_flags)

        # add gencode compiler flags to list of flags for compiler variables
        for gencode_val in self.options.get('cuda_gencode', []):
            gencode_option = 'gencode %s' % gencode_val
            self.variables.nappend('CUDA_CFLAGS', gencode_option)
            self.variables.nappend('CUDA_CXXFLAGS', gencode_option)
