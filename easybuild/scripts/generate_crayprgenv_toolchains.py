#!/usr/bin/env python
# #
# Copyright 2014 Petar Forai
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


import easybuild.tools.modules as modules
import easybuild.tools.config as config
import easybuild.tools.options as eboptions

import easybuild.tools.options as eboptions
from easybuild.tools import config, modules
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.filetools import which
from easybuild.tools.modules import modules_tool, Lmod
from easybuild.tools.config import build_option, get_modules_tool

from collections import namedtuple
import tempfile, os

#_log = fancylogger.getLogger('craytcgenerator', fname=False)


EB_EC_FILE_TMPLT = """
easyblock = 'Toolchain'

name = '%(name)s'
version = '%(version)s'

homepage = 'http://hpcugent.github.io/easybuild/'
description = \"\"\"This is a shim module for having EB pick up the Cray
Programming Environment (PrgEnv-*) modules. This module implements the EB
toolchain module for each of the cray modules.\"\"\"

toolchain = {'name': 'dummy', 'version': 'dummy'}

source_urls = []
sources = []
dependencies = []

moduleclass = 'toolchain'

modtclfooter = \"\"\"
module load %(craymodule)s/%(version)s
module load %(craypetarget)s
\"\"\"

"""

eb_go = eboptions.parse_options()
config.init(eb_go.options, eb_go.get_options_by_section('config'))

config.init_build_options({'suffix_modules_path':'all'})
config.set_tmpdir()



#FIXME: This needs to be usable from not only Lmod, but other environment modules tool in EasyBuild.
# from easybuild.tools.modules import get_software_root, modules_tool
# use something like self.modules_tool = modules_tool()
ml = modules_tool()

prgenvmods = []

print "Running module avail commands for the Cray compiler wrappers."
#print "using modules tool " + str(ml.__class__.__name__)

prgenvmods = ml.available("PrgEnv")

if len(prgenvmods) == 0:
    print """No Cray Programming Environment modules are visible in the modules tool.\n
             Make sure to include them in $MODULEPATH or this is not a Cray system."""

print prgenvmods

craymod_to_tc = {'PrgEnv-cray': 'CrayCCE',
                 'PrgEnv-intel': 'CrayIntel',
                 'PrgEnv-gnu': 'CrayGNU',
                 'PrgEnv-pgi': 'CrayPGI', }

tc_to_craymod = {'CrayCCE': 'PrgEnv-cray',
                 'CrayIntel': 'PrgEnv-intel',
                 'CrayGCC': 'PrgEnv-gnu',
                 'CrayPGI': 'PrgEnv-pgi', }


def modToTC(m):
    modname, version = m.split('/')
    if modname not in craymod_to_tc:
        print "Can't map Cray module name to EasyBuild toolchain name module."
    else:
        # The TC name for a given cray module name is defined to be the mapping table craymod_to_tc
        # and the EB toolchain version is identical to the version of the PrgEnv module itself.
        # Cray already does all the work of coming up with numbers, so let's use this.
        toolchain = namedtuple('toolchain', 'toolchainname , toolchainversion')
        return toolchain(toolchainname=craymod_to_tc[modname], toolchainversion=version)


def generate_EB_config(tmpdir, craytc):
    name = craytc.toolchainname
    version = craytc.toolchainversion
    ebconfigfile = os.path.join(tmpdir, '%s-%s.eb' % (name, version))
    print "Generating file ", ebconfigfile
    f = open(ebconfigfile, "w")
    f.write(EB_EC_FILE_TMPLT % {'name': name,
                                'version': version,
                                'craymodule': tc_to_craymod[name],
                                'craypetarget': 'craype-haswell', #@todo this needs to ne somehow better or at least an option!
    })
    f.close()


tmpdir = tempfile.mkdtemp()
print tmpdir
os.chdir(tmpdir)

for mod in prgenvmods:
    toolchain = modToTC(mod)
    generate_EB_config(tmpdir, toolchain)
