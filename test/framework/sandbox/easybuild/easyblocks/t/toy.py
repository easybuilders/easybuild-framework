##
# Copyright 2009-2016 Ghent University
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
EasyBuild support for building and installing toy, implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""

import os
import platform
import shutil

from easybuild.framework.easyblock import EasyBlock
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import mkdir
from easybuild.tools.modules import get_software_root, get_software_version
from easybuild.tools.run import run_cmd


class EB_toy(EasyBlock):
    """Support for building/installing toy."""

    def prepare_for_extensions(self):
        """
        Prepare for installing toy extensions.
        """
        # insert new packages by building them with RPackage
        self.cfg['exts_defaultclass'] = "Toy_Extension"
        self.cfg['exts_filter'] = ("%(ext_name)s", "")

    def configure_step(self, name=None):
        """Configure build of toy."""
        if name is None:
            name = self.name
        # make sure Python system dep is handled correctly when specified
        if self.cfg['allow_system_deps']:
            if get_software_root('Python') != 'Python' or get_software_version('Python') != platform.python_version():
                raise EasyBuildError("Sanity check on allowed Python system dep failed.")

        if os.path.exists("%s.source" % name):
            os.rename('%s.source' % name, '%s.c' % name)

    def build_step(self, name=None):
        """Build toy."""
        if name is None:
            name = self.name
        run_cmd('%(prebuildopts)s gcc %(name)s.c -o %(name)s' % {
            'name': name,
            'prebuildopts': self.cfg['prebuildopts'],
        })

    def install_step(self, name=None):
        """Install toy."""
        if name is None:
            name = self.name
        bindir = os.path.join(self.installdir, 'bin')
        mkdir(bindir, parents=True)
        if os.path.exists(name):
            shutil.copy2(name, bindir)
        # also install a dummy libtoy.a, to make the default sanity check happy
        libdir = os.path.join(self.installdir, 'lib')
        mkdir(libdir, parents=True)
        f = open(os.path.join(libdir, 'lib%s.a' % name), 'w')
        f.write(name.upper())
        f.close()
