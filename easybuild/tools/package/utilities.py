##
# Copyright 2015-2015 Ghent University
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
Various utilities related to packaging support.

@author: Marc Litherland
@author: Gianluca Santarossa (Novartis)
@author: Robert Schmidt (Ottawa Hospital Research Institute)
@author: Fotis Georgatos (Uni.Lu, NTUA)
@author: Kenneth Hoste (Ghent University)
"""
import os
import tempfile
import pprint

from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses
from vsc.utils.patterns import Singleton

from easybuild.tools.config import get_package_naming_scheme
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import which
from easybuild.tools.package.packaging_naming_scheme.pns import PackagingNamingScheme
from easybuild.tools.run import run_cmd
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.utilities import import_available_modules


DEFAULT_PNS = 'EasyBuildPNS'

_log = fancylogger.getLogger('tools.package')


def avail_package_naming_schemes():
    """
    Returns the list of valed naming schemes that are in the easybuild.package.package_naming_scheme namespace
    """
    import_available_modules('easybuild.tools.package.packaging_naming_scheme')
    class_dict = dict([(x.__name__, x) for x in get_subclasses(PackagingNamingScheme)])
    return class_dict


def package_fpm(easyblock, modfile_path, package_type='rpm'):
    """
    This function will build a package using fpm and return the directory where the packages are
    """
    workdir = tempfile.mkdtemp(prefix='eb-pkgs')
    _log.info("Will be creating packages in %s", workdir)

    try:
        os.chdir(workdir)
    except OSError, err:
        raise EasyBuildError("Failed to chdir into workdir %s: %s", workdir, err)

    package_naming_scheme = ActivePNS()

    pkgname = package_naming_scheme.name(easyblock.cfg)
    pkgver = package_naming_scheme.version(easyblock.cfg)
    pkgrel = package_naming_scheme.release(easyblock.cfg)

    _log.debug("Got the PNS values for (name, version, release): (%s, %s, %s)", pkgname, pkgver, pkgrel)
    deps = []
    if easyblock.toolchain.name != DUMMY_TOOLCHAIN_NAME:
        toolchain_dict = easyblock.toolchain.as_dict()
        deps.extend([toolchain_dict])

    deps.extend(easyblock.cfg.dependencies())

    _log.debug("The dependencies to be added to the package are: %s",
               pprint.pformat([easyblock.toolchain.as_dict()] + easyblock.cfg.dependencies()))
    depstring = ''
    for dep in deps:
        _log.debug("The dep added looks like %s ", dep)
        dep_pkgname = package_naming_scheme.name(dep)
        depstring += " --depends '%s'" % dep_pkgname

    cmdlist = [
        'fpm',
        '--workdir', workdir,
        '--name', pkgname,
        '--provides', pkgname,
        '-t', package_type,  # target
        '-s', 'dir',  # source
        '--version', pkgver,
        '--iteration', pkgrel,
        depstring,
        easyblock.installdir,
        modfile_path,
    ]
    cmd = ' '.join(cmdlist)
    _log.debug("The flattened cmdlist looks like: %s", cmd)
    run_cmd(cmd, log_all=True, simple=True)

    _log.info("Created %s package in %s", package_type, workdir)

    return workdir


def check_pkg_support():
    """Check whether packaging is supported, i.e. whether the required dependencies are available."""

    _log.experimental("Support for packaging installed software.")
    fpm_path = which('fpm')
    rpmbuild_path = which('rpmbuild')
    if fpm_path and rpmbuild_path:
        _log.info("fpm found at: %s", fpm_path)
    else:
        raise EasyBuildError("Need both fpm and rpmbuild. Found fpm: %s rpmbuild: %s", fpm_path, rpmbuild_path)


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

    def name(self, ec):
        """Determine package name"""
        name = self.pns.name(ec)
        return name

    def version(self, ec):
        """Determine package version"""
        version = self.pns.version(ec)
        return version

    def release(self, ec):
        """Determine package release"""
        release = self.pns.release()
        return release
