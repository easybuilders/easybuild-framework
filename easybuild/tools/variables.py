##
# Copyright 2012 Stijn De Weirdt
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

from vsc.fancylogger import getLogger
import os


"""
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
                res[k] = v
            elif type(k) in (type,):
                tmp = res.setdefault(k, [])
                tmp.append(v)
            else:
                _log.raiseException("join_map_class: impossible to join key %s value %s" % (k, v))

    return res

class StrList(list):
    """List of strings"""
    SEPARATOR = ' '

    PREFIX = None
    SUFFIX = None

    START = None
    END = None

    def __init__(self, *args , **kwargs):
        super(StrList, self).__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)

    def str_convert(self, x):
        ## no prefix of start and end
        return ''.join([x for x in [self.PREFIX, str(x), self.SUFFIX] if x])

    def _str_self(self):
        return [self.str_convert(x) for x in self if x is not None]

    def __str__(self):
        xs = [self.START] + self._str_self() + [self.END]
        return self.SEPARATOR.join([str(x) for x in xs if x is not None])

class CommaList(StrList):
    """Comma-separated list"""
    SEPARATOR = ','

## TODO (KH) These are toolchain specific classes/functions already, so move to toolchain.variables?
## FlagList, CommandFlagList, LibraryList, LinkerFlagList
class FlagList(StrList):
    """Flag list"""
    PREFIX = "-"

class CommandFlagList(StrList):
    """
    Command and flags list
    First of the list has no prefix (i.e. the executable)
    The remainder of the options are considered flags
    """
    PREFIX = "-"
    def _str_self(self):
        tmp = [self.str_convert(x) for x in self if x is not None]
        tmp[0] = self[0]
        return tmp

class LibraryList(StrList):
    """Link library list"""
    PREFIX = "-l"

class LinkerFlagList(StrList):
    """Linker flags"""
    PREFIX = '-Wl,'

    LINKER_TOGGLE_STATIC_DYNAMIC = None

    def toggle_static(self):
        if self.LINKER_TOGGLE_STATIC_DYNAMIC is not None and 'static' in self.LINKER_TOGGLE_STATIC_DYNAMIC:
            self.append(self.LINKER_TOGGLE_STATIC_DYNAMIC['static'])

    def toggle_dynamic(self):
        if self.LINKER_TOGGLE_STATIC_DYNAMIC is not None and 'dynamic' in self.LINKER_TOGGLE_STATIC_DYNAMIC:
            self.append(self.LINKER_TOGGLE_STATIC_DYNAMIC['dynamic'])

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
    PREFIX = '-I'

class LinkLibraryPaths(AbsPathList):
    PREFIX = '-L'

def get_linker_startgroup(static_dynamic=None):
    """Return most common startgroup"""
    l = LinkerFlagList(['--start-group'])
    l.LINKER_TOGGLE_STATIC_DYNAMIC = static_dynamic
    return l

def get_linker_endgroup(static_dynamic=None):
    """Return most common endgroup"""
    l = LinkerFlagList(['--end-group'])
    l.LINKER_TOGGLE_STATIC_DYNAMIC = static_dynamic
    return l

class ListOfLists(list):
    """List of lists"""

    STR_SEPARATOR = ' '
    DEFAULT_CLASS = StrList
    PROTECTED_CLASSES = []  # classes that are not converted to DEFAULT_CLASS
    MAP_CLASS = {}  # predefined map to specify (default) mapping between variables and classes

    def append_empty(self, name=None):
        #self.append(name=None)
        self.append(None, name=None)

    #TODO (KH) this should be append(self, value, name=None)?
    #def append(self, name=None, value=None):
    def append(self, value, name=None):
        klass = get_class(name, self.DEFAULT_CLASS, self.MAP_CLASS)

        if value is None:
            newvalue = klass()
        elif type(value) in self.PROTECTED_CLASSES:
            newvalue = value
        else:
            newvalue = klass(value)

        super(ListOfLists, self).append(newvalue)

    def str_convert(self, x):
        return str(x)

    def __str__(self):
        return self.STR_SEPARATOR.join([self.str_convert(x) for x in self])



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
    DEFAULT_CLASS = ListOfLists
    MAP_LISTCLASS = {}  # map between variable name and ListOfList classes (ie not the (default) class for the variable)

    def __init__(self, *args, **kwargs):
        super(Variables, self).__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)

    def get_instance(self, name=None):
        """Return an instance of the class"""
        klass = get_class(name, self.DEFAULT_CLASS, self.MAP_LISTCLASS)
        return klass()

    def append(self, name, value):
        current = self.setdefault(name, self.get_instance(name))
        current.append(value, name=name)

    def __setitem__(self, name, value):
        """Automatically create a list for each name"""
        self.append(value, name=name)

    def setdefault(self, name, default=None):
        tmp = super(Variables, self).setdefault(name, default)
        if len(tmp) == 0:
            self.log.debug("setdefault: name %s initialising." % name)
            tmp.append_empty(name=name)
        return tmp

    def append_el(self, name, value, idx= -1):
        """Add the value to the idx-th element of the current value of name"""
        current = self.setdefault(name, self.get_instance(name))
        current[idx].append(value)

    def extend_el(self, name, value, idx= -1):
        """Extend the value of the idx-th element of the current value of name"""
        current = self.setdefault(name, self.get_instance(name))
        current[idx].extend(value)

    ## functions that pass through
    def append_exists(self, name, *args, **kwargs):
        idx = kwargs.pop('idx', -1)
        current = self.setdefault(name, self.get_instance(name))
        current[idx].append_exists(*args, **kwargs)

    def append_subdirs(self, name, *args, **kwargs):
        idx = kwargs.pop('idx', -1)
        current = self.setdefault(name, self.get_instance(name))
        current[idx].append_subdirs(*args, **kwargs)


if __name__ == '__main__':
    class TestListOfLists(ListOfLists):
        MAP_CLASS = {'FOO':CommaList}

    class TestVariables(Variables):
        MAP_LISTCLASS = {TestListOfLists : ['FOO']}

    v = TestVariables()

    print 'initial: BAR 0-5'
    v['BAR'] = range(5)
    print v['BAR'], v
    print type(v['BAR'])
    print '------------'

    print 'added 10-15 to BAR'
    v['BAR'].append(StrList(range(10, 15)))
    print v['BAR'], v
    print '------------'

    print 'added 20 to BAR'
    v.append_el('BAR', 20)
    print v['BAR'], v
    print str(v['BAR'])
    print '------------'

    ##
    print 'set FOO to 0-10 (commalist)'
    v['FOO'] = range(10)
    print v['FOO']
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