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

"""

import os
from easybuild.tools.run import run_cmd

def package_fpm(easyblock, modfile_path ):
    rpmname = "HPCBIOS.20150211-%s-%s" % (easyblock.name, easyblock.version)
    workdir = tempfile.mkdtemp()
    try:
        os.chdir(workdir)
    except OSError, err:
        _log.error("Failed to chdir into workdir: %s : %s" % (workdir, err))

    pkgtemplate = "HPCBIOS.20150211-%(name)s-%(version)s"

    pkgname=pkgtemplate % {
        'name' : easyblock.name,
        'version' : easyblock.version,
    }
    dependencies = []
    dependencies.extend([ "=".join([ dep['name'], dep['version'] ]) for dep in easyblock.cfg.dependencies() ])
    depstring = '--depends ' + ' --depends '.join(dependencies)
    cmdlist=[
        'fpm',
        '--workdir', workdir,
        '--name', pkgname,
        '-t', 'rpm', # target
        '-s', 'dir', # source
        '-C', easyblock.installdir,
    ]
    cmdlist.extend([ depstring ])
    cmdlist.extend([
        easyblock.installdir,
    ])

    (out, _) = run_cmd(cmdlist, log_all=True, simple=True)
