# #
# Copyright 2009-2014 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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
# #
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
import sys
from distutils.version import StrictVersion
from subprocess import PIPE
from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses, any

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, get_modules_tool, install_path
from easybuild.tools.filetools import convert_name, mkdir, read_file, which
from easybuild.tools.module_generator import det_full_module_name, DEVEL_MODULE_SUFFIX, GENERAL_CLASS
from easybuild.tools.run import run_cmd
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME, DUMMY_TOOLCHAIN_VERSION
from vsc.utils.missing import nub

# software root/version environment variable name prefixes
ROOT_ENV_VAR_NAME_PREFIX = "EBROOT"
VERSION_ENV_VAR_NAME_PREFIX = "EBVERSION"
DEVEL_ENV_VAR_NAME_PREFIX = "EBDEVEL"

# keep track of original LD_LIBRARY_PATH, because we can change it by loading modules and break modulecmd
# see e.g., https://bugzilla.redhat.com/show_bug.cgi?id=719785
LD_LIBRARY_PATH = os.getenv('LD_LIBRARY_PATH', '')

output_matchers = {
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

_log = fancylogger.getLogger('modules', fname=False)


class ModulesTool(object):
    """An abstract interface to a tool that deals with modules."""
    # position and optionname
    TERSE_OPTION = (0, '--terse')
    # module command to use
    COMMAND = None
    # environment variable to determine the module command (instead of COMMAND)
    COMMAND_ENVIRONMENT = None
    # run module command explicitly using this shell
    COMMAND_SHELL = None
    # option to determine the version
    VERSION_OPTION = '--version'
    # minimal required version (StrictVersion; suffix rc replaced with b (and treated as beta by StrictVersion))
    REQ_VERSION = None
    # the regexp, should have a "version" group (multiline search)
    VERSION_REGEXP = None

    def __init__(self, mod_paths=None):
        """
        Create a ModulesTool object
        @param mod_paths: A list of paths where the modules can be located
        @type mod_paths: list
        """

        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        # make sure we don't have the same path twice
        if mod_paths is None:
            self.mod_paths = None
        else:
            self.mod_paths = nub(mod_paths)

        # DEPRECATED!
        self._modules = []

        self.check_module_path()

        # actual module command (i.e., not the 'module' wrapper function, but the binary)
        self.cmd = self.COMMAND
        if self.COMMAND_ENVIRONMENT is not None and self.COMMAND_ENVIRONMENT in os.environ:
            self.log.debug('Set command via environment variable %s' % self.COMMAND_ENVIRONMENT)
            self.cmd = os.environ[self.COMMAND_ENVIRONMENT]

        if self.cmd is None:
            self.log.error('No command set.')
        else:
            self.log.debug('Using command %s' % self.cmd)

        # version of modules tool
        self.version = None

        # some initialisation/verification
        self.check_cmd_avail()
        self.check_module_function(allow_mismatch=build_option('allow_modules_tool_mismatch'))
        self.set_and_check_version()
        self.use_module_paths()

        # this can/should be set to True during testing
        self.testing = False

    def buildstats(self):
        """Return tuple with data to be included in buildstats"""
        return (self.__class__.__name__, self.cmd, self.version)

    @property
    def modules(self):
        """Property providing access to deprecated 'modules' class variable."""
        self.log.deprecated("'modules' class variable is deprecated, just use load([<list of modules>])", '2.0')
        return self._modules

    def set_and_check_version(self):
        """Get the module version, and check any requirements"""
        txt = self.run_module(self.VERSION_OPTION, return_output=True)
        if self.VERSION_REGEXP is None:
            self.log.error('No VERSION_REGEXP defined')

        try:
            txt = self.run_module(self.VERSION_OPTION, return_output=True)

            ver_re = re.compile(self.VERSION_REGEXP, re.M)
            res = ver_re.search(txt)
            if res:
                self.version = res.group('version')
                self.log.info("Found version %s" % self.version)
            else:
                self.log.error("Failed to determine version from option '%s' output: %s" % (self.VERSION_OPTION, txt))
        except (OSError), err:
            self.log.error("Failed to check version: %s" % err)

        if self.REQ_VERSION is None:
            self.log.debug('No version requirement defined.')
        else:
            # replace 'rc' by 'b', to make StrictVersion treat it as a beta-release
            if StrictVersion(self.version.replace('rc', 'b')) < StrictVersion(self.REQ_VERSION):
                msg = "EasyBuild requires v%s >= v%s (no rc), found v%s"
                self.log.error(msg % (self.__class__.__name__, self.REQ_VERSION, self.version))
            else:
                self.log.debug('Version %s matches requirement %s' % (self.version, self.REQ_VERSION))

    def check_cmd_avail(self):
        """Check whether modules tool command is available."""
        cmd_path = which(self.cmd)
        if cmd_path is not None:
            self.cmd = cmd_path
            self.log.info("Full path for module command is %s, so using it" % self.cmd)
        else:
            mod_tool = self.__class__.__name__
            self.log.error("%s modules tool can not be used, '%s' command is not available." % (mod_tool, self.cmd))

    def check_module_function(self, allow_mismatch=False, regex=None):
        """Check whether selected module tool matches 'module' function definition."""
        out, ec = run_cmd("type module", simple=False, log_ok=False, log_all=False)
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
                    self.log.error(msg)
        else:
            # module function may not be defined (weird, but fine)
            self.log.warning("No 'module' function defined, can't check if it matches %s." % mod_details)

    def check_module_path(self):
        """
        Check if MODULEPATH is set and change it if necessary.
        """
        # if self.mod_paths is not specified, use $MODULEPATH and make sure the EasyBuild module path is in there (first)
        if self.mod_paths is None:
            # take module path from environment
            self.mod_paths = [x for x in nub(os.environ.get('MODULEPATH', '').split(':')) if len(x) > 0]
            self.log.debug("self.mod_paths set based on $MODULEPATH: %s" % self.mod_paths)

            # determine module path for EasyBuild install path to be included in $MODULEPATH
            eb_modpath = os.path.join(install_path(typ='modules'), GENERAL_CLASS)

            # make sure EasyBuild module path is in 1st place
            self.mod_paths = [x for x in self.mod_paths if not x == eb_modpath]
            self.mod_paths.insert(0, eb_modpath)
            self.log.info("Prepended list of module paths with path used by EasyBuild: %s" % eb_modpath)

        # set the module path environment accordingly
        os.environ['MODULEPATH'] = ':'.join(self.mod_paths)
        self.log.info("$MODULEPATH set based on list of module paths: %s" % os.environ['MODULEPATH'])

    def use_module_paths(self):
        """Run 'module use' on all paths in $MODULEPATH."""
        # we need to run '<module command> python use <path>' on all paths in $MODULEPATH
        # not all modules tools follow whatever is in $MODULEPATH, some take extra action for every module path
        # usually, additional environment variables are set, e.g. $LMOD_DEFAULT_MODULEPATH or $MODULEPATH_modshare
        # note: we're stepping through the mod_paths in reverse order to preserve order in $MODULEPATH in the end
        for modpath in self.mod_paths[::-1]:
            if not os.path.isabs(modpath):
                modpath = os.path.join(os.getcwd(), modpath)
            if os.path.exists(modpath):
                self.run_module(['use', modpath])
            else:
                self.log.warning("Ignoring non-existing module path in $MODULEPATH: %s" % modpath)

    def available(self, mod_name=None):
        """
        Return a list of available modules for the given (partial) module name;
        use None to obtain a list of all available modules.

        @param mod_name: a (partial) module name for filtering (default: None)
        """
        if mod_name is None:
            mod_name = ''
        mods = self.run_module('avail', mod_name)

        # sort list of modules in alphabetical order
        mods.sort(key=lambda m: m['mod_name'])
        ans = nub([mod['mod_name'] for mod in mods])

        self.log.debug("'module available %s' gave %d answers: %s" % (mod_name, len(ans), ans))
        return ans

    def exists(self, mod_name):
        """
        Check if module with specified name exists.
        """
        return mod_name in self.available(mod_name)

    def add_module(self, modules):
        """
        Check if module exist, if so add to list.
        """
        self.log.deprecated("Use of add_module function should be replaced by load([<list of modules>])", '2.0')
        for mod in modules:
            if isinstance(mod, (list, tuple)):
                mod_dict = {
                    'name': mod[0],
                    'version': mod[1],
                    'versionsuffix': '',
                    'toolchain': {
                        'name': DUMMY_TOOLCHAIN_NAME,
                        'version': DUMMY_TOOLCHAIN_VERSION,
                    },
                }
                mod_name = det_full_module_name(mod_dict)
            elif isinstance(mod, basestring):
                mod_name = mod
            elif isinstance(mod, dict):
                mod_name = det_full_module_name(mod)
            else:
                self.log.error("Can't add module %s: unknown type" % str(mod))

            mods = self.available(mod_name)
            if mod_name in mods:
                # ok
                self._modules.append(mod_name)
            else:
                if len(mods) == 0:
                    self.log.warning('No module %s available' % str(mod))
                else:
                    self.log.warning('More than one module found for %s: %s' % (mod, mods))
                continue

    def remove_module(self, modules):
        """
        Remove modules from list.
        """
        self.log.deprecated("remove_module should no longer be used (add_module is deprecated too).", '2.0')
        for mod in modules:
            self._modules = [m for m in self._modules if not m == mod]

    def load(self, modules=None):
        """
        Load all requested modules.
        """
        if modules is None:
            # deprecated behavior if no modules were passed by argument
            self.log.deprecated("Loading modules listed in _modules class variable", '2.0')
            modules = self._modules[:]

        for mod in modules:
            self.run_module('load', mod)

    def unload(self, modules=None):
        """
        Unload all requested modules.
        """
        if modules is None:
            self.log.deprecated("Unloading modules listed in _modules class variable", '2.0')
            modules = self._modules[:]

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
        return self.run_module('show', mod_name, return_output=True)

    def get_value_from_modulefile(self, mod_name, regex):
        """
        Get info from the module file for the specified module.

        @param mod_name: module name
        @param regex: (compiled) regular expression, with one group
        """
        if self.exists(mod_name):
            modinfo = self.show(mod_name)
            self.log.debug("modinfo: %s" % modinfo)
            res = regex.search(modinfo)
            if res:
                return res.group(1)
            else:
                self.log.error("Failed to determine value from 'show' (pattern: '%s') in %s" % (regex.pattern, modinfo))
        else:
            raise EasyBuildError("Can't get module file path for non-existing module %s" % mod_name)

    def modulefile_path(self, mod_name):
        """Get the path of the module file for the specified module."""
        # (possible relative) path is always followed by a ':', and may be prepended by whitespace
        # this works for both environment modules and Lmod
        modpath_re = re.compile('^\s*(?P<modpath>[^/\n]*/[^ ]+):$', re.M)
        return self.get_value_from_modulefile(mod_name, modpath_re)

    def module_software_name(self, mod_name):
        """Get the software name for a given module name."""
        raise NotImplementedError

    def set_ld_library_path(self, ld_library_paths):
        """Set $LD_LIBRARY_PATH to the given list of paths."""
        os.environ['LD_LIBRARY_PATH'] = ':'.join(ld_library_paths)

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
        original_module_path = None
        if 'mod_paths' in kwargs:
            module_path_key = 'mod_paths'
        elif 'modulePath' in kwargs:
            module_path_key = 'modulePath'
        if module_path_key is not None:
            original_module_path = os.environ['MODULEPATH']
            os.environ['MODULEPATH'] = kwargs[module_path_key]
            self.log.deprecated("Use of '%s' named argument in 'run_module'" % module_path_key, '2.0')

        # after changing $MODULEPATH, we should adjust self.mod_paths and run use_module_paths(),
        # but we can't do that here becaue it would yield infinite recursion on run_module
        self.log.debug('Current MODULEPATH: %s' % os.environ['MODULEPATH'])

        # change our LD_LIBRARY_PATH here
        environ = os.environ.copy()
        environ['LD_LIBRARY_PATH'] = LD_LIBRARY_PATH
        cur_ld_library_path = os.environ.get('LD_LIBRARY_PATH', '')
        new_ld_library_path = environ['LD_LIBRARY_PATH']
        self.log.debug("Adjusted LD_LIBRARY_PATH from '%s' to '%s'" % (cur_ld_library_path, new_ld_library_path))

        # prefix if a particular shell is specified, using shell argument to Popen doesn't work (no output produced (?))
        cmdlist = [self.cmd, 'python']
        if self.COMMAND_SHELL is not None:
            if not isinstance(self.COMMAND_SHELL, (list, tuple)):
                msg = 'COMMAND_SHELL needs to be list or tuple, now %s (value %s)'
                self.log.error(msg % (type(self.COMMAND_SHELL), self.COMMAND_SHELL))
            cmdlist = self.COMMAND_SHELL + cmdlist

        self.log.debug("Running module command '%s' from %s" % (' '.join(cmdlist + args), os.getcwd()))
        proc = subprocess.Popen(cmdlist + args, stdout=PIPE, stderr=PIPE, env=environ)
        # stdout will contain python code (to change environment etc)
        # stderr will contain text (just like the normal module command)
        (stdout, stderr) = proc.communicate()
        if original_module_path is not None:
            os.environ['MODULEPATH'] = original_module_path
            self.log.deprecated("Restoring $MODULEPATH back to what it was before running module command/.", '2.0')
            # after changing $MODULEPATH, we should adjust self.mod_paths and run use_module_paths(),
            # but we can't do that here becaue it would yield infinite recursion on run_module

        if kwargs.get('return_output', False):
            return stdout + stderr
        else:
            # the module command was run with an outdated LD_LIBRARY_PATH, which will be adjusted on loading a module
            # this needs to be taken into account when updating the environment via produced output, see below

            # keep track of current LD_LIBRARY_PATH, so we can correct the adjusted LD_LIBRARY_PATH below
            prev_ld_library_path = os.environ.get('LD_LIBRARY_PATH', '').split(':')[::-1]

            # Change the environment
            try:
                tweak_fn = kwargs.get('tweak_stdout')
                if tweak_fn is not None:
                    stdout = tweak_fn(stdout)
                exec stdout
            except Exception, err:
                out = "stdout: %s, stderr: %s" % (stdout, stderr)
                raise EasyBuildError("Changing environment as dictated by module failed: %s (%s)" % (err, out))

            # correct LD_LIBRARY_PATH as yielded by the adjustments made
            # make sure we get the order right (reverse lists with [::-1])
            curr_ld_library_path = os.environ.get('LD_LIBRARY_PATH', '').split(':')
            new_ld_library_path = [x for x in nub(prev_ld_library_path + curr_ld_library_path[::-1]) if len(x)][::-1]

            self.log.debug("Correcting paths in LD_LIBRARY_PATH from %s to %s" %
                           (curr_ld_library_path, new_ld_library_path))
            self.set_ld_library_path(new_ld_library_path)

            # Process stderr
            result = []
            for line in stderr.split('\n'):  # IGNORE:E1103
                if output_matchers['whitespace'].search(line):
                    continue

                error = output_matchers['error'].search(line)
                if error:
                    self.log.error(line)
                    raise EasyBuildError(line)

                modules = output_matchers['available'].finditer(line)
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

    # depth=sys.maxint should be equivalent to infinite recursion depth
    def dependencies_for(self, mod_name, depth=sys.maxint):
        """
        Obtain a list of dependencies for the given module, determined recursively, up to a specified depth (optionally)
        """
        modfilepath = self.modulefile_path(mod_name)
        self.log.debug("modulefile path %s: %s" % (mod_name, modfilepath))

        modtxt = read_file(modfilepath)

        loadregex = re.compile(r"^\s+module load\s+(.*)$", re.M)
        mods = loadregex.findall(modtxt)

        if depth > 0:
            # recursively determine dependencies for these dependency modules, until depth is non-positive
            moddeps = [self.dependencies_for(mod, depth=depth - 1) for mod in mods]
        else:
            # ignore any deeper dependencies
            moddeps = []

        # add dependencies of dependency modules only if they're not there yet
        for moddepdeps in moddeps:
            for dep in moddepdeps:
                if not dep in mods:
                    mods.append(dep)

        return mods

    def update(self):
        """Update after new modules were added."""
        raise NotImplementedError


class EnvironmentModulesC(ModulesTool):
    """Interface to (C) environment modules (modulecmd)."""
    COMMAND = "modulecmd"
    VERSION_REGEXP = r'^\s*(VERSION\s*=\s*)?(?P<version>\d\S*)\s*'

    def module_software_name(self, mod_name):
        """Get the software name for a given module name."""
        # line that specified conflict contains software name
        name_re = re.compile('^conflict\s*(?P<name>\S+).*$', re.M)
        return self.get_value_from_modulefile(mod_name, name_re)

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
    VERSION_REGEXP = r'^Modules\s+Release\s+Tcl\s+(?P<version>\d\S*)\s'

    def set_ld_library_path(self, ld_library_paths):
        """Set $LD_LIBRARY_PATH to the given list of paths."""
        super(EnvironmentModulesTcl, self).set_ld_library_path(ld_library_paths)
        # for Tcl environment modules, we need to make sure the _modshare env var is kept in sync
        os.environ['LD_LIBRARY_PATH_modshare'] = ':1:'.join(ld_library_paths)

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
        if args[0] in ['load', 'purge', 'unload', 'use']:
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


class Lmod(ModulesTool):
    """Interface to Lmod."""
    COMMAND = 'lmod'
    COMMAND_ENVIRONMENT = 'LMOD_CMD'
    # required and optimal version
    # we need at least Lmod v5.2 (and it can't be a release candidate)
    REQ_VERSION = '5.2'
    VERSION_REGEXP = r"^Modules\s+based\s+on\s+Lua:\s+Version\s+(?P<version>\d\S*)\s"

    def __init__(self, *args, **kwargs):
        """Constructor, set lmod-specific class variable values."""
        # $LMOD_EXPERT needs to be set to avoid EasyBuild tripping over fiddly bits in output
        os.environ['LMOD_EXPERT'] = '1'
        # make sure Lmod ignores the spider cache ($LMOD_IGNORE_CACHE supported since Lmod 5.2)
        os.environ['LMOD_IGNORE_CACHE'] = '1'

        super(Lmod, self).__init__(*args, **kwargs)

    def set_and_check_version(self):
        """Get the module version, and check any requirements"""

        # 'lmod python update' needs to be run after changing $MODULEPATH
        self.run_module('update')

        super(Lmod, self).set_and_check_version()

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
        mods = super(Lmod, self).available(mod_name=mod_name)
        # only retain actual modules, exclude module directories (which end with a '/')
        real_mods = [mod for mod in mods if not mod.endswith('/')]

        # only retain modules that with a <mod_name> prefix
        # Lmod will also returns modules with a matching substring
        correct_real_mods = [mod for mod in real_mods if mod_name is None or mod.startswith(mod_name)]

        return correct_real_mods

    def update(self):
        """Update after new modules were added."""
        spider_cmd = os.path.join(os.path.dirname(self.cmd), 'spider')
        cmd = [spider_cmd, '-o', 'moduleT', os.environ['MODULEPATH']]
        self.log.debug("Running command '%s'..." % ' '.join(cmd))
        proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, env=os.environ)
        (stdout, stderr) = proc.communicate()

        if stderr:
            self.log.error("An error occured when running '%s': %s" % (' '.join(cmd), stderr))

        if self.testing:
            # don't actually update local cache when testing, just return the cache contents
            return stdout
        else:
            try:
                cache_filefn = os.path.join(os.path.expanduser('~'), '.lmod.d', '.cache', 'moduleT.lua')
                self.log.debug("Updating Lmod spider cache %s with output from '%s'" % (cache_filefn, ' '.join(cmd)))
                cache_dir = os.path.dirname(cache_filefn)
                if not os.path.exists(cache_dir):
                    mkdir(cache_dir, parents=True)
                cache_file = open(cache_filefn, 'w')
                cache_file.write(stdout)
                cache_file.close()
            except (IOError, OSError), err:
                self.log.error("Failed to update Lmod spider cache %s: %s" % (cache_filefn, err))

    def module_software_name(self, mod_name):
        """Get the software name for a given module name."""
        # line that specified conflict contains software name
        name_re = re.compile('^conflict\("*(?P<name>[^ "]+)"\).*$', re.M)
        return self.get_value_from_modulefile(mod_name, name_re)


def get_software_root_env_var_name(name):
    """Return name of environment variable for software root."""
    newname = convert_name(name, upper=True)
    return ''.join([ROOT_ENV_VAR_NAME_PREFIX, newname])


def get_software_root(name, with_env_var=False):
    """
    Return the software root set for a particular software name.
    """
    environment_key = get_software_root_env_var_name(name)
    newname = convert_name(name, upper=True)
    legacy_key = "SOFTROOT%s" % newname

    # keep on supporting legacy installations
    if environment_key in os.environ:
        env_var = environment_key
    else:
        env_var = legacy_key
        if legacy_key in os.environ:
            _log.deprecated("Legacy env var %s is being relied on!" % legacy_key, "2.0")

    root = os.getenv(env_var)

    if with_env_var:
        return (root, env_var)
    else:
        return root


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
        # if no library subdir was found, return None
        if not res:
            return None
        if only_one:
            if len(res) == 1:
                res = res[0]
            else:
                _log.error("Multiple library subdirectories found for %s in %s: %s" % (name, root, ', '.join(res)))
        return res
    else:
        # return None if software package root could not be determined
        return None


def get_software_version_env_var_name(name):
    """Return name of environment variable for software root."""
    newname = convert_name(name, upper=True)
    return ''.join([VERSION_ENV_VAR_NAME_PREFIX, newname])


def get_software_version(name):
    """
    Return the software version set for a particular software name.
    """
    environment_key = get_software_version_env_var_name(name)
    newname = convert_name(name, upper=True)
    legacy_key = "SOFTVERSION%s" % newname

    # keep on supporting legacy installations
    if environment_key in os.environ:
        return os.getenv(environment_key)
    else:
        if legacy_key in os.environ:
            _log.deprecated("Legacy env var %s is being relied on!" % legacy_key, "2.0")
        return os.getenv(legacy_key)


def curr_module_paths():
    """
    Return a list of current module paths.
    """
    return os.environ.get('MODULEPATH', '').split(':')


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


def modules_tool(mod_paths=None):
    """
    Return interface to modules tool (environment modules (C, Tcl), or Lmod)
    """
    # get_modules_tool might return none (e.g. if config was not initialized yet)
    modules_tool = get_modules_tool()
    if modules_tool is not None:
        modules_tool_class = avail_modules_tools().get(modules_tool)
        return modules_tool_class(mod_paths=mod_paths)
    else:
        return None


# provide Modules class for backward compatibility (e.g., in easyblocks)
class Modules(EnvironmentModulesC):
    """Deprecated interface to modules tool."""

    def __init__(self, *args, **kwargs):
        _log.deprecated("modules.Modules class is now an abstract interface, use modules.modules_tool instead", "2.0")
        super(Modules, self).__init__(*args, **kwargs)
