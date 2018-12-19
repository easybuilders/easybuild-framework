##
# Copyright 2016-2018 Ghent University
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
##
"""
Implementation of a categorized module naming scheme using module classes.

:author: Maxime Schmitt (University of Luxembourg)
:author: Xavier Besseron (University of Luxembourg)
"""

import os
import re

from easybuild.tools.module_naming_scheme import ModuleNamingScheme
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version

class CategorizedModuleNamingScheme(ModuleNamingScheme):
    """Class implementing the categorized module naming scheme."""

    REQUIRED_KEYS = ['name', 'version', 'versionsuffix', 'toolchain', 'moduleclass']

    def det_full_module_name(self, ec):
        """
        Determine full module name from given easyconfig, according to the thematic module naming scheme.

        :param ec: dict-like object with easyconfig parameter values (e.g. 'name', 'version', etc.)
        :return: string representing full module name, e.g.: 'biology/ABySS/1.3.4-goolf-1.4.10'
        """
        return os.path.join(ec['moduleclass'], ec['name'], det_full_ec_version(ec))

    def is_short_modname_for(self, short_modname, name):
        """
        Determine whether the specified (short) module name is a module for software with the specified name.
        Default implementation checks via a strict regex pattern, and assumes short module names are of the form:
        <name>/<version>[-<toolchain>]
        """
        modname_regex = re.compile('^[^/]+/%s/\S+$' % re.escape(name))
        res = bool(modname_regex.match(short_modname))

        tup = (short_modname, name, modname_regex.pattern, res)
        self.log.debug("Checking whether '%s' is a module name for software with name '%s' via regex %s: %s" % tup)

        return res

