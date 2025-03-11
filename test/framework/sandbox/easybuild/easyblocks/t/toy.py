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
EasyBuild support for building and installing toy, implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import platform
import shutil

from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.extensioneasyblock import ExtensionEasyBlock
from easybuild.tools.build_log import EasyBuildError, print_warning
from easybuild.tools.environment import setvar
from easybuild.tools.filetools import mkdir, write_file
from easybuild.tools.modules import get_software_root, get_software_version
from easybuild.tools.run import run_cmd


def compose_toy_build_cmd(cfg, name, prebuildopts, buildopts):
    """
    Compose command to build toy.
    """

    cmd = "%(prebuildopts)s gcc %(name)s.c -o %(name)s %(buildopts)s" % {
        'name': name,
        'prebuildopts': prebuildopts,
        'buildopts': buildopts,
    }
    return cmd


class EB_toy(ExtensionEasyBlock):
    """Support for building/installing toy."""

    @staticmethod
    def extra_options(extra_vars=None):
        """Custom easyconfig parameters for toy."""
        if extra_vars is None:
            extra_vars = {}

        extra_vars['make_module'] = [True, "Skip generating (final) module file", CUSTOM]

        return ExtensionEasyBlock.extra_options(extra_vars)

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

    def run_all_steps(self, *args, **kwargs):
        """
        Tweak iterative easyconfig parameters.
        """
        if isinstance(self.cfg['buildopts'], list):
            # inject list of values for prebuildopts, same length as buildopts
            self.cfg['prebuildopts'] = ["echo hello && "] * len(self.cfg['buildopts'])

        return super(EB_toy, self).run_all_steps(*args, **kwargs)

    def configure_step(self, name=None, cfg=None):
        """Configure build of toy."""
        if name is None:
            name = self.name
        # Allow overwrite from Toy-Extension
        if cfg is None:
            cfg = self.cfg
        # make sure Python system dep is handled correctly when specified
        if cfg['allow_system_deps']:
            if get_software_root('Python') != 'Python' or get_software_version('Python') != platform.python_version():
                raise EasyBuildError("Sanity check on allowed Python system dep failed.")

        cmd = ' '.join([
            cfg['preconfigopts'],
            'echo "Configured"',
            cfg['configopts']
        ])
        run_cmd(cmd)

        if os.path.exists("%s.source" % name):
            os.rename('%s.source' % name, '%s.c' % name)

    def build_step(self, name=None, cfg=None):
        """Build toy."""
        # Allow overwrite from Toy-Extension
        if cfg is None:
            cfg = self.cfg
        if name is None:
            name = self.name

        cmd = compose_toy_build_cmd(self.cfg, name, cfg['prebuildopts'], cfg['buildopts'])
        # purposely run build command without checking exit code;
        # we rely on this in test_toy_build_hooks
        (out, ec) = run_cmd(cmd, log_ok=False, log_all=False)
        if ec:
            print_warning("Command '%s' failed, but we'll ignore it..." % cmd)

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
        write_file(os.path.join(libdir, 'lib%s.a' % name), name.upper())

    @property
    def required_deps(self):
        """Return list of required dependencies for this extension."""
        if self.name == 'toy':
            return ['bar', 'barbar']
        else:
            raise EasyBuildError("Dependencies for %s are unknown!", self.name)

    def prerun(self):
        """
        Prepare installation of toy as extension.
        """
        super(EB_toy, self).run(unpack_src=True)
        self.configure_step()

    def run(self):
        """
        Install toy as extension.
        """
        self.build_step()

    def run_async(self):
        """
        Asynchronous installation of toy as extension.
        """
        cmd = compose_toy_build_cmd(self.cfg, self.name, self.cfg['prebuildopts'], self.cfg['buildopts'])
        self.async_cmd_start(cmd)

    def postrun(self):
        """
        Wrap up installation of toy as extension.
        """
        self.install_step()

    def make_module_step(self, fake=False):
        """Generate module file."""
        if self.cfg.get('make_module', True) or fake:
            modpath = super(EB_toy, self).make_module_step(fake=fake)
        else:
            modpath = self.module_generator.get_modules_path(fake=fake)

        return modpath

    def make_module_extra(self):
        """Extra stuff for toy module"""
        txt = super(EB_toy, self).make_module_extra()
        txt += self.module_generator.set_environment('TOY', os.getenv('TOY', '<TOY_env_var_not_defined>'))
        return txt
