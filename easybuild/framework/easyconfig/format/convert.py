# #
# Copyright 2014-2021 Ghent University
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
# #

"""
This module implements easyconfig specific formats and their conversions.

:author: Stijn De Weirdt (Ghent University)
"""
from easybuild.framework.easyconfig.format.version import VersionOperator, ToolchainVersionOperator
from easybuild.tools.convert import Convert


class Dependency(Convert):
    """Handle dependency"""
    SEPARATOR_DEP = ';'
    __wraps__ = dict

    def __init__(self, obj, name=None):
        """Convert pass object to a dependency, use specified name if provided."""
        super(Dependency, self).__init__(obj)
        if name is not None:
            self['name'] = name

    def _from_string(self, txt):
        """Convert from string
            versop_str;tc_versop_str -> {'versop': versop, 'tc_versop': tc_versop}
        """
        res = {}

        items = self._split_string(txt, sep=self.SEPARATOR_DEP)
        if len(items) < 1 or len(items) > 2:
            msg = 'Dependency has at least one element (a version operator string), '
            msg += 'and at most 2 (2nd element the toolchain version operator string). '
            msg += 'Separator %s.' % self.SEPARATOR_DEP
            raise ValueError(msg)

        res['versop'] = VersionOperator(items[0])

        if len(items) > 1:
            res['tc_versop'] = ToolchainVersionOperator(items[1])

        return res

    def __str__(self):
        """Return string"""
        tmp = [str(self['versop'])]
        if 'tc_versop' in self:
            tmp.append(str(self['tc_versop']))

        return self.SEPARATOR_DEP.join(tmp)

    def name(self):
        """Get dependency name."""
        return self.get('name', None)

    def version(self):
        """Get dependency version."""
        if 'versop' in self:
            return self['versop'].get_version_str()
        else:
            return None

    def versionsuffix(self):
        """Get dependency versionsuffix (if any)."""
        return self['versop'].suffix

    def toolchain(self):
        """Get toolchain spec for dependency (if any)."""
        if 'tc_versop' in self:
            return self['tc_versop'].as_dict()
        else:
            return None
