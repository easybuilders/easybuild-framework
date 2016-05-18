# #
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
# #
"""
Toolchain specific variables

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

from easybuild.tools.variables import AbsPathList
from easybuild.tools.toolchain.variables import LinkLibraryPaths, IncludePaths, CommandFlagList, CommaStaticLibs
from easybuild.tools.toolchain.variables import FlagList, LibraryList


COMPILER_VARIABLES = [
    ('CC', 'C compiler'),
    ('CXX', 'C++ compiler'),
    ('F77', 'Fortran 77 compiler'),
    ('F90', 'Fortran 90 compiler'),
    ('FC', 'Fortran compiler'),
]

COMPILER_FLAGS = [
    ('CFLAGS', 'C compiler flags'),
    ('CXXFLAGS', 'C++ compiler flags'),
    ('FCFLAGS', 'Fortran 77/90 compiler flags'),
    ('FFLAGS', 'Fortran 77 compiler flags'),
    ('F90FLAGS', 'Fortran 90 compiler flags'),
]

COMPILER_MAP_CLASS = {
    FlagList: [
        ('OPTFLAGS', 'Optimization flags'),
        ('PRECFLAGS', 'FP precision flags'),
    ] + COMPILER_FLAGS,
    LibraryList: [
        ('LIBS', 'Libraries'),  # TODO: where are these used? ld?
        ('FLIBS', 'Fortran libraries'),  # TODO: where are these used? gfortran only?
    ],
    LinkLibraryPaths: [
        ('LDFLAGS', 'Flags passed to linker'),  # TODO: overridden by command line?
    ],
    IncludePaths: [
        ('CPPFLAGS', 'Precompiler flags'),
    ],
    CommandFlagList: COMPILER_VARIABLES,
}

CO_COMPILER_MAP_CLASS = {
    CommandFlagList: [
        ('CUDA_CC', 'CUDA C compiler command'),
        ('CUDA_CXX', 'CUDA C++ compiler command'),
        ('CUDA_F77', 'CUDA Fortran 77 compiler command'),
        ('CUDA_F90', 'CUDA Fortran 90 compiler command'),
        ('CUDA_FC', 'CUDA Fortran 77/90 compiler command'),
    ],
    FlagList: [
        ('CUDA_CFLAGS', 'CUDA C compiler flags'),
        ('CUDA_CXXFLAGS', 'CUDA C++ compiler flags'),
        ('CUDA_FCFLAGS', 'CUDA Fortran 77/90 compiler flags'),
        ('CUDA_FFLAGS', 'CUDA Fortran 77 compiler flags'),
        ('CUDA_F90FLAGS', 'CUDA Fortran 90 compiler flags'),
    ],
}

MPI_COMPILER_TEMPLATE = "MPI%(c_var)s"
MPI_COMPILER_VARIABLES = [(MPI_COMPILER_TEMPLATE % {'c_var': v}, "MPI %s wrapper" % d)
                          for (v, d) in COMPILER_VARIABLES]

SEQ_COMPILER_TEMPLATE = "%(c_var)s_SEQ"
SEQ_COMPILER_VARIABLES = [(SEQ_COMPILER_TEMPLATE % {'c_var': v}, "sequential %s" % d)
                          for (v, d) in COMPILER_VARIABLES]

MPI_MAP_CLASS = {
    AbsPathList: [
        # TODO: useful at all? shouldn't these be obtained from mpiXX --show
        ('MPI_LIB_STATIC', 'MPI libraries (static)'),
        ('MPI_LIB_SHARED', 'MPI libraries (shared)'),
        ('MPI_LIB_DIR', 'MPI library directory'),
        ('MPI_INC_DIR', 'MPI include directory'),
    ],
    CommandFlagList: MPI_COMPILER_VARIABLES + SEQ_COMPILER_VARIABLES,
}

BLAS_MAP_CLASS = {
    AbsPathList: [
        ('BLAS_LIB_DIR', 'BLAS library directory'),
        ('BLAS_INC_DIR', 'BLAS include directory'),

    ],
    LibraryList: [
        ('LIBBLAS', 'BLAS libraries'),
        ('LIBBLAS_MT', 'multithreaded BLAS libraries'),
    ],
    CommaStaticLibs: [
        ('BLAS_STATIC_LIBS', 'Comma-separated list of static BLAS libraries'),
        ('BLAS_MT_STATIC_LIBS', 'Comma-separated list of static multithreaded BLAS libraries'),
    ],
}
LAPACK_MAP_CLASS = {
    AbsPathList: [
        ('LAPACK_LIB_DIR', 'LAPACK library directory'),
        ('LAPACK_INC_DIR', 'LAPACK include directory'),
        ('BLAS_LAPACK_LIB_DIR', 'BLAS and LAPACK library directory'),
        ('BLAS_LAPACK_INC_DIR', 'BLAS and LAPACK include directory'),
    ],
    LibraryList: [
        ('LIBLAPACK_ONLY', 'LAPACK libraries (LAPACK only)'),
        ('LIBLAPACK_MT_ONLY', 'multithreaded LAPACK libraries (LAPACK only)'),
        ('LIBLAPACK', 'LAPACK libraries'),
        ('LIBLAPACK_MT', 'multithreaded LAPACK libraries'),
    ],
    CommaStaticLibs: [
        ('LAPACK_STATIC_LIBS', 'Comma-separated list of static LAPACK libraries'),
        ('LAPACK_MT_STATIC_LIBS', 'Comma-separated list of static LAPACK libraries'),
        ('BLAS_LAPACK_STATIC_LIBS', 'Comma-separated list of static BLAS and LAPACK libraries'),
        ('BLAS_LAPACK_MT_STATIC_LIBS', 'Comma-separated list of static BLAS and LAPACK libraries'),
    ],
}
BLACS_MAP_CLASS = {
    AbsPathList: [
        ('BLACS_LIB_DIR', 'BLACS library directory'),
        ('BLACS_INC_DIR', 'BLACS include directory'),

    ],
    LibraryList: [
        ('LIBBLACS', 'BLACS libraries'),
        ('LIBBLACS_MT', 'multithreaded BLACS libraries'),
    ],
    CommaStaticLibs: [
        ('BLACS_STATIC_LIBS', 'Comma-separated list of static BLACS libraries'),
        ('BLACS_MT_STATIC_LIBS', 'Comma-separated list of static multithreaded BLACS libraries'),
    ],
}

SCALAPACK_MAP_CLASS = {
    AbsPathList: [
        ('SCALAPACK_LIB_DIR', 'SCALAPACK library directory'),
        ('SCALAPACK_INC_DIR', 'SCALAPACK include directory'),
    ],
    LibraryList: [
        ('LIBSCALAPACK_ONLY', 'SCALAPACK libraries (SCALAPACK only)'),
        ('LIBSCALAPACK_MT_ONLY', 'multithreaded SCALAPACK libraries (SCALAPACK only)'),
        ('LIBSCALAPACK', 'SCALAPACK libraries'),
        ('LIBSCALAPACK_MT', 'multithreaded SCALAPACK libraries'),
    ],
    CommaStaticLibs: [
        ('SCALAPACK_STATIC_LIBS', 'Comma-separated list of static SCALAPACK libraries'),
        ('SCALAPACK_MT_STATIC_LIBS', 'Comma-separated list of static SCALAPACK libraries'),
    ],
}

FFT_MAP_CLASS = {
    AbsPathList: [
        ('FFT_LIB_DIR', 'FFT library directory'),
        ('FFT_INC_DIR', 'FFT include directory'),
    ],
    LibraryList: [
        ('LIBFFT', 'FFT libraries'),
    ],
    CommaStaticLibs: [
        ('FFT_STATIC_LIBS', 'Comma-separated list of static FFT libraries'),
    ],
}

FFTW_MAP_CLASS = {
    AbsPathList: [
        ('FFTW_LIB_DIR', 'FFTW library directory'),
        ('FFTW_INC_DIR', 'FFTW include directory'),
    ],
    CommaStaticLibs: [
        ('FFTW_STATIC_LIBS', 'Comma-separated list of static FFTW libraries'),
    ],
}

ALL_MAP_CLASSES = [
    COMPILER_MAP_CLASS, MPI_MAP_CLASS,
    BLAS_MAP_CLASS, LAPACK_MAP_CLASS, BLACS_MAP_CLASS, SCALAPACK_MAP_CLASS,
    FFT_MAP_CLASS, FFTW_MAP_CLASS, CO_COMPILER_MAP_CLASS,
]


