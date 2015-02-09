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
Deprecated functionality for EasyBuild v1.x

@author: Kenneth Hoste (Ghent University)
"""
from vsc.utils.wrapper import Wrapper


class ExtraOptionsDeprecatedReturnValue(Wrapper):
    """
    Hybrid list/dict object: is a list (of 2-element tuples), but also acts like a dict.

    Supported dict-like methods include: update(adict), items(), keys(), values()

    Consistency of values being 2-element tuples is *not* checked!
    """
    __wraps__ = list

    def __getitem__(self, index_key):
        """Get value by specified index/key."""
        if isinstance(index_key, int):
            res = self._obj[index_key]
        else:
            res = dict(self._obj)[index_key]
        return res

    def __setitem__(self, index_key, value):
        """Add value at specified index/key."""
        if isinstance(index_key, int):
            self._obj[index_key] = value
        else:
            self._obj = [(k, v) for (k, v) in self._obj if k != index_key]
            self._obj.append((index_key, value))

    def update(self, extra):
        """Update with keys/values in supplied dictionary."""
        self._obj = [(k, v) for (k, v) in self._obj if k not in extra.keys()]
        self._obj.extend(extra.items())

    def items(self):
        """Get list of key/value tuples."""
        return self._obj

    def keys(self):
        """Get list of keys."""
        return [x[0] for x in self.items()]

    def values(self):
        """Get list of values."""
        return [x[1] for x in self.items()]
