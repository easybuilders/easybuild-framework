# #
# Copyright 2012-2018 Ghent University
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
Toolchain specific variables

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.variables import StrList, AbsPathList


class IncludePaths(AbsPathList):
    """Absolute path to directory containing include files"""
    PREFIX = '-I'


class LinkLibraryPaths(AbsPathList):
    """Absolute path to directory containing libraries"""
    PREFIX = '-L'


class FlagList(StrList):
    """Flag list"""
    PREFIX = "-"


class CommandFlagList(FlagList):
    """
    Command and flags list
        First of the list has no prefix (i.e. the executable)
        The remainder of the options are considered flags
    """
    def _str_self(self):
        """Like a regular flag list, but set first element to original value"""
        tmp_str = [self.str_convert(x) for x in self if self._str_ok(x)]
        if len(tmp_str) > 0:
            tmp_str[0] = self[0]
        return tmp_str


class LibraryList(StrList):
    """Link library list"""
    PREFIX = "-l"

    SANITIZE_REMOVE_DUPLICATE_KEEP = -1  #  sanitize from end

    JOIN_BEGIN_END = True

    def set_packed_linker_options(self, separator=',', separator_begin_end=',', prefix=None, prefix_begin_end=None):
        """Use packed linker options format"""
        if isinstance(self.BEGIN, LinkerFlagList) and isinstance(self.END, LinkerFlagList):
            self.log.devel("sanitize: PACKED_LINKER_OPTIONS")

            self.BEGIN.PACKED_LINKER_OPTIONS = True
            self.END.PACKED_LINKER_OPTIONS = True
            if separator_begin_end is not None:
                self.BEGIN.SEPARATOR = separator_begin_end
                self.END.SEPARATOR = separator_begin_end
            if prefix_begin_end is not None:
                self.BEGIN.PREFIX = prefix_begin_end
                self.END.PREFIX = prefix_begin_end

            # this is intentional only on the elements that have BEGIN/END
            if separator is not None:
                self.SEPARATOR = separator
            if prefix is not None:
                self.PREFIX = prefix

    def change(self, separator=None, separator_begin_end=None, prefix=None, prefix_begin_end=None):
        """Change prefix and/or separator of base and/or BEGIN/END"""
        if separator is not None:
            self.SEPARATOR = separator
        if prefix is not None:
            self.PREFIX = prefix

        if isinstance(self.BEGIN, LinkerFlagList):
            if separator_begin_end is not None:
                self.BEGIN.SEPARATOR = separator_begin_end
            if prefix_begin_end is not None:
                self.BEGIN.PREFIX = prefix_begin_end

        if isinstance(self.END, LinkerFlagList):
            if separator_begin_end is not None:
                self.END.SEPARATOR = separator_begin_end
            if prefix_begin_end is not None:
                self.END.PREFIX = prefix_begin_end


class CommaStaticLibs(LibraryList):
    """Comma-separated list"""
    SEPARATOR = ','

    PREFIX = 'lib'
    SUFFIX = '.a'


class LinkerFlagList(StrList):
    """Linker flags"""

    PREFIX = '-Wl,'

    LINKER_TOGGLE_START_STOP_GROUP = None
    LINKER_TOGGLE_STATIC_DYNAMIC = None

    PACKED_LINKER_OPTIONS = None

    IS_BEGIN = None
    IS_END = None

    def _toggle_map(self, toggle_map, name, descr, idx=None):
        """Append value from toggle_map. Raise if not None and name not found
            descr string to add to raise
        """
        if toggle_map is not None:
            if name in toggle_map:
                if idx is None:
                    self.append(toggle_map[name])
                else:
                    self.insert(idx, toggle_map[name])
            else:
                raise EasyBuildError("%s name %s not found in map %s", descr, name, toggle_map)

    def toggle_startgroup(self):
        """Append start group"""
        self._toggle_map(self.LINKER_TOGGLE_START_STOP_GROUP, 'start', 'toggle_startgroup', idx=None)

    def toggle_stopgroup(self):
        """Append stop group"""
        self._toggle_map(self.LINKER_TOGGLE_START_STOP_GROUP, 'stop', 'toggle_stopgroup', idx=0)

    def toggle_static(self):
        """Append static linking flags"""
        self._toggle_map(self.LINKER_TOGGLE_STATIC_DYNAMIC, 'static', 'toggle_static', idx=0)

    def toggle_dynamic(self):
        """Append dynamic linking flags"""
        self._toggle_map(self.LINKER_TOGGLE_STATIC_DYNAMIC, 'dynamic', 'toggle_dynamic', idx=None)

    def sanitize(self):
        # TODO: rewrite to avoid changing constants
        if self.PACKED_LINKER_OPTIONS:
            # somehow this should only be run once.
            self.PACKED_LINKER_OPTIONS = None

            self.log.devel("sanitize: PACKED_LINKER_OPTIONS")
            if self.IS_BEGIN and self.SEPARATOR:
                self.BEGIN = str(self.PREFIX).rstrip(self.SEPARATOR)
            self.PREFIX = None
            self.log.devel("sanitize: PACKED_LINKER_OPTIONS IS_BEGIN %s PREFIX %s BEGIN %s",
                           self.IS_BEGIN, self.PREFIX, self.BEGIN)

        super(LinkerFlagList, self).sanitize()


