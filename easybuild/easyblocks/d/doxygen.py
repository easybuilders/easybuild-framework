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
EasyBuild support for building and installing Doxygen, implemented as an easyblock
"""

from easybuild.easyblocks.generic.configuremake import ConfigureMake
from easybuild.tools.filetools import run_cmd


class EB_Doxygen(ConfigureMake):
    """Support for building/installing Doxygen"""

    def configure_step(self):
        """Configure build using non-standard configure script (see prefix option)"""

        cmd = "%s ./configure --prefix %s %s" % (self.cfg['preconfigopts'], self.installdir,
                                                   self.cfg['configopts'])
        run_cmd(cmd, log_all=True, simple=True)

    def sanity_check_step(self):
        """
        Custom sanity check for Doxygen
        """

        custom_paths = {
                        'files': ["bin/doxygen"],
                        'dirs': []
                       }

        super(EB_Doxygen, self).sanity_check_step(custom_paths=custom_paths)
