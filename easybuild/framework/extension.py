##
# Copyright 2009-2026 Ghent University
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
from collections import namedtuple
from concurrent.futures import Future
from logging import Logger
from typing import Any, Dict, List, Optional, Tuple, Union

from easybuild.base import fancylogger
from easybuild.framework.easyconfig.default import get_easyconfig_parameter_default
from easybuild.framework.easyconfig.easyconfig import resolve_template
from easybuild.framework.easyconfig.templates import TEMPLATE_NAMES_EASYBLOCK_RUN_STEP, template_constant_dict
from easybuild.tools.build_log import EasyBuildError, EasyBuildExit
from easybuild.tools.deprecated_dict import make_deprecated_key_accessor, dict_update_to_setitem
from easybuild.tools.filetools import change_dir
from easybuild.tools.run import run_shell_cmd, RunShellCmdResult
from easybuild.tools.utilities import trace_msg

_log = fancylogger.getLogger('extension', fname=False)


class _ExtensionOptions:
    """
    Options for an extension, exposed as a (deprecated) view over the easyconfig parameters.

    Keys that are known easyconfig parameters are read from and written to the owning
    extension's easyconfig any other key is stored in this dictionary itself.

    Accessing this object, typically via the deprecated `Extension.options` attribute,
    should be replaced by using the corresponding easyconfig parameter(s) directly.
    """

    _decorator = make_deprecated_key_accessor(key_description="Extension option key", deprecated_keys={
        'modulename': ('load_name', '6.0'),
        'parallel': ('max_parallel', '6.0'),
    })

    def __init__(self, extension: 'Extension'):
        super().__init__()
        self._ext = extension
        self._unknown_opts: dict[str, Any] = {}

    @property
    def _cfg(self):
        return self._ext.cfg

    def _check_is_param(self, key: str) -> bool:
        """Check whether the key is a known easyconfig parameter."""
        if key in self._cfg:
            return True
        self._ext.log.deprecated(
            f"Extension option '{key}' for {self._ext.name}/{self._ext.version} is not a known easyconfig parameter; "
            f"declare it as an easyconfig parameter for {type(self._ext).name}", '6.0')
        return False

    @_decorator
    def __contains__(self, key) -> bool:
        try:
            self[key]  # Reuse logic below
            return True
        except KeyError:
            return False

    @_decorator
    def __getitem__(self, key):
        if self._check_is_param(key):
            value = self._cfg.get(key)
            # A parameter is considered set when it was given a value other than None.
            # None may not be the default value in general but is OK for the (previously) known extension options
            if value is None:
                raise KeyError(key)
            return value
        return self._unknown_opts[key]

    @_decorator
    def __setitem__(self, key, value):
        if self._check_is_param(key):
            self._cfg[key] = value
        else:
            self._unknown_opts[key] = value

    @_decorator
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    @_decorator
    def setdefault(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return default

    @_decorator
    def pop(self, key, *args):
        if self._check_is_param(key):
            # a parameter cannot really be removed, so reset it to None
            value = self._cfg[key]
            self._cfg[key] = None
            return value
        return self._unknown_opts.pop(key, *args)

    update = dict_update_to_setitem


def get_load_names(ext: 'Extension') -> List[str]:
    """Return a list of load names for the extension"""
    cfg = ext.cfg
    load_names = cfg.get('load_name')
    if load_names is None:
        load_names = cfg.get('extension_name')
        if load_names is None:
            load_names = ext.name

    if load_names is False:
        return []
    if not load_names:
        raise EasyBuildError(f"Empty load_name for {ext.name} is not supported."
                             "Use `False` to skip checking for module existence!")
    if isinstance(load_names, list):
        return load_names
    elif isinstance(load_names, str):
        return [load_names]
    raise EasyBuildError(f"Invalid type for load_name of {ext.name}. "
                         f"Expected False, str, or list, but got {type(load_names).__name__}: {load_names}")


def _dict_to_ExtensionLike(ext: Dict[str, Any]):
    """Convert a dictionary to a named tuple similar enough to an extension for get_load_names

    Handles modulename to load_name transition.
    """
    options = ext.get('options', {})
    if 'modulename' in options:
        if 'load_name' in options:
            raise EasyBuildError("Both 'load_name' and deprecated 'modulename' "
                                 f"are specified for extension {ext['name']}")
        _log.deprecated("Extension option 'modulename' is deprecated, "
                        "use the 'load_name' easyconfig parameter instead", '6.0')
        options = copy.deepcopy(options)
        options['load_name'] = options.pop('modulename')

    ExtensionLike = namedtuple('ExtensionLike', ('name', 'version', 'cfg', 'src'))
    cfg = copy.deepcopy(ext)
    cfg.update(options)
    return ExtensionLike(ext['name'], ext.get('version'), cfg, ext.get('src'))


def get_modulenames(ext: Union['Extension', Dict[str, Any]], use_name_for_false: bool):
    """[DEPRECATED] Return a list of load names for the extension, see get_load_names()
    :param ext: Instance of Extension or dictionary with 'name' and optionally 'options', 'version', 'src' keys
    :param use_name_for_false: Whether to return a list with the name or an empty list when the load_name is False
    """
    _log.deprecated("get_modulenames() is deprecated, use get_load_names() instead", '6.0')
    if isinstance(ext, dict):
        _log.deprecated("Extension instance should be passed to get_modulenames instead of dict", '6.0')
        ext = _dict_to_ExtensionLike(ext)
    result = get_load_names(ext)
    if not result and use_name_for_false:
        result = ext.name
    return result


def construct_exts_filter_cmds(exts_filter: Union[str, Tuple[str, str]], ext: Union['Extension', Dict[str, Any]],
                               log: Logger = _log) -> List[Tuple[str, Optional[str]]]:
    """
    Resolve the exts_filter tuple by replacing the template values using the extension
    :param exts_filter: Tuple of (command, input) using template values (ext_name, ext_version, src)
    :param ext: Instance of Extension or (DEPRECATED): dictionary with 'name' and opt. 'options', 'version', 'src' keys
    :return: (cmd, input) as a tuple of strings for each load name. Might be empty if no filtering is intented
    """

    if isinstance(exts_filter, str) or len(exts_filter) != 2:
        raise EasyBuildError('exts_filter should be a list or tuple of ("command","input"), '
                             f"got: {exts_filter} (type {type(exts_filter)})")

    cmd, cmdinput = exts_filter

    if isinstance(ext, dict):
        log.deprecated("Extension instance should be passed to construct_exts_filter_cmds instead of dict", '6.0')
        ext = _dict_to_ExtensionLike(ext)

    load_names = get_load_names(ext)

    result = []
    for load_name in load_names:
        tmpl_dict = {
            'ext_name': load_name,
            'ext_version': ext.version,
            'src': ext.src,
        }
        try:
            result.append((cmd % tmpl_dict,
                           cmdinput % tmpl_dict if cmdinput else None))
        except KeyError as err:
            raise EasyBuildError(f"KeyError occurred on completing extension filter template '{exts_filter}': {err}")
    return result


class Extension:
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
        self.async_cmd_task: Optional[Future[RunShellCmdResult]] = None

        # Make extra params known
        if extra_params:
            self.cfg.extend_params(extra_params, overwrite=False)

        if 'name' not in self.ext:
            raise EasyBuildError("'name' is missing in supplied class instance 'ext'.")

        name, version = self.ext['name'], self.ext.get('version', None)

        # Reset some options that should not be inherited from the parent
        restore_options = (
            'checksums',
            'data_sources',
            'extension_name',
            'patches',
            'postinstallcmds',
            'sanity_check_commands',
            'sanity_check_paths',
            'skipsteps',
            'sources',
        )
        for opt_name in restore_options:
            self.cfg[opt_name] = get_easyconfig_parameter_default(opt_name)

        # Update name and version
        self.cfg['name'] = name
        self.cfg['version'] = version
        # construct dict with template values that can be used
        self.cfg.template_values.update(template_constant_dict({'name': name, 'version': version}))

        # Add install/builddir templates with values from master.
        for key in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP:
            self.cfg.template_values[key] = str(getattr(self.master, key, None))

        # We can't inherit the 'start_dir' value from the parent (which will be set, and will most likely be wrong).
        # It should be specified for the extension specifically, or be empty (so it is auto-derived).
        self.cfg['start_dir'] = self.ext.get('options', {}).get('start_dir', None)
        # Also clear the template
        del self.cfg.template_values['start_dir']

        # list of source/patch files: we use an empty list as default value like in EasyBlock
        self.src = resolve_template(self.ext.get('src', []), self.cfg.template_values)
        self.src_extract_cmd = self.ext.get('extract_cmd', None)
        self.patches = resolve_template(self.ext.get('patches', []), self.cfg.template_values)
        # Some options may not be resolvable yet
        options = resolve_template(copy.deepcopy(self.ext.get('options', {})),
                                   self.cfg.template_values,
                                   expect_resolved=False)
        # Custom easyconfig parameters for extension are included in self.options
        # make sure they are merged into self.cfg so they can be queried;
        # this allows to specify custom easyconfig parameters on a per-extension basis
        self._options = _ExtensionOptions(self)
        self._options.update(options)
        for key, value in options.items():
            if key in self.cfg:
                # Log only for now, setting done by _options.update
                self.log.debug("Customising known easyconfig parameter '%s' for extension %s/%s: %s",
                               key, name, version, value)
            else:
                # TODO: Error out when removing self.options
                # Deprecation warning triggered by _options.update
                self.log.debug("Unknown custom easyconfig parameter '%s' for extension %s/%s: %s",
                               key, name, version, value)

        # If parallelism has been set already take potentially new limitation into account
        if self.cfg.is_parallel_set:
            max_par = self.cfg['max_parallel']
            if max_par is not None and max_par < self.cfg.parallel:
                self.cfg.parallel = max_par

        self.sanity_check_fail_msgs = []
        self.sanity_check_module_loaded = False
        self.fake_mod_data = None

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

    @property
    def options(self) -> Dict[str, Any]:
        """[DEPRECATED] Dictionary with options for this extension"""
        self.log.deprecated("The 'options' attribute of Extension is deprecated, "
                            "use the corresponding easyconfig parameter(s) instead", '6.0', exception=None)
        return self._options

    @options.setter
    def options(self, value: Dict[str, Any]):
        self.log.deprecated("Setting the 'options' attribute of Extension is deprecated, "
                            "use the corresponding easyconfig parameter(s) instead", '6.0')
        if not isinstance(value, dict):
            raise EasyBuildError(f"Extension options should be a dict, got {type(value).__name__}")
        self._options = _ExtensionOptions(self)
        self._options.update(value)

    def prerun(self):
        """
        [DEPRECATED][6.0] Stuff to do before installing a extension.
        """
        # Deprecation warning triggered by Extension.install_extension_substep()
        self.pre_install_extension()

    def pre_install_extension(self):
        """
        Stuff to do before installing a extension.
        """
        pass

    def run(self, *args, **kwargs):
        """
        [DEPRECATED][6.0] Actual installation of an extension.
        """
        # Deprecation warning triggered by Extension.install_extension_substep()
        self.install_extension(*args, **kwargs)

    def install_extension(self, *args, **kwargs):
        """
        Actual installation of an extension.
        """
        pass

    def run_async(self, *args, **kwargs):
        """
        [DEPRECATED][6.0] Asynchronous installation of an extension.
        """
        # Deprecation warning triggered by Extension.install_extension_substep()
        self.install_extension_async(*args, **kwargs)

    def install_extension_async(self, *args, **kwargs):
        """
        Asynchronous installation of an extension.
        """
        raise NotImplementedError

    def async_cmd_check(self) -> Optional[RunShellCmdResult]:
        """
        Check progress of installation command that was started asynchronously.
        :return: True if command completed, False otherwise
        """
        if self.async_cmd_task is None:
            raise EasyBuildError(f"async_cmd_check was called, but no asynchronous command running for {self.name}")

        if not self.async_cmd_task.done():
            return None

        res: RunShellCmdResult = self.async_cmd_task.result()
        self.log.info(f"Asynchronous command for {self.name} finished with exit code {res.exit_code}")
        return res

    def postrun(self):
        """
        [DEPRECATED][6.0] Stuff to do after installing a extension.
        """
        # Deprecation warning triggered by Extension.install_extension_substep()
        self.post_install_extension()

    def post_install_extension(self):
        """
        Stuff to do after installing a extension.
        """
        self.master.run_post_install_commands(commands=self.cfg.get('postinstallcmds', []))
        self.master.apply_post_install_patches(patches=[p for p in self.patches if p['postinstall']])
        self.master.print_post_install_messages(msgs=self.cfg.get('postinstallmsgs', []))

    def install_extension_substep(self, substep, *args, **kwargs):
        """
        Carry out extension installation substep allowing use of deprecated
        methods on those extensions using an older EasyBlock
        """
        substeps_mapping = {
            'pre_install_extension': 'prerun',
            'install_extension': 'run',
            'install_extension_async': 'run_async',
            'post_install_extension': 'postrun',
        }

        deprecated_substep = substeps_mapping.get(substep)
        if deprecated_substep is None:
            raise EasyBuildError("Unknown extension installation substep: %s", substep)

        try:
            substep_method = getattr(self, deprecated_substep)
        except AttributeError:
            log_msg = f"EasyBlock does not implement deprecated method '{deprecated_substep}' "
            log_msg += f"for installation substep {substep}"
            self.log.debug(log_msg)
            substep_method = getattr(self, substep)
        else:
            # Qualified method name contains class defining the method (PEP 3155)
            substep_method_name = substep_method.__qualname__
            self.log.debug(f"Found deprecated method in EasyBlock: {substep_method_name}")

            base_method_name = f"Extension.{deprecated_substep}"
            if substep_method_name == base_method_name:
                # No custom method in child Easyblock, deprecated method is defined by base Extension class
                # Switch to non-deprecated substep method
                substep_method = getattr(self, substep)
            else:
                # Custom deprecated method used by child Easyblock
                self.log.deprecated(
                    f"{substep_method_name}() is deprecated, use {substep}() instead.",
                    "6.0",
                )

        return substep_method(*args, **kwargs)

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
            return res

        exts_filter_cmds = construct_exts_filter_cmds(exts_filter, self)
        if not exts_filter_cmds:
            self.log.info("load_name set to False for '%s' extension, so skipping sanity check", self.name)
        else:
            fail_msgs = []
            for cmd, stdin in exts_filter_cmds:
                cmd_res = run_shell_cmd(cmd, fail_on_error=False, stdin=stdin, hidden=True)

                msg = f"Extension sanity check command '{cmd}': "
                if cmd_res.exit_code == EasyBuildExit.SUCCESS:
                    trace_msg(msg + 'OK')
                else:
                    trace_msg(msg + 'FAIL')
                    if stdin:
                        fail_msg = 'command "%s" (stdin: "%s") failed' % (cmd, stdin)
                    else:
                        fail_msg = 'command "%s" failed' % cmd
                    fail_msg += "; output:\n%s" % cmd_res.output.strip()
                    fail_msgs.append(fail_msg)
            if fail_msgs:
                fail_msg = '\n'.join(fail_msgs)
                self.log.warning("Sanity check for '%s' extension failed: %s", self.name, fail_msg)
                # keep track of all reasons of failure
                # (only relevant when this extension is installed stand-alone via ExtensionEasyBlock)
                self.sanity_check_fail_msgs.append(fail_msg)
                res = (False, fail_msg)

        return res
