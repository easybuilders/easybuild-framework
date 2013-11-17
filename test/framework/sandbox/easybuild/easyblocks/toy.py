##
# Copyright 2009-2013 Ghent University
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
EasyBuild support for building and installing toy, implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""

import os
import shutil

from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig import CUSTOM, MANDATORY
from easybuild.tools.filetools import run_cmd

class EB_toy(EasyBlock):
    """Support for building/installing toy."""

    def configure_step(self):
        """Configure build of toy."""
        os.rename('toy.source', 'toy.c')

    def build_step(self):
        """Build toy."""
        run_cmd('gcc toy.c -o toy')

    def install_step(self):
        """Install toy."""
        bindir = os.path.join(self.installdir, 'bin')
        os.mkdir(bindir)
        shutil.copy2('toy', bindir)
        # also install a dummy libtoy.a, to make the default sanity check happy
        libdir = os.path.join(self.installdir, 'lib')
        os.mkdir(libdir)
        f = open(os.path.join(libdir, 'libtoy.a'), 'w')
        f.write('TOY')
        f.close()
