##
# Copyright 2013-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
"""
EasyBuild support for building and installing extensions as actual extensions or as stand-alone modules,
implemented as an easyblock

@author: Kenneth Hoste (Ghent University)
"""
import copy
import os
from vsc.utils import fancylogger

from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.extension import Extension
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import apply_patch, extract_file
from easybuild.tools.utilities import remove_unwanted_chars


_log = fancylogger.getLogger('extensioneasyblock', fname=False)


class ExtensionEasyBlock(EasyBlock, Extension):
    """
    Install an extension as a separate module, or as an extension.

    Deriving classes should implement the following functions:
    * required EasyBlock functions:
      - configure_step
      - build_step
      - install_step
    * required Extension functions
      - run
    """

    @staticmethod
    def extra_options(extra_vars=None):
        """Extra easyconfig parameters specific to ExtensionEasyBlock."""
        if extra_vars is None:
            extra_vars = {}

        if not isinstance(extra_vars, dict):
            _log.nosupport("Obtained value of type '%s' for extra_vars, should be 'dict'" % type(extra_vars), '2.0')

        extra_vars.update({
            'options': [{}, "Dictionary with extension options.", CUSTOM],
        })
        return EasyBlock.extra_options(extra_vars)

    def __init__(self, *args, **kwargs):
        """Initialize either as EasyBlock or as Extension."""

        self.is_extension = False

        if isinstance(args[0], EasyBlock):
            Extension.__init__(self, *args, **kwargs)
            # name and version properties of EasyBlock are used, so make sure name and version are correct
            self.cfg['name'] = self.ext.get('name', None)
            self.cfg['version'] = self.ext.get('version', None)
            self.builddir = self.master.builddir
            self.installdir = self.master.installdir
            self.is_extension = True
            self.unpack_options = None

            # make sure that extra custom easyconfig parameters are known
            extra_params = self.__class__.extra_options()
            self.cfg.extend_params(extra_params, overwrite=False)
        else:
            EasyBlock.__init__(self, *args, **kwargs)
            self.options = copy.deepcopy(self.cfg.get('options', {}))  # we need this for Extension.sanity_check_step

        self.ext_dir = None  # dir where extension source was unpacked

    def run(self, unpack_src=False):
        """Common operations for extensions: unpacking sources, patching, ..."""

        # unpack file if desired
        if unpack_src:
            targetdir = os.path.join(self.master.builddir, remove_unwanted_chars(self.name))
            self.ext_dir = extract_file("%s" % self.src, targetdir, extra_options=self.unpack_options)

        # patch if needed
        if self.patches:
            for patchfile in self.patches:
                if not apply_patch(patchfile, self.ext_dir):
                    raise EasyBuildError("Applying patch %s failed", patchfile)

    def sanity_check_step(self, exts_filter=None, custom_paths=None, custom_commands=None):
        """
        Custom sanity check for extensions, whether installed as stand-alone module or not
        """
        if not self.cfg['exts_filter']:
            self.cfg['exts_filter'] = exts_filter
        self.log.debug("starting sanity check for extension with filter %s", self.cfg['exts_filter'])

        fake_mod_data = None
        if not (self.is_extension or self.dry_run):
            # load fake module
            fake_mod_data = self.load_fake_module(purge=True)

        # perform sanity check
        sanity_check_ok = Extension.sanity_check_step(self)

        if fake_mod_data:
            # unload fake module and clean up
            self.clean_up_fake_module(fake_mod_data)

        if custom_paths or custom_commands or not self.is_extension:
            super(ExtensionEasyBlock, self).sanity_check_step(custom_paths=custom_paths,
                                                              custom_commands=custom_commands,
                                                              extension=self.is_extension)

        # pass or fail sanity check
        if not sanity_check_ok:
            msg = "Sanity check for %s failed: %s" % (self.name, '; '.join(self.sanity_check_fail_msgs))
            if self.is_extension:
                self.log.warning(msg)
            else:
                raise EasyBuildError(msg)
            return False
        else:
            self.log.info("Sanity check for %s successful!" % self.name)
            return True

    def make_module_extra(self, extra=None):
        """Add custom entries to module."""

        txt = EasyBlock.make_module_extra(self)
        if not extra is None:
            txt += extra
        return txt
