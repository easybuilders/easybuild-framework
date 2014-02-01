# #
# Copyright 2014-2014 Ghent University
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
This module implements easyconfig specific formats and their conversions.

@author: Stijn De Weirdt (Ghent University)
"""
from easybuild.framework.easyconfig.format.version import VersionOperator, ToolchainVersionOperator
from easybuild.tools.convert import Convert, DictOfStrings, ListOfStrings


class Patch(DictOfStrings):
    """Handle single patch
        # shorthand
        filename;level:<int>;dest:<string> -> {'filename': filename, 'level': level, 'dest': dest}
        # full dict notation
        filename:filename;level:<int>;dest:<string> -> {'filename': filename, 'level': level, 'dest': dest}
    """
    ALLOWED_KEYS = ['level', 'dest']
    MIXED_LIST = ['filename']  # filename as first element (also filename:some_path i supported)
    __str__ = DictOfStrings.__str__
    def _from_string(self, txt):
        res = DictOfStrings._from_string(self, txt)
        if 'level' in res:
            res['level'] = int(res['level'])
        return res


class Patches(ListOfStrings):
    """Handle patches as list of Patch
    """
    def __init__(self):
        raise NotImplementedError


class Dependency(Convert):
    """Handle dependency
        versop_str;tc_versop_str -> {'versop': versop, 'tc_versop': tc_versop}
    """
    SEPARATOR_DEP = ';'
    __wraps__ = dict

    def _from_string(self, txt):
        res = {}

        items = self._split_string(txt, sep=self.SEPARATOR_DEP)
        if len(items) < 1 or len(items) > 2:
            raise ValueError('Dependency has at least one element (versop_str), and at most 2 (2nd element the tc_versop). Separator')

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
