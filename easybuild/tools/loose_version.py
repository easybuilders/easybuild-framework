"""
This file contains the LooseVersion class based on the class with the same name
as present in Python 3.7.4 distutils.
The original class is licensed under the Python Software Foundation License Version 2.
It was slightly simplified as needed to make it shorter and easier to read.
In particular the following changes were made:
- Subclass object directly instead of abstract Version class
- Fully init the class in the constructor removing the parse method
- Always set self.vstring and self.version
- Shorten the comparison operators as the NotImplemented case doesn't apply anymore
- Changes to documentation and formatting
"""

import re
from itertools import zip_longest


class LooseVersion(object):
    """Version numbering for anarchists and software realists.

    A version number consists of a series of numbers,
    separated by either periods or strings of letters.
    When comparing version numbers, the numeric components will be compared
    numerically, and the alphabetic components lexically.
    """

    component_re = re.compile(r'(\d+ | [a-z]+ | \.)', re.VERBOSE)

    def __init__(self, vstring=None):
        self._vstring = vstring
        if vstring:
            components = [x for x in self.component_re.split(vstring)
                          if x and x != '.']
            for i, obj in enumerate(components):
                try:
                    components[i] = int(obj)
                except ValueError:
                    pass
            self._version = components
        else:
            self._version = None

    @property
    def vstring(self):
        """Readonly access to the unparsed version(-string)"""
        return self._vstring

    @property
    def version(self):
        """Readonly access to the parsed version (list or None)"""
        return self._version

    def is_prerelease(self, other, markers):
        """Check if this is a prerelease of other

        Markers is a list of strings that denote a prerelease
        """
        if isinstance(other, str):
            vstring = other
        else:
            vstring = other._vstring
        if self._vstring.startswith(vstring):
            prerelease = self._vstring[len(vstring):]
            for marker in markers:
                if prerelease.startswith(marker):
                    return True
        return False

    def __str__(self):
        return self._vstring

    def __repr__(self):
        return "LooseVersion ('%s')" % str(self)

    def _cmp(self, other):
        """Rich comparison method used by the operators below"""
        if isinstance(other, str):
            other = LooseVersion(other)

        # Modified: Use string comparison for different types and fill with zeroes/empty strings
        # Based on https://bugs.python.org/issue14894
        for i, j in zip_longest(self.version, other.version):
            if i is None:
                i = 0 if isinstance(j, int) else ''
            elif j is None:
                j = 0 if isinstance(i, int) else ''
            elif not type(i) is type(j):
                i = str(i)
                j = str(j)
            if i < j:
                return -1
            if i > j:
                return 1
        return 0

    def __eq__(self, other):
        return self._cmp(other) == 0

    def __ne__(self, other):
        return self._cmp(other) != 0

    def __lt__(self, other):
        return self._cmp(other) < 0

    def __le__(self, other):
        return self._cmp(other) <= 0

    def __gt__(self, other):
        return self._cmp(other) > 0

    def __ge__(self, other):
        return self._cmp(other) >= 0
