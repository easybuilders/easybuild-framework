#
# Copyright 2013-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
@author: Kenneth Hoste (Ghent University)
"""

from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses


_log = fancylogger.getLogger('easyconfig.licenses', fname=False)


class License(object):
    """EasyBuild easyconfig license class
        This is also the default restrictive license
    """
    HIDDEN = False  # disable subclasses from being seen/used
    NAME = None
    VERSION = None
    DESCRIPTION = None

    DISTRIBUTE_SOURCE = False  # does the license allows to (re)distribute the code
    GROUP_SOURCE = True  # does the license require to keep the source under dedicated group
    GROUP_BINARY = True  # does the license require to install the binaries under dedicated group

    CLASSNAME_PREFIX = 'License'

    @property
    def name(self):
        """Return license name."""
        if self.NAME is None:
            name = self.__class__.__name__
            if name.startswith(self.CLASSNAME_PREFIX):
                name = name[len(self.CLASSNAME_PREFIX):]
        else:
            name = self.NAME

        return name

    def __init__(self):
        """License constructor."""
        self.version = self.VERSION
        self.description = self.DESCRIPTION
        self.distribute_source = self.DISTRIBUTE_SOURCE
        self.group_source = self.GROUP_SOURCE
        self.group_binary = self.GROUP_BINARY


class LicenseVeryRestrictive(License):
    """Default license should be very restrictive, so nothing to do here, just a placeholder"""
    pass


class LicenseUnknown(LicenseVeryRestrictive):
    """A (temporary) license, could be used as default in case nothing was specified"""
    pass


# inspiration
# http://en.wikipedia.org/wiki/Category:Free_and_open-source_software_licenses

class LicenseOpen(License):
    """
    Hidden license class to subclass open licenses.
    'Open' here means, that source can be redistributed, and that both source
    and binaries do not need special groups (ie anyone can access/use it).
    """
    HIDDEN = True
    DISTRIBUTE_SOURCE = True
    GROUP_SOURCE = False
    GROUP_BINARY = False


class LicenseGPL(LicenseOpen):
    """
    Hidden license class to subclass GPL licenses.
    """
    DESCRIPTION = ("The GNU General Public License is a free, "
                   "copyleft license for software and other kinds of works.")


class LicenseGPLv2(LicenseGPL):
    """GPLv2 license"""
    HIDDEN = False
    VERSION = (2,)


class LicenseGPLv3(LicenseGPLv2):
    """GPLv3 license"""
    VERSION = (3,)


class LicenseGCC(LicenseGPLv3):
    """GPLv3 with GCC Runtime Library Exception.
        Latest GPLv2 GCC release was 4.2.1 (http://gcc.gnu.org/ml/gcc-announce/2007/msg00003.html).
    """
    DESCRIPTION = ("The GNU General Public License is a free, "
                   "copyleft license for software and other kinds of works. "
                   "The GCC Runtime Library Exception is an additional permission "
                   "under section 7 of the GNU General Public License, version 3.")


class LicenseGCCOld(LicenseGPLv2):
    """GPLv2 with GCC Runtime Library Exception for older GCC versions.
        Latest GPLv2 GCC release was 4.2.1 (http://gcc.gnu.org/ml/gcc-announce/2007/msg00003.html).
    """
    DESCRIPTION = LicenseGCC.DESCRIPTION


class LicenseZlib(LicenseOpen):
    """The zlib License is a permissive free software license 
        http://www.zlib.net/zlib_license.html
    """
    DESCRIPTION = ("Permission is granted to anyone to use this software for any purpose,"
                   " including commercial applications, and to alter it and redistribute it"
                   " freely, subject to 3 restrictions;"
                   " http://www.zlib.net/zlib_license.html for full license")


class LicenseLibpng(LicenseOpen):
    """The PNG license is derived from the zlib license, 
        http://libpng.org/pub/png/src/libpng-LICENSE.txt
    """
    HIDDEN = False
    DESCRIPTION = ("Permission is granted to use, copy, modify, and distribute the "
                   "source code, or portions hereof, for any purpose, without fee, subject "
                   "to 3 restrictions; http://libpng.org/pub/png/src/libpng-LICENSE.txt for full license")


def what_licenses():
    """Return a dict of License subclasses names and license instances"""
    res = {}
    for lic in get_subclasses(License):
        if lic.HIDDEN:
            continue
        res[lic.__name__] = lic

    return res


EASYCONFIG_LICENSES_DICT = what_licenses()


def license_documentation():
    """Generate the easyconfig licenses documentation"""
    indent_l0 = ' ' * 2
    indent_l1 = indent_l0 + ' ' * 2
    doc = []

    doc.append("Constants that can be used in easyconfigs")
    for lic_name, lic in EASYCONFIG_LICENSES_DICT.items():
        lic_inst = lic()
        strver = ''
        if lic_inst.version:
            strver = " (version: %s)" % '.'.join([str(d) for d in lic_inst.version])
        doc.append("%s%s: %s%s" % (indent_l1, lic_inst.name, lic_inst.description, strver))

    return '\n'.join(doc)
