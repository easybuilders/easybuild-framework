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

from distutils.version import LooseVersion

from easybuild.framework.easyconfig.format.format import EasyConfigFormatConfigObj


class FormatTwoZero(EasyConfigFormatConfigObj):
    """Simple extension of FormatOne with configparser blocks
    Deprecates setting version and toolchain/toolchain version in FormatOne
        - if no version in pyheader, then no references to it directly!
            - either templates or insert it !

    NOT in 2.0
        - order preservation: need more recent ConfigParser
        - nested sections (need other ConfigParser, eg INITools)
        - type validation
        - commandline generation
    """
    VERSION = LooseVersion('2.0')

    def check_docstring(self):
        """Verify docstring"""
        # TODO check for @author and/or @maintainer

    def pyheader_env(self):
        # TODO further restrict env
        """
        Restrict environment with modified builtin / builtins

        As a side effect, an implementation may insert additional keys into the dictionaries given besides
        those corresponding to variable names set by the executed code. For example,
        the current implementation may add a reference to the dictionary of
        the built-in module __builtin__ under the key __builtins__ (!).
        """
        global_vars, local_vars = super(FormatTwoZero, self).pyheader_env()
        return global_vars, local_vars
