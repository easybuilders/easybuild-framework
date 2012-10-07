##
# Copyright 2012 Stijn De Weirdt
# Copyright 2012 Kenneth Hoste
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
##
"""
Module that contains a set of classes and function to generate variables to be used
eg in compiling or linking

TODO:
    new classes that extend lists
        retain original provided data
            options or libnames
        override __str__
        add static methods
    introduce legacy class
        dict when accessed prints warnings and gives
        http://stackoverflow.com/questions/9008444/how-to-warn-about-class-name-deprecation
            not exactly what i need though
                we don't want to redefine the class (eg dict) but it's uage (eg tk.vars)
"""

from vsc.fancylogger import getLogger, setLogLevelDebug
import copy
import os
import re

_log = getLogger()

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
        for k, v in map_class.items():
            if isinstance(k, (str,)) and k == name:
                klass = v
            elif type(k) in (type,) and name in v:
                klass = k
            else:
                _log.debug("get_class: key %s value %s no str or type" % (k, v))

    return klass

def join_map_class(*map_classes):
    """Join all class_maps into single class_map"""
    res = {}
    for map_class in map_classes:
        for k, v in map_class.items():
            if isinstance(k, (str,)):
                var_name = k
                if isinstance(v, (tuple, list)):
                    ## second element is documentation
                    klass = v[0]
                res[var_name] = klass
            elif type(k) in (type,):
                ## k is the class, v a list of tuples (name,doc)
                klass = k
                default = res.setdefault(klass, [])
                default.extend([tpl[0] for tpl in v])
            else:
                _log.raiseException("join_map_class: impossible to join key %s value %s" % (k, v))

    return res

class StrList(list):
    """List of strings"""
    SEPARATOR = ' '

    PREFIX = None
    SUFFIX = None

    BEGIN = None
    END = None

    def __init__(self, *args , **kwargs):
        super(StrList, self).__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)

    def str_convert(self, x):
        """Convert members of list to string (no prefix of begin and end)"""
        return ''.join([str(y) for y in [self.PREFIX, str(x), self.SUFFIX] if y is not None])

    def _str_self(self):
        """Main part of __str__"""
        return [self.str_convert(x) for x in self if x is not None]

    def __str__(self):
        """_str_self and support for BEGIN/END"""
        xs = [self.BEGIN] + self._str_self() + [self.END]
        return self.SEPARATOR.join([str(x) for x in xs if x is not None])

    def __getattribute__(self, attr_name):
        """Filter out function calls from Variables class"""
        if attr_name == 'nappend_el':
            return self.append
        elif attr_name == 'nextend_el':
            return self.extend
        else:
            return super(StrList, self).__getattribute__(attr_name)


class CommaList(StrList):
    """Comma-separated list"""
    SEPARATOR = ','

## TODO (KH) These are toolchain specific classes/functions already, so move to toolchain.variables?
## FlagList, CommandFlagList, LibraryList, LinkerFlagList
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
        tmp_str = [self.str_convert(x) for x in self if x is not None]
        tmp_str[0] = self[0]
        return tmp_str

class LibraryList(StrList):
    """Link library list"""
    PREFIX = "-l"

class LinkerFlagList(StrList):
    """Linker flags"""
    PREFIX = '-Wl,'

    LINKER_TOGGLE_STATIC_DYNAMIC = None

    def toggle_static(self):
        """Append static linking flags"""
        if self.LINKER_TOGGLE_STATIC_DYNAMIC is not None and 'static' in self.LINKER_TOGGLE_STATIC_DYNAMIC:
            self.append(self.LINKER_TOGGLE_STATIC_DYNAMIC['static'])

    def toggle_dynamic(self):
        """Append dynamic linking flags"""
        if self.LINKER_TOGGLE_STATIC_DYNAMIC is not None and 'dynamic' in self.LINKER_TOGGLE_STATIC_DYNAMIC:
            self.append(self.LINKER_TOGGLE_STATIC_DYNAMIC['dynamic'])

    def set_static_dynamic(self, static_dynamic):
        """Set the static/dynamic toggle values"""
        self.LINKER_TOGGLE_STATIC_DYNAMIC = copy.deepcopy(static_dynamic)

class AbsPathList(StrList):
    """Absolute paths (eg -L or -I)"""

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

## TODO (KH) These are toolchain specific classes/functions already, so move to toolchain.variables?
## IncludePaths, LinkLibraryPaths, get_linker*
class IncludePaths(AbsPathList):
    """Absolute path to directory containing include files"""
    PREFIX = '-I'

class LinkLibraryPaths(AbsPathList):
    """Absolute path to directory containing libraries"""
    PREFIX = '-L'

def get_linker_startgroup(static_dynamic=None):
    """Return most common startgroup"""
    lfl = LinkerFlagList(['--start-group'])
    lfl.set_static_dynamic(static_dynamic)
    return lfl

def get_linker_endgroup(static_dynamic=None):
    """Return most common endgroup"""
    lfl = LinkerFlagList(['--end-group'])
    lfl.set_static_dynamic(static_dynamic)
    return lfl

class ListOfLists(list):
    """List of lists"""

    STR_SEPARATOR = ' '
    DEFAULT_CLASS = StrList
    PROTECTED_CLASSES = []  # classes that are not converted to DEFAULT_CLASS
    MAP_CLASS = {}  # predefined map to specify (default) mapping between variables and classes

    def __init__(self, *args , **kwargs):
        super(ListOfLists, self).__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)

    def append_empty(self, name):
        """Initialise MAP_CLASS instance"""
        self.nappend(name, None)

    def get_class(self, name):
        """Return the class associated with the name accordong to the DEFAULT_CLASS and MAP_CLASS"""
        return get_class(name, self.DEFAULT_CLASS, self.MAP_CLASS)

    def nappend(self, name, value=None):
        """Named append"""
        klass = self.get_class(name)

        if type(value) in self.PROTECTED_CLASSES:
            newvalue = value
        else:
            if isinstance(value, (str, int,)):
                ## convert to list. although the try/except will work
                ##  list('XYZ') creates ['X','Y','Z']
                value = [value]

            try:
                ## this might work, but probably not
                newvalue = klass(value)
            except:
                newvalue = klass()
                if value is not None:
                    newvalue.append(value)

        self.append(newvalue)

    def nextend(self, name, value=None):
        """Named extend, value is list type (TODO: tighten the allowed values)"""
        klass = self.get_class(name)

        res = []
        if value is None:
            ## TODO ? append_empty ?
            self.log.raiseException("extend_el with None value unimplemented")
        else:
            for el in value:
                if type(el) in self.PROTECTED_CLASSES:
                    res.append(el)
                else:
                    if isinstance(el, (str, int,)):
                        ## convert to list. although the try/except will work
                        ##  list('XYZ') creates ['X','Y','Z']
                        el = [el]

                    try:
                        ## this might work, but probably not
                        newvalue = klass(el)
                    except:
                        newvalue = klass()
                        if value is not None:
                            newvalue.append(el)

                    res.append(newvalue)

        self.extend(res)


    def str_convert(self, x):
        """Given x, return a string representing x
            called in __str__ of this class
        """
        return str(x)

    def __str__(self):
        return self.STR_SEPARATOR.join([self.str_convert(x) for x in self if x is not None and len(x) > 0])



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

    def __init__(self, *args, **kwargs):
        super(Variables, self).__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)

    def get_class(self, name):
        """Return the class associated with the name accordong to the DEFAULT_CLASS and MAP_CLASS"""
        return get_class(name, self.DEFAULT_LISTCLASS, self.MAP_LISTCLASS)

    def get_instance(self, name=None):
        """Return an instance of the class"""
        klass = self.get_class(name)
        return klass()

    def append(self, name, value):
        """Append value to element name (alias for nappend)"""
        self.nappend(name, value)

    def __setitem__(self, name, value):
        """Automatically creates a list for each name"""
        self.append(name, value)

    def setdefault(self, name, default=None):
        #"""append_empty to non-existing element"""
        default = super(Variables, self).setdefault(name, default)
        if len(default) == 0:
            self.log.debug("setdefault: name %s initialising." % name)
            default.append_empty(name)
        return default

    def __getattribute__(self, attr_name):
        # allow for pass-through
        if attr_name in ['nappend', 'nextend', 'append_empty']:
            self.log.debug("Passthrough to LISTCLASS function %s" % attr_name)
            def _passthrough(name, *args, **kwargs):
                """functions that pass through to LISTCLASS instances"""
                current = self.setdefault(name, self.get_instance(name))
                actual_function = getattr(current, attr_name)
                res = actual_function(name, *args, **kwargs)
                return res
            return _passthrough
        elif attr_name in ['nappend_el', 'nextend_el', 'append_exists', 'append_subdirs']:
            self.log.debug("Passthrough to LISTCLASS element function %s" % attr_name)
            def _passthrough(name, *args, **kwargs):
                """"Functions that pass through to elements of LISTCLASS (accept idx as index)"""
                idx = kwargs.pop('idx', -1)
                current = self.setdefault(name, self.get_instance(name))
                print type(self), name, current, type(current), current.get_class(name), current.MAP_CLASS
                actual_function = getattr(current[idx], attr_name)
                res = actual_function(*args, **kwargs)
                return res
            return _passthrough
        else:
            return super(Variables, self).__getattribute__(attr_name)


if __name__ == '__main__':
    setLogLevelDebug()
    class TestListOfLists(ListOfLists):
        """Test ListOfList class"""
        MAP_CLASS = {'FOO':CommaList}

    class TestVariables(Variables):
        """Test Variables class"""
        MAP_LISTCLASS = {TestListOfLists : ['FOO']}

    va = TestVariables()
    print va

    print 'initial: BAR 0-5'
    va['BAR'] = range(5)
    print va['BAR'], va
    print type(va['BAR'])
    print '------------'

    print 'initial: BARSTR XYZ'
    va['BARSTR'] = 'XYZ'
    print va['BARSTR'].__repr__(), va
    print type(va['BARSTR'])
    print '------------'

    print 'initial: BARINT 0'
    va['BARINT'] = 0
    print va['BARINT'], va
    print type(va['BARINT'])
    print '------------'


    print 'added 10-15 to BAR'
    va['BAR'].append(StrList(range(10, 15)))
    print va['BAR'], va
    print '------------'

    print 'added 20 to BAR'
    va.nappend('BAR', 20)
    print va['BAR'], va
    print str(va['BAR'])
    print '------------'

    print 'added 30 to 2nd last element of BAR'
    va.nappend_el('BAR', 30, idx= -2)
    print va['BAR'], va
    print str(va['BAR'])
    print '------------'


    ##
    print 'set FOO to 0-10 (commalist)'
    va['FOO'] = range(10)
    print va['FOO']
    print '------------'

    ## startgroup
    print 'linker endgroup'
    l = get_linker_endgroup()
    print l
    print '------------'

    print 'linker startgroup with static toggle'
    l2 = get_linker_startgroup({'static':'-Bstatic',
                                'dynamic':'-Bdynamic',
                               })
    l2.toggle_static()
    print l2
    print '------------'

    ##
    cmd = CommandFlagList(range(5))
    print cmd
    print '------------'


