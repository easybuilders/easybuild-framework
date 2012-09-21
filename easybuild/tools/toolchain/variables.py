##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
# Copyright 2012 Toon Willems
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
class _List(list):
    """new list with class method
        usage:
            print OptionList.str(['ok'])

            opts=OptionList()
            opts.append('ok')
            print opts
    """
    @classmethod
    def str(cls, *args, **kwargs):
        r = cls(*args, **kwargs)
        return r.__str__()


    EXTRA_ATTRS = ['prefix', 'suffix', 'start', 'end']
    def __init__(self, *args , **kwargs):
        for attr in self.EXTRA_ATTRS:
            setattr(self, attr, kwargs.pop(attr, None))
        super(_List, self).__init__(*args, **kwargs)

    def _handle_with_care(self, name):
        """To deal with start/stop who can also be _List instances
            TODO: reimplement
        """
        tmp = getattr(self, name, None)
        self.log.debug("_handle_with_care: name %s tmp %s type_tmp %s" % (name, tmp, type(tmp)))
        if isinstance(tmp, (_List)) or tmp is None:
            pass
        elif isinstance(tmp, (list, tuple,)):
            tmp = self.__class__(tmp)
        elif isinstance(tmp, str):
            tmp = self.__class__([tmp])
        else:
            self.log.raiseExcpetion("_handle_with_care: unknown tmp %s type %s" % (tmp, type(tmp)))
        return tmp

    def _copy_xattrs(self, orig):
        """Restore the added _List attributes from other instance"""
        self.log.debug("_copy_xattrs: copying xattrs %s from  %s type %s" % (self.EXTRA_ATTRS, orig, type(orig)))
        for attr in self.EXTRA_ATTRS:
            setattr(self, attr, getattr(orig, attr, None))

    def _sanity_lib(self):
        """Unique version, for libs
            start at the end, work to the front
        """
        self.log.debug("_sanity_lib: repr %s" % (self.__repr__))

class OptionsList(_List):
    def __str__(self):
        """As option list"""
        self.log.debug("__str__: repr %s" % (self.__repr__))
        if self.prefix is None:
            prefix = ''
        else:
            prefix = "%s" % self.prefix
        if self.suffix is None:
            suffix = ''
        else:
            suffix = "%s" % self.suffix

        tmp = []
        for x in self.__iter__():
            if isinstance(x, (list, tuple,)):
                tmp.extend(x)
            else:
                tmp.append(x)
        res = " ".join(["-%s%s%s" % (prefix, x, suffix) for x in tmp if (x is not None) and (len(x) > 0)])

        start = self._handle_with_care('start')
        end = self._handle_with_care('end')

        return " ".join(["%s" % x for x in [start, res, end] if (x is not None) and (len(x) > 0)])

class CmdOptionsList(_List):
    def __str__(self):
        """print as cmd with options option:
            if list, add '-' to each item, except first, otherwise just return
        """
        self.log.debug("__str__: repr %s" % (self.__repr__))
        if self.__len__() == 0:
            res = ''
        else:
            cmd = "%s" % self.__getitem__(0)
            if self.__len__() > 1:
                opts = OptionsList(self.__getslice__(1, self.__len__()))
                opts._copy_xattrs(self)
                res = "%s %s" % (cmd, opts)
            else:
                res = cmd
        return res

class CommaList(_List):
    def __str__(self):
        self.log.debug("__str__: repr %s" % (self.__repr__))
        tmp = []
        if self.prefix is None:
            prefix = ''
        else:
            prefix = "%s" % self.prefix
        if self.suffix is None:
            suffix = ''
        else:
            suffix = "%s" % self.suffix

        for x in self.__iter__():
            if isinstance(x, (list, tuple,)):
                tmp.extend(x)
            else:
                tmp.append(x)

        return ",".join(["%s%s%s" % (prefix, x, suffix) for x in tmp])


class Variables(dict):
    """Extend dict with

    ## example code
    v=Variables()
    v.extend('CFLAGS',['O3','lto'])
    v.flags_for_subdirs('LDFLAGS','/usr',subdirs=['lib','lib64','unknown'])


    for o in ['CFLAGS','LDFLAGS']:
        print o, v.options(o)

    ## output
    2012-09-10 08:11:52,189 WARNING    test.Variables      MainThread  _flags_for_subdirs: directory /usr/unknown was not found
    CFLAGS -O3 -lto
    LDFLAGS -L/usr/lib -L/usr/lib64

    TODO:
        introduce proper classes for features like cmd+flags, flags, comma_separated_lists
            with correct __str__
        make conversion from Variables to old text-only vars
    """
    LINKER_PREFIX = 'Wl,'

    START_GROUP = 'start-group'
    END_GROUP = 'end-group'

    TOGGLE_STATIC = None
    TOGGLE_DYNAMIC = None

    def __init__(self, *args, **kwargs):
        super(Variables, self).__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)

    def _append(self, k, v, defclass=list, **kwargs):
        """append (k,v) : if k does not ,exists, initialise a defclass; append v to list"""
        self.log.debug("append: k %s v %s defclass %s kwargs %s" % (k, v, defclass, kwargs))
        tmp = self.setdefault(k, defclass(**kwargs))
        tmp.append(v)

    def _extend(self, k, v, defclass=None, **kwargs):
        """extend (k,v) : if k does not ,exists, initialise type v; extend list with v"""
        self.log.debug("extend: k %s v %s type_v %s defclass %s kwargs %s" % (k, v, type(v), defclass, kwargs))
        if defclass is None:
            defclass = type(v)
        if k in self:
            tmp = self.get(k)
        else:
            tmp = defclass(**kwargs)
            if isinstance(v, _List):
                tmp._copy_xattrs(v)
        if type(tmp) == type(v):
            tmp.extend(v)
        else:
            ## TODO: is this fixable ?
            self.log.raiseException("extend k=%s: mixing existing type %s with value type %s" % (k, type(tmp), type(v)))

    def join(self, k, *args):
        """args is list of keys, join them into k; use copy of the first one"""
        self.log.debug("join: k %s args %s" % (k, args))
        v = self.get(args[0], None)
        if v is None:
            self.log.raiseException("join: k %k args %s : first name %s not in self" % (k, args, args[0]))
        if k in self:
            tmp = self.get(k)
        else:
            tmp = type(v)()
            if isinstance(v, _List):
                tmp._copy_xattrs(v)

        for name in args:
            if not name in self:
                self.log.raiseException("join: k %k args %s : name %s not in self" % (k, args, name))
            v = self.get(name)
            if type(tmp) == type(v):
                tmp.extend(v)
            else:
                ## TODO: is this fixable ?
                self.log.raiseException("join k=%s: mixing existing type %s with value type %s" % (k, type(tmp), type(v)))

        self.__setitem__(k, tmp)

    def append_option(self, k, v):
        self.log.debug("append_option: k %s v %s" % (k, v))
        self._append(k, v, defclass=OptionsList)

    def extend_option(self, k, v):
        self.log.debug("extend_option: k %s v %s" % (k, v))
        self._extend(k, v, defclass=OptionsList)

    def append_cmd_option(self, k, v):
        self.log.debug("append_cmd_option: k %s v %s" % (k, v))
        self._append(k, v, defclass=CmdOptionsList)

    def extend_cmd_option(self, k, v):
        self.log.debug("extend_cmd_option: k %s v %s" % (k, v))
        self._extend(k, v, defclass=CmdOptionsList)


    def toggle_static(self, on=True):
        """Return link flag to prefer linking to static target
            on = True: set static
            on = False : set dynamic
        """
        self.log.debug("toggle_static: on %s TOGGLE_STATIC %s TOGGLE_DYNAMIC %s" % (on, self.TOGGLE_STATIC, self.TOGGLE_DYNAMIC))
        if on and self.TOGGLE_STATIC is not None:
            return self.TOGGLE_STATIC
        elif (not on) and self.TOGGLE_DYNAMIC is not None:
            return self.TOGGLE_DYNAMIC
        return []

    def extend_linker_option(self, var, flags):
        """Add flags as linker flags"""
        if isinstance(flags, str):
            flags = [flags]
        self.log.debug("extend_linke_option: var %s flags %s LINKER_PREFIX %s" % (var, flags, self.LINKER_PREFIX))
        self._extend(var, OptionsList(flags, prefix=self.LINKER_PREFIX))


    def append_lib_option(self, k, v):
        self.log.debug("append_lib_option: k %s v %s" % (k, v))
        self._append(k, v, defclass=OptionsList, prefix='l')

    def extend_lib_option(self, var, libs, libmap=None, group=False, static=False):
        """Given libs, add them prefixed with 'l'
            map : fill in the templates
            if group: add them in start/end group construct
            if static true, toggle static at start and restore dynamic at end
        """
        if isinstance(libs, str):
            libs = [libs]
        self.log.debug("extend_lib_option: var %s libs %s libmap %s group %s static %s" % (var, libs, libmap, group, static))
        if libmap is not None:
            libs = [x % libmap for x in libs]

        start = OptionsList(prefix=self.LINKER_PREFIX)
        end = OptionsList(prefix=self.LINKER_PREFIX)

        if group:
            start.append('--%s' % self.START_GROUP)
            end.append('--%s' % self.END_GROUP)

        ## toggle static
        if static:
            start.insert(0, self.toggle_static(on=True))
            end.extend(self.toggle_static(on=False))

        self._extend(var, OptionsList(libs, prefix='l', start=start, end=end))


    def extend_comma_libs(self, var, libs, prefix='lib', suffix=None):
        """Add libs as list of lib%s
            to be returned as comma-separated list
        """
        self.log.debug("extend_comma_libs: var %s libs %s prefix %s suffix %s" % (var, libs, prefix, suffix))
        self._extend(var, CommaList(libs, prefix=prefix, suffix=suffix))


    def append_exists(self, var, prefix, paths, filename=None, suffix=None):
        """Given prefix and list of paths, return first that exists
            if filename : look for filename in prefix+paths
            if suffix : extend the paths with prefixes

            TODO: deal with instances of itself
        """
        self.log.debug("append_exists: var %s prefix %s paths %s filename %s suffix %s" % (var, prefix, paths, filename, suffix))
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
                self.append(var, abs_path)
                return

        self.log.raiseException("add_exists: no existing path found (var %s ; prefix %s ; path %s ; filename %s; suffix %s)" % (var, prefix, paths, filename, suffix))

    def extend_subdirs_option(self, var, base  , subdirs=None, flag=None):
        """Generate flags to pass to the compiler """
        self.log.debug("extend_subdirs_option: var %s base %s subdirs %s flag %s" % (var, base, subdirs, flag))
        if flag is None:
            if var == 'LDFLAGS':
                flag = "L"
            elif var == 'CPPFLAGS':
                flag = 'I'
            else:
                self.log.raiseException("flags_for_subdirs: flag not set and can't derive value for var %s" % var)

        dirs = OptionsList(prefix=flag)

        if subdirs is None:
            subdirs = [None]
        for subdir in subdirs:
            if subdir is None:
                directory = base
            else:
                directory = os.path.join(base, subdir)

            if os.path.isdir(directory):
                dirs.append(directory)
            else:
                self.log.warning("flags_for_subdirs: directory %s was not found" % directory)

        self._extend(var, dirs)

