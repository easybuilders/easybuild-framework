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
import shlex
import subprocess
import time

from vsc.utils import fancylogger
from vsc.utils.frozendict import FrozenDict


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


def get_subclasses(klass):
    """Get all subclasses recursively"""
    res = []
    for cl in klass.__subclasses__():
        res.extend(get_subclasses(cl))
        res.append(cl)
    return res


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
        def new_function(*args, **kwargs ):
            log = fancylogger.getLogger(function.__name__)
            for i in xrange(0,self.n):
                try:
                    return function(*args, **kwargs)
                except self.exceptions, err:
                    if i == self.n - 1:
                        raise
                    log.exception("try_or_fail caught an exception - attempt %d: %s" % (i, err))
                    if self.sleep > 0:
                        log.warning("try_or_fail is sleeping for %d seconds before the next attempt" % (self.sleep,))
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

