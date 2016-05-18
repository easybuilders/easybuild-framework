##
# Copyright 2009-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
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
This python module implements the environment modules functionality:
 - loading modules
 - checking for available modules
 - ...

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: David Brown (Pacific Northwest National Laboratory)
"""
import os
import re
import subprocess
from distutils.version import StrictVersion
from subprocess import PIPE
from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, get_modules_tool, install_path
from easybuild.tools.environment import ORIG_OS_ENVIRON, restore_env
from easybuild.tools.filetools import convert_name, mkdir, read_file, path_matches, which
from easybuild.tools.module_naming_scheme import DEVEL_MODULE_SUFFIX
from easybuild.tools.run import run_cmd
from vsc.utils.missing import nub

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
    # the regexp, should have a "version" group (multiline search)
    VERSION_REGEXP = None
    # modules tool user cache directory
    USER_CACHE_DIR = None

    def __init__(self, mod_paths=None, testing=False):
        """
        Create a ModulesTool object
        @param mod_paths: A list of paths where the modules can be located
        @type mod_paths: list
        """
        # this can/should be set to True during testing
        self.testing = testing

        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        # DEPRECATED!
        self._modules = []

        # actual module command (i.e., not the 'module' wrapper function, but the binary)
        self.cmd = self.COMMAND
        env_cmd_path = os.environ.get(self.COMMAND_ENVIRONMENT)

        self.mod_paths = None
        if mod_paths is not None:
            self.set_mod_paths(mod_paths)

        # only use command path in environment variable if command in not available in $PATH
        if which(self.cmd) is None and env_cmd_path is not None:
            self.log.debug('Set command via environment variable %s: %s', self.COMMAND_ENVIRONMENT, self.cmd)
            self.cmd = env_cmd_path

        # check whether paths obtained via $PATH and $LMOD_CMD are different
        elif which(self.cmd) != env_cmd_path:
            self.log.debug("Different paths found for module command '%s' via which/$PATH and $%s: %s vs %s",
                           self.COMMAND, self.COMMAND_ENVIRONMENT, self.cmd, env_cmd_path)

        # make sure the module command was found
        if self.cmd is None:
            raise EasyBuildError("No command set.")
        else:
            self.log.debug('Using command %s' % self.cmd)

        # version of modules tool
        self.version = None

        # some initialisation/verification
        self.check_cmd_avail()
        self.check_module_path()
        self.check_module_function(allow_mismatch=build_option('allow_modules_tool_mismatch'))
        self.set_and_check_version()

    def buildstats(self):
        """Return tuple with data to be included in buildstats"""
        return (self.__class__.__name__, self.cmd, self.version)

    @property
    def modules(self):
        """(NO LONGER SUPPORTED!) Property providing access to 'modules' class variable"""
        self.log.nosupport("'modules' class variable is not supported anymore, use load([<list of modules>]) instead", '2.0')

    def set_and_check_version(self):
        """Get the module version, and check any requirements"""
        if self.COMMAND in MODULE_VERSION_CACHE:
            self.version = MODULE_VERSION_CACHE[self.COMMAND]
            self.log.debug("Found cached version for %s: %s", self.COMMAND, self.version)
            return

        if self.VERSION_REGEXP is None:
            raise EasyBuildError("No VERSION_REGEXP defined")

        try:
            txt = self.run_module(self.VERSION_OPTION, return_output=True)

            ver_re = re.compile(self.VERSION_REGEXP, re.M)
            res = ver_re.search(txt)
            if res:
                self.version = res.group('version')
                self.log.info("Found version %s" % self.version)

                # make sure version is a valid StrictVersion (e.g., 5.7.3.1 is invalid),
                # and replace 'rc' by 'b', to make StrictVersion treat it as a beta-release
                self.version = self.version.replace('rc', 'b')
                if len(self.version.split('.')) > 3:
                    self.version = '.'.join(self.version.split('.')[:3])

                self.log.info("Converted actual version to '%s'" % self.version)
            else:
                raise EasyBuildError("Failed to determine version from option '%s' output: %s",
                                     self.VERSION_OPTION, txt)
        except (OSError), err:
            raise EasyBuildError("Failed to check version: %s", err)

        if self.REQ_VERSION is None:
            self.log.debug("No version requirement defined.")
        else:
            if StrictVersion(self.version) < StrictVersion(self.REQ_VERSION):
                raise EasyBuildError("EasyBuild requires v%s >= v%s (no rc), found v%s",
                                     self.__class__.__name__, self.REQ_VERSION, self.version)
            else:
                self.log.debug('Version %s matches requirement %s' % (self.version, self.REQ_VERSION))

        MODULE_VERSION_CACHE[self.COMMAND] = self.version

    def check_cmd_avail(self):
        """Check whether modules tool command is available."""
        cmd_path = which(self.cmd)
        if cmd_path is not None:
            self.cmd = cmd_path
            self.log.info("Full path for module command is %s, so using it" % self.cmd)
        else:
            mod_tool = self.__class__.__name__
            raise EasyBuildError("%s modules tool can not be used, '%s' command is not available.", mod_tool, self.cmd)

    def check_module_function(self, allow_mismatch=False, regex=None):
        """Check whether selected module tool matches 'module' function definition."""
        if self.testing:
            # grab 'module' function definition from environment if it's there; only during testing
            if 'module' in os.environ:
                out, ec = os.environ['module'], 0
            else:
                out, ec = None, 1
        else:
            out, ec = run_cmd("type module", simple=False, log_ok=False, log_all=False, force_in_dry_run=True)

        if regex is None:
            regex = r".*%s" % os.path.basename(self.cmd)
        mod_cmd_re = re.compile(regex, re.M)
        mod_details = "pattern '%s' (%s)" % (mod_cmd_re.pattern, self.__class__.__name__)

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

        @param mod_paths: list of entries for $MODULEPATH to use
        """
        # make sure we don't have the same path twice, using nub
        if mod_paths is None:
            # no paths specified, so grab list of (existing) module paths from $MODULEPATH
            self.mod_paths = [p for p in nub(curr_module_paths()) if os.path.exists(p)]
        else:
            for mod_path in nub(mod_paths):
                self.prepend_module_path(mod_path, set_mod_paths=False)
            self.mod_paths = nub(mod_paths)

        self.log.debug("$MODULEPATH after set_mod_paths: %s" % os.environ.get('MODULEPATH', ''))

    def use(self, path):
        """Add module path via 'module use'."""
        # make sure path exists before we add it
        mkdir(path, parents=True)
        self.run_module(['use', path])

    def unuse(self, path):
        """Remove module path via 'module unuse'."""
        self.run_module(['unuse', path])

    def add_module_path(self, path, set_mod_paths=True):
        """
        Add specified module path (using 'module use') if it's not there yet.

        @param path: path to add to $MODULEPATH via 'use'
        @param set_mod_paths: (re)set self.mod_paths
        """
        if path not in curr_module_paths():
            # add module path via 'module use' and make sure self.mod_paths is synced
            self.use(path)
            if set_mod_paths:
                self.set_mod_paths()

    def remove_module_path(self, path, set_mod_paths=True):
        """
        Remove specified module path (using 'module unuse').

        @param path: path to remove from $MODULEPATH via 'unuse'
        @param set_mod_paths: (re)set self.mod_paths
        """
        # remove module path via 'module unuse' and make sure self.mod_paths is synced
        if path in curr_module_paths():
            self.unuse(path)

            if set_mod_paths:
                self.set_mod_paths()

    def prepend_module_path(self, path, set_mod_paths=True):
        """
        Prepend given module path to list of module paths, or bump it to 1st place.

        @param path: path to prepend to $MODULEPATH
        @param set_mod_paths: (re)set self.mod_paths
        """
        # generic approach: remove the path first (if it's there), then add it again (to the front)
        modulepath = curr_module_paths()
        if not modulepath:
            self.add_module_path(path, set_mod_paths=set_mod_paths)
        elif modulepath[0] != path:
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
            self.prepend_module_path(eb_modpath)
            self.log.info("Prepended list of module paths with path used by EasyBuild: %s" % eb_modpath)

        # set the module path environment accordingly
        if curr_module_paths() == self.mod_paths:
            self.log.debug("Current value of $MODULEPATH already matches list of module path %s", self.mod_paths)
        else:
            for mod_path in self.mod_paths[::-1]:
                self.prepend_module_path(mod_path)
            self.log.info("$MODULEPATH set via list of module paths (w/ 'module use'): %s" % os.environ['MODULEPATH'])

    def available(self, mod_name=None, extra_args=None):
        """
        Return a list of available modules for the given (partial) module name;
        use None to obtain a list of all available modules.

        @param mod_name: a (partial) module name for filtering (default: None)
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

    def exist(self, mod_names, mod_exists_regex_template=r'^\s*\S*/%s.*:\s*$', skip_avail=False):
        """
        Check if modules with specified names exists.

        @param mod_names: list of module names
        @param mod_exists_regex_template: template regular expression to search 'module show' output with
        @param skip_avail: skip checking through 'module avail', only check via 'module show'
        """
        def mod_exists_via_show(mod_name):
            """
            Helper function to check whether specified module name exists through 'module show'.

            @param mod_name: module name
            """
            mod_exists_regex = mod_exists_regex_template % re.escape(mod_name)
            txt = self.show(mod_name)
            return bool(re.search(mod_exists_regex, txt, re.M))

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
            if visible:
                # module name may be partial, so also check via 'module show' as fallback
                mods_exist.append(mod_name in avail_mod_names or mod_exists_via_show(mod_name))
            else:
                # hidden modules are not visible in 'avail', need to use 'show' instead
                self.log.debug("checking whether hidden module %s exists via 'show'..." % mod_name)
                mods_exist.append(mod_exists_via_show(mod_name))

        return mods_exist

    def exists(self, mod_name):
        """NO LONGER SUPPORTED: use exist method instead"""
        self.log.nosupport("exists(<mod_name>) is not supported anymore, use exist([<mod_name>]) instead", '2.0')

    def load(self, modules, mod_paths=None, purge=False, init_env=None):
        """
        Load all requested modules.

        @param modules: list of modules to load
        @param mod_paths: list of module paths to activate before loading
        @param purge: whether or not a 'module purge' should be run before loading
        @param init_env: original environment to restore after running 'module purge'
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
            self.prepend_module_path(full_mod_path)

        for mod in modules:
            self.run_module('load', mod)

    def unload(self, modules=None):
        """
        Unload all requested modules.
        """
        if modules is None:
            self.log.nosupport("Unloading modules listed in _modules class variable", '2.0')

        for mod in modules:
            self.run_module('unload', mod)

    def purge(self):
        """
        Purge loaded modules.
        """
        self.log.debug("List of loaded modules before purge: %s" % os.getenv('_LMFILES_'))
        self.run_module('purge', '')

    def show(self, mod_name):
        """
        Run 'module show' for the specified module.
        """
        key = self.mk_module_cache_key(mod_name)
        if key in MODULE_SHOW_CACHE:
            ans = MODULE_SHOW_CACHE[key]
            self.log.debug("Found cached result for 'module show %s' with key '%s': %s", mod_name, key, ans)
        else:
            ans = self.run_module('show', mod_name, return_output=True)
            MODULE_SHOW_CACHE[key] = ans
            self.log.debug("Cached result for 'module show %s' with key '%s': %s", mod_name, key, ans)

        return ans

    def get_value_from_modulefile(self, mod_name, regex):
        """
        Get info from the module file for the specified module.

        @param mod_name: module name
        @param regex: (compiled) regular expression, with one group
        """
        if self.exist([mod_name], skip_avail=True)[0]:
            modinfo = self.show(mod_name)
            res = regex.search(modinfo)
            if res:
                return res.group(1)
            else:
                raise EasyBuildError("Failed to determine value from 'show' (pattern: '%s') in %s",
                                     regex.pattern, modinfo)
        else:
            raise EasyBuildError("Can't get value from a non-existing module %s", mod_name)

    def modulefile_path(self, mod_name, strip_ext=False):
        """
        Get the path of the module file for the specified module

        @param mod_name: module name
        @param strip_ext: strip (.lua) extension from module fileame (if present)"""
        # (possible relative) path is always followed by a ':', and may be prepended by whitespace
        # this works for both environment modules and Lmod
        modpath_re = re.compile('^\s*(?P<modpath>[^/\n]*/[^ ]+):$', re.M)
        modpath = self.get_value_from_modulefile(mod_name, modpath_re)

        if strip_ext and modpath.endswith('.lua'):
            modpath = os.path.splitext(modpath)[0]

        return modpath

    def set_path_env_var(self, key, paths):
        """Set path environment variable to the given list of paths."""
        os.environ[key] = os.pathsep.join(paths)

    def run_module(self, *args, **kwargs):
        """
        Run module command.
        """
        if isinstance(args[0], (list, tuple,)):
            args = args[0]
        else:
            args = list(args)

        if args[0] in ('available', 'avail', 'list',):
            # run these in terse mode for easier machine reading
            args.insert(*self.TERSE_OPTION)

        module_path_key = None
        if 'mod_paths' in kwargs:
            module_path_key = 'mod_paths'
        elif 'modulePath' in kwargs:
            module_path_key = 'modulePath'
        if module_path_key is not None:
            self.log.nosupport("Use of '%s' named argument in 'run_module'" % module_path_key, '2.0')

        self.log.debug('Current MODULEPATH: %s' % os.environ.get('MODULEPATH', ''))

        # restore selected original environment variables before running module command
        environ = os.environ.copy()
        for key in LD_ENV_VAR_KEYS:
            environ[key] = ORIG_OS_ENVIRON.get(key, '')
            self.log.debug("Changing %s from '%s' to '%s' in environment for module command",
                           key, os.environ.get(key, ''), environ[key])

        # prefix if a particular shell is specified, using shell argument to Popen doesn't work (no output produced (?))
        cmdlist = [self.cmd, 'python']
        if self.COMMAND_SHELL is not None:
            if not isinstance(self.COMMAND_SHELL, (list, tuple)):
                raise EasyBuildError("COMMAND_SHELL needs to be list or tuple, now %s (value %s)",
                                     type(self.COMMAND_SHELL), self.COMMAND_SHELL)
            cmdlist = self.COMMAND_SHELL + cmdlist

        full_cmd = ' '.join(cmdlist + args)
        self.log.debug("Running module command '%s' from %s" % (full_cmd, os.getcwd()))

        proc = subprocess.Popen(cmdlist + args, stdout=PIPE, stderr=PIPE, env=environ)
        # stdout will contain python code (to change environment etc)
        # stderr will contain text (just like the normal module command)
        (stdout, stderr) = proc.communicate()
        self.log.debug("Output of module command '%s': stdout: %s; stderr: %s" % (full_cmd, stdout, stderr))

        if kwargs.get('return_output', False):
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
                exec stdout
            except Exception, err:
                out = "stdout: %s, stderr: %s" % (stdout, stderr)
                raise EasyBuildError("Changing environment as dictated by module failed: %s (%s)", err, out)

            # correct values of selected environment variables as yielded by the adjustments made
            # make sure we get the order right (reverse lists with [::-1])
            for key in LD_ENV_VAR_KEYS:
                curr_ld_val = os.environ.get(key, '').split(os.pathsep)
                new_ld_val = [x for x in nub(prev_ld_values[key] + curr_ld_val[::-1]) if x][::-1]

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

    def read_module_file(self, mod_name):
        """
        Read module file with specified name.
        """
        modfilepath = self.modulefile_path(mod_name)
        self.log.debug("modulefile path %s: %s" % (mod_name, modfilepath))

        return read_file(modfilepath)

    def modpath_extensions_for(self, mod_names):
        """
        Determine dictionary with $MODULEPATH extensions for specified modules.
        All potential $MODULEPATH extensions are included, even the ones guarded by a condition (which is not checked).
        Only direct $MODULEPATH extensions are found, no recursion if performed for modules that load other modules.
        Modules with an empty list of $MODULEPATH extensions are included in the result.

        @param mod_names: list of module names for which to determine the list of $MODULEPATH extensions
        @return: dictionary with module names as keys and lists of $MODULEPATH extensions as values
        """
        self.log.debug("Determining $MODULEPATH extensions for modules %s" % mod_names)

        # copy environment so we can restore it
        env = os.environ.copy()

        # regex for $MODULEPATH extensions;
        # via 'module use ...' or 'prepend-path MODULEPATH' in Tcl modules,
        # or 'prepend_path("MODULEPATH", "...") in Lua modules
        modpath_ext_regex = r'|'.join([
            r'^\s*module\s+use\s+"?([^"\s]+)"?',  # 'module use' in Tcl module files
            r'^\s*prepend-path\s+MODULEPATH\s+"?([^"\s]+)"?',  # prepend to $MODULEPATH in Tcl modules
            r'^\s*prepend_path\(\"MODULEPATH\",\s*\"(\S+)\"',  # prepend to $MODULEPATH in Lua modules
        ])
        modpath_ext_regex = re.compile(modpath_ext_regex, re.M)

        modpath_exts = {}
        for mod_name in mod_names:
            modtxt = self.read_module_file(mod_name)
            exts = [ext for tup in modpath_ext_regex.findall(modtxt) for ext in tup if ext]
            self.log.debug("Found $MODULEPATH extensions for %s: %s", mod_name, exts)
            modpath_exts.update({mod_name: exts})

            if exts:
                # load this module, since it may extend $MODULEPATH to make other modules available
                # this is required to obtain the list of $MODULEPATH extensions they make (via 'module show')
                self.load([mod_name])

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

        @param top_paths: list of potentation 'top of module tree' (absolute) paths
        @param mod_name: (short) module name for starting point (only used in log messages)
        @param full_mod_subdir: absolute path to module subdirectory for starting point
        @param deps: list of dependency modules for module at starting point
        @param modpath_exts: list of module path extensions for each of the dependency modules
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
                dep_full_mod_subdir = self.modulefile_path(dep, strip_ext=True)[:-len(dep)-1]
                full_mod_subdirs.append(dep_full_mod_subdir)

                mods_to_top.append(dep)
                self.log.debug("Found module to top of module tree: %s (subdir: %s, modpath extensions %s)",
                               dep, dep_full_mod_subdir, full_modpath_exts)

            if full_modpath_exts:
                # load module for this dependency, since it may extend $MODULEPATH to make dependencies available
                # this is required to obtain the corresponding module file paths (via 'module show')
                self.load([dep])

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

    def update(self):
        """Update after new modules were added."""
        raise NotImplementedError


class EnvironmentModulesC(ModulesTool):
    """Interface to (C) environment modules (modulecmd)."""
    COMMAND = "modulecmd"
    REQ_VERSION = '3.2.10'
    VERSION_REGEXP = r'^\s*(VERSION\s*=\s*)?(?P<version>\d\S*)\s*'

    def update(self):
        """Update after new modules were added."""
        pass


class EnvironmentModulesTcl(EnvironmentModulesC):
    """Interface to (Tcl) environment modules (modulecmd.tcl)."""
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
        os.environ['%s_modshare' % key] = ':1:'.join(paths)

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
            modulescript_regex = "^exec\s+[\"'](?P<modulescript>/tmp/modulescript_[0-9_]+)[\"']$"
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

        @param name: a (partial) module name for filtering (default: None)
        """
        mods = super(EnvironmentModulesTcl, self).available(mod_name=mod_name)
        # strip off slash at beginning, if it's there
        # under certain circumstances, 'modulecmd.tcl avail' (DEISA variant) spits out available modules like this
        clean_mods = [mod.lstrip(os.path.sep) for mod in mods]

        return clean_mods

    def remove_module_path(self, path, set_mod_paths=True):
        """
        Remove specified module path (using 'module unuse').

        @param path: path to remove from $MODULEPATH via 'unuse'
        @param set_mod_paths: (re)set self.mod_paths
        """
        # remove module path via 'module use' and make sure self.mod_paths is synced
        # modulecmd.tcl keeps track of how often a path was added via 'module use',
        # so we need to check to make sure it's really removed
        while path in curr_module_paths():
            self.unuse(path)
        if set_mod_paths:
            self.set_mod_paths()


class Lmod(ModulesTool):
    """Interface to Lmod."""
    COMMAND = 'lmod'
    COMMAND_ENVIRONMENT = 'LMOD_CMD'
    # required and optimal version
    # we need at least Lmod v5.6.3 (and it can't be a release candidate)
    REQ_VERSION = '5.6.3'
    VERSION_REGEXP = r"^Modules\s+based\s+on\s+Lua:\s+Version\s+(?P<version>\d\S*)\s"
    USER_CACHE_DIR = os.path.join(os.path.expanduser('~'), '.lmod.d', '.cache')

    def __init__(self, *args, **kwargs):
        """Constructor, set lmod-specific class variable values."""
        # $LMOD_QUIET needs to be set to avoid EasyBuild tripping over fiddly bits in output
        os.environ['LMOD_QUIET'] = '1'
        # make sure Lmod ignores the spider cache ($LMOD_IGNORE_CACHE supported since Lmod 5.2)
        os.environ['LMOD_IGNORE_CACHE'] = '1'
        # hard disable output redirection, we expect output messages (list, avail) to always go to stderr
        os.environ['LMOD_REDIRECT'] = 'no'

        super(Lmod, self).__init__(*args, **kwargs)

    def check_module_function(self, *args, **kwargs):
        """Check whether selected module tool matches 'module' function definition."""
        if not 'regex' in kwargs:
            kwargs['regex'] = r".*(%s|%s)" % (self.COMMAND, self.COMMAND_ENVIRONMENT)
        super(Lmod, self).check_module_function(*args, **kwargs)

    def available(self, mod_name=None):
        """
        Return a list of available modules for the given (partial) module name;
        use None to obtain a list of all available modules.

        @param name: a (partial) module name for filtering (default: None)
        """
        extra_args = []
        if StrictVersion(self.version) >= StrictVersion('5.7.5'):
            # make hidden modules visible for recent version of Lmod
            extra_args = ['--show_hidden']

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

            proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, env=os.environ)
            (stdout, stderr) = proc.communicate()

            if stderr:
                raise EasyBuildError("An error occured when running '%s': %s", ' '.join(cmd), stderr)

            if self.testing:
                # don't actually update local cache when testing, just return the cache contents
                return stdout
            else:
                try:
                    cache_fp = os.path.join(self.USER_CACHE_DIR, 'moduleT.lua')
                    self.log.debug("Updating Lmod spider cache %s with output from '%s'" % (cache_fp, ' '.join(cmd)))
                    cache_dir = os.path.dirname(cache_fp)
                    if not os.path.exists(cache_dir):
                        mkdir(cache_dir, parents=True)
                    cache_file = open(cache_fp, 'w')
                    cache_file.write(stdout)
                    cache_file.close()
                except (IOError, OSError), err:
                    raise EasyBuildError("Failed to update Lmod spider cache %s: %s", cache_fp, err)

    def prepend_module_path(self, path, set_mod_paths=True):
        """
        Prepend given module path to list of module paths, or bump it to 1st place.

        @param path: path to prepend to $MODULEPATH
        @param set_mod_paths: (re)set self.mod_paths
        """
        # Lmod pushes a path to the front on 'module use', no need for (costly) 'module unuse'
        modulepath = curr_module_paths()
        if not modulepath or modulepath[0] != path:
            self.use(path)
            if set_mod_paths:
                self.set_mod_paths()

    def exist(self, mod_names, skip_avail=False):
        """
        Check if modules with specified names exists.

        @param mod_names: list of module names
        @param skip_avail: skip checking through 'module avail', only check via 'module show'
        """
        # module file may be either in Tcl syntax (no file extension) or Lua sytax (.lua extension);
        # the current configuration for matters little, since the module may have been installed with a different cfg;
        # Lmod may pick up both Tcl and Lua module files, regardless of the EasyBuild configuration
        return super(Lmod, self).exist(mod_names, mod_exists_regex_template=r'^\s*\S*/%s.*(\.lua)?:\s*$',
                                       skip_avail=skip_avail)


def get_software_root_env_var_name(name):
    """Return name of environment variable for software root."""
    newname = convert_name(name, upper=True)
    return ROOT_ENV_VAR_NAME_PREFIX + newname


def get_software_root(name, with_env_var=False):
    """
    Return the software root set for a particular software name.
    """
    env_var = get_software_root_env_var_name(name)
    legacy_key = "SOFTROOT%s" % convert_name(name, upper=True)

    root = None
    if env_var in os.environ:
        root = os.getenv(env_var)

    elif legacy_key in os.environ:
        _log.nosupport("Legacy env var %s is being relied on!" % legacy_key, "2.0")

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

    @param: name of the software package
    @param only_one: indicates whether only one lib path is expected to be found
    @param fs: only retain library subdirs that contain one of the files in this list
    """
    lib_subdirs = ['lib', 'lib64']
    root = get_software_root(name)
    res = []
    if root:
        for lib_subdir in lib_subdirs:
            if os.path.exists(os.path.join(root, lib_subdir)):
                if fs is None or any([os.path.exists(os.path.join(root, lib_subdir, f)) for f in fs]):
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
    legacy_key = "SOFTVERSION%s" % convert_name(name, upper=True)

    version = None
    if env_var in os.environ:
        version = os.getenv(env_var)
    elif legacy_key in os.environ:
        _log.nosupport("Legacy env var %s is being relied on!" % legacy_key, "2.0")

    return version

def curr_module_paths():
    """
    Return a list of current module paths.
    """
    # avoid empty entries, which don't make any sense
    return [p for p in os.environ.get('MODULEPATH', '').split(':') if p]


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
    return class_dict


def modules_tool(mod_paths=None, testing=False):
    """
    Return interface to modules tool (environment modules (C, Tcl), or Lmod)
    """
    # get_modules_tool might return none (e.g. if config was not initialized yet)
    modules_tool = get_modules_tool()
    if modules_tool is not None:
        modules_tool_class = avail_modules_tools().get(modules_tool)
        return modules_tool_class(mod_paths=mod_paths, testing=testing)
    else:
        return None


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
        for key in cache.keys():
            paths_in_key = '='.join(key[0].split('=')[1:]).split(os.pathsep)
            _log.debug("Paths for 'module %s' key '%s': %s", subcmd, key, paths_in_key)
            for path_in_key in paths_in_key:
                if path == path_in_key or (os.path.exists(path_in_key) and os.path.samefile(path, path_in_key)):
                    _log.debug("Entry '%s' in 'module %s' cache is evicted, marked as invalid via path '%s': %s",
                               key, subcmd, path, cache[key])
                    del cache[key]


class Modules(EnvironmentModulesC):
    """NO LONGER SUPPORTED: interface to modules tool, use modules_tool from easybuild.tools.modules instead"""
    def __init__(self, *args, **kwargs):
        _log.nosupport("modules.Modules class is now an abstract interface, use modules.modules_tool instead", '2.0')
