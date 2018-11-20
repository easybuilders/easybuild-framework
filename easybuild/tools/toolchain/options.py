# #
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
# #
"""
The toolchain options module contains the ToolchainOptions class
    These are the options that can be passed to the toolchain through the easyconfig files

Map values can be string with named templates
    By default following named options is filled
        %(opt)s : option name
        %(value)s : option value

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""

from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError


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
        if not options is None:
            self._add_options(options)

        if not options_map is None:
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
            if not name in self:
                if name.startswith('_opt_'):
                    self.log.devel("_add_options_map: no option with name %s defined, but allowed", name)
                else:
                    raise EasyBuildError("No toolchain option with name %s defined", name)

        self.options_map.update(options_map)

    def option(self, name, templatedict=None):
        """Return option value"""
        value = self.get(name, None)
        if value is None and name not in self.options_map:
            self.log.warning("option: option with name %s returns None" % name)
            res = None
        elif name in self.options_map:
            res = self.options_map[name]

            if templatedict is None:
                templatedict = {}
            templatedict.update({
                                 'opt':name,
                                 'value':value,
                                })

            if isinstance(res, basestring):
                # allow for template
                res = self.options_map[name] % templatedict
            elif isinstance(res, (list, tuple,)):
                # allow for template per element
                res = self.options_map[name]
                for i in xrange(0, len(res)):
                    res[i] = res[i] % templatedict
            else:
                # check if True?
                res = self.options_map[name]
        else:
            res = value

        return res
