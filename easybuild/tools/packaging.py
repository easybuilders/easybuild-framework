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
from easybuild.tools.config import install_path, package_template
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME

_log = fancylogger.getLogger('tools.packaging')

def package_fpm(easyblock, modfile_path, package_type="rpm" ):
    '''
    This function will build a package using fpm and return the directory where the packages are
    '''
    
    workdir = tempfile.mkdtemp()
    _log.info("Will be writing RPM to %s" % workdir)

    try:
        os.chdir(workdir)
    except OSError, err:
        _log.error("Failed to chdir into workdir: %s : %s" % (workdir, err))

    # default package_template is "eb-%(toolchain)s-%(name)s"
    pkgtemplate = package_template()
    full_ec_version = det_full_ec_version(easyblock.cfg)
    _log.debug("I got a package template that looks like: %s " % pkgtemplate )

    toolchain_name = "%s-%s" % (easyblock.toolchain.name, easyblock.toolchain.version)

    pkgname = pkgtemplate % {
        'toolchain' : toolchain_name,
        'version': '-'.join([x for x in [easyblock.cfg.get('versionprefix', ''), easyblock.cfg['version'], easyblock.cfg['versionsuffix']] if x]),
        'name' : easyblock.name,
    }
    
    deps = []
    if easyblock.toolchain.name != DUMMY_TOOLCHAIN_NAME:
        toolchain_dict = easyblock.toolchain.as_dict()
        deps.extend([toolchain_dict])

    deps.extend(easyblock.cfg.dependencies())
 
    _log.debug("The dependencies to be added to the package are: " + pprint.pformat([easyblock.toolchain.as_dict()]+easyblock.cfg.dependencies()))
    depstring = ""    
    for dep in deps:
        full_dep_version = det_full_ec_version(dep)
        #by default will only build iteration 1 packages, do we need to enhance this?
        _log.debug("The dep added looks like %s " % dep)
        dep_pkgname = pkgtemplate % {
            'name': dep['name'],
            'version': '-'.join([x for x in [dep.get('versionprefix',''), dep['version'], dep['versionsuffix']] if x]),
            'toolchain': "%s-%s" % (dep['toolchain']['name'], dep['toolchain']['version']),
        }
        depstring += " --depends '%s'" % ( dep_pkgname)

    cmdlist=[
        'fpm',
        '--workdir', workdir,
        '--name', pkgname,
        '--provides', pkgname,
        '-t', package_type, # target
        '-s', 'dir', # source
        '--version', "eb",
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

