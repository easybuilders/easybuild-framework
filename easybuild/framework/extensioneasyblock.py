##
# Copyright 2013-2022 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
EasyBuild support for building and installing extensions as actual extensions or as stand-alone modules,
implemented as an easyblock

:author: Kenneth Hoste (Ghent University)
"""
import copy
import os

from easybuild.base import fancylogger
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.extension import Extension
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import change_dir, extract_file
from easybuild.tools.utilities import remove_unwanted_chars, trace_msg


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
            # make sure that extra custom easyconfig parameters are known
            extra_params = self.__class__.extra_options()
            kwargs['extra_params'] = extra_params

            Extension.__init__(self, *args, **kwargs)

            # name and version properties of EasyBlock are used, so make sure name and version are correct
            self.cfg['name'] = self.ext.get('name', None)
            self.cfg['version'] = self.ext.get('version', None)
            # We can't inherit the 'start_dir' value from the parent (which will be set, and will most likely be wrong).
            # It should be specified for the extension specifically, or be empty (so it is auto-derived).
            self.cfg['start_dir'] = self.ext.get('options', {}).get('start_dir', None)
            self.builddir = self.master.builddir
            self.installdir = self.master.installdir
            self.modules_tool = self.master.modules_tool
            self.module_generator = self.master.module_generator
            self.robot_path = self.master.robot_path
            self.is_extension = True
            self.unpack_options = None
        else:
            EasyBlock.__init__(self, *args, **kwargs)
            self.options = copy.deepcopy(self.cfg.get('options', {}))  # we need this for Extension.sanity_check_step

        self.ext_dir = None  # dir where extension source was unpacked

    def _set_start_dir(self):
        """Set value for self.start_dir

        Uses existing value of self.start_dir if it is already set and exists
        otherwise self.ext_dir (path to extracted source) if that is set and exists, similar to guess_start_dir
        """
        possible_dirs = (self.start_dir, self.ext_dir)
        for possible_dir in possible_dirs:
            if possible_dir and os.path.isdir(possible_dir):
                self.cfg['start_dir'] = possible_dir
                self.log.debug("Using start_dir: %s", self.start_dir)
                return
        self.log.debug("Unable to determine start_dir as none of these paths is set and exists: %s", possible_dirs)

    def run(self, unpack_src=False):
        """Common operations for extensions: unpacking sources, patching, ..."""

        # unpack file if desired
        if unpack_src:
            targetdir = os.path.join(self.master.builddir, remove_unwanted_chars(self.name))
            self.ext_dir = extract_file(self.src, targetdir, extra_options=self.unpack_options,
                                        change_into_dir=False, cmd=self.src_extract_cmd)

            # setting start dir must be done from unpacked source directory for extension,
            # because start_dir value is usually a relative path (if it is set)
            change_dir(self.ext_dir)

            self._set_start_dir()
            change_dir(self.start_dir)
        else:
            self._set_start_dir()

        # patch if needed
        EasyBlock.patch_step(self, beginpath=self.ext_dir)

    def sanity_check_step(self, exts_filter=None, custom_paths=None, custom_commands=None):
        """
        Custom sanity check for extensions, whether installed as stand-alone module or not
        """
        if not self.cfg.get_ref('exts_filter'):
            self.cfg['exts_filter'] = exts_filter
        self.log.debug("starting sanity check for extension with filter %s", self.cfg.get_ref('exts_filter'))

        # for stand-alone installations that were done for multiple dependency versions (via multi_deps),
        # we need to perform the extension sanity check for each of them, by loading the corresponding modules first
        if self.cfg['multi_deps'] and not self.is_extension:
            multi_deps = self.cfg.get_parsed_multi_deps()
            lists_of_extra_modules = [[d['short_mod_name'] for d in deps] for deps in multi_deps]
        else:
            # make sure Extension sanity check step is run once, by using a single empty list of extra modules
            lists_of_extra_modules = [[]]

        for extra_modules in lists_of_extra_modules:

            fake_mod_data = None

            # only load fake module + extra modules for stand-alone installations (not for extensions),
            # since for extension the necessary modules should already be loaded at this point
            if not (self.is_extension or self.dry_run):
                # load fake module
                fake_mod_data = self.load_fake_module(purge=True, extra_modules=extra_modules)

                if extra_modules:
                    info_msg = "Running extension sanity check with extra modules: %s" % ', '.join(extra_modules)
                    self.log.info(info_msg)
                    trace_msg(info_msg)

            # perform extension sanity check
            (sanity_check_ok, fail_msg) = Extension.sanity_check_step(self)

            if fake_mod_data:
                # unload fake module and clean up
                self.clean_up_fake_module(fake_mod_data)

        if custom_paths or custom_commands or not self.is_extension:
            super(ExtensionEasyBlock, self).sanity_check_step(custom_paths=custom_paths,
                                                              custom_commands=custom_commands,
                                                              extension=self.is_extension)

        # pass or fail sanity check
        if sanity_check_ok:
            self.log.info("Sanity check for %s successful!", self.name)
        else:
            if not self.is_extension:
                msg = "Sanity check for %s failed: %s" % (self.name, '; '.join(self.sanity_check_fail_msgs))
                raise EasyBuildError(msg)

        return (sanity_check_ok, '; '.join(self.sanity_check_fail_msgs))

    def make_module_extra(self, extra=None):
        """Add custom entries to module."""

        txt = EasyBlock.make_module_extra(self)
        if extra is not None:
            txt += extra
        return txt
