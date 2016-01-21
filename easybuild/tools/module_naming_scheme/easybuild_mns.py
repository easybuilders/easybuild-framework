##
# Copyright 2013-2015 Ghent University
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
Implementation of (default) EasyBuild module naming scheme.

@author: Kenneth Hoste (Ghent University)
"""
import copy
import os

from easybuild.framework.easyconfig.easyconfig import robot_find_easyconfig
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.module_naming_scheme import ModuleNamingScheme
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME, DUMMY_TOOLCHAIN_VERSION
from easybuild.tools.toolchain.utilities import search_toolchain


class EasyBuildMNS(ModuleNamingScheme):
    """Class implementing the default EasyBuild module naming scheme."""

    REQUIRED_KEYS = ['name', 'version', 'versionsuffix', 'toolchain']

    def det_full_module_name(self, ec):
        """
        Determine full module name from given easyconfig, according to the EasyBuild module naming scheme.

        @param ec: dict-like object with easyconfig parameter values (e.g. 'name', 'version', etc.)

        @return: string with full module name <name>/<installversion>, e.g.: 'gzip/1.5-goolf-1.4.10'
        """
        return os.path.join(ec['name'], det_full_ec_version(ec))

    def parse_full_module_name(self, mod_name):
        """
        Parse specified full module name into list of possible matching name/version/versionsuffix/toolchain specs.

        @param mod_name: full module name to parse
        @return: list of dictionaries with possible matching specs
        """
        res = []
        specs = {
            'name': None,
            'toolchain': {'name': None, 'version': None},
            'version': None,
            'versionsuffix': None,
        }

        # expected format is <name>/<version>-[<toolchain_name>-<toolchain_version>][-<versionsuffix>]
        mod_name_parts = mod_name.split('/')

        # split name and install version
        # ASSUMPTION: no '/' in software name
        name = mod_name_parts[0]
        installver = '/'.join(mod_name_parts[1:])
        installver_parts = installver.split('-')

        specs['name'] = name

        # <name>/<version> is the bare minumum
        if len(mod_name_parts) < 2:
            self.log.debug("Specified module name '%s' has fewer parts than expected: %s", mod_name, mod_name_parts)

        # ASSUMPTION: versionsuffix starts with '-'
        elif len(installver_parts) <= 2:
            # no toolchain => dummy toolchain
            specs['version'] = installver_parts[0]
            specs['toolchain']['name'] = DUMMY_TOOLCHAIN_NAME
            specs['toolchain']['version'] = DUMMY_TOOLCHAIN_VERSION
            if len(installver_parts) == 1:
                # version only, no versionsuffix
                specs['versionsuffix'] = ''
            else:
                # version + versionsuffix
                specs['versionsuffix'] = '-' + installver_parts[1]

            derived_mod_name = self.det_full_module_name(specs)
            if mod_name == derived_mod_name:
                res.append(specs)
            else:
                raise EasyBuildError("Parsing full module naming unexpectedly failed: '%s' vs '%s'",
                                     mod_name, derived_mod_name)

        else:
            # try and find toolchain name first, can be used as an anchor point
            # ASSUMPTION: no '-' in toolchain name
            _, all_tcs = search_toolchain('')
            all_tcs_names = [x.NAME for x in all_tcs]

            tcname_index = None
            for i, pot_tcname in enumerate(installver_parts):
                if pot_tcname in all_tcs_names:
                    tcname_index = i
                    break

            # derive information we can from obtained index for toolchain name
            if tcname_index is None:
                # no toolchain name found => dummy toolchain
                specs['toolchain']['name'] = DUMMY_TOOLCHAIN_NAME
                specs['toolchain']['version'] = DUMMY_TOOLCHAIN_VERSION

            elif tcname_index > 0:
                # toolchain name found => software version (and toolchain name) known
                specs['version'] = '-'.join(installver_parts[:tcname_index])
                specs['toolchain']['name'] = installver_parts[tcname_index]
                installver_parts = installver_parts[tcname_index+1:]

            else:
                # no software version?!
                raise EasyBuildError("Toolchain name found as first part of install version, software version missing?")

            # potentially still unknown: software version, toolchain version, versionsuffix
            orig_specs = copy.deepcopy(specs)
            derived_mod_name = self.det_full_module_name(specs)
            split_indices = (1, 2)
            while split_indices[0] <= len(installver_parts):
                # restore correctly derived specs until now
                specs = copy.deepcopy(orig_specs)

                start_index, end_index = 0, split_indices[0]
                if specs['version'] is None:
                    specs['version'] = '-'.join(installver_parts[:end_index])
                    start_index, end_index = end_index, split_indices[1]
                if specs['toolchain']['version'] is None:
                    specs['toolchain']['version'] = '-'.join(installver_parts[start_index:end_index])
                    start_index = end_index
                if installver_parts[start_index:]:
                    # ASSUMPTION: versionsuffix starts with '-'
                    specs['versionsuffix'] = '-' + '-'.join(installver_parts[start_index:])
                    end_index = len(installver_parts)
                else:
                    specs['versionsuffix'] = ''

                derived_mod_name = self.det_full_module_name(specs)
                if mod_name == derived_mod_name:
                    res.append(specs)

                # move along to try new version/toolchain version/versionsuffix split
                if end_index < len(installver_parts):
                    split_indices = (split_indices[0], split_indices[1] + 1)
                else:
                    split_indices = (split_indices[0] + 1, split_indices[0] + 2)

        return res
