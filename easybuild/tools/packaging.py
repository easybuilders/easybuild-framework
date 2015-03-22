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
from easybuild.tools.config import install_path, package_prefix

_log = fancylogger.getLogger('tools.packaging')

def package_fpm(easyblock, modfile_path ):
    
    workdir = tempfile.mkdtemp()
    _log.info("Will be writing RPM to %s" % workdir)

    try:
        os.chdir(workdir)
    except OSError, err:
        _log.error("Failed to chdir into workdir: %s : %s" % (workdir, err))

    pkgprefix   = package_prefix()
    pkgtemplate = "%(prefix)s-%(name)s"
    #"HPCBIOS.20150211-%(name)s-%(version)s"

    pkgname=pkgtemplate % {
        'prefix' : pkgprefix,
        'name' : easyblock.name,
    }
    _log.debug("The dependencies to be added to the package are: " + pprint.pformat(easyblock.cfg.dependencies()))
    depstring = ""    
    for dep in easyblock.cfg.dependencies():
        depstring += " --depends '%s-%s = %s-1'" % ( pkgprefix , dep['name'], dep['version'])

    cmdlist=[
        'fpm',
        '--workdir', workdir,
        '--name', pkgname,
        '--provides', "%s-%s" %(pkgprefix,easyblock.name),
        '-t', 'rpm', # target
        '-s', 'dir', # source
        '--version', easyblock.version,
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

