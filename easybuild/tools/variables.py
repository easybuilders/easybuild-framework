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
Module that contains a set of classes and function to generate variables to be used
e.g., in compiling or linking

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import copy
import os
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError


_log = fancylogger.getLogger('variables', fname=False)


def get_class(name, default_class, map_class=None):
    """Return class based on default
        map_class
             if key == str -> value = class
             else: key = class -> list of strings
    """
    if map_class is None:
        map_class = {}

    klass = default_class
    if name is not None:
        try:
            klass = map_class[name]
        except:
            for k, v in map_class.items():
                if type(k) in (type,) and name in v:
                    klass = k
                    break

    return klass


def join_map_class(map_classes):
    """Join all class_maps into single class_map"""
    res = {}
    for map_class in map_classes:
        for key, val in map_class.items():
            if isinstance(key, (str,)):
                var_name = key
                if isinstance(val, (tuple, list)):
                    # second element is documentation
                    klass = val[0]
                res[var_name] = klass
            elif type(key) in (type,):
                # k is the class, v a list of tuples (name,doc)
                klass = key
                default = res.setdefault(klass, [])
                default.extend([tpl[0] for tpl in val])
            else:
                raise EasyBuildError("join_map_class: impossible to join key %s value %s", key, val)

    return res


class StrList(list):
    """List of strings"""
    SEPARATOR = ' '

    PREFIX = None
    SUFFIX = None

    BEGIN = None
    END = None

    POSITION = 0  # when sorting in list of list: < 0 -> left; > 0 : right
    SANITIZE_REMOVE_DUPLICATE_KEEP = None  # used with ListOfList

    JOIN_BEGIN_END = False

    def __init__(self, *args, **kwargs):
        super(StrList, self).__init__(*args, **kwargs)
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

    def str_convert(self, x):
        """Convert members of list to string (no prefix of begin and end)"""
        return ''.join([str(y) for y in [self.PREFIX, str(x), self.SUFFIX] if y is not None])

    def _str_ok(self, x):
        """Test if x can be added to returned string"""
        test = x is not None and len(str(x)) > 0
        return test

    def _str_self(self):
        """Main part of __str__"""
        return [self.str_convert(x) for x in self if self._str_ok(x)]

    def sanitize(self):
        """Sanitize self"""

    def __str__(self):
        """_str_self and support for BEGIN/END"""
        self.sanitize()
        xs = [self.BEGIN] + self._str_self() + [self.END]
        return str(self.SEPARATOR).join([str(x) for x in xs if self._str_ok(x)])

    def __getattribute__(self, attr_name):
        """Filter out function calls from Variables class"""
        if attr_name == 'nappend_el':
            return self.append
        elif attr_name == 'nextend_el':
            return self.extend
        else:
            return super(StrList, self).__getattribute__(attr_name)

    def copy(self):
        """Return copy of self"""
        return copy.deepcopy(self)

    def try_remove(self, values):
        """Remove without ValueError in case of missing element"""
        for value in values:
            try:
                self.remove(value)
            except ValueError:
                pass


class CommaList(StrList):
    """Comma-separated list"""
    SEPARATOR = ','


class AbsPathList(StrList):
    """Absolute paths (eg -L or -I)"""

    SANITIZE_REMOVE_DUPLICATE_KEEP = -1  #  sanitize from end

    def append_exists(self, prefix, paths, suffix=None, filename=None, append_all=False):
        """
        Given prefix and list of paths, return first that exists
            if suffix : extend the paths with prefixes
            if filename : look for filename in prefix+paths
        """
        self.log.debug("append_exists: prefix %s paths %s suffix %s filename %s append_all %s" % (prefix, paths, suffix, filename, append_all))
        if suffix is not None:
            res = []
            for path in paths:
                res.extend(["%s%s" % (path, suffix), path])
            paths = res

        for path in paths:
            abs_path = os.path.join(prefix, path)
            if filename is not None:
                abs_path = os.path.join(abs_path, filename)
            if os.path.exists(abs_path):
                self.append(abs_path)
                self.log.debug("append_exists: added abssolute path %s" % abs_path)
                if not append_all:
                    return

    def append_subdirs(self, base, subdirs=None):
        """
        Add directory base, or its subdirs if subdirs is not None
        """
        self.log.debug("append_subdirs: base %s subdirs %s" % (base, subdirs))

        if subdirs is None:
            subdirs = [None]
        for subdir in subdirs:
            if subdir is None:
                directory = base
            else:
                directory = os.path.join(base, subdir)

            if os.path.isdir(directory):
                self.append(directory)
                self.log.debug("append_subdirs: added directory %s" % directory)
            else:
                self.log.warning("flags_for_subdirs: directory %s was not found" % directory)


class ListOfLists(list):
    """List of lists"""
    DEFAULT_CLASS = StrList
    PROTECTED_CLASSES = []  # classes that are not converted to DEFAULT_CLASS
    # PROTECTED_INSTANCES = [AbsPathList, LibraryList]
    PROTECTED_INSTANCES = []
    PROTECT_CLASS_SELF = True  # don't convert values that are same class as DEFAULT_CLASS
    PROTECT_INSTANCE_SELF = True  # don't convert values that are instance of DEFAULT_CLASS

    SEPARATOR = None

    SANITIZE_SORT = True
    SANITIZE_REMOVE_DUPLICATE = False
    SANITIZE_REMOVE_DUPLICATE_KEEP = None

    JOIN_BEGIN_END = False

    def __init__(self, *args, **kwargs):
        super(ListOfLists, self).__init__(*args, **kwargs)
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self._first = None

        self.protected_classes = self.PROTECTED_CLASSES[:]
        if self.PROTECT_CLASS_SELF:
            if not self.DEFAULT_CLASS in self.protected_classes:
                self.protected_classes.append(self.DEFAULT_CLASS)
        self.protected_instances = self.PROTECTED_INSTANCES[:]
        if self.PROTECT_INSTANCE_SELF:
            if not self.DEFAULT_CLASS in self.protected_instances:
                self.protected_instances.append(self.DEFAULT_CLASS)

    def append_empty(self):
        """Initialise MAP_CLASS instance"""
        self.nappend(None, append_empty=True)

    def show_el(self):
        """Show some info on the elements"""
        res = []
        for el in self:
            res.append("%s B_ %s _E" % (type(el), el))
        return ";".join(res)

    def get_first(self):
        """Return first non-empty list
            if it doesn't exist, try to return first element
        """
        for x in self:
            if self._str_ok(x):
                return x

        if len(self) > 0:
            return self[0]

    def _is_protected(self, value):
        """Check if value is protected from conversion to default class"""
        res = False

        if type(value) in self.protected_classes:
            self.log.debug("_is_protected: %s value %s (%s)" % (self.protected_classes, value, type(value)))
            res = True
        elif isinstance(value, tuple(self.protected_instances)):
            self.log.debug("_is_protected: %s value %s (%s)" % (self.protected_instances, value, type(value)))
            res = True

        self.log.debug("_is_protected: %s value %s (%s)" % (res, value, value.__repr__()))
        return res

    def nappend(self, value, **kwargs):
        """Named append
            name is not used anymore
        """
        append_empty = kwargs.pop('append_empty', False)
        position = kwargs.pop('position', None)
        klass = kwargs.pop('var_class', self.DEFAULT_CLASS)

        if self._is_protected(value):
            newvalue = value.copy()
        else:
            if isinstance(value, (str, int,)):
                # convert to list. although the try/except will work
                #  list('XYZ') creates ['X','Y','Z']
                value = [value]

            try:
                # this might work, but probably not
                newvalue = klass(value, **kwargs)
            except:
                newvalue = klass(**kwargs)
                if value is not None:
                    newvalue.append(value)
        if not position is None:
            newvalue.POSITION = position
        if self._str_ok(newvalue) or append_empty:
            self.append(newvalue)
            self.log.debug("nappend: value %s newvalue %s position %s" % (value.__repr__(), newvalue.__repr__(), position))
            return newvalue
        else:
            self.log.debug("nappend: ignoring value %s newvalue %s (not _str_ok)" % (value.__repr__(), newvalue.__repr__()))

    def nextend(self, value=None, **kwargs):
        """Named extend, value is list type (TODO: tighten the allowed values)
            name not used anymore
        """
        klass = kwargs.pop('var_class', self.DEFAULT_CLASS)
        res = []
        if value is None:
            # TODO ? append_empty ?
            raise EasyBuildError("extend_el with None value unimplemented")
        else:
            for el in value:
                if not self._str_ok(el):
                    self.log.debug("nextend: ignoring el %s from value %s (not _str_ok)" % (el, value.__repr__()))
                    continue

                if type(el) in self.PROTECTED_CLASSES:
                    newvalue = el
                else:
                    if isinstance(el, (str, int,)):
                        # convert to list. although the try/except will work
                        #  list('XYZ') creates ['X','Y','Z']
                        el = [el]

                    try:
                        # this might work, but probably not
                        newvalue = klass(el)
                    except:
                        newvalue = klass()
                        if value is not None:
                            newvalue.append(el)

                res.append(newvalue)

        self.extend(res)
        self.log.debug("nextend: value %s res %s" % (value.__repr__(), res.__repr__()))
        return res

    def str_convert(self, x):
        """Given x, return a string representing x
            called in __str__ of this class
        """
        return str(x)

    def _str_ok(self, x):
        """Test if x can be added returned string"""
        test = x is not None and len(x) > 0
        return test

    def sanitize(self):
        """Cleanup self"""
        if self.SANITIZE_SORT:
            self.sort(key=lambda x: getattr(x, 'POSITION'))

        if self.SANITIZE_REMOVE_DUPLICATE:
            # get all occurences with their index
            to_remove = []
            for el in self:
                all_idx = [idx for idx, x in enumerate(self) if x == el]
                if len(all_idx) > 1:
                    if self.SANITIZE_REMOVE_DUPLICATE_KEEP == 0:
                        # keep first
                        to_remove.extend(all_idx[1:])
                    elif self.SANITIZE_REMOVE_DUPLICATE_KEEP == -1:
                        # keep last
                        to_remove.extend(all_idx[:-1])

            to_remove = sorted(list(set(to_remove)), reverse=True)
            self.log.debug("sanitize: to_remove in %s %s" % (self.__repr__(), to_remove))
            for idx in to_remove:
                del self[idx]

        if self.JOIN_BEGIN_END:
            # group elements with same begin/end into one element
            to_remove = []
            for idx in range(1, len(self))[::-1]:  # work in reversed order;don't check last one (ie real el 0), it has no next element
                if self[idx].BEGIN is None or self[idx].END is None: continue
                self.log.debug("idx %s len %s" % (idx, len(self)))
                if self[idx].BEGIN == self[idx - 1].BEGIN and self[idx].END == self[idx - 1].END:  # do check POSITION, sorting already done
                    self.log.debug("sanitize: JOIN_BEGIN_END idx %s joining %s and %s" % (idx, self[idx], self[idx - 1]))
                    self[idx - 1].extend(self[idx])
                    to_remove.append(idx)  # remove current el
            to_remove = sorted(list(set(to_remove)), reverse=True)
            for idx in to_remove:
                del self[idx]

    def flatten(self):
        res = []
        for x in self:
            if self._str_ok(x):
                res.extend(x)
        return res

    def __str__(self):
        self._first = self.get_first()
        self.sanitize()
        sep = ''  # default no separator

        if self._first is None:
            # return empty string
            self.log.debug("__str__: first is None (self %s)" % self.__repr__())
            return ''
        else:
            sep = self.SEPARATOR

            txt = str(sep).join([self.str_convert(x) for x in self if self._str_ok(x)])
            self.log.debug("__str__: return %s (self: %s)" % (txt, self.__repr__()))
            return txt

    def try_function_on_element(self, function_name, names=None, args=None, kwargs=None):
        """Try to run function function_name on each element"""
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        for el in self:
            if hasattr(el, function_name):
                function = getattr(el, function_name)
                function(*args, **kwargs)

    def try_remove(self, values):
        """Try to remove one or more values from the elements"""
        self.try_function_on_element('try_remove', args=[values])

    def copy(self):
        """Return copy of self"""
        return copy.deepcopy(self)


class Variables(dict):
    """
    Class to hold variable-like key/value pairs
        All values are lists (or derived from list class)
            most only have a single element though
            some are lists of lists
        __str__ creates a single string

        Most items are of same DEFAULT_CLASS
            but are in different classes
    """
    DEFAULT_LISTCLASS = ListOfLists
    MAP_LISTCLASS = {}  # map between variable name and ListOfList classes (ie not the (default) class for the variable)

    DEFAULT_CLASS = StrList
    MAP_CLASS = {}  # predefined map to specify (default) mapping between variables and classes

    def __init__(self, *args, **kwargs):
        super(Variables, self).__init__(*args, **kwargs)
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

    def get_list_class(self, name):
        """Return the class associated with the name according to the DEFAULT_LISTCLASS and MAP_LISTCLASS"""
        return get_class(name, self.DEFAULT_LISTCLASS, self.MAP_LISTCLASS)

    def get_element_class(self, name):
        """Return the class associated with the name according to the DEFAULT_CLASS and MAP_CLASS"""
        return get_class(name, self.DEFAULT_CLASS, self.MAP_CLASS)

    def get_instance(self, name=None):
        """Return an instance of the class"""
        list_class = self.get_list_class(name)
        element_class = self.get_element_class(name)

        class klass(list_class):
            DEFAULT_CLASS = element_class

            SEPARATOR = element_class.SEPARATOR

            SANITIZE_REMOVE_DUPLICATE = element_class.SANITIZE_REMOVE_DUPLICATE_KEEP is not None
            SANITIZE_REMOVE_DUPLICATE_KEEP = element_class.SANITIZE_REMOVE_DUPLICATE_KEEP

            JOIN_BEGIN_END = element_class.JOIN_BEGIN_END

        # better log messages (most use self.__class__.__name__; would give klass otherwise)
        klass.__name__ = "%s_%s" % (self.__class__.__name__, name)
        return klass()

    def join(self, name, *others):
        """Join all values in others into name
            it is first tested if other is an existing element
                else it is nappend-ed
        """
        self.log.debug("join name %s others %s" % (name, others))

        # make sure name is defined, even if 'others' list is empty
        self.setdefault(name)

        for other in others:
            if other in self:
                self.log.debug("join other %s in self: other %s" % (other, self.get(other).__repr__()))
                for el in self.get(other):
                    self.nappend(name, el)
            else:
                raise EasyBuildError("join: name %s; other %s not found in self.", name, other)

    def append(self, name, value):
        """Append value to element name (alias for nappend)"""
        return self.nappend(name, value)

    def __setitem__(self, name, value):
        """Automatically creates a list for each name"""
        if name in self:
            del self[name]
        self.nappend(name, value)

    def setdefault(self, name, default=None, append_empty=False):
        # """append_empty to non-existing element"""
        if name in self:
            default = self[name]
        else:
            if default is None:
                default = self.get_instance(name)
            super(Variables, self).__setitem__(name, default)

        if len(default) == 0:
            self.log.debug("setdefault: name %s initialising." % name)
            if append_empty:
                default.append_empty()
        return default

    def try_function_on_element(self, function_name, names=None, args=None, kwargs=None):
        """Try to run function function_name on each element of names"""
        if names is None:
            names = self.keys()
        for name in names:
            self.log.debug("try_function_el: name %s function_name %s" % (name, function_name))
            self[name].try_function_on_element(function_name, args=args, kwargs=kwargs)

    def __getattribute__(self, attr_name):
        # allow for pass-through
        if attr_name in ['nappend', 'nextend', 'append_empty', 'first', 'get_class']:
            self.log.debug("Passthrough to LISTCLASS function %s" % attr_name)

            def _passthrough(name, *args, **kwargs):
                """functions that pass through to LISTCLASS instances"""
                current = self.setdefault(name)
                actual_function = getattr(current, attr_name)
                res = actual_function(*args, **kwargs)
                return res
            return _passthrough
        elif attr_name in ['nappend_el', 'nextend_el', 'append_exists', 'append_subdirs']:
            self.log.debug("Passthrough to LISTCLASS element function %s" % attr_name)

            def _passthrough(name, *args, **kwargs):
                """"Functions that pass through to elements of LISTCLASS (accept idx as index)"""
                idx = kwargs.pop('idx', -1)
                if attr_name in ['append_exists', 'append_subdirs']:
                    current = self.setdefault(name)
                    current.append_empty()  # always add empty
                else:
                    current = self.setdefault(name, append_empty=True)
                actual_function = getattr(current[idx], attr_name)
                res = actual_function(*args, **kwargs)
                return res
            return _passthrough
        else:
            return super(Variables, self).__getattribute__(attr_name)

