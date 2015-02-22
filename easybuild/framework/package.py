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

def package_fpm(easyblock,modfile_path ):
    rpmname = "HPCBIOS.20150211-%s-%s" % (easyblock.name, easyblock.version)
    os.chdir("/tmp")

    if easyblock.toolchain.name == "dummy":
        dependencies = []
    else:
        dependencies = [ "=".join([ easyblock.toolchain.name, easyblock.toolchain.version ]) ]
    dependencies.extend([ "=".join([ dep['name'], dep['version'] ]) for dep in easyblock.cfg.dependencies() ])
    depstring = '--depends ' + ' --depends '.join(dependencies)
    cmdlist=[
        'fpm',
        '--workdir', workdir,
        '--name', pkgname,

    ]
    cmdlist.extend(' --depends '.join(dependencies))
    [
        '-t', flavour, # target
        '-s', 'dir', # source
        '-C', easyblock.installdir,
    ]
    cmdlist.extend(deplist)

    cmd = "fpm --workdir /tmp --name %s %s -s dir -t rpm -C %s ." % (rpmname, depstring, easyblock.installdir)
    (out, _) = run_cmd(cmd, log_all=True, simple=False)
