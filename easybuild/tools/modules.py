##
# Copyright 2009-2021 Ghent University
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
This python module implements the environment modules functionality:
 - loading modules
 - checking for available modules
 - ...

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: David Brown (Pacific Northwest National Laboratory)
"""
import os
import re
import shlex
from distutils.version import StrictVersion

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError, print_warning
from easybuild.tools.config import ERROR, IGNORE, PURGE, UNLOAD, UNSET
from easybuild.tools.config import EBROOT_ENV_VAR_ACTIONS, LOADED_MODULES_ACTIONS
from easybuild.tools.config import build_option, get_modules_tool, install_path
from easybuild.tools.environment import ORIG_OS_ENVIRON, restore_env, setvar, unset_env_vars
from easybuild.tools.filetools import convert_name, mkdir, normalize_path, path_matches, read_file, which, write_file
from easybuild.tools.module_naming_scheme.mns import DEVEL_MODULE_SUFFIX
from easybuild.tools.py2vs3 import subprocess_popen_text
from easybuild.tools.run import run_cmd
from easybuild.tools.utilities import get_subclasses, nub

# software root/version environment variable name prefixes
ROOT_ENV_VAR_NAME_PREFIX = "EBROOT"
VERSION_ENV_VAR_NAME_PREFIX = "EBVERSION"
DEVEL_ENV_VAR_NAME_PREFIX = "EBDEVEL"

# environment variables to reset/restore when running a module command (to avoid breaking it)
# see e.g., https://bugzilla.redhat.com/show_bug.cgi?id=719785
LD_ENV_VAR_KEYS = ['LD_LIBRARY_PATH', 'LD_PRELOAD']

OUTPUT_MATCHES = {
    # matches whitespace and module-listing headers
    'whitespace': re.compile(r"^\s*$|^(-+).*(-+)$"),
    # matches errors such as "cmdTrace.c(713):ERROR:104: 'asdfasdf' is an unrecognized subcommand"
    # # following errors should not be matches, they are considered warnings
    # ModuleCmd_Avail.c(529):ERROR:57: Error while reading directory '/usr/local/modulefiles/SCIENTIFIC'
    # ModuleCmd_Avail.c(804):ERROR:64: Directory '/usr/local/modulefiles/SCIENTIFIC/tremolo' not found
    'error': re.compile(r"^\S+:(?P<level>\w+):(?P<code>(?!57|64)\d+):\s+(?P<msg>.*)$"),
    # 'available' with --terse has one module per line, with some extra lines (module path(s), module directories...)
    # regex below matches modules like 'ictce/3.2.1.015.u4', 'OpenMPI/1.6.4-no-OFED', ...
    #
    # Module lines notes:
    # * module name may have '(default)' appended [modulecmd]
    # ignored lines:
    # * module paths lines may start with a (empty) set of '-'s, which will be followed by a space [modulecmd.tcl]
    # * module paths may end with a ':' [modulecmd, lmod]
    # * module directories lines may end with a '/' [lmod >= 5.1.5]
    #
    # Note: module paths may be relative paths!
    #
    # Example outputs for the different supported module tools, for the same set of modules files (only two, both GCC):
    #
    #   $ modulecmd python avail --terse GCC > /dev/null
    #       /path/tomodules:
    #       GCC/4.6.3
    #       GCC/4.6.4(default)
    #
    #   $ lmod python avail --terse GCC > /dev/null
    #       /path/to/modules:
    #       GCC/
    #       GCC/4.6.3
    #       GCC/4.6.4
    #
    #   $ modulecmd.tcl python avail -t GCC > /dev/null
    #       -------- /path/to/modules --------
    #       GCC/4.6.3
    #       GCC/4.6.4
    #
    # Note on modulecmd.tcl: if the terminal is not wide enough, or the module path too long, the '-'s are not there!
    #
    # Any modules with a name that does not match the regex constructed below, will be HIDDEN from EasyBuild
    #
    'available': re.compile(r"""
        ^(?!-*\s)                     # disallow lines starting with (empty) list of '-'s followed by a space
        (?P<mod_name>                 # start named group for module name
            [^\s\(]*[^:/]             # module name must not have '(' or whitespace in it, must not end with ':' or '/'
        )                             # end named group for module name
        (?P<default>\(default\))?     # optional '(default)' that's not part of module name
        (\([^()]+\))?                 # ignore '(...)' that is not part of module name (e.g. for symbolic versions)
        \s*$                          # ignore whitespace at the end of the line
        """, re.VERBOSE),
}
# cache for result of module subcommands
# key: tuple with $MODULEPATH and (stringified) list of extra arguments/options for module subcommand
# value: result of module subcommand
MODULE_AVAIL_CACHE = {}
MODULE_SHOW_CACHE = {}

# cache for modules tool version
# cache key: module command
# value: corresponding (validated) module version
MODULE_VERSION_CACHE = {}


_log = fancylogger.getLogger('modules', fname=False)


class ModulesTool(object):
    """An abstract interface to a tool that deals with modules."""
    # name of this modules tool (used in log/warning/error messages)
    NAME = None
    # position and optionname
    TERSE_OPTION = (0, '--terse')
    # module command to use
    COMMAND = None
    # environment variable to determine path to module command;
    # used as fallback in case command is not available in $PATH
    COMMAND_ENVIRONMENT = None
    # run module command explicitly using this shell
    COMMAND_SHELL = None
    # option to determine the version
    VERSION_OPTION = '--version'
    # minimal required version (StrictVersion; suffix rc replaced with b (and treated as beta by StrictVersion))
    REQ_VERSION = None
    # deprecated version limit (support for versions below this version is deprecated)
    DEPR_VERSION = None
    # maximum version allowed (StrictVersion; suffix rc replaced with b (and treated as beta by StrictVersion))
    MAX_VERSION = None
    # the regexp, should have a "version" group (multiline search)
    VERSION_REGEXP = None
    # modules tool user cache directory
    USER_CACHE_DIR = None

    def __init__(self, mod_paths=None, testing=False):
        """
        Create a ModulesTool object
        :param mod_paths: A list of paths where the modules can be located
        @type mod_paths: list
        """
        # this can/should be set to True during testing
        self.testing = testing

        self.log = fancylogger.getLogger(self.NAME, fname=False)

        # DEPRECATED!
        self._modules = []

        # actual module command (i.e., not the 'module' wrapper function, but the binary)
        self.cmd = self.COMMAND

        if self.COMMAND_ENVIRONMENT:
            env_cmd_path = os.environ.get(self.COMMAND_ENVIRONMENT)
        else:
            env_cmd_path = None

        self.mod_paths = None
        if mod_paths is not None:
            self.set_mod_paths(mod_paths)

        if env_cmd_path:
            cmd_path = which(self.cmd, log_ok=False, on_error=IGNORE)
            # only use command path in environment variable if command in not available in $PATH
            if cmd_path is None:
                self.cmd = env_cmd_path
                self.log.debug("Set %s command via environment variable %s: %s",
                               self.NAME, self.COMMAND_ENVIRONMENT, self.cmd)
            # check whether paths obtained via $PATH and $LMOD_CMD are different
            elif cmd_path != env_cmd_path:
                self.log.debug("Different paths found for %s command '%s' via which/$PATH and $%s: %s vs %s",
                               self.NAME, self.COMMAND, self.COMMAND_ENVIRONMENT, cmd_path, env_cmd_path)

        # make sure the module command was found
        if self.cmd is None:
            raise EasyBuildError("No command set for %s", self.NAME)
        else:
            self.log.debug('Using %s command %s', self.NAME, self.cmd)

        # version of modules tool
        self.version = None

        # some initialisation/verification
        self.check_cmd_avail()
        self.check_module_path()
        self.check_module_function(allow_mismatch=build_option('allow_modules_tool_mismatch'))
        self.set_and_check_version()
        self.supports_depends_on = False

    def buildstats(self):
        """Return tuple with data to be included in buildstats"""
        return (self.NAME, self.cmd, self.version)

    def set_and_check_version(self):
        """Get the module version, and check any requirements"""
        if self.cmd in MODULE_VERSION_CACHE:
            self.version = MODULE_VERSION_CACHE[self.cmd]
            self.log.debug("Found cached version for %s command %s: %s", self.NAME, self.COMMAND, self.version)
            return

        if self.VERSION_REGEXP is None:
            raise EasyBuildError("No VERSION_REGEXP defined")

        try:
            txt = self.run_module(self.VERSION_OPTION, return_output=True, check_output=False, check_exit_code=False)

            ver_re = re.compile(self.VERSION_REGEXP, re.M)
            res = ver_re.search(txt)
            if res:
                self.version = res.group('version')
                self.log.info("Found %s version %s", self.NAME, self.version)

                # make sure version is a valid StrictVersion (e.g., 5.7.3.1 is invalid),
                # and replace 'rc' by 'b', to make StrictVersion treat it as a beta-release
                self.version = self.version.replace('rc', 'b').replace('-beta', 'b1')
                if len(self.version.split('.')) > 3:
                    self.version = '.'.join(self.version.split('.')[:3])

                self.log.info("Converted actual version to '%s'" % self.version)
            else:
                raise EasyBuildError("Failed to determine %s version from option '%s' output: %s",
                                     self.NAME, self.VERSION_OPTION, txt)
        except (OSError) as err:
            raise EasyBuildError("Failed to check %s version: %s", self.NAME, err)

        if self.REQ_VERSION is None and self.MAX_VERSION is None:
            self.log.debug("No version requirement defined.")

        elif build_option('modules_tool_version_check'):
            self.log.debug("Checking whether %s version %s meets requirements", self.NAME, self.version)

            if self.REQ_VERSION is not None:
                self.log.debug("Required minimum %s version defined: %s", self.NAME, self.REQ_VERSION)
                if StrictVersion(self.version) < StrictVersion(self.REQ_VERSION):
                    raise EasyBuildError("EasyBuild requires %s >= v%s, found v%s",
                                         self.NAME, self.REQ_VERSION, self.version)
                else:
                    self.log.debug('%s version %s matches requirement >= %s', self.NAME, self.version, self.REQ_VERSION)

            if self.DEPR_VERSION is not None:
                self.log.debug("Deprecated %s version limit defined: %s", self.NAME, self.DEPR_VERSION)
                if StrictVersion(self.version) < StrictVersion(self.DEPR_VERSION):
                    depr_msg = "Support for %s version < %s is deprecated, " % (self.NAME, self.DEPR_VERSION)
                    depr_msg += "found version %s" % self.version

                    silence_deprecation_warnings = build_option('silence_deprecation_warnings') or []

                    if self.version.startswith('6') and 'Lmod6' in silence_deprecation_warnings:
                        self.log.warning(depr_msg)
                    else:
                        self.log.deprecated(depr_msg, '5.0')

            if self.MAX_VERSION is not None:
                self.log.debug("Maximum allowed %s version defined: %s", self.NAME, self.MAX_VERSION)
                if StrictVersion(self.version) > StrictVersion(self.MAX_VERSION):
                    raise EasyBuildError("EasyBuild requires %s <= v%s, found v%s",
                                         self.NAME, self.MAX_VERSION, self.version)
                else:
                    self.log.debug('Version %s matches requirement <= %s', self.version, self.MAX_VERSION)
        else:
            self.log.debug("Skipping modules tool version '%s' requirements check", self.version)

        MODULE_VERSION_CACHE[self.cmd] = self.version

    def check_cmd_avail(self):
        """Check whether modules tool command is available."""
        cmd_path = which(self.cmd, log_ok=False)
        if cmd_path is not None:
            self.cmd = cmd_path
            self.log.info("Full path for %s command is %s, so using it", self.NAME, self.cmd)
        else:
            mod_tools = avail_modules_tools().keys()
            error_msg = "%s modules tool can not be used, '%s' command is not available" % (self.NAME, self.cmd)
            error_msg += "; use --modules-tool to specify a different modules tool to use (%s)" % ', '.join(mod_tools)
            raise EasyBuildError(error_msg)

    def check_module_function(self, allow_mismatch=False, regex=None):
        """Check whether selected module tool matches 'module' function definition."""
        if self.testing:
            # grab 'module' function definition from environment if it's there; only during testing
            if 'module' in os.environ:
                out, ec = os.environ['module'], 0
            else:
                out, ec = None, 1
        else:
            cmd = "type module"
            out, ec = run_cmd(cmd, simple=False, log_ok=False, log_all=False, force_in_dry_run=True, trace=False)

        if regex is None:
            regex = r".*%s" % os.path.basename(self.cmd)
        mod_cmd_re = re.compile(regex, re.M)
        mod_details = "pattern '%s' (%s)" % (mod_cmd_re.pattern, self.NAME)

        if ec == 0:
            if mod_cmd_re.search(out):
                self.log.debug("Found pattern '%s' in defined 'module' function." % mod_cmd_re.pattern)
            else:
                msg = "%s not found in defined 'module' function.\n" % mod_details
                msg += "Specify the correct modules tool to avoid weird problems due to this mismatch, "
                msg += "see the --modules-tool and --avail-modules-tools command line options.\n"
                if allow_mismatch:
                    msg += "Obtained definition of 'module' function: %s" % out
                    self.log.warning(msg)
                else:
                    msg += "Or alternatively, use --allow-modules-tool-mismatch to stop treating this as an error. "
                    msg += "Obtained definition of 'module' function: %s" % out
                    raise EasyBuildError(msg)
        else:
            # module function may not be defined (weird, but fine)
            self.log.warning("No 'module' function defined, can't check if it matches %s." % mod_details)

    def mk_module_cache_key(self, partial_key):
        """Create a module cache key, using the specified partial key, by combining it with the current $MODULEPATH."""
        return ('MODULEPATH=%s' % os.environ.get('MODULEPATH', ''), self.COMMAND, partial_key)

    def set_mod_paths(self, mod_paths=None):
        """
        Set mod_paths, based on $MODULEPATH unless a list of module paths is specified.

        :param mod_paths: list of entries for $MODULEPATH to use
        """
        # make sure we don't have the same path twice, using nub
        if mod_paths is None:
            # no paths specified, so grab list of (existing) module paths from $MODULEPATH
            self.mod_paths = nub(curr_module_paths())
        else:
            for mod_path in nub(mod_paths):
                self.prepend_module_path(mod_path, set_mod_paths=False)
            self.mod_paths = nub(mod_paths)

        self.log.debug("$MODULEPATH after set_mod_paths: %s" % os.environ.get('MODULEPATH', ''))

    def use(self, path, priority=None):
        """
        Add path to $MODULEPATH via 'module use'.

        :param path: path to add to $MODULEPATH
        :param priority: priority for this path in $MODULEPATH (Lmod-specific)
        """
        if priority:
            self.log.info("Ignoring specified priority '%s' when running 'module use %s' (Lmod-specific)",
                          priority, path)

        if not path:
            raise EasyBuildError("Cannot add empty path to $MODULEPATH")
        if not os.path.exists(path):
            self.log.deprecated("Path '%s' for module.use should exist" % path, '5.0')
            # make sure path exists before we add it
            mkdir(path, parents=True)
        self.run_module(['use', path])

    def unuse(self, path):
        """Remove module path via 'module unuse'."""
        self.run_module(['unuse', path])

    def add_module_path(self, path, set_mod_paths=True):
        """
        Add specified module path (using 'module use') if it's not there yet.

        :param path: path to add to $MODULEPATH via 'use'
        :param set_mod_paths: (re)set self.mod_paths
        """
        path = normalize_path(path)
        if path not in curr_module_paths(normalize=True):
            # add module path via 'module use' and make sure self.mod_paths is synced
            self.use(path)
            if set_mod_paths:
                self.set_mod_paths()

    def remove_module_path(self, path, set_mod_paths=True):
        """
        Remove specified module path (using 'module unuse').

        :param path: path to remove from $MODULEPATH via 'unuse'
        :param set_mod_paths: (re)set self.mod_paths
        """
        # remove module path via 'module unuse' and make sure self.mod_paths is synced
        path = normalize_path(path)
        try:
            # Unuse the path that is actually present in the environment
            module_path = next(p for p in curr_module_paths() if normalize_path(p) == path)
        except StopIteration:
            pass
        else:
            self.unuse(module_path)

            if set_mod_paths:
                self.set_mod_paths()

    def prepend_module_path(self, path, set_mod_paths=True, priority=None):
        """
        Prepend given module path to list of module paths, or bump it to 1st place.

        :param path: path to prepend to $MODULEPATH
        :param set_mod_paths: (re)set self.mod_paths
        :param priority: priority for this path in $MODULEPATH (Lmod-specific)
        """
        if priority:
            self.log.info("Ignoring specified priority '%s' when prepending %s to $MODULEPATH (Lmod-specific)",
                          priority, path)

        # generic approach: remove the path first (if it's there), then add it again (to the front)
        modulepath = curr_module_paths()
        if not modulepath:
            self.add_module_path(path, set_mod_paths=set_mod_paths)
        elif os.path.realpath(modulepath[0]) != os.path.realpath(path):
            self.remove_module_path(path, set_mod_paths=False)
            self.add_module_path(path, set_mod_paths=set_mod_paths)

    def check_module_path(self):
        """
        Check if MODULEPATH is set and change it if necessary.
        """
        # if self.mod_paths is not specified, define it and make sure the EasyBuild module path is in there (first)
        if self.mod_paths is None:
            # take (unique) module paths from environment
            self.set_mod_paths()
            self.log.debug("self.mod_paths set based on $MODULEPATH: %s" % self.mod_paths)

            # determine module path for EasyBuild install path to be included in $MODULEPATH
            eb_modpath = os.path.join(install_path(typ='modules'), build_option('suffix_modules_path'))

            # make sure EasyBuild module path is in 1st place
            mkdir(eb_modpath, parents=True)
            self.prepend_module_path(eb_modpath)
            self.log.info("Prepended list of module paths with path used by EasyBuild: %s" % eb_modpath)

        # set the module path environment accordingly
        curr_mod_paths = curr_module_paths()
        self.log.debug("Current module paths: %s; target module paths: %s", curr_mod_paths, self.mod_paths)
        if curr_mod_paths == self.mod_paths:
            self.log.debug("Current value of $MODULEPATH already matches list of module path %s", self.mod_paths)
        else:
            # filter out tail of paths that already matches tail of target, to avoid unnecessary 'unuse' commands
            idx = 1
            while(curr_mod_paths[-idx:] == self.mod_paths[-idx:]):
                idx += 1
            self.log.debug("Not prepending %d last entries of %s", idx - 1, self.mod_paths)

            for mod_path in self.mod_paths[::-1][idx - 1:]:
                self.prepend_module_path(mod_path)

            self.log.info("$MODULEPATH set via list of module paths (w/ 'module use'): %s" % os.environ['MODULEPATH'])

    def available(self, mod_name=None, extra_args=None):
        """
        Return a list of available modules for the given (partial) module name;
        use None to obtain a list of all available modules.

        :param mod_name: a (partial) module name for filtering (default: None)
        """
        if extra_args is None:
            extra_args = []
        if mod_name is None:
            mod_name = ''

        # cache 'avail' calls without an argument, since these are particularly expensive...
        key = self.mk_module_cache_key(';'.join(extra_args))
        if not mod_name and key in MODULE_AVAIL_CACHE:
            ans = MODULE_AVAIL_CACHE[key]
            self.log.debug("Found cached result for 'module avail' with key '%s': %s", key, ans)
        else:
            args = ['avail'] + extra_args + [mod_name]
            mods = self.run_module(*args)

            # sort list of modules in alphabetical order
            mods.sort(key=lambda m: m['mod_name'])
            ans = nub([mod['mod_name'] for mod in mods])
            self.log.debug("'module available %s' gave %d answers: %s" % (mod_name, len(ans), ans))

            if not mod_name:
                MODULE_AVAIL_CACHE[key] = ans
                self.log.debug("Cached result for 'module avail' with key '%s': %s", key, ans)

        return ans

    def module_wrapper_exists(self, mod_name, modulerc_fn='.modulerc', mod_wrapper_regex_template=None):
        """
        Determine whether a module wrapper with specified name exists.
        Only .modulerc file in Tcl syntax is considered here.
        """

        if mod_wrapper_regex_template is None:
            mod_wrapper_regex_template = "^[ ]*module-version (?P<wrapped_mod>[^ ]*) %s$"

        wrapped_mod = None

        mod_dir = os.path.dirname(mod_name)
        wrapper_regex = re.compile(mod_wrapper_regex_template % os.path.basename(mod_name), re.M)
        for mod_path in curr_module_paths():
            modulerc_cand = os.path.join(mod_path, mod_dir, modulerc_fn)
            if os.path.exists(modulerc_cand):
                self.log.debug("Found %s that may define %s as a wrapper for a module file", modulerc_cand, mod_name)
                res = wrapper_regex.search(read_file(modulerc_cand))
                if res:
                    wrapped_mod = res.group('wrapped_mod')
                    self.log.debug("Confirmed that %s is a module wrapper for %s", mod_name, wrapped_mod)
                    break

        mod_dir = os.path.dirname(mod_name)
        if wrapped_mod is not None and not wrapped_mod.startswith(mod_dir):
            # module wrapper uses 'short' module name of module being wrapped,
            # so we need to correct it in case a hierarchical module naming scheme is used...
            # e.g. 'Java/1.8.0_181' should become 'Core/Java/1.8.0_181' for wrapper 'Core/Java/1.8'
            self.log.debug("Full module name prefix mismatch between module wrapper '%s' and wrapped module '%s'",
                           mod_name, wrapped_mod)

            mod_name_parts = mod_name.split(os.path.sep)
            wrapped_mod_subdir = ''
            while not os.path.join(wrapped_mod_subdir, wrapped_mod).startswith(mod_dir) and mod_name_parts:
                wrapped_mod_subdir = os.path.join(wrapped_mod_subdir, mod_name_parts.pop(0))

            full_wrapped_mod_name = os.path.join(wrapped_mod_subdir, wrapped_mod)
            if full_wrapped_mod_name.startswith(mod_dir):
                self.log.debug("Full module name for wrapped module %s: %s", wrapped_mod, full_wrapped_mod_name)
                wrapped_mod = full_wrapped_mod_name
            else:
                raise EasyBuildError("Failed to determine full module name for module wrapped by %s: %s | %s",
                                     mod_name, wrapped_mod_subdir, wrapped_mod)

        return wrapped_mod

    def exist(self, mod_names, mod_exists_regex_template=None, skip_avail=False, maybe_partial=True):
        """
        Check if modules with specified names exists.

        :param mod_names: list of module names
        :param mod_exists_regex_template: DEPRECATED and unused
        :param skip_avail: skip checking through 'module avail', only check via 'module show'
        :param maybe_partial: indicates if the module name may be a partial module name
        """
        if mod_exists_regex_template is not None:
            self.log.deprecated('mod_exists_regex_template is no longer used', '5.0')

        def mod_exists_via_show(mod_name):
            """
            Helper function to check whether specified module name exists through 'module show'.

            :param mod_name: module name
            """
            self.log.debug("Checking whether %s exists based on output of 'module show'", mod_name)
            stderr = self.show(mod_name)
            res = False
            # Parse the output:
            # - Skip whitespace
            # - Any error -> Module does not exist
            # - Check first non-whitespace line for something that looks like an absolute path terminated by a colon
            mod_exists_regex = r'\s*/.+:\s*'
            for line in stderr.split('\n'):

                self.log.debug("Checking line '%s' to determine whether %s exists...", line, mod_name)

                # skip whitespace lines
                if OUTPUT_MATCHES['whitespace'].search(line):
                    self.log.debug("Treating line '%s' as whitespace, so skipping it", line)
                    continue

                # if any errors occured, conclude that module doesn't exist
                if OUTPUT_MATCHES['error'].search(line):
                    self.log.debug("Line '%s' looks like an error, so concluding that %s doesn't exist",
                                   line, mod_name)
                    break

                # skip warning lines, which may be produced by modules tool but should not be used
                # to determine whether a module file exists
                if line.startswith('WARNING: '):
                    self.log.debug("Skipping warning line '%s'", line)
                    continue

                # skip lines that start with 'module-' (like 'module-version'),
                # see https://github.com/easybuilders/easybuild-framework/issues/3376
                if line.startswith('module-'):
                    self.log.debug("Skipping line '%s' since it starts with 'module-'", line)
                    continue

                # if line matches pattern that indicates an existing module file, the module file exists
                res = bool(re.match(mod_exists_regex, line))
                self.log.debug("Result for existence check of %s based on 'module show' output line '%s': %s",
                               mod_name, line, res)
                break

            return res

        if skip_avail:
            avail_mod_names = []
        elif len(mod_names) == 1:
            # optimize for case of single module name ('avail' without arguments can be expensive)
            avail_mod_names = self.available(mod_name=mod_names[0])
        else:
            avail_mod_names = self.available()

        # differentiate between hidden and visible modules
        mod_names = [(mod_name, not os.path.basename(mod_name).startswith('.')) for mod_name in mod_names]

        mods_exist = []
        for (mod_name, visible) in mod_names:
            self.log.info("Checking whether %s exists...", mod_name)
            if visible:
                mod_exists = mod_name in avail_mod_names
                # module name may be partial, so also check via 'module show' as fallback
                if mod_exists:
                    self.log.info("Module %s exists (found in list of available modules)", mod_name)
                elif maybe_partial:
                    self.log.info("Module %s not found in list of available modules, checking via 'module show'...",
                                  mod_name)
                    mod_exists = mod_exists_via_show(mod_name)
            else:
                # hidden modules are not visible in 'avail', need to use 'show' instead
                self.log.info("Checking whether hidden module %s exists via 'show'..." % mod_name)
                mod_exists = mod_exists_via_show(mod_name)

            # if no module file was found, check whether specified module name can be a 'wrapper' module...
            # this fallback mechanism is important when using a hierarchical module naming scheme,
            # where "full" module names (like Core/Java/11) are used to check whether modules exist already;
            # Lmod will report module wrappers as non-existent when full module name is used,
            # see https://github.com/TACC/Lmod/issues/446
            if not mod_exists:
                self.log.info("Module %s not found via module avail/show, checking whether it is a wrapper", mod_name)
                wrapped_mod = self.module_wrapper_exists(mod_name)
                if wrapped_mod is not None:
                    # module wrapper only really exists if the wrapped module file is also available
                    mod_exists = wrapped_mod in avail_mod_names or mod_exists_via_show(wrapped_mod)
                    self.log.debug("Result for existence check of wrapped module %s: %s", wrapped_mod, mod_exists)

            self.log.info("Result for existence check of %s module: %s", mod_name, mod_exists)

            mods_exist.append(mod_exists)

        return mods_exist

    def load(self, modules, mod_paths=None, purge=False, init_env=None, allow_reload=True):
        """
        Load all requested modules.

        :param modules: list of modules to load
        :param mod_paths: list of module paths to activate before loading
        :param purge: whether or not a 'module purge' should be run before loading
        :param init_env: original environment to restore after running 'module purge'
        :param allow_reload: allow reloading an already loaded module
        """
        if mod_paths is None:
            mod_paths = []

        # purge all loaded modules if desired by restoring initial environment
        # actually running 'module purge' is futile (and wrong/broken on some systems, e.g. Cray)
        if purge:
            # restore initial environment if provided
            if init_env is None:
                raise EasyBuildError("Initial environment required when purging before loading, but not available")
            else:
                restore_env(init_env)

            # make sure $MODULEPATH is set correctly after purging
            self.check_module_path()

        # extend $MODULEPATH if needed
        for mod_path in mod_paths:
            full_mod_path = os.path.join(install_path('mod'), build_option('suffix_modules_path'), mod_path)
            if os.path.exists(full_mod_path):
                self.prepend_module_path(full_mod_path)

        loaded_modules = self.loaded_modules()
        for mod in modules:
            if allow_reload or mod not in loaded_modules:
                self.run_module('load', mod)

    def unload(self, modules=None):
        """
        Unload all requested modules.
        """
        for mod in modules:
            self.run_module('unload', mod)

    def purge(self):
        """
        Purge loaded modules.
        """
        self.log.debug("List of loaded modules before purge: %s" % os.getenv('_LMFILES_'))
        self.run_module('purge')

    def show(self, mod_name):
        """
        Run 'module show' for the specified module.
        """
        key = self.mk_module_cache_key(mod_name)
        if key in MODULE_SHOW_CACHE:
            ans = MODULE_SHOW_CACHE[key]
            self.log.debug("Found cached result for 'module show %s' with key '%s': %s", mod_name, key, ans)
        else:
            ans = self.run_module('show', mod_name, check_output=False, return_stderr=True)
            MODULE_SHOW_CACHE[key] = ans
            self.log.debug("Cached result for 'module show %s' with key '%s': %s", mod_name, key, ans)

        return ans

    def get_value_from_modulefile(self, mod_name, regex, strict=True):
        """
        Get info from the module file for the specified module.

        :param mod_name: module name
        :param regex: (compiled) regular expression, with one group
        """
        value = None

        if self.exist([mod_name], skip_avail=True)[0]:
            modinfo = self.show(mod_name)
            res = regex.search(modinfo)
            if res:
                value = res.group(1)
            elif strict:
                raise EasyBuildError("Failed to determine value from 'show' (pattern: '%s') in %s",
                                     regex.pattern, modinfo)
        elif strict:
            raise EasyBuildError("Can't get value from a non-existing module %s", mod_name)

        return value

    def modulefile_path(self, mod_name, strip_ext=False):
        """
        Get the path of the module file for the specified module

        :param mod_name: module name
        :param strip_ext: strip (.lua) extension from module fileame (if present)"""
        # (possible relative) path is always followed by a ':', and may be prepended by whitespace
        # this works for both environment modules and Lmod
        modpath_re = re.compile(r'^\s*(?P<modpath>[^/\n]*/[^\s]+):$', re.M)
        modpath = self.get_value_from_modulefile(mod_name, modpath_re)

        if strip_ext and modpath.endswith('.lua'):
            modpath = os.path.splitext(modpath)[0]

        return modpath

    def set_path_env_var(self, key, paths):
        """Set path environment variable to the given list of paths."""
        setvar(key, os.pathsep.join(paths), verbose=False)

    def check_module_output(self, cmd, stdout, stderr):
        """Check output of 'module' command, see if if is potentially invalid."""
        self.log.debug("No checking of module output implemented for %s", self.NAME)

    def compose_cmd_list(self, args, opts=None):
        """
        Compose full module command to run, based on provided arguments

        :param args: list of arguments for module command
        :return: list of strings representing the full module command to run
        """
        if opts is None:
            opts = []

        cmdlist = [self.cmd, 'python']

        if args[0] in ('available', 'avail', 'list',):
            # run these in terse mode for easier machine reading
            opts.append(self.TERSE_OPTION)

        # inject options at specified location
        for idx, opt in opts:
            args.insert(idx, opt)

        # prefix if a particular shell is specified, using shell argument to Popen doesn't work (no output produced (?))
        if self.COMMAND_SHELL is not None:
            if not isinstance(self.COMMAND_SHELL, (list, tuple)):
                raise EasyBuildError("COMMAND_SHELL needs to be list or tuple, now %s (value %s)",
                                     type(self.COMMAND_SHELL), self.COMMAND_SHELL)
            cmdlist = self.COMMAND_SHELL + cmdlist

        return cmdlist + args

    def run_module(self, *args, **kwargs):
        """
        Run module command.

        :param args: list of arguments for module command; first argument should be the subcommand to run
        :param kwargs: dictionary with options that control certain aspects of how to run the module command
        """
        if isinstance(args[0], (list, tuple,)):
            args = args[0]
        else:
            args = list(args)

        self.log.debug('Current MODULEPATH: %s' % os.environ.get('MODULEPATH', ''))

        # restore selected original environment variables before running module command
        environ = os.environ.copy()
        for key in LD_ENV_VAR_KEYS:
            old_value = environ.get(key, '')
            new_value = ORIG_OS_ENVIRON.get(key, '')
            if old_value != new_value:
                environ[key] = new_value
                self.log.debug("Changing %s from '%s' to '%s' in environment for module command",
                               key, old_value, new_value)

        cmd_list = self.compose_cmd_list(args)
        full_cmd = ' '.join(cmd_list)
        self.log.debug("Running module command '%s' from %s" % (full_cmd, os.getcwd()))

        proc = subprocess_popen_text(cmd_list, env=environ)

        # stdout will contain python code (to change environment etc)
        # stderr will contain text (just like the normal module command)
        (stdout, stderr) = proc.communicate()
        self.log.debug("Output of module command '%s': stdout: %s; stderr: %s" % (full_cmd, stdout, stderr))

        # also catch and check exit code
        exit_code = proc.returncode
        if kwargs.get('check_exit_code', True) and exit_code != 0:
            raise EasyBuildError("Module command '%s' failed with exit code %s; stderr: %s; stdout: %s",
                                 ' '.join(cmd_list), exit_code, stderr, stdout)

        if kwargs.get('check_output', True):
            self.check_module_output(full_cmd, stdout, stderr)

        if kwargs.get('return_stderr', False):
            return stderr
        elif kwargs.get('return_output', False):
            return stdout + stderr
        else:
            # the module command was run with an outdated selected environment variables (see LD_ENV_VAR_KEYS list)
            # which will be adjusted on loading a module;
            # this needs to be taken into account when updating the environment via produced output, see below

            # keep track of current values of select env vars, so we can correct the adjusted values below
            prev_ld_values = dict([(key, os.environ.get(key, '').split(os.pathsep)[::-1]) for key in LD_ENV_VAR_KEYS])

            # Change the environment
            try:
                tweak_fn = kwargs.get('tweak_stdout')
                if tweak_fn is not None:
                    stdout = tweak_fn(stdout)
                exec(stdout)
            except Exception as err:
                out = "stdout: %s, stderr: %s" % (stdout, stderr)
                raise EasyBuildError("Changing environment as dictated by module failed: %s (%s)", err, out)

            # correct values of selected environment variables as yielded by the adjustments made
            # make sure we get the order right (reverse lists with [::-1])
            for key in LD_ENV_VAR_KEYS:
                curr_ld_val = os.environ.get(key, '')
                curr_ld_val = curr_ld_val.split(os.pathsep) if curr_ld_val else []  # Take care of empty/unset values
                new_ld_val = [x for x in nub(prev_ld_values[key] + curr_ld_val[::-1]) if x][::-1]

                if new_ld_val != curr_ld_val:
                    self.log.debug("Correcting paths in $%s from %s to %s" % (key, curr_ld_val, new_ld_val))
                    self.set_path_env_var(key, new_ld_val)

            # Process stderr
            result = []
            for line in stderr.split('\n'):  # IGNORE:E1103
                if OUTPUT_MATCHES['whitespace'].search(line):
                    continue

                error = OUTPUT_MATCHES['error'].search(line)
                if error:
                    raise EasyBuildError(line)

                modules = OUTPUT_MATCHES['available'].finditer(line)
                for module in modules:
                    result.append(module.groupdict())
            return result

    def list(self):
        """Return result of 'module list'."""
        return self.run_module('list')

    def loaded_modules(self):
        """Return a list of loaded modules."""
        # obtain list of loaded modules from 'module list' using --terse
        mods = [mod['mod_name'] for mod in self.list()]

        # filter out devel modules
        loaded_modules = [mod for mod in mods if not mod.endswith(DEVEL_MODULE_SUFFIX)]

        return loaded_modules

    def check_loaded_modules(self):
        """
        Check whether any (EasyBuild-generated) modules are loaded already in the current session
        """
        allowed_keys = [get_software_root_env_var_name(x) for x in build_option('allow_loaded_modules') or [] if x]

        eb_module_keys = []
        for key in os.environ:
            if key.startswith(ROOT_ENV_VAR_NAME_PREFIX) and key not in allowed_keys:
                eb_module_keys.append(key)

        if eb_module_keys:
            loaded_modules = self.loaded_modules()

            # try to track down modules that define the $EBROOT* environment variables that were found
            loaded_eb_modules = []
            for loaded_module in loaded_modules:
                out = self.show(loaded_module)
                for key in eb_module_keys[:]:
                    if key in out:
                        loaded_eb_modules.append(loaded_module)
                        eb_module_keys.remove(key)

            # warn about $EBROOT* environment variables without matching loaded module
            if eb_module_keys:
                tup = (ROOT_ENV_VAR_NAME_PREFIX, '$' + ', $'.join(eb_module_keys))
                msg = "Found defined $%s* environment variables without matching loaded module: %s" % tup
                msg_control = "\n(control action via --check-ebroot-env-vars={%s})" % ','.join(EBROOT_ENV_VAR_ACTIONS)
                action = build_option('check_ebroot_env_vars')
                if action == ERROR:
                    raise EasyBuildError(msg + msg_control)
                elif action == IGNORE:
                    self.log.info(msg + ", but ignoring as configured")
                elif action == UNSET:
                    print_warning(msg + "; unsetting them", silent=build_option('silent'))
                    unset_env_vars(eb_module_keys)
                else:
                    print_warning(msg + msg_control, silent=build_option('silent'))

            if loaded_eb_modules:
                opt = '--detect-loaded-modules={%s}' % ','.join(LOADED_MODULES_ACTIONS)
                verbose_msg = '\n'.join([
                    "Found one or more non-allowed loaded (EasyBuild-generated) modules in current environment:",
                ] + ['* %s' % x for x in loaded_eb_modules] + [
                    '',
                    "This is not recommended since it may affect the installation procedure(s) performed by EasyBuild.",
                    '',
                    "To make EasyBuild allow particular loaded modules, "
                    "use the --allow-loaded-modules configuration option.",
                    "To specify action to take when loaded modules are detected, use %s." % opt,
                    '',
                    "See http://easybuild.readthedocs.io/en/latest/Detecting_loaded_modules.html for more information.",
                ])

                action = build_option('detect_loaded_modules')

                if action == ERROR:
                    raise EasyBuildError(verbose_msg)

                elif action == IGNORE:
                    msg = "Found non-allowed loaded (EasyBuild-generated) modules, but ignoring it as configured"
                    self.log.info(msg)

                elif action == PURGE:
                    msg = "Found non-allowed loaded (EasyBuild-generated) modules (%s), running 'module purge'"
                    print_warning(msg % ', '.join(loaded_eb_modules), silent=build_option('silent'))

                    self.log.info(msg)
                    self.purge()

                elif action == UNLOAD:
                    msg = "Unloading non-allowed loaded (EasyBuild-generated) modules: %s"
                    print_warning(msg % ', '.join(loaded_eb_modules), silent=build_option('silent'))

                    self.log.info(msg)
                    self.unload(loaded_eb_modules[::-1])

                else:
                    # default behaviour is just to print out a warning and continue
                    print_warning(verbose_msg, silent=build_option('silent'))

    def read_module_file(self, mod_name):
        """
        Read module file with specified name.
        """
        modfilepath = self.modulefile_path(mod_name)
        self.log.debug("modulefile path %s: %s" % (mod_name, modfilepath))

        return read_file(modfilepath)

    def interpret_raw_path_lua(self, txt):
        """Interpret raw path (Lua syntax): resolve environment variables, join paths where `pathJoin` is specified"""

        if txt.startswith('"') and txt.endswith('"'):
            # don't touch a raw string
            res = txt
        else:
            # first, replace all 'os.getenv(...)' occurences with the values of the environment variables
            res = re.sub(r'os.getenv\("(?P<key>[^"]*)"\)', lambda res: '"%s"' % os.getenv(res.group('key'), ''), txt)

            # interpret (outer) 'pathJoin' statement if found
            path_join_prefix = 'pathJoin('
            if res.startswith(path_join_prefix):
                res = res[len(path_join_prefix):].rstrip(')')

                # split the string at ',' and whitespace, and unquotes like the shell
                lexer = shlex.shlex(res, posix=True)
                lexer.whitespace += ','
                res = os.path.join(*lexer)

        return res.strip('"')

    def interpret_raw_path_tcl(self, txt):
        """Interpret raw path (TCL syntax): resolve environment variables"""
        res = txt.strip('"')

        # first interpret (outer) 'file join' statement (if any)
        def file_join(res):
            """Helper function to compose joined path."""
            return os.path.join(*[x.strip('"') for x in res.groups()])

        res = re.sub(r'\[\s+file\s+join\s+(.*)\s+(.*)\s+\]', file_join, res)

        # also interpret all $env(...) parts
        res = re.sub(r'\$env\((?P<key>[^)]*)\)', lambda res: os.getenv(res.group('key'), ''), res)

        return res

    def modpath_extensions_for(self, mod_names):
        """
        Determine dictionary with $MODULEPATH extensions for specified modules.
        All potential $MODULEPATH extensions are included, even the ones guarded by a condition (which is not checked).
        Only direct $MODULEPATH extensions are found, no recursion if performed for modules that load other modules.
        Modules with an empty list of $MODULEPATH extensions are included in the result.

        :param mod_names: list of module names for which to determine the list of $MODULEPATH extensions
        :return: dictionary with module names as keys and lists of $MODULEPATH extensions as values
        """
        self.log.debug("Determining $MODULEPATH extensions for modules %s" % mod_names)

        # copy environment so we can restore it
        env = os.environ.copy()

        # regex for $MODULEPATH extensions;
        # via 'module use ...' or 'prepend-path MODULEPATH' in Tcl modules,
        # or 'prepend_path("MODULEPATH", ...) in Lua modules
        modpath_ext_regex = r'|'.join([
            r'^\s*module\s+use\s+(?P<tcl_use>.+)',                         # 'module use' in Tcl module files
            r'^\s*prepend-path\s+MODULEPATH\s+(?P<tcl_prepend>.+)',        # prepend to $MODULEPATH in Tcl modules
            r'^\s*prepend_path\(\"MODULEPATH\",\s*(?P<lua_prepend>.+)\)',  # prepend to $MODULEPATH in Lua modules
        ])
        modpath_ext_regex = re.compile(modpath_ext_regex, re.M)

        modpath_exts = {}
        for mod_name in mod_names:
            modtxt = self.read_module_file(mod_name)

            exts = []
            for modpath_ext in modpath_ext_regex.finditer(modtxt):
                for key, raw_ext in modpath_ext.groupdict().items():
                    if raw_ext is not None:
                        # need to expand environment variables and join paths, e.g. when --subdir-user-modules is used
                        if key in ['tcl_prepend', 'tcl_use']:
                            ext = self.interpret_raw_path_tcl(raw_ext)
                        else:
                            ext = self.interpret_raw_path_lua(raw_ext)
                        exts.append(ext)

            self.log.debug("Found $MODULEPATH extensions for %s: %s", mod_name, exts)
            modpath_exts.update({mod_name: exts})

            if exts:
                # load this module, since it may extend $MODULEPATH to make other modules available
                # this is required to obtain the list of $MODULEPATH extensions they make (via 'module show')
                self.load([mod_name], allow_reload=False)

        # restore environment (modules may have been loaded above)
        restore_env(env)

        return modpath_exts

    def path_to_top_of_module_tree(self, top_paths, mod_name, full_mod_subdir, deps, modpath_exts=None):
        """
        Recursively determine path to the top of the module tree,
        for given module, module subdir and list of $MODULEPATH extensions per dependency module.

        For example, when to determine the path to the top of the module tree for the HPL/2.1 module being
        installed with a goolf/1.5.14 toolchain in a Core/Compiler/MPI hierarchy (HierarchicalMNS):

        * starting point:
            top_paths = ['<prefix>', '<prefix>/Core']
            mod_name = 'HPL/2.1'
            full_mod_subdir = '<prefix>/MPI/Compiler/GCC/4.8.2/OpenMPI/1.6.5'
            deps = ['GCC/4.8.2', 'OpenMPI/1.6.5', 'OpenBLAS/0.2.8-LAPACK-3.5.0', 'FFTW/3.3.4', 'ScaLAPACK/...']

        * 1st iteration: find module that extends $MODULEPATH with '<prefix>/MPI/Compiler/GCC/4.8.2/OpenMPI/1.6.5',
                         => OpenMPI/1.6.5 (in '<prefix>/Compiler/GCC/4.8.2' subdir);
                         recurse with mod_name = 'OpenMPI/1.6.5' and full_mod_subdir = '<prefix>/Compiler/GCC/4.8.2'

        * 2nd iteration: find module that extends $MODULEPATH with '<prefix>/Compiler/GCC/4.8.2'
                         => GCC/4.8.2 (in '<prefix>/Core' subdir);
                         recurse with mod_name = 'GCC/4.8.2' and full_mod_subdir = '<prefix>/Core'

        * 3rd iteration: try to find module that extends $MODULEPATH with '<prefix>/Core'
                         => '<prefix>/Core' is in top_paths, so stop recursion

        :param top_paths: list of potentation 'top of module tree' (absolute) paths
        :param mod_name: (short) module name for starting point (only used in log messages)
        :param full_mod_subdir: absolute path to module subdirectory for starting point
        :param deps: list of dependency modules for module at starting point
        :param modpath_exts: list of module path extensions for each of the dependency modules
        """
        # copy environment so we can restore it
        env = os.environ.copy()

        if path_matches(full_mod_subdir, top_paths):
            self.log.debug("Top of module tree reached with %s (module subdir: %s)" % (mod_name, full_mod_subdir))
            return []

        self.log.debug("Checking for dependency that extends $MODULEPATH with %s" % full_mod_subdir)

        if modpath_exts is None:
            # only retain dependencies that have a non-empty lists of $MODULEPATH extensions
            modpath_exts = dict([(k, v) for k, v in self.modpath_extensions_for(deps).items() if v])
            self.log.debug("Non-empty lists of module path extensions for dependencies: %s" % modpath_exts)

        mods_to_top = []
        full_mod_subdirs = []
        for dep in modpath_exts:
            # if a $MODULEPATH extension is identical to where this module will be installed, we have a hit
            # use os.path.samefile when comparing paths to avoid issues with resolved symlinks
            full_modpath_exts = modpath_exts[dep]
            if path_matches(full_mod_subdir, full_modpath_exts):

                # full path to module subdir of dependency is simply path to module file without (short) module name
                dep_full_mod_subdir = self.modulefile_path(dep, strip_ext=True)[:-len(dep) - 1]
                full_mod_subdirs.append(dep_full_mod_subdir)

                mods_to_top.append(dep)
                self.log.debug("Found module to top of module tree: %s (subdir: %s, modpath extensions %s)",
                               dep, dep_full_mod_subdir, full_modpath_exts)

            if full_modpath_exts:
                # load module for this dependency, since it may extend $MODULEPATH to make dependencies available
                # this is required to obtain the corresponding module file paths (via 'module show')
                # don't reload module if it is already loaded, since that'll mess up the order in $MODULEPATH
                self.load([dep], allow_reload=False)

        # restore original environment (modules may have been loaded above)
        restore_env(env)

        path = mods_to_top[:]
        if mods_to_top:
            # remove retained dependencies from the list, since we're climbing up the module tree
            remaining_modpath_exts = dict([m for m in modpath_exts.items() if not m[0] in mods_to_top])

            self.log.debug("Path to top from %s extended to %s, so recursing to find way to the top",
                           mod_name, mods_to_top)
            for mod_name, full_mod_subdir in zip(mods_to_top, full_mod_subdirs):
                path.extend(self.path_to_top_of_module_tree(top_paths, mod_name, full_mod_subdir, None,
                                                            modpath_exts=remaining_modpath_exts))
        else:
            self.log.debug("Path not extended, we must have reached the top of the module tree")

        self.log.debug("Path to top of module tree from %s: %s" % (mod_name, path))
        return path

    def get_setenv_value_from_modulefile(self, mod_name, var_name):
        """
        Get value for specific 'setenv' statement from module file for the specified module.

        :param mod_name: module name
        :param var_name: name of the variable being set for which value should be returned
        """
        raise NotImplementedError

    def update(self):
        """Update after new modules were added."""
        raise NotImplementedError


class EnvironmentModulesC(ModulesTool):
    """Interface to (C) environment modules (modulecmd)."""
    NAME = "Environment Modules v3"
    COMMAND = "modulecmd"
    REQ_VERSION = '3.2.10'
    MAX_VERSION = '3.99'
    VERSION_REGEXP = r'^\s*(VERSION\s*=\s*)?(?P<version>\d\S*)\s*'

    def run_module(self, *args, **kwargs):
        """
        Run module command, tweak output that is exec'ed if necessary.
        """
        if isinstance(args[0], (list, tuple,)):
            args = args[0]

        # some versions of Cray's environment modules tool (3.2.10.x) include a "source */init/bash" command
        # in the output of some "modulecmd python load" calls, which is not a valid Python command,
        # which must be stripped out to avoid "invalid syntax" errors when evaluating the output
        def tweak_stdout(txt):
            """Tweak stdout before it's exec'ed as Python code."""
            source_regex = re.compile("^source .*$", re.M)
            return source_regex.sub('', txt)

        tweak_stdout_fn = None
        # for 'active' module (sub)commands that yield changes in environment, we need to tweak stdout before exec'ing
        if args[0] in ['load', 'purge', 'swap', 'unload', 'use', 'unuse']:
            tweak_stdout_fn = tweak_stdout
        kwargs.update({'tweak_stdout': tweak_stdout_fn})

        return super(EnvironmentModulesC, self).run_module(*args, **kwargs)

    def update(self):
        """Update after new modules were added."""
        pass

    def get_setenv_value_from_modulefile(self, mod_name, var_name):
        """
        Get value for specific 'setenv' statement from module file for the specified module.

        :param mod_name: module name
        :param var_name: name of the variable being set for which value should be returned
        """
        # Tcl-based module tools produce "module show" output with setenv statements like:
        # "setenv		 GCC_PATH /opt/gcc/8.3.0"
        # - line starts with 'setenv'
        # - whitespace (spaces & tabs) around variable name
        # - no quotes or parentheses around value (which can contain spaces!)
        regex = re.compile(r'^setenv\s+%s\s+(?P<value>.+)' % var_name, re.M)
        value = self.get_value_from_modulefile(mod_name, regex, strict=False)

        if value:
            value = value.strip()

        return value


class EnvironmentModulesTcl(EnvironmentModulesC):
    """Interface to (Tcl) environment modules (modulecmd.tcl)."""
    NAME = "ancient Tcl-only Environment Modules"
    # Tcl environment modules have no --terse (yet),
    #   -t must be added after the command ('avail', 'list', etc.)
    TERSE_OPTION = (1, '-t')
    COMMAND = 'modulecmd.tcl'
    # older versions of modulecmd.tcl don't have a decent hashbang, so we run it under a tclsh shell
    COMMAND_SHELL = ['tclsh']
    VERSION_OPTION = ''
    REQ_VERSION = None
    VERSION_REGEXP = r'^Modules\s+Release\s+Tcl\s+(?P<version>\d\S*)\s'

    def set_path_env_var(self, key, paths):
        """Set environment variable with given name to the given list of paths."""
        super(EnvironmentModulesTcl, self).set_path_env_var(key, paths)
        # for Tcl environment modules, we need to make sure the _modshare env var is kept in sync
        setvar('%s_modshare' % key, ':1:'.join(paths), verbose=False)

    def run_module(self, *args, **kwargs):
        """
        Run module command, tweak output that is exec'ed if necessary.
        """
        if isinstance(args[0], (list, tuple,)):
            args = args[0]

        # old versions of modulecmd.tcl spit out something like "exec '<file>'" for load commands,
        # which is not correct Python code (and it knows, as the comments in modulecmd.tcl indicate)
        # so, rewrite "exec '/tmp/modulescript_X'" to the correct "execfile('/tmp/modulescript_X')"
        # this is required for the DEISA variant of modulecmd.tcl which is commonly used
        def tweak_stdout(txt):
            """Tweak stdout before it's exec'ed as Python code."""
            modulescript_regex = r"^exec\s+[\"'](?P<modulescript>/tmp/modulescript_[0-9_]+)[\"']$"
            return re.sub(modulescript_regex, r"execfile('\1')", txt)

        tweak_stdout_fn = None
        # for 'active' module (sub)commands that yield changes in environment, we need to tweak stdout before exec'ing
        if args[0] in ['load', 'purge', 'unload', 'use', 'unuse']:
            tweak_stdout_fn = tweak_stdout
        kwargs.update({'tweak_stdout': tweak_stdout_fn})

        return super(EnvironmentModulesTcl, self).run_module(*args, **kwargs)

    def available(self, mod_name=None):
        """
        Return a list of available modules for the given (partial) module name;
        use None to obtain a list of all available modules.

        :param name: a (partial) module name for filtering (default: None)
        """
        mods = super(EnvironmentModulesTcl, self).available(mod_name=mod_name)
        # strip off slash at beginning, if it's there
        # under certain circumstances, 'modulecmd.tcl avail' (DEISA variant) spits out available modules like this
        clean_mods = [mod.lstrip(os.path.sep) for mod in mods]

        return clean_mods

    def remove_module_path(self, path, set_mod_paths=True):
        """
        Remove specified module path (using 'module unuse').

        :param path: path to remove from $MODULEPATH via 'unuse'
        :param set_mod_paths: (re)set self.mod_paths
        """
        # remove module path via 'module use' and make sure self.mod_paths is synced
        # modulecmd.tcl keeps track of how often a path was added via 'module use',
        # so we need to check to make sure it's really removed
        path = normalize_path(path)
        while True:
            try:
                # Unuse the path that is actually present in the environment
                module_path = next(p for p in curr_module_paths() if normalize_path(p) == path)
            except StopIteration:
                break
            self.unuse(module_path)
        if set_mod_paths:
            self.set_mod_paths()


class EnvironmentModules(EnvironmentModulesTcl):
    """Interface to environment modules 4.0+"""
    NAME = "Environment Modules v4"
    COMMAND = os.path.join(os.getenv('MODULESHOME', 'MODULESHOME_NOT_DEFINED'), 'libexec', 'modulecmd.tcl')
    REQ_VERSION = '4.0.0'
    MAX_VERSION = None
    VERSION_REGEXP = r'^Modules\s+Release\s+(?P<version>\d\S*)\s'

    def check_module_output(self, cmd, stdout, stderr):
        """Check output of 'module' command, see if if is potentially invalid."""
        if "_mlstatus = False" in stdout:
            raise EasyBuildError("Failed module command detected: %s (stdout: %s, stderr: %s)", cmd, stdout, stderr)
        else:
            self.log.debug("No errors detected when running module command '%s'", cmd)


class Lmod(ModulesTool):
    """Interface to Lmod."""
    NAME = "Lmod"
    COMMAND = 'lmod'
    COMMAND_ENVIRONMENT = 'LMOD_CMD'
    REQ_VERSION = '6.5.1'
    DEPR_VERSION = '7.0.0'
    REQ_VERSION_DEPENDS_ON = '7.6.1'
    VERSION_REGEXP = r"^Modules\s+based\s+on\s+Lua:\s+Version\s+(?P<version>\d\S*)\s"
    USER_CACHE_DIR = os.path.join(os.path.expanduser('~'), '.lmod.d', '.cache')

    SHOW_HIDDEN_OPTION = '--show-hidden'

    def __init__(self, *args, **kwargs):
        """Constructor, set lmod-specific class variable values."""
        # $LMOD_QUIET needs to be set to avoid EasyBuild tripping over fiddly bits in output
        setvar('LMOD_QUIET', '1', verbose=False)
        # make sure Lmod ignores the spider cache ($LMOD_IGNORE_CACHE supported since Lmod 5.2)
        setvar('LMOD_IGNORE_CACHE', '1', verbose=False)
        # hard disable output redirection, we expect output messages (list, avail) to always go to stderr
        setvar('LMOD_REDIRECT', 'no', verbose=False)
        # disable extended defaults within Lmod (introduced and set as default in Lmod 8.0.7)
        setvar('LMOD_EXTENDED_DEFAULT', 'no', verbose=False)

        super(Lmod, self).__init__(*args, **kwargs)
        self.supports_depends_on = StrictVersion(self.version) >= StrictVersion(self.REQ_VERSION_DEPENDS_ON)

    def check_module_function(self, *args, **kwargs):
        """Check whether selected module tool matches 'module' function definition."""
        if 'regex' not in kwargs:
            kwargs['regex'] = r".*(%s|%s)" % (self.COMMAND, self.COMMAND_ENVIRONMENT)
        super(Lmod, self).check_module_function(*args, **kwargs)

    def check_module_output(self, cmd, stdout, stderr):
        """Check output of 'module' command, see if if is potentially invalid."""
        if stdout:
            self.log.debug("Output found in stdout, seems like '%s' ran fine", cmd)
        else:
            raise EasyBuildError("Found empty stdout, seems like '%s' failed: %s", cmd, stderr)

    def compose_cmd_list(self, args, opts=None):
        """
        Compose full module command to run, based on provided arguments

        :param args: list of arguments for module command
        :return: list of strings representing the full module command to run
        """
        if opts is None:
            opts = []

        if build_option('debug_lmod'):
            opts.append((0, '-D'))

        # if --show_hidden is in list of arguments, pass it via 'opts' to make sure it's in the right place,
        # i.e. *before* the subcommand
        if self.SHOW_HIDDEN_OPTION in args:
            opts.append((0, self.SHOW_HIDDEN_OPTION))
            args = [a for a in args if a != self.SHOW_HIDDEN_OPTION]

        return super(Lmod, self).compose_cmd_list(args, opts=opts)

    def available(self, mod_name=None):
        """
        Return a list of available modules for the given (partial) module name;
        use None to obtain a list of all available modules.

        :param name: a (partial) module name for filtering (default: None)
        """
        # make hidden modules visible (requires Lmod 5.7.5)
        extra_args = [self.SHOW_HIDDEN_OPTION]

        mods = super(Lmod, self).available(mod_name=mod_name, extra_args=extra_args)

        # only retain actual modules, exclude module directories (which end with a '/')
        real_mods = [mod for mod in mods if not mod.endswith('/')]

        # only retain modules that with a <mod_name> prefix
        # Lmod will also returns modules with a matching substring
        correct_real_mods = [mod for mod in real_mods if mod_name is None or mod.startswith(mod_name)]

        return correct_real_mods

    def update(self):
        """Update after new modules were added."""

        if build_option('update_modules_tool_cache'):
            spider_cmd = os.path.join(os.path.dirname(self.cmd), 'spider')
            cmd = [spider_cmd, '-o', 'moduleT', os.environ['MODULEPATH']]
            self.log.debug("Running command '%s'..." % ' '.join(cmd))

            proc = subprocess_popen_text(cmd, env=os.environ)
            (stdout, stderr) = proc.communicate()

            if stderr:
                raise EasyBuildError("An error occurred when running '%s': %s", ' '.join(cmd), stderr)

            if self.testing:
                # don't actually update local cache when testing, just return the cache contents
                return stdout
            else:
                cache_fp = os.path.join(self.USER_CACHE_DIR, 'moduleT.lua')
                self.log.debug("Updating Lmod spider cache %s with output from '%s'" % (cache_fp, ' '.join(cmd)))
                cache_dir = os.path.dirname(cache_fp)
                if not os.path.exists(cache_dir):
                    mkdir(cache_dir, parents=True)
                write_file(cache_fp, stdout)

    def use(self, path, priority=None):
        """
        Add path to $MODULEPATH via 'module use'.

        :param path: path to add to $MODULEPATH
        :param priority: priority for this path in $MODULEPATH (Lmod-specific)
        """
        if not path:
            raise EasyBuildError("Cannot add empty path to $MODULEPATH")
        if not os.path.exists(path):
            self.log.deprecated("Path '%s' for module.use should exist" % path, '5.0')
            # make sure path exists before we add it
            mkdir(path, parents=True)

        if priority:
            self.run_module(['use', '--priority', str(priority), path])
        else:
            # LMod allows modifying MODULEPATH directly. So do that to avoid the costly module use
            # unless priorities are in use already
            if os.environ.get('__LMOD_Priority_MODULEPATH'):
                self.run_module(['use', path])
            else:
                path = normalize_path(path)
                cur_mod_path = os.environ.get('MODULEPATH')
                if cur_mod_path is None:
                    new_mod_path = path
                else:
                    new_mod_path = [path] + [p for p in cur_mod_path.split(':') if normalize_path(p) != path]
                    new_mod_path = ':'.join(new_mod_path)
                self.log.debug('Changing MODULEPATH from %s to %s' %
                               ('<unset>' if cur_mod_path is None else cur_mod_path, new_mod_path))
                os.environ['MODULEPATH'] = new_mod_path

    def unuse(self, path):
        """Remove a module path"""
        # We can simply remove the path from MODULEPATH to avoid the costly module call
        cur_mod_path = os.environ.get('MODULEPATH')
        if cur_mod_path is not None:
            # Removing the last entry unsets the variable
            if cur_mod_path == path:
                self.log.debug('Changing MODULEPATH from %s to <unset>' % cur_mod_path)
                del os.environ['MODULEPATH']
            else:
                path = normalize_path(path)
                new_mod_path = ':'.join(p for p in cur_mod_path.split(':') if normalize_path(p) != path)
                if new_mod_path != cur_mod_path:
                    self.log.debug('Changing MODULEPATH from %s to %s' % (cur_mod_path, new_mod_path))
                    os.environ['MODULEPATH'] = new_mod_path

    def prepend_module_path(self, path, set_mod_paths=True, priority=None):
        """
        Prepend given module path to list of module paths, or bump it to 1st place.

        :param path: path to prepend to $MODULEPATH
        :param set_mod_paths: (re)set self.mod_paths
        :param priority: priority for this path in $MODULEPATH (Lmod-specific)
        """
        # Lmod pushes a path to the front on 'module use', no need for (costly) 'module unuse'
        modulepath = curr_module_paths()
        if not modulepath or os.path.realpath(modulepath[0]) != os.path.realpath(path):
            self.use(path, priority=priority)
            if set_mod_paths:
                self.set_mod_paths()

    def module_wrapper_exists(self, mod_name):
        """
        Determine whether a module wrapper with specified name exists.
        First check for wrapper defined in .modulerc.lua, fall back to also checking .modulerc (Tcl syntax).
        """
        res = None

        # first consider .modulerc.lua with Lmod 7.8 (or newer)
        if StrictVersion(self.version) >= StrictVersion('7.8'):
            mod_wrapper_regex_template = r'^module_version\("(?P<wrapped_mod>.*)", "%s"\)$'
            res = super(Lmod, self).module_wrapper_exists(mod_name, modulerc_fn='.modulerc.lua',
                                                          mod_wrapper_regex_template=mod_wrapper_regex_template)

        # fall back to checking for .modulerc in Tcl syntax
        if res is None:
            res = super(Lmod, self).module_wrapper_exists(mod_name)

        return res

    def get_setenv_value_from_modulefile(self, mod_name, var_name):
        """
        Get value for specific 'setenv' statement from module file for the specified module.

        :param mod_name: module name
        :param var_name: name of the variable being set for which value should be returned
        """
        # Lmod produces "module show" output with setenv statements like:
        # setenv("EBROOTBZIP2","/tmp/software/bzip2/1.0.6")
        # - line starts with setenv(
        # - both variable name and value are enclosed in double quotes, separated by comma
        # - value can contain spaces!
        # - line ends with )
        regex = re.compile(r'^setenv\("%s"\s*,\s*"(?P<value>.+)"\)' % var_name, re.M)
        value = self.get_value_from_modulefile(mod_name, regex, strict=False)

        if value:
            value = value.strip()

        return value


def get_software_root_env_var_name(name):
    """Return name of environment variable for software root."""
    newname = convert_name(name, upper=True)
    return ROOT_ENV_VAR_NAME_PREFIX + newname


def get_software_root(name, with_env_var=False):
    """
    Return the software root set for a particular software name.
    """
    env_var = get_software_root_env_var_name(name)

    root = None
    if env_var in os.environ:
        root = os.getenv(env_var)

    if with_env_var:
        res = (root, env_var)
    else:
        res = root

    return res


def get_software_libdir(name, only_one=True, fs=None):
    """
    Find library subdirectories for the specified software package.

    Returns the library subdirectory, relative to software root.
    It fails if multiple library subdirs are found, unless only_one is False which yields a list of all library subdirs.

    :param name: name of the software package
    :param only_one: indicates whether only one lib path is expected to be found
    :param fs: only retain library subdirs that contain one of the files in this list
    """
    lib_subdirs = ['lib', 'lib64']
    root = get_software_root(name)
    res = []
    if root:
        for lib_subdir in lib_subdirs:
            lib_dir_path = os.path.join(root, lib_subdir)
            if os.path.exists(lib_dir_path):
                # take into account that lib64 could be a symlink to lib (or vice versa)
                # see https://github.com/easybuilders/easybuild-framework/issues/3139
                if any(os.path.samefile(lib_dir_path, os.path.join(root, x)) for x in res):
                    _log.debug("%s is the same as one of the other paths, so skipping it", lib_dir_path)

                elif fs is None or any(os.path.exists(os.path.join(lib_dir_path, f)) for f in fs):
                    _log.debug("Retaining library subdir '%s' (found at %s)", lib_subdir, lib_dir_path)
                    res.append(lib_subdir)

            elif build_option('extended_dry_run'):
                res.append(lib_subdir)
                break

        # if no library subdir was found, return None
        if not res:
            return None
        if only_one:
            if len(res) == 1:
                res = res[0]
            else:
                raise EasyBuildError("Multiple library subdirectories found for %s in %s: %s",
                                     name, root, ', '.join(res))
        return res
    else:
        # return None if software package root could not be determined
        return None


def get_software_version_env_var_name(name):
    """Return name of environment variable for software root."""
    newname = convert_name(name, upper=True)
    return VERSION_ENV_VAR_NAME_PREFIX + newname


def get_software_version(name):
    """
    Return the software version set for a particular software name.
    """
    env_var = get_software_version_env_var_name(name)

    version = None
    if env_var in os.environ:
        version = os.getenv(env_var)

    return version


def curr_module_paths(normalize=False):
    """
    Return a list of current module paths.

    :param normalize: Normalize the paths
    """
    # avoid empty or nonexistent paths, which don't make any sense
    module_paths = (p for p in os.environ.get('MODULEPATH', '').split(':') if p and os.path.exists(p))
    if normalize:
        module_paths = (normalize_path(p) for p in module_paths)
    return list(module_paths)


def mk_module_path(paths):
    """
    Create a string representing the list of module paths.
    """
    return ':'.join(paths)


def avail_modules_tools():
    """
    Return all known modules tools.
    """
    class_dict = dict([(x.__name__, x) for x in get_subclasses(ModulesTool)])
    # filter out legacy Modules class
    if 'Modules' in class_dict:
        del class_dict['Modules']
    # NoModulesTool should never be used deliberately, so remove it from the list of available module tools
    if 'NoModulesTool' in class_dict:
        del class_dict['NoModulesTool']
    return class_dict


def modules_tool(mod_paths=None, testing=False):
    """
    Return interface to modules tool (environment modules (C, Tcl), or Lmod)
    """
    # get_modules_tool might return none (e.g. if config was not initialized yet)
    modules_tool = get_modules_tool()
    modules_tool_class = avail_modules_tools().get(modules_tool, NoModulesTool)
    return modules_tool_class(mod_paths=mod_paths, testing=testing)


def reset_module_caches():
    """Reset module caches."""
    MODULE_AVAIL_CACHE.clear()
    MODULE_SHOW_CACHE.clear()


def invalidate_module_caches_for(path):
    """Invalidate cache entries related to specified path."""
    if not os.path.exists(path):
        raise EasyBuildError("Non-existing path specified to invalidate module caches: %s", path)

    _log.debug("Invallidating module cache entries for path '%s'", path)
    for cache, subcmd in [(MODULE_AVAIL_CACHE, 'avail'), (MODULE_SHOW_CACHE, 'show')]:
        for key in list(cache.keys()):
            paths_in_key = '='.join(key[0].split('=')[1:]).split(os.pathsep)
            _log.debug("Paths for 'module %s' key '%s': %s", subcmd, key, paths_in_key)
            for path_in_key in paths_in_key:
                if path == path_in_key or (os.path.exists(path_in_key) and os.path.samefile(path, path_in_key)):
                    _log.debug("Entry '%s' in 'module %s' cache is evicted, marked as invalid via path '%s': %s",
                               key, subcmd, path, cache[key])
                    del cache[key]
                    break


class Modules(EnvironmentModulesC):
    """NO LONGER SUPPORTED: interface to modules tool, use modules_tool from easybuild.tools.modules instead"""

    def __init__(self, *args, **kwargs):
        _log.nosupport("modules.Modules class is now an abstract interface, use modules.modules_tool instead", '2.0')


class NoModulesTool(ModulesTool):
    """Class that mock the module behaviour, used for operation not requiring modules. Eg. tests, fetch only"""

    def __init__(self, *args, **kwargs):
        self.version = None

    def exist(self, mod_names, *args, **kwargs):
        """No modules, so nothing exists"""
        return [False] * len(mod_names)

    def check_loaded_modules(self):
        """Nothing to do since no modules"""
        pass

    def list(self):
        """No modules loaded"""
        return []

    def available(self, *args, **kwargs):
        """No modules, so nothing available"""
        return []
