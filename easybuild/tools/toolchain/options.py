# #
# Copyright 2012-2024 Ghent University
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
The toolchain options module contains the ToolchainOptions class
    These are the options that can be passed to the toolchain through the easyconfig files

Map values can be string with named templates
    By default following named options is filled
        %(opt)s : option name
        %(value)s : option value

Authors:

* Stijn De Weirdt (Ghent University)
* Kenneth Hoste (Ghent University)
"""

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError

# alternative toolchain options, and their non-deprecated equivalents
ALTERNATIVE_TOOLCHAIN_OPTIONS = {
    # <new_param>: <equivalent_param>,
}

# deprecated toolchain options, and their replacements
DEPRECATED_TOOLCHAIN_OPTIONS = {
    # <old_param>: (<new_param>, <deprecation_version>),
}


def handle_deprecated_and_alternative_toolchain_options(tc_method):
    """Decorator to handle deprecated/alternative toolchain options."""

    def new_tc_method(self, key, *args, **kwargs):
        """Check whether any deprecated/alternative toolchain options are used."""

        if key in ALTERNATIVE_TOOLCHAIN_OPTIONS:
            key = ALTERNATIVE_TOOLCHAIN_OPTIONS[key]
        elif key in DEPRECATED_TOOLCHAIN_OPTIONS:
            depr_key = key
            key, ver = DEPRECATED_TOOLCHAIN_OPTIONS[depr_key]
            self.log.deprecated(f"Toolchain option '{depr_key}' is deprecated, use '{key}' instead", ver)

        return tc_method(self, key, *args, **kwargs)

    return new_tc_method


class ToolchainOptions(dict):
    def __init__(self):
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.options_map = {}  # map between options name and value
        self.description = {}  # short description of the options

    def add_options(self, options=None, options_map=None):
        """Add
            @options: dict with options : tuple option_name and option_description
            @options_map: dict with a mapping between and option and a value
        """
        if options is not None:
            self._add_options(options)

        if options_map is not None:
            self._add_options_map(options_map)

    def _add_options(self, options):
        """Add actual options dict to self"""
        self.log.debug("Using toolchain options %s", options)
        for name, value in options.items():
            if not isinstance(value, (list, tuple,)) and len(value) == 2:
                raise EasyBuildError("_add_options: option name %s has to be 2 element list (%s)", name, value)
            if name in self:
                self.log.devel("_add_options: redefining previous name %s (previous value %s)", name, self.get(name))
            self.__setitem__(name, value[0])
            self.description.__setitem__(name, value[1])

    def _add_options_map(self, options_map):
        """Add map dict between options and values
            map names starting with _opt_ are allowed without corresponding option
        """
        for name in options_map.keys():
            if name not in self:
                if name.startswith('_opt_'):
                    self.log.devel("_add_options_map: no option with name %s defined, but allowed", name)
                else:
                    raise EasyBuildError("No toolchain option with name %s defined", name)

        self.options_map.update(options_map)

    @handle_deprecated_and_alternative_toolchain_options
    def __contains__(self, key):
        return super().__contains__(key)

    @handle_deprecated_and_alternative_toolchain_options
    def __delitem__(self, key):
        return super().__delitem__(key)

    @handle_deprecated_and_alternative_toolchain_options
    def __getitem__(self, key):
        return super().__getitem__(key)

    @handle_deprecated_and_alternative_toolchain_options
    def __setitem__(self, key, value):
        return super().__setitem__(key, value)

    def update(self, *args, **kwargs):
        if args:
            if isinstance(args[0], dict):
                for key, value in args[0].items():
                    self.__setitem__(key, value)
            else:
                for key, value in args[0]:
                    self.__setitem__(key, value)

        for key, value in kwargs.items():
            self.__setitem__(key, value)

    def option(self, name, templatedict=None):
        """Return option value"""
        value = self.get(name, None)
        if value is None and name not in self.options_map:
            msg = "option: option with name %s returns None" % name
            # Empty options starting with _opt_ are allowed, so don't warn
            if name.startswith('_opt_'):
                self.log.devel(msg)
            else:
                self.log.warning(msg)
            res = None
        elif name in self.options_map:
            res = self.options_map[name]

            if templatedict is None:
                templatedict = {}
            templatedict.update({
                'opt': name,
                'value': value,
            })

            if isinstance(res, str):
                # allow for template
                res = self.options_map[name] % templatedict
            elif isinstance(res, (list, tuple,)):
                # allow for template per element
                res = self.options_map[name]
                for idx, elem in enumerate(res):
                    res[idx] = elem % templatedict
            else:
                # check if True?
                res = self.options_map[name]
        else:
            res = value

        return res
