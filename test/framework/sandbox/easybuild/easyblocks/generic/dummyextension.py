##
# Copyright 2009-2025 Ghent University
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
EasyBuild support for building and installing dummy extensions, implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""

from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.extensioneasyblock import ExtensionEasyBlock


class DummyExtension(ExtensionEasyBlock):
    """Support for building/installing dummy extensions."""

    @staticmethod
    def extra_options():
        """Custom easyconfig parameters for dummy extensions."""
        extra_vars = {
            'unpack_source': [None, "Unpack sources", CUSTOM],
        }
        return ExtensionEasyBlock.extra_options(extra_vars=extra_vars)

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # use lowercase name as default value for expected module name, and replace '-' with '_'
        if 'modulename' not in self.options:
            self.options['modulename'] = self.name.lower().replace('-', '_')

    def install_extension(self, unpack_src=False):
        """Install the dummy extension."""
        ec_unpack_source = self.cfg.get('unpack_source')
        if ec_unpack_source is not None:
            unpack_src = ec_unpack_source
        super().install_extension(unpack_src)
