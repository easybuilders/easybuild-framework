#!/usr/bin/env python
# #
# Copyright 2012-2013 Ghent University
#
# This file is part of vsc-base,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/vsc-base
#
# vsc-base is free software: you can redistribute it and/or modify
# it under the terms of the GNU Library General Public License as
# published by the Free Software Foundation, either version 2 of
# the License, or (at your option) any later version.
#
# vsc-base is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public License
# along with vsc-base. If not, see <http://www.gnu.org/licenses/>.
# #
"""
Various functions that are missing from the default Python library.

  - nub(list): keep the unique elements in the list
  - nub_by(list, predicate): keep the unique elements (first come, first served) that do not satisfy a given predicate
  - find_sublist_index(list, sublist): find the index of the first
    occurence of the sublist in the list
  - Monoid: implementation of the monoid concept
  - MonoidDict: dictionary that combines values upon insertiong
    according to the given monoid
  - RUDict: dictionary that allows recursively updating its values (if they are dicts too) with a new RUDict
  - shell_quote / shell_unquote : convenience functions to quote / unquote strings in shell context

@author: Andy Georges (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import os
import re
import shlex
import subprocess
import sys
import time

from vsc.utils import fancylogger
from vsc.utils.frozendict import FrozenDict


_log = fancylogger.getLogger('vsc.utils.missing')


def partial(func, *args, **keywords):
    """
    Return a new partial object which when called will behave like func called with the positional arguments args
    and keyword arguments keywords. If more arguments are supplied to the call, they are appended to args. If additional
    keyword arguments are supplied, they extend and override keywords.
    new in python 2.5, from https://docs.python.org/2/library/functools.html#functools.partial
    """
    def newfunc(*fargs, **fkeywords):
        newkeywords = keywords.copy()
        newkeywords.update(fkeywords)
        return func(*(args + fargs), **newkeywords)
    newfunc.func = func
    newfunc.args = args
    newfunc.keywords = keywords
    return newfunc


def any(ls):
    """Reimplementation of 'any' function, which is not available in Python 2.4 yet."""

    return sum([bool(x) for x in ls]) != 0


def all(ls):
    """Reimplementation of 'all' function, which is not available in Python 2.4 yet."""

    return sum([bool(x) for x in ls]) == len(ls)


def nub(list_):
    """Returns the unique items of a list of hashables, while preserving order of
    the original list, i.e. the first unique element encoutered is
    retained.

    Code is taken from
    http://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-in-python-whilst-preserving-order

    Supposedly, this is one of the fastest ways to determine the
    unique elements of a list.

    @type list_: a list :-)

    @returns: a new list with each element from `list` appearing only once (cfr. Michelle Dubois).
    """
    seen = set()
    seen_add = seen.add
    return [x for x in list_ if x not in seen and not seen_add(x)]


def nub_by(list_, predicate):
    """Returns the elements of a list that fullfil the predicate.

    For any pair of elements in the resulting list, the predicate does not hold. For example, the nub above
    can be expressed as nub_by(list, lambda x, y: x == y).

    @type list_: a list of items of some type t
    @type predicate: a function that takes two elements of type t and returns a bool

    @returns: the nubbed list
    """
    seen = set()
    seen_add = seen.add
    return [x for x in list_ if not any([predicate(x, y) for y in seen]) and not seen_add(x)]


def find_sublist_index(ls, sub_ls):
    """Find the index at which the sublist sub_ls can be found in ls.

    @type ls: list
    @type sub_ls: list

    @return: index of the matching location or None if no match can be made.
    """
    sub_length = len(sub_ls)
    for i in xrange(len(ls)):
        if ls[i:(i + sub_length)] == sub_ls:
            return i

    return None


class Monoid(object):
    """A monoid is a mathematical object with a default element (mempty or null) and a default operation to combine
    two elements of a given data type.

    Taken from http://fmota.eu/2011/10/09/monoids-in-python.html under the do whatever you want license.
    """

    def __init__(self, null, mappend):
        """Initialise.

        @type null: default element of some data type, e.g., [] for list or 0 for int (identity element in an Abelian group)
        @type op: mappend operation to combine two elements of the target datatype
        """
        self.null = null
        self.mappend = mappend

    def fold(self, xs):
        """fold over the elements of the list, combining them into a single element of the target datatype."""
        if hasattr(xs, "__fold__"):
            return xs.__fold__(self)
        else:
            return reduce(
                self.mappend,
                xs,
                self.null
            )

    def __call__(self, *args):
        """When the monoid is called, the values are folded over and the resulting value is returned."""
        return self.fold(args)

    def star(self):
        """Return a new similar monoid."""
        return Monoid(self.null, self.mappend)


class MonoidDict(dict):
    """A dictionary with a monoid operation, that allows combining values in the dictionary according to the mappend
    operation in the monoid.
    """

    def __init__(self, monoid, *args, **kwargs):
        """Initialise.

        @type monoid: Monoid instance
        """
        super(MonoidDict, self).__init__(*args, **kwargs)
        self.monoid = monoid

    def __setitem__(self, key, value):
        """Combine the value the dict has for the key with the new value using the mappend operation."""
        if super(MonoidDict, self).__contains__(key):
            current = super(MonoidDict, self).__getitem__(key)
            super(MonoidDict, self).__setitem__(key, self.monoid(current, value))
        else:
            super(MonoidDict, self).__setitem__(key, value)

    def __getitem__(self, key):
        """ Obtain the dictionary value for the given key. If no value is present,
        we return the monoid's mempty (null).
        """
        if not super(MonoidDict, self).__contains__(key):
            return self.monoid.null
        else:
            return super(MonoidDict, self).__getitem__(key)


class RUDict(dict):
    """Recursively updatable dictionary.

    When merging with another dictionary (of the same structure), it will keep
    updating the values as well if they are dicts or lists.

    Code taken from http://stackoverflow.com/questions/6256183/combine-two-dictionaries-of-dictionaries-python.
    """

    def update(self, E=None, **F):
        if E is not None:
            if 'keys' in dir(E) and callable(getattr(E, 'keys')):
                for k in E:
                    if k in self:  # existing ...must recurse into both sides
                        self.r_update(k, E)
                    else:  # doesn't currently exist, just update
                        self[k] = E[k]
            else:
                for (k, v) in E:
                    self.r_update(k, {k: v})

        for k in F:
            self.r_update(k, {k: F[k]})

    def r_update(self, key, other_dict):
        """Recursive update."""
        if isinstance(self[key], dict) and isinstance(other_dict[key], dict):
            od = RUDict(self[key])
            nd = other_dict[key]
            od.update(nd)
            self[key] = od
        elif isinstance(self[key], list):
            if isinstance(other_dict[key], list):
                self[key].extend(other_dict[key])
            else:
                self[key] = self[key].append(other_dict[key])
        else:
            self[key] = other_dict[key]


class FrozenDictKnownKeys(FrozenDict):
    """A frozen dictionary only allowing known keys."""

    # list of known keys
    KNOWN_KEYS = []

    def __init__(self, *args, **kwargs):
        """Constructor, only way to define the contents."""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        # support ignoring of unknown keys
        ignore_unknown_keys = kwargs.pop('ignore_unknown_keys', False)

        # handle unknown keys: either ignore them or raise an exception
        tmpdict = dict(*args, **kwargs)
        unknown_keys = [key for key in tmpdict.keys() if not key in self.KNOWN_KEYS]
        if unknown_keys:
            if ignore_unknown_keys:
                for key in unknown_keys:
                    self.log.debug("Ignoring unknown key '%s' (value '%s')" % (key, args[0][key]))
                    # filter key out of dictionary before creating instance
                    del tmpdict[key]
            else:
                msg = "Encountered unknown keys %s (known keys: %s)" % (unknown_keys, self.KNOWN_KEYS)
                self.log.raiseException(msg, exception=KeyError)

        super(FrozenDictKnownKeys, self).__init__(tmpdict)

    def __getitem__(self, key, *args, **kwargs):
        """Redefine __getitem__ to provide a better KeyError message."""
        try:
            return super(FrozenDictKnownKeys, self).__getitem__(key, *args, **kwargs)
        except KeyError, err:
            if key in self.KNOWN_KEYS:
                raise KeyError(err)
            else:
                tup = (key, self.__class__.__name__, self.KNOWN_KEYS)
                raise KeyError("Unknown key '%s' for %s instance (known keys: %s)" % tup)


def shell_quote(x):
    """Add quotes so it can be apssed to shell"""
    # use undocumented subprocess API call to quote whitespace (executed with Popen(shell=True))
    # (see http://stackoverflow.com/questions/4748344/whats-the-reverse-of-shlex-split for alternatives if needed)
    return subprocess.list2cmdline([str(x)])


def shell_unquote(x):
    """Take a literal string, remove the quotes as if it were passed by shell"""
    # it expects a string
    return shlex.split(str(x))[0]


def get_class_for(modulepath, class_name):
    """
    Get class for a given Python class name and Python module path.

    @param modulepath: Python module path (e.g., 'vsc.utils.generaloption')
    @param class_name: Python class name (e.g., 'GeneralOption')
    """
    # try to import specified module path, reraise ImportError if it occurs
    try:
        module = __import__(modulepath, globals(), locals(), [''])
    except ImportError, err:
        raise ImportError(err)
    # try to import specified class name from specified module path, throw ImportError if this fails
    try:
        klass = getattr(module, class_name)
    except AttributeError, err:
        raise ImportError("Failed to import %s from %s: %s" % (class_name, modulepath, err))
    return klass


def get_subclasses_dict(klass, include_base_class=False):
    """Get dict with subclasses per classes, recursively from the specified base class."""
    res = {}
    subclasses = klass.__subclasses__()
    if include_base_class:
        res.update({klass: subclasses})
    for subclass in subclasses:
        # always include base class for recursive call
        res.update(get_subclasses_dict(subclass, include_base_class=True))
    return res


def get_subclasses(klass, include_base_class=False):
    """Get list of all subclasses, recursively from the specified base class."""
    return get_subclasses_dict(klass, include_base_class=include_base_class).keys()


def modules_in_pkg_path(pkg_path):
    """Return list of module files in specified package path."""
    # if the specified (relative) package path doesn't exist, try and determine the absolute path via sys.path
    if not os.path.isabs(pkg_path) and not os.path.isdir(pkg_path):
        _log.debug("Obtained non-existing relative package path '%s', will try to figure out absolute path" % pkg_path)
        newpath = None
        for sys_path_dir in sys.path:
            abspath = os.path.join(sys_path_dir, pkg_path)
            if os.path.isdir(abspath):
                _log.debug("Found absolute path %s for package path %s, verifying it" % (abspath, pkg_path))
                # also make sure an __init__.py is in place in every subdirectory
                is_pkg = True
                subdir = ''
                for pkg_path_dir in pkg_path.split(os.path.sep):
                    subdir = os.path.join(subdir, pkg_path_dir)
                    if not os.path.isfile(os.path.join(sys_path_dir, subdir, '__init__.py')):
                        is_pkg = False
                        tup = (subdir, abspath, pkg_path)
                        _log.debug("No __init__.py found in %s, %s is not a valid absolute path for pkg_path %s" % tup)
                        break
                if is_pkg:
                    newpath = abspath
                    break

        if newpath is None:
            # give up if we couldn't find an absolute path for the imported package
            tup = (pkg_path, sys.path)
            raise OSError("Can't browse package via non-existing relative path '%s', not found in sys.path (%s)" % tup)
        else:
            pkg_path = newpath
            _log.debug("Found absolute package path %s" % pkg_path)

    module_regexp = re.compile(r"^(?P<modname>[^_].*|__init__)\.py$")
    modules = [res.group('modname') for res in map(module_regexp.match, os.listdir(pkg_path)) if res]
    _log.debug("List of modules for package in %s: %s" % (pkg_path, modules))
    return modules


def avail_subclasses_in(base_class, pkg_name, include_base_class=False):
    """Determine subclasses for specificied base classes in modules in (only) specified packages."""

    def try_import(name):
        """Try import the specified package/module."""
        try:
            # don't use return value of __import__ since it may not be the package itself but it's parent
            __import__(name, globals())
            return sys.modules[name]
        except ImportError, err:
            raise ImportError("avail_subclasses_in: failed to import %s: %s" % (name, err))

    # import all modules in package path(s) before determining subclasses
    pkg = try_import(pkg_name)
    for pkg_path in pkg.__path__:
        for mod in modules_in_pkg_path(pkg_path):
            # no need to directly import __init__ (already done by importing package)
            if not mod.startswith('__init__'):
                _log.debug("Importing module '%s' from package '%s'" % (mod, pkg_name))
                try_import('%s.%s' % (pkg_name, mod))

    return get_subclasses_dict(base_class, include_base_class=include_base_class)


class TryOrFail(object):
    """
    Perform the function n times, catching each exception in the exception tuple except on the last try
    where it will be raised again.
    """
    def __init__(self, n, exceptions=(Exception,), sleep=0):
        self.n = n
        self.exceptions = exceptions
        self.sleep = sleep

    def __call__(self, function):
        def new_function(*args, **kwargs):
            for i in xrange(0, self.n):
                try:
                    return function(*args, **kwargs)
                except self.exceptions, err:
                    if i == self.n - 1:
                        raise
                    _log.exception("try_or_fail caught an exception - attempt %d: %s" % (i, err))
                    if self.sleep > 0:
                        _log.warning("try_or_fail is sleeping for %d seconds before the next attempt" % (self.sleep,))
                        time.sleep(self.sleep)

        return new_function


def post_order(graph, root):
    """
    Walk the graph from the given root in a post-order manner by providing the corresponding generator
    """
    for node in graph[root]:
        for child in post_order(graph, node):
            yield child
    yield root


def topological_sort(graph):
    """
    Perform topological sorting of the given graph.

    The graph is a dict with the values for a key being the dependencies, i.e., an arrow from key to each value.
    """
    visited = set()
    for root in graph:
        for node in post_order(graph, root):
            if not node in visited:
                yield node
                visited.add(node)
