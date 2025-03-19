##
# Copyright 2009-2025 Ghent University
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
import os

from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.extensioneasyblock import ExtensionEasyBlock
from easybuild.easyblocks.toy import EB_toy, compose_toy_build_cmd
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.run import run_shell_cmd


class Toy_Extension(ExtensionEasyBlock):
    """Support for building/installing toy."""

    @staticmethod
    def extra_options():
        """Custom easyconfig parameters for toy extensions."""
        extra_vars = {
            'toy_ext_param': ['', "Toy extension parameter", CUSTOM],
        }
        return ExtensionEasyBlock.extra_options(extra_vars=extra_vars)

    @property
    def required_deps(self):
        """Return list of required dependencies for this extension."""
        deps = {
            'bar': [],
            'barbar': ['bar'],
            'ls': [],
        }
        if self.name in deps:
            return deps[self.name]
        else:
            raise EasyBuildError("Dependencies for %s are unknown!", self.name)

    def pre_install_extension(self):
        """
        Prepare installation of toy extension.
        """
        super(Toy_Extension, self).pre_install_extension()

        if self.src:
            super(Toy_Extension, self).install_extension(unpack_src=True)
            EB_toy.configure_step(self.master, name=self.name, cfg=self.cfg)

    def install_extension(self, *args, **kwargs):
        """
        Install toy extension.
        """
        if self.src:
            EB_toy.build_step(self.master, name=self.name, cfg=self.cfg)

            if self.cfg['toy_ext_param']:
                run_shell_cmd(self.cfg['toy_ext_param'])

            return self.module_generator.set_environment('TOY_EXT_%s' % self.name.upper().replace('-', '_'), self.name)

    def install_extension_async(self, thread_pool):
        """
        Install toy extension asynchronously.
        """
        task_id = f'ext_{self.name}_{self.version}'
        if self.src:
            cmd = compose_toy_build_cmd(self.cfg, self.name, self.cfg['prebuildopts'], self.cfg['buildopts'])
        else:
            cmd = f"echo 'no sources for {self.name}'"

        return thread_pool.submit(run_shell_cmd, cmd, asynchronous=True, env=os.environ.copy(),
                                  fail_on_error=False, task_id=task_id, work_dir=os.getcwd())

    def post_install_extension(self):
        """
        Wrap up installation of toy extension.
        """
        super(Toy_Extension, self).post_install_extension()

        EB_toy.install_step(self.master, name=self.name)

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
