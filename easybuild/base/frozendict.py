# External compatible license
# taken from https://github.com/slezica/python-frozendict on March 14th 2014 (commit ID b27053e4d1)
#
# Copyright (c) 2012 Santiago Lezica
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions
# of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
# TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE
"""
frozendict is an immutable wrapper around dictionaries that implements the complete mapping interface.
It can be used as a drop-in replacement for dictionaries where immutability is desired.
"""
import operator
from collections import Mapping
from functools import reduce

from easybuild.base import fancylogger


# minor adjustments:
# * renamed to FrozenDict
class FrozenDict(Mapping):

    def __init__(self, *args, **kwargs):
        self.__dict = dict(*args, **kwargs)
        self.__hash = None

    def __getitem__(self, key):
        return self.__dict[key]

    def copy(self, **add_or_replace):
        return FrozenDict(self, **add_or_replace)

    def __iter__(self):
        return iter(self.__dict)

    def __len__(self):
        return len(self.__dict)

    def __repr__(self):
        return '<FrozenDict %s>' % repr(self.__dict)

    def __hash__(self):
        if self.__hash is None:
            self.__hash = reduce(operator.xor, map(hash, self.iteritems()), 0)

        return self.__hash

    # minor adjustment: define missing keys() method
    def keys(self):
        return self.__dict.keys()


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
