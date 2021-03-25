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

from easybuild.base.fancylogger import getLogger
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.utilities import only_if_module_is_available
try:
    import yaml
except ImportError:
    pass
_log = getLogger('easystack', fname=True)


class EasyStack(object):
    """One class instance per easystack. General options + list of all SoftwareSpecs instances"""

    def __init__(self):
        self.software_list = []

    def compose_ec_filenames(self):
        """Returns a list of all easyconfig names"""
        ec_filenames = []
        for sw in self.software_list:
            full_ec_version = det_full_ec_version({
                'toolchain': {'name': sw.toolchain_name, 'version': sw.toolchain_version},
                'version': sw.version,
                'versionsuffix': sw.versionsuffix or '',
            })
            ec_filename = '%s-%s.eb' % (sw.name, full_ec_version)
            ec_filenames.append(ec_filename)
        return ec_filenames

    def print_full_commands(self):
        """Creates easybuild string to be run via terminal."""
        easystack_log = "Building from easystack:"
        _log.info(easystack_log)
        print(easystack_log) # todo najst printovaciu funkciu fw - print_msg() z build_log.py
        print_only_log = "Printing commands only, since a not-fully-supported keyword has been used:\n"
        _log.info(print_only_log)
        print(print_only_log)
        for sw in self.software_list:
            full_ec_version = det_full_ec_version({
                'toolchain': {'name': sw.toolchain_name, 'version': sw.toolchain_version},
                'version': sw.version,
                'versionsuffix': sw.versionsuffix or '',
            })
            ec_filename = '%s-%s.eb' % (sw.name, full_ec_version)
            robot_suffix, force_suffix, dry_run_suffix, parallel_suffix, easybuild_version_suffix, from_pr_suffix = '', '', '', '', '', ''
            if sw.robot == True: robot_suffix = ' --robot'
            if sw.force == True: force_suffix = ' --force'
            if sw.dry_run == True: dry_run_suffix = ' --dry-run'
            if sw.parallel: parallel_suffix = ' --parallel=%s' % sw.parallel
            if sw.easybuild_version: easybuild_version_suffix = ' --easybuild_version=%s' % sw.easybuild_version
            if sw.from_pr: from_pr_suffix = ' --from-pr=%s' % sw.from_pr
            full_command = 'eb %s%s%s%s%s%s%s' % (ec_filename, robot_suffix, force_suffix, dry_run_suffix, parallel_suffix,
                                               easybuild_version_suffix, from_pr_suffix)
            full_command_log = "%s; \n" % full_command
            _log.info(full_command_log)
            print(full_command_log)

    # at least one of include-labels is required on input for SW to install
    def process_include_labels(self, provided_labels):
        for sw in self.software_list[:]:
            for easystack_include_label in sw.include_labels[:]:
                # if a match IS NOT FOUND, sw must be deleted
                if provided_labels == False or easystack_include_label not in provided_labels:
                    self.software_list.remove(sw)

    # do input labels match with any of defined 'exclude-labels' ? if so, such sw wont be installed
    def process_exclude_labels(self, provided_labels):
        for sw in self.software_list[:]:
            for easystack_exclude_labels in sw.exclude_labels[:]:
                # if a match IS FOUND, sw must be deleted
                if provided_labels == False:
                    continue
                elif easystack_exclude_labels in provided_labels:
                    self.software_list.remove(sw)


class SoftwareSpecs(object):
    """Contains information about every software that should be installed"""

    def __init__(self, name, version, versionsuffix, toolchain_version, toolchain_name, easybuild_version,
                robot, force, dry_run, parallel, from_pr, include_labels, exclude_labels):
        self.name = name
        self.version = version
        self.toolchain_version = toolchain_version
        self.toolchain_name = toolchain_name
        self.versionsuffix = versionsuffix
        self.easybuild_version = easybuild_version
        self.robot = robot
        self.force = force
        self.dry_run = dry_run
        self.parallel = parallel
        self.from_pr = from_pr
        self.include_labels = include_labels or []
        self.exclude_labels = exclude_labels or []
        self.check_consistency(self.include_labels, self.exclude_labels)
    
    # general function that checks any potential inconsistencies
    def check_consistency(self, include_labels, exclude_labels):
        for include_label in include_labels:
            if exclude_labels.count(include_label) != 0:
                inconsistent_labels_err = 'One or more software specifications contain inconsistent labels. ' + \
                'Make sure there are no cases of one software having the same label specified both in include_labels ' + \
                'and exclude_labels'
                raise EasyBuildError(inconsistent_labels_err)



class EasyStackParser(object):
    """Parser for easystack files (in YAML syntax)."""

    @only_if_module_is_available('yaml', pkgname='PyYAML')
    @staticmethod
    def parse(filepath):
        """Parses YAML file and assigns obtained values to SW config instances as well as general config instance"""
        yaml_txt = read_file(filepath)
        easystack_raw = yaml.safe_load(yaml_txt)
        easystack = EasyStack()
        # should the resulting commands be only printed or should Easybuild continue building?
        print_only = False

        try:
            software = easystack_raw["software"]
        except KeyError:
            wrong_structure_file = "Not a valid EasyStack YAML file: no 'software' key found"
            raise EasyBuildError(wrong_structure_file)

        # trying to assign easybuild_version/robot/force/dry-run/parallel/from_pr on the uppermost level
        # if anything changes at any lower level, these will get overwritten
        # assign general easystack attributes
        easybuild_version = easystack_raw.get('easybuild_version', False)
        robot = easystack_raw.get('robot', False)
        force = easystack_raw.get('force', False)
        dry_run = easystack_raw.get('dry-run', False)
        parallel = easystack_raw.get('parallel', False)
        from_pr = easystack_raw.get('from-pr', False)


        # assign software-specific easystack attributes
        for name in software:
            # ensure we have a string value (YAML parser returns type = dict
            # if levels under the current attribute are present)
            name = str(name)

            # checking whether software has any labels defined on topmost level
            include_labels = []
            exclude_labels = []
            name_lvl_include_labels = []
            name_lvl_exclude_labels = []
            tmp_include = software[name].get('include-labels', False)
            tmp_exclude = software[name].get('exclude-labels', False)
            if tmp_include != False:
                name_lvl_include_labels.append(tmp_include)
            if tmp_exclude != False:
                name_lvl_exclude_labels.append(tmp_exclude)

            try:
                toolchains = software[name]['toolchains']
            except KeyError:
                raise EasyBuildError("Toolchains for software '%s' are not defined in %s", name, filepath)

            for toolchain in toolchains:
                toolchain = str(toolchain)
                toolchain_parts = toolchain.split('-', 1)
                if len(toolchain_parts) == 2:
                    toolchain_name, toolchain_version = toolchain_parts
                elif len(toolchain_parts) == 1:
                    toolchain_name, toolchain_version = toolchain, ''
                else:
                    raise EasyBuildError("Incorrect toolchain specification for '%s' in %s, too many parts: %s",
                                         name, filepath, toolchain_parts)
                
                toolchain_lvl_include_labels = name_lvl_include_labels[:]
                toolchain_lvl_exclude_labels = name_lvl_exclude_labels[:]
                tmp_include = toolchains[toolchain].get('include-labels', False)
                tmp_exclude = toolchains[toolchain].get('exclude-labels', False)
                if tmp_include != False:
                    toolchain_lvl_include_labels.append(tmp_include)
                if tmp_exclude != False:
                    toolchain_lvl_exclude_labels.append(tmp_exclude)


                try:
                    versions = toolchains[toolchain]['versions']
                except TypeError as err:
                    wrong_structure_err = "An error occurred when interpreting "
                    wrong_structure_err += "the easystack for software %s: %s" % (name, err)
                    raise EasyBuildError(wrong_structure_err)

                # if version string containts asterisk or labels, raise error (asterisks not supported)
                if '*' in str(versions):
                    asterisk_err = "EasyStack specifications of '%s' in %s contain asterisk. "
                    asterisk_err += "Wildcard feature is not supported yet."
                    raise EasyBuildError(asterisk_err, name, filepath)
                
                # yaml versions can be in different formats in yaml file
                # firstly, check if versions in yaml file are read as a dictionary.
                # Example of yaml structure:
                # ========================================================================
                # versions:
                #   2.21:
                #   2.25:
                #       robot: True
                #       include-labels: '225'
                #   2.23:
                #     versionsuffix: '-R-4.0.0'
                #     parallel: 12
                #   2.26:
                #     from_pr: 1234
                # ========================================================================
                if isinstance(versions, dict):
                    for version in versions:
                        version_lvl_include_labels = toolchain_lvl_include_labels[:]
                        version_lvl_exclude_labels = toolchain_lvl_exclude_labels[:]
                        parallel_for_version = parallel
                        robot_for_version = robot
                        force_for_version = force
                        dry_run_for_version = dry_run
                        from_pr_for_version = from_pr
                        if versions[version] is not None:
                            version_spec = versions[version]
                            versionsuffix = version_spec.get('versionsuffix', False)
                            robot_for_version = version_spec.get('robot', robot)
                            force_for_version = version_spec.get('force', force)
                            dry_run_for_version = version_spec.get('dry-run', dry_run)
                            parallel_for_version = version_spec.get('parallel', parallel)
                            from_pr_for_version = version_spec.get('from-pr', from_pr)
                            
                            # sub-version-level labels handling
                            tmp_include = version_spec.get('include-labels', False)
                            if tmp_include != False:
                                version_lvl_include_labels.append(tmp_include)
                            tmp_exclude = version_spec.get('exclude-labels', False)
                            if tmp_exclude != False:
                                version_lvl_exclude_labels.append(tmp_exclude)
                        else:
                            versionsuffix = False

                        # dont want to overwrite print_only if it's been already set to True
                        if print_only == False:
                            if easybuild_version or robot or force or dry_run or parallel or from_pr:
                                print_only = True

                        specs = {
                            'name': name,
                            'toolchain_name': toolchain_name,
                            'toolchain_version': toolchain_version,
                            'version': version,
                            'versionsuffix': versionsuffix,
                            'easybuild_version': easybuild_version,
                            'robot': robot_for_version,
                            'force': force_for_version,
                            'dry_run': dry_run_for_version,
                            'parallel': parallel_for_version,
                            'from_pr': from_pr_for_version,
                            'include_labels': version_lvl_include_labels,
                            'exclude_labels': version_lvl_exclude_labels,
                        }
                        sw = SoftwareSpecs(**specs)

                        # append newly created class instance to the list in instance of EasyStack class
                        easystack.software_list.append(sw)
                    continue

                # is format read as a list of versions?
                # ========================================================================
                # versions:
                #   [2.24, 2.51]
                # ========================================================================
                elif isinstance(versions, list):
                    versions_list = versions

                # format = multiple lines without ':' (read as a string)?
                # ========================================================================
                # versions:
                #   2.24
                #   2.51
                # ========================================================================
                elif isinstance(versions, str):
                    versions_list = str(versions).split()

                # format read as float (containing one version only without :)?
                # ========================================================================
                # versions:
                #   2.24
                # ========================================================================
                elif isinstance(versions, float):
                    versions_list = [str(versions)]

                # if no version is a dictionary, neither 
                # versionsuffix, robot, force, dry_run, parallel, easybuild_version nor from_pr,are specified on this level
                versionsuffix = False
                easybuild_version = easybuild_version or False
                robot = robot or False
                force = force or False
                dry_run = dry_run or False
                parallel = parallel or False
                from_pr = from_pr or False
                include_labels = toolchain_lvl_include_labels or False
                exclude_labels = toolchain_lvl_exclude_labels or False

                # dont want to overwrite print_only once it's been set to True
                if print_only == False:
                    if easybuild_version or robot or force or dry_run or parallel or from_pr:
                        print_only = True

                for version in versions_list:
                    sw = SoftwareSpecs(
                        name=name, version=version, versionsuffix=versionsuffix,
                        toolchain_name=toolchain_name, toolchain_version=toolchain_version,
                        easybuild_version=easybuild_version, robot=robot, force=force, dry_run=dry_run, parallel=parallel, from_pr=from_pr,
                        include_labels = include_labels, exclude_labels = exclude_labels
                        )
                    # append newly created class instance to the list in instance of EasyStack class
                    easystack.software_list.append(sw)
        return easystack, print_only


def parse_easystack(filepath, labels):
    """Parses through easystack file, returns what EC are to be installed together with their options."""
    log_msg = "Support for easybuild-ing from multiple easyconfigs based on "
    log_msg += "information obtained from provided file (easystack) with build specifications."
    _log.experimental(log_msg)
    _log.info("Building from easystack: '%s'" % filepath)


    # class instance which contains all info about planned build
    easystack, print_only = EasyStackParser.parse(filepath)

    easystack.process_include_labels(labels or False)
    easystack.process_exclude_labels(labels or False)
    if easystack.software_list == []:
        raise EasyBuildError('No software to build specified in Easystack file. Did you use correct labels?')

    easyconfig_names = easystack.compose_ec_filenames()

    if print_only:
        easystack.print_full_commands()

    _log.debug("EasyStack parsed. Proceeding to install these Easyconfigs: \n'%s'" % "',\n'".join(easyconfig_names))
    _log.debug("Number of easyconfigs extracted from Easystack: %s" % len(easyconfig_names))

    return easyconfig_names, print_only
