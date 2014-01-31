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
from vsc.utils.wrapper import Wrapper

_log = fancylogger.getLogger('tools.convert', fname=False)


class AllowedValueError(ValueError):
    """Specific type of error for non-allowed keys in DictOf classes."""
    pass


class Convert(Wrapper):
    SEPARATOR = None

    def __init__(self, obj):
        """Support the conversion of obj to something"""
        self.__dict__['log'] = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.__dict__['data'] = None
        if isinstance(obj, basestring):
            self.data = self._from_string(obj)
        else:
            self.log.error('unsupported type %s for %s' % (type(obj), self.__class__.__name__))
        super(Convert, self).__init__(self.data)

    def _split_string(self, txt, sep=None, max=0):
        """Split using sep, return list with results.
            @param sep: if not provided, self.SEPARATOR is tried
            @param max: split in max+1 elements (default: 0 == no limit)
        """
        if sep is None:
            if self.SEPARATOR is None:
                self.log.error('No SEPARATOR set, also no separator passed')
            else:
                sep = self.SEPARATOR
        return [x.strip() for x in re.split(r'' + sep, txt, maxsplit=max)]

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

    def __init__(self, obj, separator_list=None):
        self.separator_list = separator_list
        if self.separator_list is None:
            self.separator_list = self.SEPARATOR_LIST
        Convert.__init__(self, obj)

    def _from_string(self, txt):
        """Parse string as a list of strings.
            For example: "a,b" -> ['a', 'b']
        """
        return self._split_string(txt, sep=self.separator_list)

    def __str__(self):
        """Convert to string"""
        return self.separator_list.join(self)


class DictOfStrings(Convert):
    """Convert string to dict
        key/value pairs are separated via SEPARATOR_DICT
        key and value are separated via SEPARATOR_KEY_VALUE
    """
    SEPARATOR_DICT = ';'
    SEPARATOR_KEY_VALUE = ':'
    ALLOWED_KEYS = None
    __wraps__ = dict

    def __init__(self, obj, separator_dict=None, separator_key_value=None, allowed_keys=None, raise_allowed=False):
        self.separator_dict = separator_dict
        if self.separator_dict is None:
            self.separator_dict = self.SEPARATOR_DICT
        self.separator_key_value = separator_key_value
        if self.separator_key_value is None:
            self.separator_key_value = self.SEPARATOR_KEY_VALUE
        self.allowed_keys = allowed_keys
        if self.allowed_keys is None:
            self.allowed_keys = self.ALLOWED_KEYS
        self.raise_allowed = ValueError
        if self.raise_allowed:
            self.raise_allowed = AllowedValueError

        Convert.__init__(self, obj)

    def _from_string(self, txt):
        """Parse string as a dictionary of strings.
            For example: "a:b;c:d" -> {'a':'b', 'c':'d'}"
        """

        res = {}
        for pairs in self._split_string(txt, sep=self.separator_dict):
            key_value = self._split_string(pairs, sep=self.separator_key_value, max=1)
            if len(key_value) == 2:
                key, value = key_value
                if self.allowed_keys is None or key in self.allowed_keys:
                    res[key] = value
                else:
                    raise self.raise_allowed('Unsupported key %s (supported %s)' % (key, self.allowed_keys))
            else:
                msg = 'Unsupported element %s (from pairs %s, missing key_value separator %s)'
                raise ValueError(msg % (key_value, pairs, self.separator_key_value))
        return res

    def __str__(self):
        """Convert to string"""
        return self.separator_dict.join([self.separator_key_value.join(item) for item in self.items()])


class ListOfStringsAndDictOfStrings(Convert):
    """Returns a list of strings and with last element a dict"""
    SEPARATOR_LIST = ','
    SEPARATOR_DICT = ';'
    SEPARATOR_KEY_VALUE = ':'
    ALLOWED_KEYS = None
    __wraps__ = list
    def _from_string(self, txt):
        """Parse string as a list of strings, followed by a dictionary of strings at the end.
            For example, "a,b,c:d;e:f,g,h,i:j" -> ['a','b',{'c':'d', 'e': 'f'}, 'g', 'h', {'i': 'j'}]
        """
        res = []

        for element in ListOfStrings(txt, separator_list=self.SEPARATOR_LIST):
            try:
                kwargs = {
                    'separator_dict': self.SEPARATOR_DICT,
                    'separator_key_value': self.SEPARATOR_KEY_VALUE,
                    'allowed_keys': self.ALLOWED_KEYS,
                    'raise_allowed': True,
                }
                res.append(DictOfStrings(element, **kwargs))
            except AllowedValueError, msg:
                # reraise it as regular ValueError
                raise ValueError(msg)
            except ValueError:
                res.append(element)

        return res

    def __str__(self):
        """Convert to string"""
        return self.SEPARATOR_LIST.join([str(x) for x in self])


def get_convert_class(class_name):
    """Return the Convert class with name class_name"""
    res = [x for x in nub(get_subclasses(Convert)) if x.__name__ == class_name]
    if len(res) == 1:
        return res[0]
    else:
        _log.error('More then one Convert subclass found for name %s: %s' % (class_name, res))
