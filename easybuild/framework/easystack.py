# Copyright 2020-2022 Ghent University
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
#
"""
Support for easybuild-ing from multiple easyconfigs based on
information obtained from provided file (easystack) with build specifications.

:author: Denis Kristak (Inuits)
:author: Pavel Grochal (Inuits)
:author: Kenneth Hoste (HPC-UGent)
:author: Caspar van Leeuwen (SURF)
"""
import pprint

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file
from easybuild.tools.py2vs3 import string_type
from easybuild.tools.utilities import only_if_module_is_available
try:
    import yaml
except ImportError:
    pass
_log = fancylogger.getLogger('easystack', fname=False)

EASYSTACK_DOC_URL = 'https://docs.easybuild.io/en/latest/Easystack-files.html'


def check_value(value, context):
    """
    Check whether specified value obtained from a YAML file in specified context represents is valid.
    The value must be a string (not a float or an int).
    """
    if not isinstance(value, string_type):
        error_msg = '\n'.join([
            "Value %(value)s (of type %(type)s) obtained for %(context)s is not valid!",
            "Make sure to wrap the value in single quotes (like '%(value)s') to avoid that it is interpreted "
            "by the YAML parser as a non-string value.",
        ])
        format_info = {
            'context': context,
            'type': type(value),
            'value': value,
        }
        raise EasyBuildError(error_msg % format_info)


class EasyStack(object):
    """One class instance per easystack. General options + list of all SoftwareSpecs instances"""

    def __init__(self):
        self.easybuild_version = None
        self.robot = False
        self.ec_opt_tuples = []  # A list of tuples (easyconfig_name, eaysconfig_specific_opts)

    def __str__(self):
        """
        Pretty printing of an EasyStack instance
        """
        return pprint.pformat(self.ec_opt_tuples)

    # flags applicable to all sw (i.e. robot)
    def get_general_options(self):
        """Returns general options (flags applicable to all sw (i.e. --robot))"""
        general_options = {}
        # TODO add support for general_options
        # general_options['robot'] = self.robot
        # general_options['easybuild_version'] = self.easybuild_version
        return general_options


class SoftwareSpecs(object):
    """Contains information about every software that should be installed"""

    def __init__(self, name, version, versionsuffix, toolchain_version, toolchain_name):
        self.name = name
        self.version = version
        self.toolchain_version = toolchain_version
        self.toolchain_name = toolchain_name
        self.versionsuffix = versionsuffix


class EasyStackParser(object):
    """Parser for easystack files (in YAML syntax)."""

    @staticmethod
    def parse(filepath):
        """
        Parses YAML file and assigns obtained values to SW config instances as well as general config instance"""
        yaml_txt = read_file(filepath)

        try:
            easystack_raw = yaml.safe_load(yaml_txt)
        except yaml.YAMLError as err:
            raise EasyBuildError("Failed to parse %s: %s" % (filepath, err))

        key = 'easyconfigs'
        if key in easystack_raw:
            easystack_data = easystack_raw[key]
            if isinstance(easystack_data, dict) or isinstance(easystack_data, str):
                datatype = 'dict' if isinstance(easystack_data, dict) else 'str'
                msg = '\n'.join([
                    "Found %s value for '%s' in %s, should be list." % (datatype, key, filepath),
                    "Make sure you use '-' to create list items under '%s', for example:" % key,
                    "    easyconfigs:",
                    "        - example-1.0.eb",
                    "        - example-2.0.eb:",
                    "            options:"
                    "              ...",
                ])
                raise EasyBuildError(msg)
            elif not isinstance(easystack_data, list):
                raise EasyBuildError("Value type for '%s' in %s should be list, found %s",
                                     key, filepath, type(easystack_data))
        else:
            raise EasyBuildError("Top-level key '%s' missing in easystack file %s", key, filepath)

        # assign general easystack attributes
        easybuild_version = easystack_raw.get('easybuild_version', None)
        robot = easystack_raw.get('robot', False)

        return EasyStackParser.parse_by_easyconfigs(filepath, easystack_data,
                                                    easybuild_version=easybuild_version, robot=robot)

    @staticmethod
    def parse_by_easyconfigs(filepath, easyconfigs, easybuild_version=None, robot=False):
        """
        Parse easystack file with 'easyconfigs' as top-level key.
        """

        easystack = EasyStack()

        for easyconfig in easyconfigs:
            if isinstance(easyconfig, str):
                if not easyconfig.endswith('.eb'):
                    easyconfig = easyconfig + '.eb'
                easystack.ec_opt_tuples.append((easyconfig, None))
            elif isinstance(easyconfig, dict):
                if len(easyconfig) == 1:
                    # Get single key from dictionary 'easyconfig'
                    easyconf_name = list(easyconfig.keys())[0]
                    # Add easyconfig name to the list
                    if not easyconf_name.endswith('.eb'):
                        easyconf_name_with_eb = easyconf_name + '.eb'
                    else:
                        easyconf_name_with_eb = easyconf_name
                    # Get options
                    ec_dict = easyconfig[easyconf_name] or {}

                    # make sure only 'options' key is used (for now)
                    if any(x != 'options' for x in ec_dict):
                        msg = "Found one or more invalid keys for %s (only 'options' supported): %s"
                        raise EasyBuildError(msg, easyconf_name, ', '.join(sorted(ec_dict.keys())))

                    opts = ec_dict.get('options')
                    easystack.ec_opt_tuples.append((easyconf_name_with_eb, opts))
                else:
                    dict_keys = ', '.join(sorted(easyconfig.keys()))
                    msg = "Failed to parse easystack file: expected a dictionary with one key (the EasyConfig name), "
                    msg += "instead found keys: %s" % dict_keys
                    msg += ", see %s for documentation." % EASYSTACK_DOC_URL
                    raise EasyBuildError(msg)

        return easystack


@only_if_module_is_available('yaml', pkgname='PyYAML')
def parse_easystack(filepath):
    """Parses through easystack file, returns what EC are to be installed together with their options."""
    log_msg = "Support for easybuild-ing from multiple easyconfigs based on "
    log_msg += "information obtained from provided file (easystack) with build specifications."
    _log.experimental(log_msg)
    _log.info("Building from easystack: '%s'" % filepath)

    # class instance which contains all info about planned build
    easystack = EasyStackParser.parse(filepath)

    # Disabled general options for now. We weren't using them, and first want support for EasyConfig-specific options.
    # Then, we need a method to resolve conflicts (specific options should win)
    # general_options = easystack.get_general_options()

    _log.debug("Parsed easystack:\n%s" % easystack)

#    _log.debug("Using EasyConfig specific options based on the following dict:")
#    _log.debug(easystack.ec_opts)
    # if len(general_options) != 0:
    #    _log.debug("General options for installation are: \n%s" % str(general_options))
    # else:
    #    _log.debug("No general options were specified in easystack")

    return easystack
