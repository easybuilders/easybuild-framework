# #
# Copyright 2013-2026 Ghent University
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
# #

"""
Dictionary wrapper factory that handles deprecated and replaced keys gracefully, and logs a warning when they are used.
Authors:

* Stijn De Weirdt (Ghent University)
* Kenneth Hoste (Ghent University)
* Alexander Grund (TU Dresden)
"""

from typing import Dict, Optional, Tuple, Type

from easybuild.base import fancylogger

_log = fancylogger.getLogger('DeprecatedDict', fname=False)


def make_deprecated_dict_class(deprecated_keys: Optional[Dict[str, Tuple[str, str]]] = None,
                               alternative_keys: Optional[Dict[str, str]] = None,
                               key_description: Optional[str] = None) -> Type[dict]:
    """Factory function to create a DeprecatedDict class with specific deprecated and alternative constants

    :param: deprecated_keys: Dictionary mapping deprecated keys to a tuple of (new_key, version)
    :param: alternative_keys: Dictionary mapping alternative keys to their corresponding new keys
    :param: key_description: Description of the type of keys (for logging purposes)
    """
    if not deprecated_keys and not alternative_keys:
        raise ValueError("At least one of 'deprecated_keys' or 'alternative_keys' must be provided")
    if deprecated_keys is None:
        deprecated_keys = {}
    if alternative_keys is None:
        alternative_keys = {}
    if key_description is None:
        key_description = "Key"

    def handle_deprecated_keys(method):
        """Decorator to handle deprecated/replaced keys"""
        def wrapper(self, key, *args, **kwargs):
            """Check whether any deprecated key is used"""
            if key in alternative_keys:
                key = alternative_keys[key]
            elif key in deprecated_keys:
                new_key, version = deprecated_keys[key]
                _log.deprecated(f"{key_description} '{key}' is deprecated, use '{new_key}' instead", version)
                key = new_key
            return method(self, key, *args, **kwargs)
        return wrapper

    class DeprecatedDict(dict):
        """Custom dictionary that handles deprecated/replaced keys gracefully"""

        def __init__(self, *args, **kwargs):
            super().__init__()
            self.update(*args, **kwargs)

        @handle_deprecated_keys
        def __contains__(self, key):
            return super().__contains__(key)

        @handle_deprecated_keys
        def __delitem__(self, key):
            return super().__delitem__(key)

        @handle_deprecated_keys
        def __getitem__(self, key):
            return super().__getitem__(key)

        @handle_deprecated_keys
        def __setitem__(self, key, value):
            return super().__setitem__(key, value)

        @handle_deprecated_keys
        def get(self, key, default=None):
            return super().get(key, default)

        def update(self, *args, **kwargs):
            if args:
                if len(args) > 1:
                    raise TypeError(f"update expected at most 1 argument, got {len(args)}")
                other = args[0]
                if isinstance(other, dict):
                    for key, value in other.items():
                        self[key] = value
                else:
                    for key, value in other:
                        self[key] = value
            for key, value in kwargs.items():
                self[key] = value

    return DeprecatedDict
