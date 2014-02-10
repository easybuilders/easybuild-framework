# #
# Copyright 2013-2014 Ghent University
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
@author: Kenneth Hoste (Ghent University)
"""

import os
import re
import tempfile
from vsc import fancylogger

from easybuild.framework.easyconfig.format.pyheaderconfigobj import EasyConfigFormatConfigObj
from easybuild.framework.easyconfig.format.version import EasyVersion


_log = fancylogger.getLogger('easyconfig.format.one', fname=False)


class FormatOneZero(EasyConfigFormatConfigObj):
    """Support for easyconfig format 1.x"""
    VERSION = EasyVersion('1.0')
    USABLE = True  # TODO: disable it at some point, too insecure

    PYHEADER_ALLOWED_BUILTINS = None  # allow all
    PYHEADER_MANDATORY = ['version', 'name', 'toolchain', 'homepage', 'description']
    PYHEADER_BLACKLIST = []

    def validate(self):
        """Format validation"""
        # minimal checks
        self._validate_pyheader()

    def get_config_dict(self):
        """
        Return parsed easyconfig as a dictionary, based on specified arguments.
        This is easyconfig format 1.x, so there is only one easyconfig instance available.
        """
        spec_version = self.specs.get('version', None)
        spec_tc = self.specs.get('toolchain', {})
        spec_tc_name = spec_tc.get('name', None)
        spec_tc_version = spec_tc.get('version', None)
        cfg = self.pyheader_localvars
        if spec_version is not None and not spec_version == cfg['version']:
            self.log.error('Requested version %s not available, only %s' % (spec_version, cfg['version']))

        tc_name = cfg['toolchain']['name']
        tc_version = cfg['toolchain']['version']
        if spec_tc_name is not None and not spec_tc_name == tc_name:
            self.log.error('Requested toolchain name %s not available, only %s' % (spec_tc_name, tc_name))
        if spec_tc_version is not None and not spec_tc_version == tc_version:
            self.log.error('Requested toolchain version %s not available, only %s' % (spec_tc_version, tc_version))

        return cfg

    def parse(self, txt):
        """
        Pre-process txt to extract header, docstring and pyheader, with non-indented section markers enforced.
        """
        super(FormatOneZero, self).parse(txt, strict_section_markers=True)
