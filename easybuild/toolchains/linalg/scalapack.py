##
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
##
"""
Support for ScaLAPACK as toolchain linear algebra library.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

from distutils.version import LooseVersion

from easybuild.toolchains.linalg.blacs import Blacs


class ScaLAPACK(Blacs):
    """Trivial class, provides ScaLAPACK support (on top of BLACS)."""
    SCALAPACK_MODULE_NAME = ['ScaLAPACK']
    SCALAPACK_LIB = ['scalapack']

    def is_required(self, name):
        """Determine whether BLACS is a required toolchain element, based on ScaLAPACK version."""
        if name == "BLACS":
            # BLACS is no longer required for ScaLAPACK >= 2.0
            return LooseVersion(self.get_software_version(self.SCALAPACK_MODULE_NAME)[0]) < LooseVersion("2.0")
        else:
            return super(ScaLAPACK, self).is_required(name)
