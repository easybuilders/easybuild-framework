##
# Copyright 2015-2018 Ghent University
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
Various utilities related to packaging support.

:author: Marc Litherland (Novartis)
:author: Gianluca Santarossa (Novartis)
:author: Robert Schmidt (The Ottawa Hospital, Research Institute)
:author: Fotis Georgatos (Uni.Lu, NTUA)
:author: Kenneth Hoste (Ghent University)
"""
import os
import tempfile
import pprint

from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses
from vsc.utils.patterns import Singleton

from easybuild.tools.config import PKG_TOOL_FPM, PKG_TYPE_RPM, build_option, get_package_naming_scheme, log_path
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import change_dir, which
from easybuild.tools.package.package_naming_scheme.pns import PackageNamingScheme
from easybuild.tools.run import run_cmd
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.utilities import import_available_modules
_log = fancylogger.getLogger('tools.package')  # pylint: disable=C0103



def avail_package_naming_schemes():
    """
    Returns the list of valed naming schemes
    They are loaded from the easybuild.package.package_naming_scheme namespace
    """
    import_available_modules('easybuild.tools.package.package_naming_scheme')
    class_dict = dict([(x.__name__, x) for x in get_subclasses(PackageNamingScheme)])
    return class_dict


def package(easyblock):
    """
    Package installed software, according to active packaging configuration settings."""
    pkgtool = build_option('package_tool')

    if pkgtool == PKG_TOOL_FPM:
        pkgdir = package_with_fpm(easyblock)
    else:
        raise EasyBuildError("Unknown packaging tool specified: %s", pkgtool)

    return pkgdir


def package_with_fpm(easyblock):
    """
    This function will build a package using fpm and return the directory where the packages are
    """

    workdir = tempfile.mkdtemp(prefix='eb-pkgs-')
    pkgtype = build_option('package_type')
    _log.info("Will be creating %s package(s) in %s", pkgtype, workdir)

    origdir = change_dir(workdir)

    package_naming_scheme = ActivePNS()

    pkgname = package_naming_scheme.name(easyblock.cfg)
    pkgver = package_naming_scheme.version(easyblock.cfg)
    pkgrel = package_naming_scheme.release(easyblock.cfg)

    _log.debug("Got the PNS values name: %s version: %s release: %s", pkgname, pkgver, pkgrel)
    cmdlist = [
        PKG_TOOL_FPM,
        '--workdir', workdir,
        '--name', pkgname,
        '--provides', pkgname,
        '-t', pkgtype,  # target
        '-s', 'dir',  # source
        '--version', pkgver,
        '--iteration', pkgrel,
        '--description', easyblock.cfg["description"],
        '--url', easyblock.cfg["homepage"],
    ]

    extra_pkg_options = build_option('package_tool_options')
    if extra_pkg_options:
        cmdlist.extend(extra_pkg_options.split(' '))

    if build_option('debug'):
        cmdlist.append('--debug')

    deps = []
    if easyblock.toolchain.name != DUMMY_TOOLCHAIN_NAME:
        toolchain_dict = easyblock.toolchain.as_dict()
        deps.extend([toolchain_dict])

    deps.extend(easyblock.cfg.dependencies())

    _log.debug("The dependencies to be added to the package are: %s",
               pprint.pformat([easyblock.toolchain.as_dict()] + easyblock.cfg.dependencies()))
    for dep in deps:
        if dep.get('external_module', False):
            _log.debug("Skipping dep marked as external module: %s", dep['name'])
        else:
            _log.debug("The dep added looks like %s ", dep)
            dep_pkgname = package_naming_scheme.name(dep)
            cmdlist.extend(["--depends", dep_pkgname])

    # Excluding the EasyBuild logs and test reports that might be in the installdir
    exclude_files_globs = [
        os.path.join(log_path(), "*.log"),
        os.path.join(log_path(), "*.md"),
    ]
    # stripping off leading / to match expected glob in fpm
    for exclude_files_glob in exclude_files_globs:
        cmdlist.extend(['--exclude', os.path.join(easyblock.installdir.lstrip(os.sep), exclude_files_glob)])

    cmdlist.extend([
        easyblock.installdir,
        easyblock.module_generator.get_module_filepath(),
    ])
    cmd = ' '.join(cmdlist)
    _log.debug("The flattened cmdlist looks like: %s", cmd)
    run_cmd(cmdlist, log_all=True, simple=True, shell=False)

    _log.info("Created %s package(s) in %s", pkgtype, workdir)

    change_dir(origdir)

    return workdir


def check_pkg_support():
    """Check whether packaging is possible, if required dependencies are available."""
    pkgtool = build_option('package_tool')
    pkgtool_path = which(pkgtool)
    if pkgtool_path:
        _log.info("Selected packaging tool '%s' found at %s", pkgtool, pkgtool_path)

        # rpmbuild is required for generating RPMs with FPM
        if pkgtool == PKG_TOOL_FPM and build_option('package_type') == PKG_TYPE_RPM:
            rpmbuild_path = which('rpmbuild')
            if rpmbuild_path:
                _log.info("Required tool 'rpmbuild' found at %s", rpmbuild_path)
            else:
                raise EasyBuildError("rpmbuild is required when generating RPM packages but was not found")

    else:
        raise EasyBuildError("Selected packaging tool '%s' not found", pkgtool)


class ActivePNS(object):
    """
    The wrapper class for Package Naming Schemes.
    """
    __metaclass__ = Singleton

    def __init__(self):
        """Initialize logger and find available PNSes to load"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        avail_pns = avail_package_naming_schemes()
        sel_pns = get_package_naming_scheme()
        if sel_pns in avail_pns:
            self.pns = avail_pns[sel_pns]()
        else:
            raise EasyBuildError("Selected package naming scheme %s could not be found in %s",
                                 sel_pns, avail_pns.keys())

    def name(self, easyconfig):
        """Determine package name"""
        name = self.pns.name(easyconfig)
        return name

    def version(self, easyconfig):
        """Determine package version"""
        version = self.pns.version(easyconfig)
        return version

    def release(self, easyconfig):
        """Determine package release"""
        release = self.pns.release(easyconfig)
        return release
