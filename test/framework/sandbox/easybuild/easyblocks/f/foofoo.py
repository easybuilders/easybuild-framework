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
EasyBuild support for building and installing foofoo, implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""

from easybuild.easyblocks.foo import EB_foo
from easybuild.framework.easyconfig import CUSTOM, MANDATORY


class dummy1:
    """Only to verify that unrelated classes in software specific easyblocks are ignored"""


class dummy2(dummy1):
    """Same but with inheritance"""


class EB_foofoo(EB_foo):
    """Support for building/installing foofoo."""

    @staticmethod
    def extra_options():
        """Custom easyconfig parameters for foofoo."""
        extra_vars = {
            'foofoo_extra1': [None, "first foofoo-specific easyconfig parameter (mandatory)", MANDATORY],
            'foofoo_extra2': ['FOOFOO', "second foofoo-specific easyconfig parameter", CUSTOM],
        }
        return EB_foo.extra_options(extra_vars)
