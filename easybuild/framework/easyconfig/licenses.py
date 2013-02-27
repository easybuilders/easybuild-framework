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

_log = fancylogger.getLogger('easyconfig.licenses', fname=False)

class EB_License(object):
    """EasyBuild easyconfig license class"""
    HIDDEN = False  # disable subclasses from being seen/used
    NAME=None
    VERSION=None
    DESCRIPTION=None

    DISTRIBUTE_SOURCE = False    # does the license allows to (re)distribute the code
    GROUP_SOURCE = True  # does the license require to keep the source under dedicated group
    GROUP_BINARY = True  # does the license require to install the binaries under dedicated group

    def __init__(self):
        if self.NAME is None:
            name=self.__class__.__name__
            if name.startswith('EB_'):
                name = name[3:]
        else:
            name=self.NAME
        self.name = name
        self.version = self.VERSION
        self.description= self.DESCRIPTION
        self.distribute_source = self.DISTRIBUTE_SOURCE
        self.group_source = self.GROUP_SOURCE
        self.group_binary = self.GROUP_BINARY

class EB_OpenLicense(EB_License):
    HIDDEN = True
    DISTRIBUTE_SOURCE = True
    GROUP_SOURCE = False
    GROUP_BINARY = False

class EB_GPL(EB_OpenLicense):
    DESCRIPTION = ("The GNU General Public License is a free, "
                   "copyleft license for software and other kinds of works.")

class EB_GPLv2(EB_GPL):
    HIDDEN = False
    VERSION=2

class EB_GPLv3(EB_GPLv2):
    VERSION=3


def get_subclasses(klass):
    """Get all subclasses recursively"""
    res = []
    for cl in klass.__subclasses__():
        res.extend(get_subclasses(cl))
        res.append(cl)
    return res


def what_licenses():
    """Return a dict of EB_License subclasses names and license instances"""
    res = {}
    for lic in get_subclasses(EB_License):
        if lic.HIDDEN:
            continue
        lic_instance = lic()
        res[lic_instance.name] = lic_instance

    return res


EASYCONFIG_LICENSES_DICT = what_licenses()
EASYCONFIG_LICENSES = EASYCONFIG_LICENSES_DICT.keys()


def license_documentation():
    """Generate the easyconfig licenses documentation"""
    indent_l0 = " "*2
    indent_l1 = indent_l0 + " "*2
    doc = []

    doc.append("Constants that can be used in easyconfigs")
    for lic in EASYCONFIG_LICENSES:
        doc.append('%s%s: %s (version %s)' % (indent_l1, lic, EASYCONFIG_LICENSES_DICT[lic].description,
                                              EASYCONFIG_LICENSES_DICT[lic].version))

    return "\n".join(doc)

