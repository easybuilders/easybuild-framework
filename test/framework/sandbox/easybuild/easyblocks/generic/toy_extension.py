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
EasyBuild support for building and installing toy extensions, implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""

from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.extensioneasyblock import ExtensionEasyBlock
from easybuild.easyblocks.toy import EB_toy
from easybuild.tools.run import run_cmd


class Toy_Extension(ExtensionEasyBlock):
    """Support for building/installing toy."""

    @staticmethod
    def extra_options():
        """Custom easyconfig parameters for toy extensions."""
        extra_vars = {
            'toy_ext_param': ['', "Toy extension parameter", CUSTOM],
        }
        return ExtensionEasyBlock.extra_options(extra_vars=extra_vars)

    def run(self):
        """Build toy extension."""
        if self.src:
            super(Toy_Extension, self).run(unpack_src=True)
            EB_toy.configure_step(self.master, name=self.name)
            EB_toy.build_step(self.master, name=self.name, buildopts=self.cfg['buildopts'])

            if self.cfg['toy_ext_param']:
                run_cmd(self.cfg['toy_ext_param'])

            EB_toy.install_step(self.master, name=self.name)

            return self.module_generator.set_environment('TOY_EXT_%s' % self.name.upper(), self.name)

    def sanity_check_step(self, *args, **kwargs):
        """Custom sanity check for toy extensions."""
        self.log.info("Loaded modules: %s", self.modules_tool.list())
        custom_paths = {
            'files': [],
            'dirs': ['.'],  # minor hack to make sure there's always a non-empty list
        }
        if self.src:
            custom_paths['files'].extend(['bin/%s' % self.name, 'lib/lib%s.a' % self.name])
        return super(Toy_Extension, self).sanity_check_step(custom_paths=custom_paths)
