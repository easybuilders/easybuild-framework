##
# Copyright 2009-2018 Ghent University
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
EasyBuild support for building and installing toy, implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import platform
import shutil

from easybuild.framework.extensioneasyblock import ExtensionEasyBlock
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.environment import setvar
from easybuild.tools.filetools import mkdir
from easybuild.tools.modules import get_software_root, get_software_version
from easybuild.tools.run import run_cmd


class EB_toy(ExtensionEasyBlock):
    """Support for building/installing toy."""

    def __init__(self, *args, **kwargs):
        """Constructor"""
        super(EB_toy, self).__init__(*args, **kwargs)

        setvar('TOY', '%s-%s' % (self.name, self.version))

    def prepare_for_extensions(self):
        """
        Prepare for installing toy extensions.
        """
        # insert new packages by building them with RPackage
        self.cfg['exts_defaultclass'] = "Toy_Extension"
        self.cfg['exts_filter'] = ("%(ext_name)s", "")

    def configure_step(self, name=None):
        """Configure build of toy."""
        if name is None:
            name = self.name
        # make sure Python system dep is handled correctly when specified
        if self.cfg['allow_system_deps']:
            if get_software_root('Python') != 'Python' or get_software_version('Python') != platform.python_version():
                raise EasyBuildError("Sanity check on allowed Python system dep failed.")

        if os.path.exists("%s.source" % name):
            os.rename('%s.source' % name, '%s.c' % name)

    def build_step(self, name=None, buildopts=None):
        """Build toy."""

        if buildopts is None:
            buildopts = self.cfg['buildopts']

        if name is None:
            name = self.name
        run_cmd('%(prebuildopts)s gcc %(name)s.c -o %(name)s %(buildopts)s' % {
            'name': name,
            'prebuildopts': self.cfg['prebuildopts'],
            'buildopts': buildopts,
        })

    def install_step(self, name=None):
        """Install toy."""
        if name is None:
            name = self.name
        bindir = os.path.join(self.installdir, 'bin')
        mkdir(bindir, parents=True)
        for filename in glob.glob('%s_*' % name) + [name]:
            if os.path.exists(filename):
                shutil.copy2(filename, bindir)
        # also install a dummy libtoy.a, to make the default sanity check happy
        libdir = os.path.join(self.installdir, 'lib')
        mkdir(libdir, parents=True)
        f = open(os.path.join(libdir, 'lib%s.a' % name), 'w')
        f.write(name.upper())
        f.close()

    def run(self):
        """Install toy as extension."""
        super(EB_toy, self).run(unpack_src=True)
        self.configure_step()
        self.build_step()
        self.install_step()

    def make_module_extra(self):
        """Extra stuff for toy module"""
        txt = super(EB_toy, self).make_module_extra()
        txt += self.module_generator.set_environment('TOY', os.getenv('TOY', '<TOY_env_var_not_defined>'))
        return txt
