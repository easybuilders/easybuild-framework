##
# Copyright 2013-2014 Ghent University
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
##
"""
Implementation of a test module naming scheme.

@author: Kenneth Hoste (Ghent University)
"""

import os
from vsc.utils import fancylogger

from easybuild.framework.easyconfig.default import DEFAULT_CONFIG
from easybuild.tools.module_naming_scheme import ModuleNamingScheme
from easybuild.tools.ordereddict import OrderedDict

# prefer hashlib.sha1 (only in Python 2.5 and up) over sha.sha
try:
    from hashlib import sha1
except ImportError:
    from sha import sha as sha1


_log = fancylogger.getLogger('TestModuleNamingSchemeAll', fname=False)


class TestModuleNamingSchemeAll(ModuleNamingScheme):
    """Class implementing a module naming scheme that uses all available easyconfig parameters, for testing purposes."""

    def det_full_module_name(self, ec):
        """
        Determine full module name from given easyconfig, according to a testing module naming scheme,
        using all available easyconfig parameters.

        @param ec: dict-like object with easyconfig parameter values (e.g. 'name', 'version', etc.)

        @return: string with full module name, e.g.: ('gzip', '1.5'), ('intel', 'intelmpi', 'gzip', '1.5')
        """
        res = ''
        for key in sorted(DEFAULT_CONFIG.keys()):
            if isinstance(ec[key], dict):
                res += '%s=>' % key
                for item_key in sorted(ec[key].keys()):
                    res += '%s:%s,' % (item_key, ec[key][item_key])
            else:
                res += str(ec[key])
        ec_sha1 = sha1(res).hexdigest()
        _log.debug("SHA1 for string '%s' obtained for %s: %s" % (res, ec, ec_sha1))
        return os.path.join(ec['name'], ec_sha1)
