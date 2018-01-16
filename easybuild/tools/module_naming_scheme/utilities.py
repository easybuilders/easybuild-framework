##
# Copyright 2009-2018 Ghent University
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
Utility functions for implementating module naming schemes.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
"""
import os
import string
from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.tools import module_naming_scheme
from easybuild.tools.module_naming_scheme import ModuleNamingScheme
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.utilities import import_available_modules

_log = fancylogger.getLogger('module_naming_scheme.utilities', fname=False)


def det_full_ec_version(ec):
    """
    Determine exact install version, based on supplied easyconfig.
    e.g. 1.2.3-goalf-1.1.0-no-OFED or 1.2.3 (for dummy toolchains)
    """

    ecver = None
    toolchain = ec.get('toolchain', {'name': DUMMY_TOOLCHAIN_NAME})

    # determine main install version based on toolchain
    if toolchain['name'] == DUMMY_TOOLCHAIN_NAME:
        ecver = ec['version']
    else:
        ecver = "%s-%s-%s" % (ec['version'], toolchain['name'], toolchain['version'])

    # prepend/append version prefix/suffix
    ecver = ''.join([x for x in [ec.get('versionprefix', ''), ecver, ec.get('versionsuffix', '')] if x])

    return ecver


def avail_module_naming_schemes():
    """
    Returns a list of available module naming schemes.
    """
    # all ModuleNamingScheme subclasses available in easybuild.tools.module_naming_scheme namespace are eligible
    import_available_modules('easybuild.tools.module_naming_scheme')

    # construct name-to-class dict of available module naming scheme
    avail_mnss = dict([(x.__name__, x) for x in get_subclasses(ModuleNamingScheme)])

    return avail_mnss


def is_valid_module_name(mod_name):
    """Check whether the specified value is a valid module name."""
    # module name must be a string
    if not isinstance(mod_name, basestring):
        _log.warning("Wrong type for module name %s (%s), should be a string" % (mod_name, type(mod_name)))
        return False
    # module name must be relative path
    elif mod_name.startswith(os.path.sep):
        _log.warning("Module name (%s) should be a relative file path" % mod_name)
        return False
    # module name should not be empty
    elif not len(mod_name) > 0:
        _log.warning("Module name (%s) should have length > 0." % mod_name)
        return False
    else:
        # check whether module name only contains printable characters, since it's used as a filename
        # (except for carriage-control characters \r, \x0b and \xoc)
        invalid_chars = [x for x in mod_name if x not in string.printable or x in '\r\x0b\x0c']
        if len(invalid_chars) > 0:
            _log.warning("Module name %s contains invalid characters: %s" % (mod_name, invalid_chars))
            return False
    _log.debug("Module name %s validated" % mod_name)
    return True


def det_hidden_modname(modname):
    """Determine the hidden equivalent of the specified module name."""
    moddir = os.path.dirname(modname)
    modfile = os.path.basename(modname)
    return os.path.join(moddir, '.%s' % modfile).lstrip(os.path.sep)
