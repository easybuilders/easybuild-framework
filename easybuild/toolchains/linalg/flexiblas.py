##
# Copyright 2021-2021 Ghent University
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
Support for FlexiBLAS as toolchain linear algebra library.

:author: Kenneth Hoste (Ghent University)
"""
import re

from easybuild.tools.toolchain.linalg import LinAlg

from easybuild.tools.run import run_cmd
from easybuild.tools.systemtools import get_shared_lib_ext


TC_CONSTANT_FLEXIBLAS = 'FlexiBLAS'


def det_flexiblas_backend_libs():
    """Determine list of paths to FlexiBLAS backend libraries."""

    # example output for 'flexiblas list':
    # System-wide (config directory):
    #  OPENBLAS
    #    library = libflexiblas_openblas.so
    out, _ = run_cmd("flexiblas list", simple=False, trace=False)

    shlib_ext = get_shared_lib_ext()
    flexiblas_lib_regex = re.compile(r'library = (?P<lib>lib.*\.%s)' % shlib_ext, re.M)
    flexiblas_libs = flexiblas_lib_regex.findall(out)

    backend_libs = []
    for flexiblas_lib in flexiblas_libs:
        # assumption here is that the name of FlexiBLAS library (like 'libflexiblas_openblas.so')
        # maps directly to name of the backend library ('libopenblas.so')
        backend_lib = 'lib' + flexiblas_lib.replace('libflexiblas_', '')
        backend_libs.append(backend_lib)

    return backend_libs


class FlexiBLAS(LinAlg):
    """
    Trivial class, provides FlexiBLAS support.
    """
    BLAS_MODULE_NAME = ['FlexiBLAS']
    BLAS_LIB = ['flexiblas']
    BLAS_FAMILY = TC_CONSTANT_FLEXIBLAS

    LAPACK_MODULE_NAME = ['FlexiBLAS']
    LAPACK_IS_BLAS = True
    LAPACK_FAMILY = TC_CONSTANT_FLEXIBLAS

    def banned_linked_shared_libs(self):
        """
        List of shared libraries (names, file names, paths) which are
        not allowed to be linked in any installed binary/library.
        """
        banned_libs = super(FlexiBLAS, self).banned_linked_shared_libs()

        # register backends are banned shared libraries,
        # to avoid that anything links to them directly (rather than to libflexiblas.so)
        flexiblas_banned_libs = det_flexiblas_backend_libs()

        return banned_libs + flexiblas_banned_libs
