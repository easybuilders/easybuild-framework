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
        ec_names = []
        for sw in self.software_list:
            ec_to_append = '%s-%s-%s-%s.eb' % (str(sw.software), str(sw.version),
                                               str(sw.toolchain_name), str(sw.toolchain_version))
            if ec_to_append is None:
                continue
            else:
                ec_names.append(ec_to_append)
        return ec_names

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
    def __init__(self, software, version, toolchain, toolchain_version, toolchain_name):
        self.software = software
        self.version = version
        self.toolchain = toolchain
        self.toolchain_version = toolchain_version
        self.toolchain_name = toolchain_name
        self.toolchain = toolchain
        self.versionsuffix = None

    # to be implemented
    # def get_versionsuffix(self):
    #     return self.versionsuffix or ''


# implement this to your own needs - to create custom yaml/json/xml parser
class GenericSpecsParser(object):
    """Parent of all implemented parser classes"""
    @ staticmethod
    def parse(filepath):
        """Parent of all implemented parser functions (i.e. JSON, XML...)"""
        raise NotImplementedError


class YamlSpecParser(GenericSpecsParser):
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

        sw_dict = spec_dict["software"]

        # assign software-specific EB attributes
        for software in sw_dict:
            asterisk_err = "Easystack specifications of '%s' contain asterisk. " % (str(software))
            asterisk_err += "Wildcard feature is not supported yet."
            wrong_structure_err = "Easystack specifications of '%s' have wrong yaml structure." % (str(software))
            try:
                # iterates through toolchains to find out what sw version is needed
                for yaml_tc in sw_dict[software]['toolchains']:
                    # if version string containts asterisk or labels, raise error (not implemented yet)
                    if '*' in str(sw_dict[software]['toolchains'][yaml_tc]['versions']):
                        raise EasyBuildError(asterisk_err)
                    for yaml_version in sw_dict[software]['toolchains'][yaml_tc]['versions']:
                        try:
                            yaml_version_specs = sw_dict[software]['toolchains'][yaml_tc]['versions'][yaml_version]
                            if 'versionsuffix' in str(yaml_version_specs):
                                ver_suf_err = "Easystack specifications of '%s' contain versionsuffix. " % str(software)
                                ver_suf_err += "This isn't supported yet."
                                raise EasyBuildError(ver_suf_err)
                            elif 'exclude-labels' in str(yaml_version_specs) \
                                or 'include-labels' in str(yaml_version_specs):
                                    lab_err = "Easystack specifications of '%s' contain labels. " % str(software)
                                    lab_err += "Labels aren't supported yet."
                                    raise EasyBuildError(lab_err)
                        except TypeError:
                            pass
                        if '*' in str(yaml_version):
                            raise EasyBuildError(asterisk_err)
                        # TODO - think of better ID of versions
                        elif str(yaml_version)[0].isdigit() \
                                or str(yaml_version)[-1].isdigit():
                            # creates a sw class instance
                            try:
                                yaml_toolchain_name = str(yaml_tc).split('-', 1)[0]
                                yaml_toolchain_version = str(yaml_tc).split('-', 1)[1]
                            except IndexError:
                                yaml_toolchain_name = str(yaml_tc)
                                yaml_toolchain_version = ''

                            sw = SoftwareSpecs(
                                software=software, version=yaml_version,
                                toolchain=yaml_tc, toolchain_name=yaml_toolchain_name,
                                toolchain_version=yaml_toolchain_version)

                            # append newly created class instance to the list inside EbFromSpecs class
                            eb.software_list.append(sw)
                        else:
                            raise EasyBuildError(wrong_structure_err)

            except (KeyError, TypeError, IndexError):
                raise EasyBuildError(wrong_structure_err)

        # assign general EB attributes
        eb.easybuild_version = spec_dict.get('easybuild_version', None)
        eb.robot = spec_dict.get('robot', False)
        return eb


def parse_easystack(filepath):
    """Parses through easystack file, returns what EC are to be installed together with their options."""
    log_msg = "Support for easybuild-ing from multiple easyconfigs based on "
    log_msg += "information obtained from provided file (easystack) with build specifications."
    _log.experimental(log_msg)
    _log.info("Building from easystack: '%s'" % filepath)

    # class instance which contains all info about planned build
    eb = YamlSpecParser.parse(filepath)

    easyconfig_names = eb.compose_ec_names()

    general_options = eb.get_general_options()

    _log.debug("Easystack parsed. Proceeding to install these Easyconfigs: \n'%s'" % ',\n'.join(easyconfig_names))
    if len(general_options) != 0:
        _log.debug("General options for installation are: \n%s" % str(general_options))
    else:
        _log.debug("No general options were specified in easystack")

    return easyconfig_names, general_options
