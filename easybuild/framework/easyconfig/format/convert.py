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
This module implements all supported formats and their converters 

@author: Stijn De Weirdt (Ghent University)
"""
import re

from vsc import fancylogger
from vsc.utils.missing import get_subclasses, nub

_log = fancylogger.getLogger('easyconfig.format.convert', fname=False)


class Convert(object):
    SEPARATOR = None
    SEPARATOR_LIST = ','

    def __init__(self, obj):
        """Support the conversion of obj to something"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        if isinstance(obj, basestring):
            self.from_str(obj)
        else:
            self.log.error('unsupported type %s for %s' % (type(obj), self.__class__.__name__))

    def split(self, txt, sep=None):
        """Split using regexp, return finditer.
            If sep is not provides, self.SEPARATOR is tried
        """
        if sep is None:
            if self.SEPARATOR is None:
                self.log.error('No SEPARATOR set, also no separator passed')
            else:
                sep = self.SEPARATOR
        reg = re.compile(r'' + sep)
        return reg.split(txt)

    def make_liststr(self, txt):
        """Retrun list of strings"""
        return self.split(txt, sep=self.SEPARATOR_LIST)

    def from_str(self, txt):
        """Convert string txt to self.data in proper type"""
        raise NotImplementedError


class ListStr(Convert):
    """Convert str to list of strings"""
    def from_str(self, txt):
        """Use make_liststr"""
        self.data = self.make_liststr(txt)


def get_convert_class(class_name):
    """Return the Convert class with name class_name"""
    res = [x for x in nub(get_subclasses(Convert)) if x.__name__ == class_name]
    if len(res) == 1:
        return res[0]
    else:
        _log.error('More then one Convert subclass found for name %s: %s' % (class_name, res))
