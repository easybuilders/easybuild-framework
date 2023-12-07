##
# Copyright 2009-2023 Ghent University
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
Generic EasyBuild support for software extensions (e.g. Python packages).
The Extension class should serve as a base class for all extensions.

Authors:

* Stijn De Weirdt (Ghent University)
* Dries Verdegem (Ghent University)
* Kenneth Hoste (Ghent University)
* Pieter De Baets (Ghent University)
* Jens Timmerman (Ghent University)
* Toon Willems (Ghent University)
"""
import copy
import os

from easybuild.framework.easyconfig.easyconfig import resolve_template
from easybuild.framework.easyconfig.templates import TEMPLATE_NAMES_EASYBLOCK_RUN_STEP, template_constant_dict
from easybuild.tools.build_log import EasyBuildError, raise_nosupport
from easybuild.tools.filetools import change_dir
from easybuild.tools.run import check_async_cmd, run_cmd
from easybuild.tools.py2vs3 import string_type


def resolve_exts_filter_template(exts_filter, ext):
    """
    Resolve the exts_filter tuple by replacing the template values using the extension
    :param exts_filter: Tuple of (command, input) using template values (ext_name, ext_version, src)
    :param ext: Instance of Extension or dictionary like with 'name' and optionally 'options', 'version', 'source' keys
    :return: (cmd, input) as a tuple of strings
    """

    if isinstance(exts_filter, string_type) or len(exts_filter) != 2:
        raise EasyBuildError('exts_filter should be a list or tuple of ("command","input")')

    cmd, cmdinput = exts_filter

    if not isinstance(ext, dict):
        ext = {'name': ext.name, 'version': ext.version, 'src': ext.src, 'options': ext.options}

    name = ext['name']
    if 'options' in ext and 'modulename' in ext['options']:
        modname = ext['options']['modulename']
    else:
        modname = name
    tmpldict = {
        'ext_name': modname,
        'ext_version': ext.get('version'),
        'src': ext.get('src'),
    }

    try:
        cmd = cmd % tmpldict
        cmdinput = cmdinput % tmpldict if cmdinput else None
    except KeyError as err:
        msg = "KeyError occurred on completing extension filter template: %s; "
        msg += "'name'/'version' keys are no longer supported, should use 'ext_name'/'ext_version' instead"
        raise_nosupport(msg % err, '2.0')
    return cmd, cmdinput


class Extension(object):
    """
    Support for installing extensions.
    """

    def __init__(self, mself, ext, extra_params=None):
        """
        Constructor for Extension class

        :param mself: parent Easyblock instance
        :param ext: dictionary with extension metadata (name, version, src, patches, options, ...)
        :param extra_params: extra custom easyconfig parameters to take into account for this extension
        """
        self.master = mself
        self.log = self.master.log
        self.cfg = self.master.cfg.copy(validate=False)
        self.ext = copy.deepcopy(ext)
        self.dry_run = self.master.dry_run

        if 'name' not in self.ext:
            raise EasyBuildError("'name' is missing in supplied class instance 'ext'.")

        name, version = self.ext['name'], self.ext.get('version', None)

        # parent sanity check paths/commands and postinstallcmds are not relevant for extension
        self.cfg['sanity_check_commands'] = []
        self.cfg['sanity_check_paths'] = []
        self.cfg['postinstallcmds'] = []

        # construct dict with template values that can be used
        self.cfg.template_values.update(template_constant_dict({'name': name, 'version': version}))

        # Add install/builddir templates with values from master.
        for key in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP:
            self.cfg.template_values[key[0]] = str(getattr(self.master, key[0], None))

        # We can't inherit the 'start_dir' value from the parent (which will be set, and will most likely be wrong).
        # It should be specified for the extension specifically, or be empty (so it is auto-derived).
        self.cfg['start_dir'] = self.ext.get('options', {}).get('start_dir', None)
        # Also clear the template
        del self.cfg.template_values['start_dir']

        # list of source/patch files: we use an empty list as default value like in EasyBlock
        self.src = resolve_template(self.ext.get('src', []), self.cfg.template_values)
        self.src_extract_cmd = self.ext.get('extract_cmd', None)
        self.patches = resolve_template(self.ext.get('patches', []), self.cfg.template_values)
        self.options = resolve_template(copy.deepcopy(self.ext.get('options', {})), self.cfg.template_values)

        if extra_params:
            self.cfg.extend_params(extra_params, overwrite=False)

        # custom easyconfig parameters for extension are included in self.options
        # make sure they are merged into self.cfg so they can be queried;
        # unknown easyconfig parameters are ignored since self.options may include keys only there for extensions;
        # this allows to specify custom easyconfig parameters on a per-extension basis
        for key, value in self.options.items():
            if key in self.cfg:
                self.cfg[key] = value
                self.log.debug("Customising known easyconfig parameter '%s' for extension %s/%s: %s",
                               key, name, version, value)
            else:
                self.log.debug("Skipping unknown custom easyconfig parameter '%s' for extension %s/%s: %s",
                               key, name, version, value)

        self.sanity_check_fail_msgs = []
        self.sanity_check_module_loaded = False
        self.fake_mod_data = None

        self.async_cmd_info = None
        self.async_cmd_output = None
        self.async_cmd_check_cnt = None
        # initial read size should be relatively small,
        # to avoid hanging for a long time until desired output is available in async_cmd_check
        self.async_cmd_read_size = 1024

    @property
    def name(self):
        """
        Shortcut the get the extension name.
        """
        return self.ext.get('name', None)

    @property
    def version(self):
        """
        Shortcut the get the extension version.
        """
        return self.ext.get('version', None)

    def prerun(self):
        """
        Stuff to do before installing a extension.
        """
        pass

    def run(self, *args, **kwargs):
        """
        Actual installation of an extension.
        """
        pass

    def run_async(self, *args, **kwargs):
        """
        Asynchronous installation of an extension.
        """
        raise NotImplementedError

    def postrun(self):
        """
        Stuff to do after installing a extension.
        """
        self.master.run_post_install_commands(commands=self.cfg.get('postinstallcmds', []))

    def async_cmd_start(self, cmd, inp=None):
        """
        Start installation asynchronously using specified command.
        """
        self.async_cmd_output = ''
        self.async_cmd_check_cnt = 0
        self.async_cmd_info = run_cmd(cmd, log_all=True, simple=False, inp=inp, regexp=False, asynchronous=True)

    def async_cmd_check(self):
        """
        Check progress of installation command that was started asynchronously.

        :return: True if command completed, False otherwise
        """
        if self.async_cmd_info is None:
            raise EasyBuildError("No installation command running asynchronously for %s", self.name)
        elif self.async_cmd_info is False:
            self.log.info("No asynchronous command was started for extension %s", self.name)
            return True
        else:
            self.log.debug("Checking on installation of extension %s...", self.name)
            # use small read size, to avoid waiting for a long time until sufficient output is produced
            res = check_async_cmd(*self.async_cmd_info, output_read_size=self.async_cmd_read_size)
            self.async_cmd_output += res['output']
            if res['done']:
                self.log.info("Installation of extension %s completed!", self.name)
                self.async_cmd_info = None
            else:
                self.async_cmd_check_cnt += 1
                self.log.debug("Installation of extension %s still running (checked %d times)",
                               self.name, self.async_cmd_check_cnt)
                # increase read size after sufficient checks,
                # to avoid that installation hangs due to output buffer filling up...
                if self.async_cmd_check_cnt % 10 == 0 and self.async_cmd_read_size < (1024 ** 2):
                    self.async_cmd_read_size *= 2

            return res['done']

    @property
    def required_deps(self):
        """Return list of required dependencies for this extension."""
        self.log.info("Don't know how to determine required dependencies for extension '%s'", self.name)
        return None

    @property
    def toolchain(self):
        """
        Toolchain used to build this extension.
        """
        return self.master.toolchain

    def sanity_check_step(self):
        """
        Sanity check to run after installing extension
        """
        res = (True, '')

        if os.path.isdir(self.installdir):
            change_dir(self.installdir)

        # Get raw value to translate ext_name, ext_version, src
        exts_filter = self.cfg.get_ref('exts_filter')

        if exts_filter is None:
            self.log.debug("no exts_filter setting found, skipping sanitycheck")

        if 'modulename' in self.options:
            modname = self.options['modulename']
            self.log.debug("modulename found in self.options, using it: %s", modname)
        else:
            modname = self.name
            self.log.debug("self.name: %s", modname)

        # allow skipping of sanity check by setting module name to False
        if modname is False:
            self.log.info("modulename set to False for '%s' extension, so skipping sanity check", self.name)
        elif exts_filter:
            cmd, stdin = resolve_exts_filter_template(exts_filter, self)
            # set log_ok to False so we can catch the error instead of run_cmd
            (output, ec) = run_cmd(cmd, log_ok=False, simple=False, regexp=False, inp=stdin)

            if ec:
                if stdin:
                    fail_msg = 'command "%s" (stdin: "%s") failed' % (cmd, stdin)
                else:
                    fail_msg = 'command "%s" failed' % cmd
                fail_msg += "; output:\n%s" % output.strip()
                self.log.warning("Sanity check for '%s' extension failed: %s", self.name, fail_msg)
                res = (False, fail_msg)
                # keep track of all reasons of failure
                # (only relevant when this extension is installed stand-alone via ExtensionEasyBlock)
                self.sanity_check_fail_msgs.append(fail_msg)

        return res
