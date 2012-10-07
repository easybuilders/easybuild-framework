##
# Copyright 2012 Stijn De Weirdt
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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

from easybuild.tools.variables import Variables, ListOfLists, StrList, AbsPathList, FlagList, LibraryList
from easybuild.tools.variables import LinkLibraryPaths, IncludePaths, CommandFlagList, join_map_class


COMPILER_VARIABLES = [
                      ('CC', 'C compiler'),
                      ('CXX', 'C++ compiler'),
                      ('F77', 'Fortran 77 compiler'),
                      ('F90', 'Fortran 90 compiler'),
                      ]

COMPILER_MAP_CLASS = {
                      FlagList: [
                                 ('OPTFLAGS', 'Optimisation flags'),
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

MPI_MAP_CLASS = {
                 AbsPathList: [
                               ('MPI_LIB_STATIC', 'MPI libraries (static)'), ## TODO: useful at all? shouldn't these be obtained from mpiXX --show
                               ('MPI_LIB_SHARED', 'MPI libraries (shared)'),
                               ('MPI_LIB_DIR', 'MPI library directory'),
                               ('MPI_INC_DIR', 'MPI include directory'),
                               ],
                 CommandFlagList: MPI_COMPILER_VARIABLES,
                 }

SCALAPACK_MAP_CLASS = {StrList:[],
                       }

class ToolchainList(ListOfLists):
    DEFAULT_CLASS = FlagList
    MAP_CLASS = join_map_class(COMPILER_MAP_CLASS, MPI_MAP_CLASS) ## join_map_class strips explanation

class ToolchainVariables(Variables):
    """
    Class to hold variable-like key/value pairs
    in context of compilers (i.e. the generated string are e.g. compiler options or link flags)
    """
    DEFAULT_LISTCLASS = ToolchainList
