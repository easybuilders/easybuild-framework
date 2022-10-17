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
"""
from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
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
        self.software_list = []
        self.easyconfigs = []  # A list of easyconfig names. May or may not include .eb extension
        # A dict where keys are easyconfig names, values are dictionary of options that should be
        # applied for that easyconfig
        self.ec_opts = {}

    def compose_ec_filenames(self):
        """Returns a list of all easyconfig names"""
        ec_filenames = []

        # entries specified via 'software' top-level key
        for sw in self.software_list:
            full_ec_version = det_full_ec_version({
                'toolchain': {'name': sw.toolchain_name, 'version': sw.toolchain_version},
                'version': sw.version,
                'versionsuffix': sw.versionsuffix,
            })
            ec_filename = '%s-%s.eb' % (sw.name, full_ec_version)
            ec_filenames.append(ec_filename)

        # entries specified via 'easyconfigs' top-level key
        for ec in self.easyconfigs:
            ec_filenames.append(ec)
        return ec_filenames

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

        easystack_data = None
        top_keys = ('easyconfigs', 'software')
        keys_found = []
        for key in top_keys:
            if key in easystack_raw:
                keys_found.append(key)
        # For now, we don't support mixing multiple top_keys, so check that only one was defined
        if len(keys_found) > 1:
            keys_string = ', '.join(keys_found)
            msg = "Specifying multiple top level keys (%s) " % keys_string
            msg += "in one EasyStack file is currently not supported"
            msg += ", see %s for documentation." % EASYSTACK_DOC_URL
            raise EasyBuildError(msg)
        elif len(keys_found) == 0:
            msg = "Not a valid EasyStack YAML file: no 'easyconfigs' or 'software' top-level key found"
            msg += ", see %s for documentation." % EASYSTACK_DOC_URL
            raise EasyBuildError(msg)
        else:
            key = keys_found[0]
            easystack_data = easystack_raw[key]

        parse_method_name = 'parse_by_' + key
        parse_method = getattr(EasyStackParser, 'parse_by_%s' % key, None)
        if parse_method is None:
            raise EasyBuildError("Easystack parse method '%s' not found!", parse_method_name)

        # assign general easystack attributes
        easybuild_version = easystack_raw.get('easybuild_version', None)
        robot = easystack_raw.get('robot', False)

        return parse_method(filepath, easystack_data, easybuild_version=easybuild_version, robot=robot)

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
                easystack.easyconfigs.append(easyconfig)
            elif isinstance(easyconfig, dict):
                if len(easyconfig) == 1:
                    # Get single key from dictionary 'easyconfig'
                    easyconf_name = list(easyconfig.keys())[0]
                    # Add easyconfig name to the list
                    if not easyconf_name.endswith('.eb'):
                        easyconf_name_with_eb = easyconf_name + '.eb'
                    else:
                        easyconf_name_with_eb = easyconf_name
                    easystack.easyconfigs.append(easyconf_name_with_eb)
                    # Add options to the ec_opts dict
                    if 'options' in easyconfig[easyconf_name].keys():
                        easystack.ec_opts[easyconf_name_with_eb] = easyconfig[easyconf_name]['options']
                else:
                    dict_keys = ', '.join(easyconfig.keys())
                    msg = "Failed to parse easystack file: expected a dictionary with one key (the EasyConfig name), "
                    msg += "instead found keys: %s" % dict_keys
                    msg += ", see %s for documentation." % EASYSTACK_DOC_URL
                    raise EasyBuildError(msg)

        return easystack

    @staticmethod
    def parse_by_software(filepath, software, easybuild_version=None, robot=False):
        """
        Parse easystack file with 'software' as top-level key.
        """

        easystack = EasyStack()

        # assign software-specific easystack attributes
        for name in software:
            # ensure we have a string value (YAML parser returns type = dict
            # if levels under the current attribute are present)
            check_value(name, "software name")
            try:
                toolchains = software[name]['toolchains']
            except KeyError:
                raise EasyBuildError("Toolchains for software '%s' are not defined in %s", name, filepath)
            for toolchain in toolchains:
                check_value(toolchain, "software %s" % name)

                if toolchain == 'SYSTEM':
                    toolchain_name, toolchain_version = 'system', ''
                else:
                    toolchain_parts = toolchain.split('-', 1)
                    if len(toolchain_parts) == 2:
                        toolchain_name, toolchain_version = toolchain_parts
                    elif len(toolchain_parts) == 1:
                        toolchain_name, toolchain_version = toolchain, ''
                    else:
                        raise EasyBuildError("Incorrect toolchain specification for '%s' in %s, too many parts: %s",
                                             name, filepath, toolchain_parts)

                try:
                    # if version string containts asterisk or labels, raise error (asterisks not supported)
                    versions = toolchains[toolchain]['versions']
                except TypeError as err:
                    wrong_structure_err = "An error occurred when interpreting "
                    wrong_structure_err += "the data for software %s: %s" % (name, err)
                    raise EasyBuildError(wrong_structure_err)
                if '*' in str(versions):
                    asterisk_err = "EasyStack specifications of '%s' in %s contain asterisk. "
                    asterisk_err += "Wildcard feature is not supported yet."
                    raise EasyBuildError(asterisk_err, name, filepath)

                # yaml versions can be in different formats in yaml file
                # firstly, check if versions in yaml file are read as a dictionary.
                # Example of yaml structure:
                # ========================================================================
                # versions:
                #   '2.25':
                #   '2.23':
                #     versionsuffix: '-R-4.0.0'
                # ========================================================================
                if isinstance(versions, dict):
                    for version in versions:
                        check_value(version, "%s (with %s toolchain)" % (name, toolchain_name))
                        if versions[version] is not None:
                            version_spec = versions[version]
                            if 'versionsuffix' in version_spec:
                                versionsuffix = str(version_spec['versionsuffix'])
                            else:
                                versionsuffix = ''
                            if 'exclude-labels' in str(version_spec) or 'include-labels' in str(version_spec):
                                lab_err = "EasyStack specifications of '%s' in %s "
                                lab_err += "contain labels. Labels aren't supported yet."
                                raise EasyBuildError(lab_err, name, filepath)
                        else:
                            versionsuffix = ''

                        specs = {
                            'name': name,
                            'toolchain_name': toolchain_name,
                            'toolchain_version': toolchain_version,
                            'version': version,
                            'versionsuffix': versionsuffix,
                        }
                        sw = SoftwareSpecs(**specs)

                        # append newly created class instance to the list in instance of EasyStack class
                        easystack.software_list.append(sw)
                    continue

                elif isinstance(versions, (list, tuple)):
                    pass

                # multiple lines without ':' is read as a single string; example:
                # versions:
                #   '2.24'
                #   '2.51'
                elif isinstance(versions, string_type):
                    versions = versions.split()

                # single values like '2.24' should be wrapped in a list
                else:
                    versions = [versions]

                # if version is not a dictionary, versionsuffix is not specified
                versionsuffix = ''

                for version in versions:
                    check_value(version, "%s (with %s toolchain)" % (name, toolchain_name))
                    sw = SoftwareSpecs(
                        name=name, version=version, versionsuffix=versionsuffix,
                        toolchain_name=toolchain_name, toolchain_version=toolchain_version)
                    # append newly created class instance to the list in instance of EasyStack class
                    easystack.software_list.append(sw)

            # assign general easystack attributes
            easystack.easybuild_version = easybuild_version
            easystack.robot = robot

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

    easyconfig_names = easystack.compose_ec_filenames()

    # Disabled general options for now. We weren't using them, and first want support for EasyConfig-specific options.
    # Then, we need a method to resolve conflicts (specific options should win)
    # general_options = easystack.get_general_options()

    _log.debug("EasyStack parsed. Proceeding to install these Easyconfigs: %s" % ', '.join(sorted(easyconfig_names)))
    _log.debug("Using EasyConfig specific options based on the following dict:")
    _log.debug(easystack.ec_opts)
    # if len(general_options) != 0:
    #    _log.debug("General options for installation are: \n%s" % str(general_options))
    # else:
    #    _log.debug("No general options were specified in easystack")

    return easyconfig_names, easystack.ec_opts
