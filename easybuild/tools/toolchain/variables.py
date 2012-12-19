##
# Copyright 2012 Ghent University
# Copyright 2012 Stijn De Weirdt
# Copyright 2012 Kenneth Hoste
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
Toolchain specific variables
"""

from easybuild.tools.variables import Variables, CommaStaticLibs, AbsPathList, LinkerFlagList, FlagList, LibraryList
from easybuild.tools.variables import LinkLibraryPaths, IncludePaths, CommandFlagList, join_map_class


COMPILER_VARIABLES = [
                      ('CC', 'C compiler'),
                      ('CXX', 'C++ compiler'),
                      ('F77', 'Fortran 77 compiler'),
                      ('F90', 'Fortran 90 compiler'),
                      ]

COMPILER_MAP_CLASS = {
                      FlagList: [
                                 ('OPTFLAGS', 'Optimization flags'),
                                 ('PRECFLAGS', 'FP precision flags'),
                                 ('CFLAGS', 'C compiler flags'),
                                 ('CXXFLAGS', 'C++ compiler flags'),
                                 ('FFLAGS', 'Fortran compiler flags'),
                                 ('F90FLAGS', 'Fortran 90 compiler flags'),
                                ],
                      LibraryList: [
                                    ('LIBS', 'Libraries'), ## TODO: where are these used? ld?
                                    ('FLIBS', 'Fortran libraries'), ## TODO: where are these used? gfortran only?
                                   ],
                      LinkLibraryPaths: [
                                         ('LDFLAGS', 'Flags passed to linker'), ## TODO: overridden by command line?
                                        ],
                      IncludePaths: [
                                     ('CPPFLAGS', 'Precompiler flags'),
                                    ],
                      CommandFlagList: COMPILER_VARIABLES,
                      }

MPI_COMPILER_TEMPLATE = "MPI%(c_var)s"
MPI_COMPILER_VARIABLES = [(MPI_COMPILER_TEMPLATE % {'c_var': v}, "MPI %s wrapper" % d)
                          for (v, d) in COMPILER_VARIABLES]

SEQ_COMPILER_TEMPLATE = "%(c_var)s_SEQ"
SEQ_COMPILER_VARIABLES = [(SEQ_COMPILER_TEMPLATE % {'c_var': v}, "sequential %s" % d)
                          for (v, d) in COMPILER_VARIABLES]

MPI_MAP_CLASS = {
                 AbsPathList: [
                               ('MPI_LIB_STATIC', 'MPI libraries (static)'), ## TODO: useful at all? shouldn't these be obtained from mpiXX --show
                               ('MPI_LIB_SHARED', 'MPI libraries (shared)'),
                               ('MPI_LIB_DIR', 'MPI library directory'),
                               ('MPI_INC_DIR', 'MPI include directory'),
                               ],
                 CommandFlagList: MPI_COMPILER_VARIABLES + SEQ_COMPILER_VARIABLES,
                 }

BLAS_MAP_CLASS = {
                  AbsPathList:[
                               ('BLAS_LIB_DIR', 'BLAS library directory'),
                               ('BLAS_INC_DIR', 'BLAS include directory'),

                               ],
                  LibraryList:[
                               ('LIBBLAS', 'BLAS libraries'),
                               ('LIBBLAS_MT', 'multithreaded BLAS libraries'),
                               ],
                  CommaStaticLibs:[
                                   ('BLAS_STATIC_LIBS', 'Comma-separated list of static BLAS libraries'),
                                   ('BLAS_MT_STATIC_LIBS', 'Comma-separated list of static multithreaded BLAS libraries'),
                                   ],
                  }
LAPACK_MAP_CLASS = {
                    AbsPathList:[
                                 ('LAPACK_LIB_DIR', 'LAPACK library directory'),
                                 ('LAPACK_INC_DIR', 'LAPACK include directory'),
                                 ('BLAS_LAPACK_LIB_DIR', 'BLAS and LAPACK library directory'),
                                 ('BLAS_LAPACK_INC_DIR', 'BLAS and LAPACK include directory'),
                                 ],
                    LibraryList:[
                                 ('LIBLAPACK_ONLY', 'LAPACK libraries (LAPACK only)'),
                                 ('LIBLAPACK_MT_ONLY', 'multithreaded LAPACK libraries (LAPACK only)'),
                                 ('LIBLAPACK', 'LAPACK libraries'),
                                 ('LIBLAPACK_MT', 'multithreaded LAPACK libraries'),
                                 ],
                    CommaStaticLibs:[
                                     ('LAPACK_STATIC_LIBS', 'Comma-separated list of static LAPACK libraries'),
                                     ('LAPACK_MT_STATIC_LIBS', 'Comma-separated list of static LAPACK libraries'),
                                     ('BLAS_LAPACK_STATIC_LIBS', 'Comma-separated list of static BLAS and LAPACK libraries'),
                                     ('BLAS_LAPACK_MT_STATIC_LIBS', 'Comma-separated list of static BLAS and LAPACK libraries'),
                                     ],
                    }
BLACS_MAP_CLASS = {
                  AbsPathList:[
                               ('BLACS_LIB_DIR', 'BLACS library directory'),
                               ('BLACS_INC_DIR', 'BLACS include directory'),

                               ],
                  LibraryList:[
                               ('LIBBLACS', 'BLACS libraries'),
                               ('LIBBLACS_MT', 'multithreaded BLACS libraries'),
                               ],
                  CommaStaticLibs:[
                                   ('BLACS_STATIC_LIBS', 'Comma-separated list of static BLACS libraries'),
                                   ('BLACS_MT_STATIC_LIBS', 'Comma-separated list of static multithreaded BLACS libraries'),
                                   ],
                  }

SCALAPACK_MAP_CLASS = {
                    AbsPathList:[
                                 ('SCALAPACK_LIB_DIR', 'SCALAPACK library directory'),
                                 ('SCALAPACK_INC_DIR', 'SCALAPACK include directory'),
                                 ],
                    LibraryList:[
                                 ('LIBSCALAPACK_ONLY', 'SCALAPACK libraries (SCALAPACK only)'),
                                 ('LIBSCALAPACK_MT_ONLY', 'multithreaded SCALAPACK libraries (SCALAPACK only)'),
                                 ('LIBSCALAPACK', 'SCALAPACK libraries'),
                                 ('LIBSCALAPACK_MT', 'multithreaded SCALAPACK libraries'),
                                 ],
                       CommaStaticLibs:[
                                        ('SCALAPACK_STATIC_LIBS', 'Comma-separated list of static SCALAPACK libraries'),
                                        ('SCALAPACK_MT_STATIC_LIBS', 'Comma-separated list of static SCALAPACK libraries'),
                                        ],
                       }

FFT_MAP_CLASS = {
                  AbsPathList:[
                               ('FFT_LIB_DIR', 'FFT library directory'),
                               ('FFT_INC_DIR', 'FFT include directory'),
                               ],
                  LibraryList:[
                               ('LIBFFT', 'FFT libraries'),
                               ],
                  CommaStaticLibs:[
                                   ('FFT_STATIC_LIBS', 'Comma-separated list of static FFT libraries'),
                                   ],
                 }

FFTW_MAP_CLASS = {
                  AbsPathList:[
                               ('FFTW_LIB_DIR', 'FFTW library directory'),
                               ('FFTW_INC_DIR', 'FFTW include directory'),
                               ],
                  CommaStaticLibs:[
                                   ('FFTW_STATIC_LIBS', 'Comma-separated list of static FFTW libraries'),
                                   ],
                  }

ALL_MAP_CLASSES = [
                   COMPILER_MAP_CLASS, MPI_MAP_CLASS,
                   BLAS_MAP_CLASS, LAPACK_MAP_CLASS, BLACS_MAP_CLASS, SCALAPACK_MAP_CLASS,
                   FFT_MAP_CLASS, FFTW_MAP_CLASS,
                   ]


class ToolchainVariables(Variables):
    """
    Class to hold variable-like key/value pairs
    in context of compilers (i.e. the generated string are e.g. compiler options or link flags)
    """
    MAP_CLASS = join_map_class(ALL_MAP_CLASSES) ## join_map_class strips explanation
    DEFAULT_CLASS = FlagList
    LINKER_TOGGLE_START_STOP_GROUP = None
    LINKER_TOGGLE_STATIC_DYNAMIC = None

    def add_begin_end_linkerflags(self, lib, toggle_startstopgroup=False, toggle_staticdynamic=False):
        """
        For given lib
            if toggle_startstopgroup: toggle begin/end group
            if toggle_staticdynamic: toggle static/dynamic
        """
        class LFL(LinkerFlagList):
            LINKER_TOGGLE_START_STOP_GROUP = self.LINKER_TOGGLE_START_STOP_GROUP
            LINKER_TOGGLE_STATIC_DYNAMIC = self.LINKER_TOGGLE_STATIC_DYNAMIC

        def make_lfl(begin=True):
            """make linkerflaglist for begin/end of library"""
            lfl = LFL()
            if toggle_startstopgroup:
                if begin:
                    lfl.toggle_startgroup()
                else:
                    lfl.toggle_stopgroup()
            if toggle_staticdynamic:
                if begin:
                    lfl.toggle_static()
                else:
                    lfl.toggle_dynamic()
            return lfl

        lib.BEGIN = make_lfl(True)
        lib.BEGIN.IS_BEGIN = True
        lib.END = make_lfl(False)
        lib.END.IS_END = True

