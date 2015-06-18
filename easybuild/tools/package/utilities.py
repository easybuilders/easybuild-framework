# #
# Copyright 2009-2014 Ghent University
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
# #

"""
A place for packaging functions

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

from easybuild.tools.run import run_cmd
from easybuild.tools.config import build_option
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import which
from easybuild.tools.package.activepns import ActivePNS

DEFAULT_PNS = 'EasyBuildPNS'

_log = fancylogger.getLogger('tools.packaging')
# This is an abbreviated list of the package options, eventually it might make sense to set them
# all in the "plugin" rather than in tools.options
config_options = [ 'package_tool', 'package_type' ]

def package_fpm(easyblock, modfile_path, package_type="rpm" ):
    '''
    This function will build a package using fpm and return the directory where the packages are
    '''
    
    workdir = tempfile.mkdtemp()
    _log.info("Will be writing RPM to %s" % workdir)

    try:
        os.chdir(workdir)
    except OSError, err:
        raise EasyBuildError("Failed to chdir into workdir: %s : %s", workdir, err)

    package_naming_scheme = ActivePNS()

    pkgname = package_naming_scheme.name(easyblock.cfg)
    pkgver  = package_naming_scheme.version(easyblock.cfg)
    pkgrel  = package_naming_scheme.release(easyblock.cfg)
 
    deps = []
    if easyblock.toolchain.name != DUMMY_TOOLCHAIN_NAME:
        toolchain_dict = easyblock.toolchain.as_dict()
        deps.extend([toolchain_dict])

    deps.extend(easyblock.cfg.dependencies())
 
    _log.debug("The dependencies to be added to the package are: " + pprint.pformat([easyblock.toolchain.as_dict()]+easyblock.cfg.dependencies()))
    depstring = ""    
    for dep in deps:
        _log.debug("The dep added looks like %s " % dep)
        dep_pkgname = package_naming_scheme.name(dep)
        depstring += " --depends '%s'" % ( dep_pkgname)

    cmdlist=[
        'fpm',
        '--workdir', workdir,
        '--name', pkgname,
        '--provides', pkgname,
        '-t', package_type, # target
        '-s', 'dir', # source
        '--version', pkgver,
    ]
    cmdlist.extend([ depstring ])
    cmdlist.extend([
        easyblock.installdir,
        modfile_path
    ])
    cmdstr = " ".join(cmdlist)
    _log.debug("The flattened cmdlist looks like" + cmdstr)
    out = run_cmd(cmdstr, log_all=True, simple=True)
   
    _log.info("wrote rpm to %s" % (workdir) )

    return workdir


def option_postprocess():
    '''
    Called from easybuild.tools.options.postprocess to check that experimental is triggered and fpm is available
    '''

    _log.experimental("Using the packaging module, This is experimental")
    fpm_path = which('fpm')
    rpmbuild_path = which('rpmbuild')
    if fpm_path and rpmbuild_path:
        _log.info("fpm found at: %s" % fpm_path)
    else:
        raise EasyBuildError("Need both fpm and rpmbuild. Found fpm: %s rpmbuild: %s", fpm_path, rpmbuild_path)


