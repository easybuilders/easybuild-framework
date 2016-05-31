# #
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
Toolchain specific variables

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

from easybuild.tools.variables import Variables, join_map_class
from easybuild.tools.toolchain.constants import ALL_MAP_CLASSES
from easybuild.tools.toolchain.variables import LinkerFlagList, FlagList


class ToolchainVariables(Variables):
    """
    Class to hold variable-like key/value pairs
    in context of compilers (i.e. the generated string are e.g. compiler options or link flags)
    """
    MAP_CLASS = join_map_class(ALL_MAP_CLASSES)  # join_map_class strips explanation
    DEFAULT_CLASS = FlagList
    LINKER_TOGGLE_START_STOP_GROUP = None
    LINKER_TOGGLE_STATIC_DYNAMIC = None

    def add_begin_end_linkerflags(self, lib, toggle_startstopgroup=False, toggle_staticdynamic=False):
        """
        For given lib
            if toggle_startstopgroup: toggle begin/end group
            if toggle_staticdynamic: toggle static/dynamic
        """
        class LFL(LinkerFlagList):
            LINKER_TOGGLE_START_STOP_GROUP = self.LINKER_TOGGLE_START_STOP_GROUP
            LINKER_TOGGLE_STATIC_DYNAMIC = self.LINKER_TOGGLE_STATIC_DYNAMIC

        def make_lfl(begin=True):
            """make linkerflaglist for begin/end of library"""
            lfl = LFL()
            if toggle_startstopgroup:
                if begin:
                    lfl.toggle_startgroup()
                else:
                    lfl.toggle_stopgroup()
            if toggle_staticdynamic:
                if begin:
                    lfl.toggle_static()
                else:
                    lfl.toggle_dynamic()
            return lfl

        if lib is not None:
            lib.BEGIN = make_lfl(True)
            lib.BEGIN.IS_BEGIN = True
            lib.END = make_lfl(False)
            lib.END.IS_END = True


