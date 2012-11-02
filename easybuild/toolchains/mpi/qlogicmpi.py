##
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
Support for QLogicMPI as toolchain MPI library.
"""

from easybuild.tools.toolchain.mpi import Mpi


TC_CONSTANT_QLOGICMPI = "QLogicMPI"


class QLogicMPI(Mpi):
    """QLogicMPI MPI class"""
    MPI_MODULE_NAME = ["QLogicMPI"]
    MPI_FAMILY = TC_CONSTANT_QLOGICMPI

    MPI_LIBRARY_NAME = 'mpich'

    ## qlogic: cxx -> -CC only
    ## qlogic has seperate -m32 / -m64 option to mpicc/.. --> only one
    MPI_UNIQUE_OPTION_MAP = {
                             '_opt_MPICXX':'CC="%(CXX_base)s"',
                             }

