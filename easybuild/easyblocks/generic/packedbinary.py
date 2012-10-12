##
# Copyright 2012 Jens Timmerman
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild. If not, see <http://www.gnu.org/licenses/>.
##
"""
EasyBlock for binary applications that need unpacking,
e.g., binary applications shipped as a .tar.gz file
"""
import os

from easybuild.framework.easyblock import EasyBlock
from easybuild.easyblocks.generic.binary import Binary


class PackedBinary(Binary, EasyBlock):
    """Support for installing packed binary software.
    Just unpack the sources in the install dir
    """

    def extract_step(self):
        """Unpack the source"""
        EasyBlock.extract_step(self)

    def make_install(self):
        """Copy all unpacked source directories to install directory, one-by-one."""
        try:
            os.chdir(self.builddir)
            for src in os.listdir(self.builddir):
                srcpath = os.path.join(self.builddir, src)
                if os.path.isdir(srcpath):
                    # copy files to install dir via Binary
                    self.cfg['start_dir'] = src
                    Binary.make_install(self)
        except OSError, err:
            self.log.error("Failed to copy unpacked sources to install directory: %s" % err)

