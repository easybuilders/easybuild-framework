##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
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
EasyBuild support for building and installing netCDF-Fortran, implemented as an easyblock
"""

import os

import easybuild.tools.environment as env
import easybuild.tools.toolkit as toolchain
from easybuild.easyblocks.generic.configuremake import ConfigureMake


class EB_netCDF_minus_Fortran(ConfigureMake):
    """Support for building/installing the netCDF-Fortran library"""

    def configure_step(self):
        """Configure build: set config options and configure"""

        if self.toolchain.opts['pic']:
            self.cfg.update('configopts', "--with-pic")

        self.cfg.update('configopts', 'FCFLAGS="%s" FC="%s"' % (os.getenv('FFLAGS'), os.getenv('F90')))

        # add -DgFortran to CPPFLAGS when building with GCC
        if self.toolchain.comp_family() == toolchain.GCC:
            env.setvar('CPPFLAGS', "%s -DgFortran" % os.getenv('CPPFLAGS'))

        super(EB_netCDF_minus_Fortran, self).configure_step()

    def sanity_check_step(self):
        """
        Custom sanity check for netCDF-Fortran
        """

        custom_paths = {
                        'files': ["bin/nf-config"] + ["lib/%s" % x for x in ["libnetcdff.so", "libnetcdff.a"]] +
                                 ["include/%s" % x for x in ["netcdf.inc", "netcdf.mod", "typesizes.mod"]],
                        'dirs': []
                       }

        super(EB_netCDF_minus_Fortran, self).sanity_check_step(custom_paths=custom_paths)
