# #
# Copyright 2013-2013 Ghent University
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
# #
"""
This describes the easyconfig format version 1.X

This is the original pure python code, to be exec'ed rather then parsed

@author: Stijn De Weirdt (Ghent University)
"""

from easybuild.framework.easyconfig.format.pyheaderconfigobj import EasyConfigFormatConfigObj
from easybuild.framework.easyconfig.format.version import EasyVersion


class FormatOneZero(EasyConfigFormatConfigObj):
    """Simple extension of FormatOne with configparser blocks
        Deprecates setting version and toolchain/toolchain version in FormatOne
    """
    VERSION = EasyVersion('1.0')
    PYHEADER_ALLOWED_BUILTINS = None  # allow all

    USABLE = True  # TODO: disable it, too insecure

    def get_config_dict(self, version=None, toolchain_name=None, toolchain_version=None):
        """There should only be one."""
        cfg = self.pyheader_localvars
        if not 'version' in cfg:
            # TODO replace with proper exception, fix unittest
            self.log.error('mandatory variable version not provided')
        if version is not None and not version == cfg['version']:
            self.log.error('Requested version not available (req %s avail %s)' % (version, cfg['version']))
        if not 'toolchain' in cfg:
            self.log.error('mandatory variable toolchain not provided')

        tc_name = cfg['toolchain']['name']
        tc_version = cfg['toolchain']['version']
        if toolchain_name is not None and not toolchain_name == tc_name:
            self.log.error('Requested toolchain_name not available (req %s avail %s)' %
                           (toolchain_name, tc_name))
        if toolchain_version is not None and not toolchain_version == tc_version:
            self.log.error('Requested toolchain_version not available (req %s avail %s)' %
                           (toolchain_version, tc_version))

        return cfg
