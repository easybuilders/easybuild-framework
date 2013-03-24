#
# Copyright 2013-2013 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
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
#

"""
Easyconfig licenses module that provides all licenses that can
be used within an Easyconfig file.

@author: Stijn De Weirdt (Ghent University)
"""

from vsc import fancylogger
from vsc.utils.missing import get_subclasses

_log = fancylogger.getLogger('easyconfig.licenses', fname=False)


class License(object):
    """EasyBuild easyconfig license class"""
    HIDDEN = False  # disable subclasses from being seen/used
    NAME = None
    VERSION = None
    DESCRIPTION = None

    DISTRIBUTE_SOURCE = False  # does the license allows to (re)distribute the code
    GROUP_SOURCE = True  # does the license require to keep the source under dedicated group
    GROUP_BINARY = True  # does the license require to install the binaries under dedicated group

    CLASSNAME_PREFIX = 'License_'

    def __init__(self):
        if self.NAME is None:
            name = self.__class__.__name__
            if name.startswith(self.CLASSNAME_PREFIX):
                name = name[len(self.CLASSNAME_PREFIX):]
        else:
            name = self.NAME
        self.name = name
        self.version = self.VERSION
        self.description = self.DESCRIPTION
        self.distribute_source = self.DISTRIBUTE_SOURCE
        self.group_source = self.GROUP_SOURCE
        self.group_binary = self.GROUP_BINARY


class License_Open(License):
    """
    Hidden license class to subclass open licenses.
    'Open' here means, that source can be redistributed, and that both source
    and binaries do not need special groups (ie anyone can access/use it).
    """
    HIDDEN = True
    DISTRIBUTE_SOURCE = True
    GROUP_SOURCE = False
    GROUP_BINARY = False


class License_GPL(License_Open):
    """
    Hidden license class to subclass GPL licenses.
    """
    DESCRIPTION = ("The GNU General Public License is a free, "
                   "copyleft license for software and other kinds of works.")


class License_GPLv2(License_GPL):
    """GPLv2 license"""
    HIDDEN = False
    VERSION = (2,)


class License_GPLv3(License_GPLv2):
    """GPLv3 license"""
    VERSION = (3,)


def what_licenses():
    """Return a dict of License subclasses names and license instances"""
    res = {}
    for lic in get_subclasses(License):
        if lic.HIDDEN:
            continue
        lic_instance = lic()
        res[lic_instance.name] = lic_instance

    return res


EASYCONFIG_LICENSES_DICT = what_licenses()
EASYCONFIG_LICENSES = EASYCONFIG_LICENSES_DICT.keys()


def license_documentation():
    """Generate the easyconfig licenses documentation"""
    indent_l0 = " " * 2
    indent_l1 = indent_l0 + " " * 2
    doc = []

    doc.append("Constants that can be used in easyconfigs")
    for lic_name, lic in EASYCONFIG_LICENSES_DICT.items():
        doc.append('%s%s: %s (version %s)' % (indent_l1, lic_name, lic.description, lic.version))

    return "\n".join(doc)

