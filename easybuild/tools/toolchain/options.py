##
# Copyright 2012 Stijn De Weirdt
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
"""
The toolchain options module contains the ToolchainOptions class
    These are the options that can be passed to the toolchain through the easyconfig files

Map values can be string with named templates
    By default following named options is filled
        %(opt)s : option name
        %(value)s : option value
"""

from vsc.fancylogger import getLogger



class ToolchainOptions(dict):
    def __init__(self):
        self._log = getLogger(self.__class__.__name__)

        self.map = {}  # map between options name and value
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
        self.log.debug("_add_options: adding options %s" % options)
        for name, value in options.items():
            if not isinstance(value, (list, tuple,)) and len(value) == 2:
                self.log.raiseException("_add_options: option name %s has to be 2 element list (%s)" % (name, value))
            if name in self:
                self.log.debug("_add_options: redefining previous name %s (prev value %s)" % (name, self.get(name)))
            self.__setitem__(name, value[0])
            self.description.__setitem__(name, value[1])

    def _add_options_map(self, options_map):
        for name in options_map.keys():
            if not name in self:
                self.log.raiseException("_add_options_map: no option with name %s defined" % name)

        self.map.update(options_map)

    def option(self, name, templatedict=None):
        """Return option value"""
        value = self.get(name, None)
        if value is None:
            self.log.warning("option: option with name %s returns None" % name)
            res = None
        elif name in self.map:
            res = self.map[name]

            if isinstance(res, str):
                ## allow for template
                if templatedict is None:
                    templatedict = {}
                templatedict.update({'opt':name,
                                     'value':value,
                                     })
                res = self.map[name] % templatedict
            else:
                ## check if True?
                res = self.map[name]
        else:
            res = value

        return res


if __name__ == '__main__':
    to = ToolchainOptions()
