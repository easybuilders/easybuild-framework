##
# Copyright 2009-2023 Ghent University
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
EasyBuild support for building and installing foo, implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""

from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig import CUSTOM, MANDATORY


class EB_foo(EasyBlock):
    """Support for building/installing foo."""

    @staticmethod
    def extra_options(more_extra_vars=None):
        """Custom easyconfig parameters for foo."""
        if more_extra_vars is None:
            more_extra_vars = {}
        extra_vars = {
            'foo_extra1': [None, "first foo-specific easyconfig parameter (mandatory)", MANDATORY],
            'foo_extra2': ['FOO', "second foo-specific easyconfig parameter", CUSTOM],
        }
        extra_vars.update(more_extra_vars)
        return EasyBlock.extra_options(extra_vars)
