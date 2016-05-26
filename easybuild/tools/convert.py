# #
# Copyright 2014-2016 Ghent University
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
This module implements all supported formats and their converters 

@author: Stijn De Weirdt (Ghent University)
"""
import re

from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses, nub
from vsc.utils.wrapper import Wrapper

from easybuild.tools.build_log import EasyBuildError


_log = fancylogger.getLogger('tools.convert', fname=False)


class AllowedValueError(ValueError):
    """Specific type of error for non-allowed keys in DictOf classes."""
    pass


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
        if isinstance(obj, basestring):
            self.data = self._from_string(obj)
        else:
            raise EasyBuildError("unsupported type %s for %s: %s", type(obj), self.__class__.__name__, obj)
        super(Convert, self).__init__(self.data)

    def _split_string(self, txt, sep=None, max=0):
        """Split using sep, return list with results.
            @param sep: if not provided, self.SEPARATOR is tried
            @param max: split in max+1 elements (default: 0 == no limit)
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


class ListOfStrings(Convert):
    """Convert str to list of strings"""
    SEPARATOR_LIST = ','
    __wraps__ = list

    def __init__(self, obj, separator_list=None):
        self.separator_list = separator_list
        if self.separator_list is None:
            self.separator_list = self.SEPARATOR_LIST
        super(ListOfStrings, self).__init__(obj)

    def _from_string(self, txt):
        """Parse string as a list of strings.
            For example: "a,b" -> ['a', 'b']
        """
        return self._split_string(txt, sep=self.separator_list)

    def __str__(self):
        """Convert to string. str() is used for easy subclassing"""
        return self.SEPARATOR_LIST.join([str(x) for x in self])


class DictOfStrings(Convert):
    """Convert string to dictionary with string values
        key/value pairs are separated via SEPARATOR_DICT
        key and value are separated via SEPARATOR_KEY_VALUE
    """
    SEPARATOR_DICT = ';'
    SEPARATOR_KEY_VALUE = ':'
    ALLOWED_KEYS = None
    KEYLESS_ENTRIES = []
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
        if raise_allowed:
            self.raise_allowed = AllowedValueError

        super(DictOfStrings, self).__init__(obj)

    def _from_string(self, txt):
        """Parse string as a dictionary of /with string values.
            For example: "a:b;c:d" -> {'a':'b', 'c':'d'}"
            
            It also supports automagic dictionary creation via the KEYLESS_ENTRIES list of keys, 
            but the order is important.
            KEYLESS_ENTRIES=['first','second']
            will convert 
            "val1;val2;third:val3" -> {'first': 'val1', 'second': 'val2', 'third': 'val3'}
        """

        res = {}
        ke_usage = []
        for idx, entry in enumerate(self._split_string(txt, sep=self.separator_dict)):
            key_value = self._split_string(entry, sep=self.separator_key_value, max=1)
            if len(key_value) == 2:
                key, value = key_value
                if self.allowed_keys is None or key in self.allowed_keys:
                    res[key] = value
                else:
                    raise self.raise_allowed('Unsupported key %s (allowed %s)' % (key, self.allowed_keys))
            elif idx + 1 <= len(self.KEYLESS_ENTRIES):
                # auto-complete list into dict
                # only valid if all previous keyless entries were processed before and in order
                if  ke_usage == range(idx):
                    # all elements have to used before this one
                    ke_usage.append(idx)
                    res[self.KEYLESS_ENTRIES[idx]] = entry
                else:
                    msg = 'Unsupported element %s (previous keyless entries %s, current idx %s)'
                    raise ValueError(msg % (key_value, ke_usage, idx))

            else:
                msg = 'Unsupported element %s (from entry %s, missing key_value separator %s)'
                raise ValueError(msg % (key_value, entry, self.separator_key_value))
        return res

    def __str__(self):
        """Convert to string"""
        # the str conversions are needed for subclasses that use non-string values
        keyless_entries = [str(self[ml]) for ml in self.KEYLESS_ENTRIES if ml in self]
        def join_item(item):
            return self.separator_key_value.join([item[0], str(item[1])])
        regular = [join_item(it) for it in self.items() if not it[0] in self.KEYLESS_ENTRIES]
        return self.separator_dict.join(keyless_entries + regular)


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
                raise ValueError(str(msg))
            except ValueError, msg:
                # ValueError because the string can't be converted to DictOfStrings
                # assuming regular string value
                self.log.debug('ValueError catched with message %s, treat as regular string.' % msg)
                res.append(element)

        return res

    def __str__(self):
        """Return string"""
        return self.SEPARATOR_LIST.join([str(x) for x in self])


def get_convert_class(class_name):
    """Return the Convert class with specified class name class_name"""
    res = [x for x in nub(get_subclasses(Convert)) if x.__name__ == class_name]
    if len(res) == 1:
        return res[0]
    else:
        raise EasyBuildError("More than one Convert subclass found for name %s: %s", class_name, res)
