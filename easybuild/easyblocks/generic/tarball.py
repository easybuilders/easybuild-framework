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
EasyBuild support for installing (precompiled) software which is supplied as a tarball,
implemented as an easyblock
"""

import shutil

from easybuild.framework.easyblock import EasyBlock


class Tarball(EasyBlock):
    """
    Precompiled software supplied as a tarball:
    - will unpack binary and copy it to the install dir
    """

    def configure_step(self):
        """
        Dummy configure method
        """
        pass

    def build_step(self):
        """
        Dummy build method: nothing to build
        """
        pass

    def install_step(self):

        src = self.cfg['start_dir']
        # shutil.copytree cannot handle destination dirs that exist already.
        # On the other hand, Python2.4 cannot create entire paths during copytree.
        # Therefore, only the final directory is deleted.
        shutil.rmtree(self.installdir)
        try:
            # self.cfg['keepsymlinks'] is False by default except when explicitly put to True in .eb file
            shutil.copytree(src,self.installdir, symlinks=self.cfg['keepsymlinks'])
        except:
            self.log.exception("Copying %s to installation dir %s failed" % (src,self.installdir))
