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
This module implements all supported formats and their converters

:author: Stijn De Weirdt (Ghent University)
"""
import re

from easybuild.base import fancylogger
from easybuild.base.wrapper import Wrapper
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.py2vs3 import string_type


_log = fancylogger.getLogger('tools.convert', fname=False)


class Convert(Wrapper):
    """
    Convert casts a string passed via the initialisation to a Convert (sub)class instance,
     mainly for typechecking and printing purposes.
    """
    SEPARATOR = None

    def __init__(self, obj):
        """Support the conversion of obj to something"""
        self.__dict__['log'] = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.__dict__['data'] = None
        if isinstance(obj, string_type):
            self.data = self._from_string(obj)
        else:
            raise EasyBuildError("unsupported type %s for %s: %s", type(obj), self.__class__.__name__, obj)
        super(Convert, self).__init__(self.data)

    def _split_string(self, txt, sep=None, max=0):
        """Split using sep, return list with results.
            :param sep: if not provided, self.SEPARATOR is tried
            :param max: split in max+1 elements (default: 0 == no limit)
        """
        if sep is None:
            if self.SEPARATOR is None:
                raise EasyBuildError("No SEPARATOR set, also no separator passed")
            else:
                sep = self.SEPARATOR
        return [x.strip() for x in re.split(r'' + sep, txt, maxsplit=max)]

    def _from_string(self, txt):
        """Convert string txt to self.data in proper type"""
        raise NotImplementedError

    def __str__(self):
        """Convert to string"""
        raise NotImplementedError
