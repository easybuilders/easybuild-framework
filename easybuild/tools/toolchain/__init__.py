##
# Copyright 2012 Stijn De Weirdt
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
Toolchain terminology
---------------------

Toolchain: group of development related utilities (eg compiler) and libraries (eg MPI, linear algebra)
    -> eg tc=Toolchain()


Toolchain options : options passed to the toolchain through the easyconfig file
    -> eg tc.options

Options : all options passed to an executable
    Flags: specific subset of options, typically involved with compilation
        -> eg tc.variables.CFLAGS
    LinkOptions: specific subset of options, typically involved with linking
        -> eg tc.variables.LIBBLAS

TooclchainVariables: list of environment variables that are set when the toolchain is initialised
           and the toolchain options have been parsed.
    -> eg tc.variables['X'] will be available as os.environ['X']


This module initializes the tools toolchain submodule of EasyBuild,
which contains toolchain related modules.

Easy access to actual Toolchain classes
    search

Based on VSC-tools vsc.mympirun.mpi.mpi and vsc.mympirun.rm.sched
"""

from easybuild.tools.toolchain.compiler import IntelIccIfort, GNUCompilerCollection, Dummy
from easybuild.tools.toolchain.fft import FFTW, IntelFFTW
from easybuild.tools.toolchain.mpi import OpenMPI, IntelMPI, MVAPICH2, MPICH2, QLogicMPI
from easybuild.tools.toolchain.scalapack import IntelMKL, ScaATLAS
from easybuild.tools.toolchain.toolchain import Toolchain

def get_subclasses(klass):
    """
    Get all subclasses recursively
    """
    res = []
    for cl in klass.__subclasses__():
        res.extend(get_subclasses(cl))
        res.append(cl)
    return res

def search_toolchain(name):
    """Find a toolchain with matching name
        returns toolchain (or None), found_toolchains
    """
    found_tcs = get_subclasses(Toolchain)

    for tc in found_tcs:
        if tc._is_toolchain_for(name):
            return tc, found_tcs

    return None, found_tcs

class ICTCE(IntelIccIfort, IntelMPI, IntelMKL, IntelFFTW):
    NAME = 'ictce'

class GOALF(GNUCompilerCollection, OpenMPI, ScaATLAS, FFTW):
    NAME = 'goalf'
