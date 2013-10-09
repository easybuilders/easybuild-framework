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
This describes the easyconfig format versions 2.X

This is a mix between version 1 and configparser-style configuration

@author: Stijn De Weirdt (Ghent University)
"""

from easybuild.framework.easyconfig.format.pyheaderconfigobj import EasyConfigFormatConfigObj
from easybuild.framework.easyconfig.format.version import EasyVersion

class FormatTwoZero(EasyConfigFormatConfigObj):
    """Support for easyconfig format 2.x
    Simple extension of FormatOneZero with configparser blocks

    Doesn't set version and toolchain/toolchain version like in FormatOneZero
        - if no 'version' in pyheader, then referencing it directly in pyheader doesn't work
            - either use templates ('%(version)s'), or include version spec

    NOT in 2.0
        - order preservation: need more recent ConfigParser (more recent Python as minimal version)
        - nested sections (need other ConfigParser/ConfigObj, eg INITools)
        - type validation
        - command line generation (--try-X command line options)
    """
    VERSION = EasyVersion('2.0')
    USABLE = True
    PYHEADER_ALLOWED_BUILTINS = ['len']

    def check_docstring(self):
        """Verify docstring"""
        # TODO check for @author and/or @maintainer
        pass

    def get_config_dict(self, version=None, toolchain_name=None, toolchain_version=None):
        """Return the best matching easyconfig dict"""
        # the toolchain name and/or version should not be specified in the pyheader, but other toolchain options are allowed
        pass
