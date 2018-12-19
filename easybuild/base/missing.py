#
# Copyright 2012-2018 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
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
#
"""
Various functions that are missing from the default Python library.

  - nub(list): keep the unique elements in the list
  - nub_by(list, predicate): keep the unique elements (first come, first served) that do not satisfy a given predicate
  - find_sublist_index(list, sublist): find the index of the first
    occurence of the sublist in the list
    according to the given monoid
  - shell_quote / shell_unquote : convenience functions to quote / unquote strings in shell context

:author: Andy Georges (Ghent University)
:author: Stijn De Weirdt (Ghent University)
"""
import shlex
try:
    from shlex import quote  # python 3.3
except ImportError:
    from pipes import quote  # python 2.7

from easybuild.base import fancylogger
from easybuild.base.frozendict import FrozenDict


_log = fancylogger.getLogger('easybuild.base.missing')


def is_string(item):
    """Check whether specified value is a string or not."""
    return isinstance(item, basestring)


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


def nub(list_):
    """Returns the unique items of a list of hashables, while preserving order of
    the original list, i.e. the first unique element encoutered is
    retained.

    Code is taken from
    http://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-in-python-whilst-preserving-order

    Supposedly, this is one of the fastest ways to determine the
    unique elements of a list.

    @type list_: a list :-)

    :return: a new list with each element from `list` appearing only once (cfr. Michelle Dubois).
    """
    seen = set()
    seen_add = seen.add
    return [x for x in list_ if x not in seen and not seen_add(x)]


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
        unknown_keys = [key for key in tmpdict.keys() if key not in self.KNOWN_KEYS]
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

    # pylint: disable=arguments-differ
    def __getitem__(self, key, *args, **kwargs):
        """Redefine __getitem__ to provide a better KeyError message."""
        try:
            return super(FrozenDictKnownKeys, self).__getitem__(key, *args, **kwargs)
        except KeyError as err:
            if key in self.KNOWN_KEYS:
                raise KeyError(err)
            else:
                tup = (key, self.__class__.__name__, self.KNOWN_KEYS)
                raise KeyError("Unknown key '%s' for %s instance (known keys: %s)" % tup)


def shell_quote(x):
    """Add quotes so it can be passed to shell"""
    return quote(str(x))


def shell_unquote(x):
    """Take a literal string, remove the quotes as if it were passed by shell"""
    # it expects a string
    return ' '.join(shlex.split(str(x)))


def get_class_for(modulepath, class_name):
    """
    Get class for a given Python class name and Python module path.

    :param modulepath: Python module path (e.g., 'easybuild.base.generaloption')
    :param class_name: Python class name (e.g., 'GeneralOption')
    """
    # try to import specified module path, reraise ImportError if it occurs
    try:
        module = __import__(modulepath, globals(), locals(), [''])
    except ImportError as err:
        raise ImportError(err)
    # try to import specified class name from specified module path, throw ImportError if this fails
    try:
        klass = getattr(module, class_name)
    except AttributeError as err:
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
