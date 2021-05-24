##
# Copyright 2021-2021 Ghent University
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
EasyBuild support for building and installing libtoy, implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""
import os

from easybuild.framework.easyblock import EasyBlock
from easybuild.tools.run import run_cmd
from easybuild.tools.systemtools import get_shared_lib_ext

SHLIB_EXT = get_shared_lib_ext()


class EB_libtoy(EasyBlock):
    """Support for building/installing libtoy."""

    def banned_linked_shared_libs(self):
        default = '/thiswillnotbethere,libtoytoytoy.%s,toytoytoy' % SHLIB_EXT
        return os.getenv('EB_LIBTOY_BANNED_SHARED_LIBS', default).split(',')

    def required_linked_shared_libs(self):
        default = '/lib,.*'
        return os.getenv('EB_LIBTOY_REQUIRED_SHARED_LIBS', default).split(',')

    def configure_step(self, name=None):
        """No configuration for libtoy."""
        pass

    def build_step(self, name=None, buildopts=None):
        """Build libtoy."""
        run_cmd('make')

    def install_step(self, name=None):
        """Install libtoy."""
        run_cmd('make install PREFIX="%s"' % self.installdir)
