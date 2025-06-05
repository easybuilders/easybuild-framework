##
# Copyright 2013-2025 Ghent University
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
EasyBuild support for foss compiler toolchain (includes GCC, OpenMPI, OpenBLAS, LAPACK, ScaLAPACK and FFTW).

Authors:

* Kenneth Hoste (Ghent University)
* Davide Grassano (CECAM EPFL)
"""
from easybuild.toolchains.lompi import Lompi
from easybuild.toolchains.lfbf import Lfbf
from easybuild.toolchains.lolf import Lolf
from easybuild.toolchains.fft.fftw import Fftw
from easybuild.toolchains.linalg.flexiblas import FlexiBLAS
from easybuild.toolchains.linalg.scalapack import ScaLAPACK
from easybuild.tools import LooseVersion


class LFoss(Lompi, FlexiBLAS, ScaLAPACK, Fftw):
    """Compiler toolchain with GCC, OpenMPI, FlexiBLAS, ScaLAPACK and FFTW."""
    NAME = 'lfoss'
    SUBTOOLCHAIN = [
        Lompi.NAME,
        Lolf.NAME,
        Lfbf.NAME
    ]

    def __init__(self, *args, **kwargs):
        """Toolchain constructor."""
        super(LFoss, self).__init__(*args, **kwargs)

        # need to transform a version like '2018b' with something that is safe to compare with '2019'
        # comparing subversions that include letters causes TypeErrors in Python 3
        # 'a' is assumed to be equivalent with '.01' (January), and 'b' with '.07' (June) (good enough for this purpose)
        version = self.version.replace('a', '.01').replace('b', '.07')

        self.looseversion = LooseVersion(version)

        constants = ('BLAS_MODULE_NAME', 'BLAS_LIB', 'BLAS_LIB_MT', 'BLAS_FAMILY',
                     'LAPACK_MODULE_NAME', 'LAPACK_IS_BLAS', 'LAPACK_FAMILY')

        for constant in constants:
            setattr(self, constant, getattr(FlexiBLAS, constant))

    def banned_linked_shared_libs(self):
        """
        List of shared libraries (names, file names, paths) which are
        not allowed to be linked in any installed binary/library.
        """
        res = []
        res.extend(Lompi.banned_linked_shared_libs(self))
        res.extend(FlexiBLAS.banned_linked_shared_libs(self))
        res.extend(ScaLAPACK.banned_linked_shared_libs(self))
        res.extend(Fftw.banned_linked_shared_libs(self))

        return res

    def is_deprecated(self):
        """Return whether or not this toolchain is deprecated."""

        # lfoss toolchains older than 2023b should not exist (need GCC >= 13)
        if self.looseversion < LooseVersion('2023'):
            deprecated = True
        else:
            deprecated = False

        return deprecated
