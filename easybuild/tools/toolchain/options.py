##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
# Copyright 2012 Toon Willems
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

from vsc.fancylogger import getLogger
import os


class Options(dict):
    def __init__(self, *args, **kwargs):
        super(Options, self).__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)
        self.map = {}

    def update_map(self, option_map):
        ## sanity check: do all options from the optionmap have a corresponding entry in opts
        ## - reverse is not necessarily an issue
        for k in option_map.keys():
            if not k in self:
                self.log.raiseException("update_map: entry %s in option_map has no option with that name" % k)

        self.map.update(option_map)

    def option(self, name, templatedict=None):
        """Return option value"""
        opt = self.get(name, None)
        if opt is None:
            self.log.warning("_get_compiler_option: opt with name %s returns None" % name)
            res = None
        elif isinstance(opt, bool):
            ## check if True?
            res = self.map[name]
        else:
            ## allow for template
            if templatedict is None:
                templatedict = {'opt':opt}
            res = self.map[name] % templatedict

        return res
