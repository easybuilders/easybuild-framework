# Copyright 2020-2020 Ghent University
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
"""

from easybuild.tools.build_log import EasyBuildError
from easybuild.base import fancylogger
try:
    import yaml
except ImportError:
    pass
_log = fancylogger.getLogger('easystack', fname=False)


class Easystack(object):
    """One class instance per easystack. General options + list of all SoftwareSpecs instances"""
    def __init__(self):
        self.easybuild_version = None
        self.robot = False
        self.software_list = []

    def compose_ec_names(self):
        """Returns a list of all easyconfig names"""
        ec_filenames = []
        for sw in self.software_list:
            full_ec_version = self.det_full_ec_version({
                'toolchain': {'name': sw.toolchain_name, 'version': sw.toolchain_version},
                'version': sw.version,
                'versionsuffix': sw.versionsuffix,
            })
            ec_filename = '%s-%s.eb' % (sw.name, full_ec_version)
            ec_filenames.append(ec_filename)
        return ec_filenames

    def det_full_ec_version(self, version_specs):
        ec_version_string = '%s-%s-%s%s' % (
            version_specs['version'], version_specs['toolchain']['name'],
            version_specs['toolchain']['version'], version_specs['versionsuffix']
        )
        return ec_version_string

    # flags applicable to all sw (i.e. robot)
    def get_general_options(self):
        """Returns general options (flags applicable to all sw (i.e. --robot))"""
        general_options = {}
        # TODO add support for general_options
        # general_options['robot'] = self.robot
        # general_options['easybuild_version'] = self.easybuild_version
        return general_options


class SoftwareSpecs(object):
    """Contains information about every SW that should be installed"""
    def __init__(self, name, version, versionsuffix, toolchain, toolchain_version, toolchain_name):
        self.name = name
        self.version = version
        self.toolchain = toolchain
        self.toolchain_version = toolchain_version
        self.toolchain_name = toolchain_name
        self.toolchain = toolchain
        self.versionsuffix = versionsuffix


# implement this to your own needs - to create custom yaml/json/xml parser
class GenericEasystackParser(object):
    """Parent of all implemented parser classes"""
    @ staticmethod
    def parse(filepath):
        """Parent of all implemented parser functions (i.e. JSON, XML...)"""
        raise NotImplementedError


class YamlEasystackParser(GenericEasystackParser):
    """YAML file parser"""
    @ staticmethod
    def parse(filepath):
        """Parses YAML file and assigns obtained values to SW config instances as well as general config instance"""
        try:
            with open(filepath, 'r') as f:
                spec_dict = yaml.safe_load(f)

                eb = Easystack()
        except Exception:
            raise EasyBuildError("Could not read provided easystack.")

        try:
            sw_dict = spec_dict["software"]

            # assign software-specific EB attributes
            for software in sw_dict:
                try:
                    yaml_toolchains = sw_dict[software]['toolchains']
                except (KeyError):
                    raise EasyBuildError("Toolchains for software '%s' are not defined" % software)
                try:
                    for yaml_tc in yaml_toolchains:
                        try:
                            yaml_toolchain_name = str(yaml_tc).split('-', 1)[0]
                            yaml_toolchain_version = str(yaml_tc).split('-', 1)[1]
                        except IndexError:
                            yaml_toolchain_name = str(yaml_tc)
                            yaml_toolchain_version = ''

                        try:
                            # if version string containts asterisk or labels, raise error (asterisks not supported)
                            yaml_versions = yaml_toolchains[yaml_tc]['versions']
                        except TypeError:
                            wrong_structure_err = "Easystack specifications of '%s' ." % software
                            wrong_structure_err += "have wrong yaml structure."
                            raise EasyBuildError(wrong_structure_err)
                        if '*' in str(yaml_versions):
                            asterisk_err = "Easystack specifications of '%s' contain asterisk. " % (str(software))
                            asterisk_err += "Wildcard feature is not supported yet."
                            raise EasyBuildError(asterisk_err)

                        # yaml versions can be in different formats in yaml file
                        # firstly, check if versions in yaml file are read as a dictionary. 
                        # Example of yaml structure:
                        # ========================================================================
                        # versions:
                        #   2.25:
                        #   2.23:
                        #     versionsuffix: '-R-4.0.0'
                        # ========================================================================
                        if isinstance(yaml_versions, dict):
                            for yaml_version in yaml_versions:
                                if yaml_versions[yaml_version] is not None:
                                    yaml_ver_specs = yaml_versions[yaml_version]
                                    if 'versionsuffix' in yaml_ver_specs:
                                        yaml_versionsuffix = str(yaml_ver_specs['versionsuffix'])
                                    else:
                                        yaml_versionsuffix = ''
                                    if 'exclude-labels' in str(yaml_ver_specs) \
                                        or 'include-labels' in str(yaml_ver_specs):
                                            lab_err = "Easystack specifications of '%s' " % str(software)
                                            lab_err += "contain labels. Labels aren't supported yet."
                                            raise EasyBuildError(lab_err)
                                else:
                                    yaml_versionsuffix = ''
                                sw = SoftwareSpecs(
                                    name=software, version=yaml_version, versionsuffix = yaml_versionsuffix,
                                    toolchain=yaml_tc, toolchain_name=yaml_toolchain_name,
                                    toolchain_version=yaml_toolchain_version)
                                # append newly created class instance to the list in instance of Easystack class
                                eb.software_list.append(sw)
                            continue

                        # is format read as a list of versions?
                        # ========================================================================
                        # versions:
                        #   [2.24, 2.51]
                        # ========================================================================
                        elif isinstance(yaml_versions, list):
                            yaml_versions_list = yaml_versions

                        # format = multiple lines without ':' (read as a string)?
                        # ========================================================================
                        # versions:
                        #   2.24
                        #   2.51
                        # ========================================================================
                        elif isinstance(yaml_versions, str):
                            yaml_versions_list = str(yaml_versions).split()

                        # format read as float (containing one version only)?
                        # ========================================================================
                        # versions:
                        #   2.24
                        # ========================================================================
                        elif isinstance(yaml_versions, float):
                            yaml_versions_list = [str(yaml_versions)]

                        # if no version is a dictionary, versionsuffix isn't specified
                        yaml_versionsuffix = ''

                        for yaml_version_string in yaml_versions_list:
                            sw = SoftwareSpecs(
                                name=software, version=yaml_version_string, versionsuffix = yaml_versionsuffix,
                                toolchain=yaml_tc, toolchain_name=yaml_toolchain_name,
                                toolchain_version=yaml_toolchain_version)
                            # append newly created class instance to the list in instance of Easystack class
                            eb.software_list.append(sw)
                except (KeyError):
                    wrong_structure_err = "Easystack specifications of '%s' have wrong yaml structure." % software
                    raise EasyBuildError(wrong_structure_err)

            # assign general EB attributes
            eb.easybuild_version = spec_dict.get('easybuild_version', None)
            eb.robot = spec_dict.get('robot', False)
        except (KeyError):
            wrong_structure_file = "Provided easystack has wrong structure"
            raise EasyBuildError(wrong_structure_file)
        
        return eb


def parse_easystack(filepath):
    """Parses through easystack file, returns what EC are to be installed together with their options."""
    log_msg = "Support for easybuild-ing from multiple easyconfigs based on "
    log_msg += "information obtained from provided file (easystack) with build specifications."
    _log.experimental(log_msg)
    _log.info("Building from easystack: '%s'" % filepath)

    # class instance which contains all info about planned build
    eb = YamlEasystackParser.parse(filepath)

    easyconfig_names = eb.compose_ec_names()

    general_options = eb.get_general_options()

    _log.debug("Easystack parsed. Proceeding to install these Easyconfigs: \n'%s'" % "',\n'".join(easyconfig_names))
    if len(general_options) != 0:
        _log.debug("General options for installation are: \n%s" % str(general_options))
    else:
        _log.debug("No general options were specified in easystack")

    return easyconfig_names, general_options
