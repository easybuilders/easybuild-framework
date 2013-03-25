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
Generic EasyBuild support for building and installing bar, implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""

from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig import CUSTOM, MANDATORY


class bar(EasyBlock):
    """Generic support for building/installing bar."""

    @staticmethod
    def extra_options():
        """Custom easyconfig parameters for bar."""

        extra_vars = [
                      ('bar_extra1', [None, "first bar-specific easyconfig parameter (mandatory)", MANDATORY]),
                      ('bar_extra2', ['BAR', "second bar-specific easyconfig parameter", CUSTOM]),
                     ]
        return EasyBlock.extra_options(extra_vars)
