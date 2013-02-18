#!/usr/bin/env python
##
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
##
"""
Various functions that are missing from the default Python library.

  - nub(list): keep the unique elements in the list
  - find_sublist_index(list, sublist): find the index of the first
    occurence of the sublist in the list
  - Monoid: implementation of the monoid concept
  - MonoidDict: dictionary that combines values upon insertiong
    according to the given monoid
  - shell_quote / shell_unquote : convenience functions to quote / unquote strings in shell context

@author: Andy Georges (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import shlex
import subprocess


def nub(list_):
    """Returns the unique items of a list, while preserving order of
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


class Monoid (object):
    """A monoid is a mathematical object with a default element (mempty or null) and a default operation to combine
    two elements of a given data type.

    Taken from http://fmota.eu/2011/10/09/monoids-in-python.html under the do whatever you want license.
    """

    def __init__(self, null, lift, op):
        """Initialise.

        @type null: default element of some data type, e.g., [] for list or 0 for int (identity element in an Abelian group)
        @type lift: operation that injects an element into the target datatype (for duck typing)
        @type op: mappend operation to combine two elements of the target datatype
        """
        self.null = null
        self.lift = lift
        self.op = op

    def fold(self, xs):
        """fold over the elements of the list, combining them into a single element of the target datatype."""
        if hasattr(xs, "__fold__"):
            return xs.__fold__(self)
        else:
            return reduce(
                self.op,
                map(self.lift, xs),
                self.null
            )

    def __call__(self, *args):
        """When the monoid is called, the values are folded over and the resulting value is returned."""
        return self.fold(args)

    def star(self):
        """Return a new similar monoid."""
        return Monoid(self.null, self.fold, self.op)


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

def shell_quote(x):
    """Add quotes so it can be apssed to shell"""
    # use undocumented subprocess API call to quote whitespace (executed with Popen(shell=True))
    # (see http://stackoverflow.com/questions/4748344/whats-the-reverse-of-shlex-split for alternatives if needed)
    return subprocess.list2cmdline([str(x)])

def shell_unquote(x):
    """Take a literal string, remove the quotes as if it were passed by shell"""
    # it expects a string
    return shlex.split(str(x))[0]

