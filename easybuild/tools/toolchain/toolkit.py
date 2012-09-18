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
import copy
import os
from distutils.version import LooseVersion

import easybuild.tools.environment as env
from easybuild.tools import systemtools
from easybuild.tools.modules import Modules, get_software_root, get_software_version

from easybuild.tools.toolchain.compiler import IccIfort
from easybuild.tools.toolchain.mpi import IntelMPI
from easybuild.tools.toolchain.scalapack import IntelMKL
from easybuild.tools.toolchain.fft import IntelFFT

from vsc.fancylogger import getLogger

"""
TODO
    - itac support ; not in old one either

"""

# constants used for recognizing compilers, MPI libraries, ...
GCC = "GCC"
INTEL = "Intel"


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
    LINKER_TEMPLATE = 'Wl,%s'

    START_GROUP = 'start-group'
    END_GROUP = 'end-group'

    TOGGLE_STATIC = None
    TOGGLE_DYNAMIC = None

    def __init__(self, *args, **kwargs):
        super(Variables, self).__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)
        self.strmap = {}

    def append(self, k, v):
        """append (k,v) : if k does not ,exists, initialise a list; append v to list"""

        tmp = self.setdefault(k, [])
        tmp.append(v)

    def extend(self, k, v):
        """extend (k,v) : if k does not ,exists, initialise a list; extend list with v"""
        tmp = self.setdefault(k, [])
        tmp.extend(v)

    def as_options(self, k, res=None):
        """as_options(k):
                print as option: if list, add '-' to each item, otherwise just return
        """
        if res is None:
            res = self.__getitem__(k)
        if isinstance(res, (list,)):
            tmp = []
            for x in res:
                if isinstance(x, (list, tuple,)):
                    tmp.extend(x)
                else:
                    tmp.append(x)
            res = " ".join(["-%s" % x for x in tmp if (x is not None and len(x) > 0)])
        return res

    def as_cmd_options(self, k, res=None):
        """as_cmd_options(k):
                print as cmd with options option: if list, add '-' to each item, except first, otherwise just return
        """
        if res is None:
            res = self.__getitem__(k)
        if isinstance(res, (list,)):
            cmd = res[0]
            if len(res) > 1:
                opts = self.as_options('', res=res[1:])
            res = "%s %s" % (cmd, opts)
        return res

    def as_comma_list(self, k, res=None):
        """Return comma-separated list"""
        if res is None:
            res = self.__getitem__(k)
        if isinstance(res, (list,)):
            tmp = []
            for x in res:
                if isinstance(x, (list, tuple,)):
                    tmp.extend(x)
                else:
                    tmp.append(x)
            res = ",".join(tmp)
        return res

    def flags_for_subdirs(self, var, base  , subdirs=None, flag=None):
        """Generate flags to pass to the compiler """
        if flag is None:
            if var == 'LDFLAGS':
                flag = "L"
            elif var == 'CPPFLAGS':
                flag = 'I'
            else:
                self.log.raiseException("flags_for_subdirs: flag not set and can't derive value for var %s" % var)
        flags = []
        if subdirs is None:
            subdirs = ['']
        for subdir in subdirs:
            directory = os.path.join(base, subdir).rstrip(os.sep)
            if os.path.isdir(directory):
                flags.append("%s%s" % (flag , directory))
            else:
                self.log.warning("flags_for_subdirs: directory %s was not found" % directory)

        self.extend(var, flags)
        self.strmap[var] = self.as_options

    def toggle_static(self, on=True):
        """Return link flag to prefer linking to static target
            on = True: set static
            on = False : set dynamic
        """
        if on and self.TOGGLE_STATIC is not None:
            return self.TOGGLE_STATIC
        elif (not on) and self.TOGGLE_DYNAMIC is not None:
            return self.TOGGLE_DYNAMIC
        return []

    def flags_for_linker(self, var, flags):
        """Add flags as linker flags"""
        if isinstance(flags, str):
            flags = [flags]
        self.extend(var, [self.LINKER_TEMPLATE % x for x in flags])
        self.strmap[var] = self.as_options


    def flags_for_libs(self, var, libs, map=None, group=False, static=False):
        """Given libs, add them prefixed with 'l'
            map : fill in the templates
            if group: add them in start/end group construct
            if static true, toggle static at start and restore dynamic at end
        """
        if isinstance(libs, str):
            libs = [libs]
        if map is not None:
            libs = [x % map for x in libs]

        ## toggle static
        if static:
            self.flags_for_linker(var, self.as_options(None, self.toggle_static(on=True)))

        ## start group
        if group:
            self.flags_for_linker(var, '--%s' % self.START_GROUP)

        self.extend(var, ["l%s" % x for x in libs])

        ## end group
        if group:
            self.flags_for_linker(var, '--%s' % self.END_GROUP)

        ## un-toggle static
        if static:
            self.flags_for_linker(var, self.as_options(None, self.toggle_static(on=False)))

        self.strmap[var] = self.as_options

    def add_exists(self, var, prefix, paths, filename=None, suffix=None):
        """Given prefix and list of paths, return first that exists
            if filename : look for filename in prefix+paths
            if suffix : extend the paths with prefixes
        """
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

    def add_comma_libs(self, var, libs, prefix='lib', suffix=None):
        """Add libs as list of lib%s
            to be returned as comma-separated list
        """
        if suffix is None:
            suffix = ''

        self.extend(var, ["%s%s%s" % (prefix, x, suffix) for x in libs])

        self.strmap[var] = self.as_comma_list


class Options(dict):
    def __init__(self, *args, **kwargs):
        super(Options, self).__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)
        self.map = {}

    def update_map(self, option_map):
        ## sanity check: do all options from the optionmap have a corresponding entry in opts
        ## - reverse is not necessarily an issue
        for k in option_map.keys():
            if not k in self:
                self.log.raiseException("update_map: entry %s in option_map has no option with that name" % k)

        self.map.update(option_map)

    def option(self, name, templatedict=None):
        """Return option value"""
        opt = self.get(name, None)
        if opt is None:
            self.log.warning("_get_compiler_option: opt with name %s returns None" % name)
            res = None
        elif isinstance(opt, bool):
            ## check if True?
            res = self.map[name]
        else:
            ## allow for template
            if templatedict is None:
                templatedict = {'opt':opt}
            res = self.map[name] % templatedict

        return res



class Toolkit(object):
    """General toolkit class"""
    def __init__(self):
        if not hasattr(self, 'log'):
            self.log = getLogger(self.__class__.__name__)

class Ictce(IccIfort, IntelMPI, IntelMKL, IntelFFT, Toolkit):
    """The ictce toolkit"""
