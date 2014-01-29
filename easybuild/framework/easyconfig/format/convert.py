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

from easybuild.framework.easyconfig.format.wrapper import Wrapper

_log = fancylogger.getLogger('easyconfig.format.convert', fname=False)


class Convert(Wrapper):
    SEPARATOR = None

    def __init__(self, obj):
        """Support the conversion of obj to something"""
        self.__dict__['log'] = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.__dict__['data'] = None
        if isinstance(obj, basestring):
            data = self._from_string(obj)
        else:
            self.log.error('unsupported type %s for %s' % (type(obj), self.__class__.__name__))
        super(Convert, self).__init__(data)

    def _split_string(self, txt, sep=None, max=0):
        """Split using regexp, return finditer.
            @param sep: if not provided, self.SEPARATOR is tried
            @param max: split in max+1 elements (default: 0 == no limit)
        """
        if sep is None:
            if self.SEPARATOR is None:
                self.log.error('No SEPARATOR set, also no separator passed')
            else:
                sep = self.SEPARATOR
        return re.split(r'' + sep, txt, maxsplit=max)

    def _from_string(self, txt):
        """Convert string txt to self.data in proper type"""
        raise NotImplementedError

    def __str__(self):
        """Convert to string"""
        raise NotImplementedError


class ListOfStrings(Convert):
    """Convert str to list of strings"""
    SEPARATOR_LIST = ','
    __wraps__ = list

    def _from_string(self, txt):
        """ a,b -> ['a', 'b']"""
        return self._split_string(txt, sep=self.SEPARATOR_LIST)

    def __str__(self):
        """Convert to string"""
        return self.SEPARATOR_LIST.join(self._obj)


class DictOfStrings(Convert):
    """Convert string to dict
        key/value pairs are separated via SEPARATOR_DICT
        key and value are separated via SEPARATOR_KEY_VALUE
    """
    SEPARATOR_KEY_VALUE = ':'
    SEPARATOR_DICT = ','
    ALLOWED_KEYS = None
    __wraps__ = dict

    def _from_string(self, txt):
        """ a:b,c:d -> {'a':'b', 'c':'d'} """
        res = {}
        for pairs in self._split_string(txt, sep=self.SEPARATOR_DICT):
            key, value = self._split_string(pairs, sep=self.SEPARATOR_KEY_VALUE, max=1)
            if self.ALLOWED_KEYS is None or key in self.ALLOWED_KEYS:
                res[key] = value
            else:
                raise TypeError('Unsupported key %s (supported %s)' % (key, self.ALLOWED_KEYS))
        return res

    def __str__(self):
        """Convert to string"""
        tmp = [self.SEPARATOR_KEY_VALUE.join(item) for item in self.items() ]
        return self.SEPARATOR_DICT.join(tmp)


class ListOfStringsAndDictOfStrings(Convert):
    """Returns a list of strings and with last element a dict"""
    SEPARATOR_LIST = ','
    SEPARATOR_KEY_VALUE = ':'
    ALLOWED_KEYS = None
    __wraps__ = list
    def _from_string(self, txt):
        """ a,b,c:d -> ['a','b',{'c':'d'}] """
        res = []
        res_dict = {}
        for element in self._split_string(txt, sep=self.SEPARATOR_LIST):
            key_value = self._split_string(element, sep=self.SEPARATOR_KEY_VALUE, max=1)
            if len(key_value) == 2:
                key, value = key_value
                if self.ALLOWED_KEYS is None or key in self.ALLOWED_KEYS:
                    res_dict[key] = value
                else:
                    raise TypeError('Unsupported key %s (supported %s)' % (key, self.ALLOWED_KEYS))
            else:
                res.append(element)

        if res_dict:
            res.append(res_dict)
        return res

    def __str__(self):
        """Convert to string"""
        if isinstance(self[-1], dict):
            tmp = [self.SEPARATOR_KEY_VALUE.join(item) for item in self[-1].items() ]
            return self.SEPARATOR_LIST.join(self[:-1] + tmp)
        else:
            return self.SEPARATOR_LIST.join(self)


def get_convert_class(class_name):
    """Return the Convert class with name class_name"""
    res = [x for x in nub(get_subclasses(Convert)) if x.__name__ == class_name]
    if len(res) == 1:
        return res[0]
    else:
        _log.error('More then one Convert subclass found for name %s: %s' % (class_name, res))
