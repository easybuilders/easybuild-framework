##
# Copyright 2013-2025 Ghent University
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

Authors:

* Kenneth Hoste (Ghent University)
"""
import copy
import os

from easybuild.base import fancylogger
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.extension import Extension
from easybuild.tools.build_log import EasyBuildError, print_warning
from easybuild.tools.config import build_option
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
        """Set absolute path of self.start_dir similarly to EasyBlock.guess_start_dir

        Uses existing value of self.start_dir defaulting to self.ext_dir.
        If self.ext_dir (path to extracted source) is set, it is used as the base dir for relative paths.
        Otherwise otherwise self.builddir is used as the base.
        When neither start_dir nor ext_dir are set or when the computed start_dir does not exist
        the start dir is not changed.
        The computed start dir will not end in path separators
        """
        ext_start_dir = self.start_dir
        if self.ext_dir:
            if not os.path.isabs(self.ext_dir):
                raise EasyBuildError("ext_dir must be an absolute path. Is: '%s'", self.ext_dir)
            ext_start_dir = os.path.join(self.ext_dir, ext_start_dir or '')
        elif ext_start_dir is not None:
            if not os.path.isabs(self.builddir):
                raise EasyBuildError("builddir must be an absolute path. Is: '%s'", self.builddir)
            ext_start_dir = os.path.join(self.builddir, ext_start_dir)

        if ext_start_dir and os.path.isdir(ext_start_dir):
            ext_start_dir = ext_start_dir.rstrip(os.sep) or os.sep
            self.log.debug("Using extension start dir: %s", ext_start_dir)
            self.cfg['start_dir'] = ext_start_dir
            self.cfg.template_values['start_dir'] = ext_start_dir
        elif ext_start_dir is None:
            # This may be on purpose, e.g. for Python WHL files which do not get extracted
            self.log.debug("Start dir is not set.")
        elif self.start_dir:
            # non-existing start dir means wrong input from user
            raise EasyBuildError("Provided start dir (%s) for extension %s does not exist: %s",
                                 self.start_dir, self.name, ext_start_dir)
        else:
            warn_msg = 'Failed to determine start dir for extension %s: %s' % (self.name, ext_start_dir)
            self.log.warning(warn_msg)
            print_warning(warn_msg, silent=build_option('silent'))

    def run(self, unpack_src=False):
        """Common operations for extensions: unpacking sources, patching, ..."""

        # unpack file if desired
        if self.options.get('nosource', False):
            # If no source wanted use the start_dir from the main EC
            self.ext_dir = self.master.start_dir
        elif unpack_src:
            targetdir = os.path.join(self.master.builddir, remove_unwanted_chars(self.name))
            self.ext_dir = extract_file(self.src, targetdir, extra_options=self.unpack_options,
                                        change_into_dir=False, cmd=self.src_extract_cmd)

            # setting start dir must be done from unpacked source directory for extension,
            # because start_dir value is usually a relative path (if it is set)
            change_dir(self.ext_dir)

        self._set_start_dir()
        if self.start_dir:
            change_dir(self.start_dir)

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
            # since for extension the necessary modules should already be loaded at this point;
            # take into account that module may already be loaded earlier in sanity check
            if not (self.sanity_check_module_loaded or self.is_extension or self.dry_run):
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
