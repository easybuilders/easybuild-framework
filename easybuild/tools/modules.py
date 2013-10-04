##
# Copyright 2009-2013 Ghent University
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
import tempfile
from distutils.version import LooseVersion
from subprocess import PIPE
from vsc import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import get_modules_tool
from easybuild.tools.filetools import convert_name, run_cmd, read_file
from easybuild.tools.module_generator import det_full_module_name, DEVEL_MODULE_SUFFIX
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME, DUMMY_TOOLCHAIN_VERSION
from vsc.utils.missing import nub

# software root/version environment variable name prefixes
ROOT_ENV_VAR_NAME_PREFIX = "EBROOT"
VERSION_ENV_VAR_NAME_PREFIX = "EBVERSION"
DEVEL_ENV_VAR_NAME_PREFIX = "EBDEVEL"

# keep track of original LD_LIBRARY_PATH, because we can change it by loading modules and break modulecmd
# see e.g., https://bugzilla.redhat.com/show_bug.cgi?id=719785
LD_LIBRARY_PATH = os.getenv('LD_LIBRARY_PATH', '')

outputMatchers = {
    # matches whitespace and module-listing headers
    'whitespace': re.compile(r"^\s*$|^(-+).*(-+)$"),
    # matches errors such as "cmdTrace.c(713):ERROR:104: 'asdfasdf' is an unrecognized subcommand"
    ## following errors should not be matches, they are considered warnings
    # ModuleCmd_Avail.c(529):ERROR:57: Error while reading directory '/usr/local/modulefiles/SCIENTIFIC'
    # ModuleCmd_Avail.c(804):ERROR:64: Directory '/usr/local/modulefiles/SCIENTIFIC/tremolo' not found
    'error': re.compile(r"^\S+:(?P<level>\w+):(?P<code>(?!57|64)\d+):\s+(?P<msg>.*)$"),
    # available with --terse has one module per line
    # matches modules such as "ictce/3.2.1.015.u4"
    # line ending with : is ignored (the modulepath in --terse)
    # FIXME: --terse ignores defaultness
    'available': re.compile(r"^\s*(?P<mod_name>[^\(\s:]+)\s*[^:\S]*$")
}

_log = fancylogger.getLogger('modules', fname=False)


class ModulesTool(object):
    """An abstract interface to a tool that deals with modules."""

    def __init__(self, mod_paths=None):
        """
        Create a ModulesTool object
        @param mod_paths: A list of paths where the modules can be located
        @type mod_paths: list
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        # make sure we don't have the same path twice
        if mod_paths:
            self.mod_paths = nub(mod_paths)
        else:
            self.mod_paths = None

        # DEPRECATED!
        self._modules = []

        self.check_module_path()

        # actual module command (i.e., not the 'module' wrapper function, but the binary)
        self.cmd = None

        # version of modules tool
        self.version = None

    @property
    def modules(self):
        """Property providing access to deprecated 'modules' class variable."""
        self.log.deprecated("'modules' class variable is deprecated, just use load([<list of modules>])", '2.0')
        return self._modules

    def check_cmd_avail(self):
        """Check whether modules tool command is available."""
        which_ec = subprocess.call(["which", self.cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if which_ec != 0:
            self.log.error("%s modules tool can not be used, '%s' command is not available." % (self.__class__.__name__, self.cmd))

    def check_module_path(self):
        """
        Check if MODULEPATH is set and change it if necessary.
        """
        if not 'MODULEPATH' in os.environ:
            errormsg = 'MODULEPATH not found in environment'
            # check if environment-modules is found
            module_regexp = re.compile(r"^module is a function\s*\nmodule\s*()")
            cmd = "type module"
            (out, ec) = run_cmd(cmd, log_all=False, log_ok=False)
            if ec != 0 or not module_regexp.match(out):
                errormsg += "; environment-modules doesn't seem to be installed: "
                errormsg += "'%s' failed with exit code %s and output: '%s'" % (cmd, ec, out.strip('\n'))
            self.log.error(errormsg)

        if self.mod_paths:
            # set the module path environment accordingly
            os.environ['MODULEPATH'] = ':'.join(self.mod_paths)
            self.log.debug("$MODULEPATH set based on supplied list of module paths: %s" % os.environ['MODULEPATH'])
        else:
            # take module path from environment
            self.mod_paths = nub(os.environ['MODULEPATH'].split(':'))
            self.log.debug("self.mod_paths set based on $MODULEPATH: %s" % self.mod_paths)

        if not 'LOADEDMODULES' in os.environ:
            os.environ['LOADEDMODULES'] = ''

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
                    self.log.warning('More then one module found for %s: %s' % (mod, mods))
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

    def run_module(self, *args, **kwargs):
        """
        Run module command.
        """
        if isinstance(args[0], (list, tuple,)):
            args = args[0]
        else:
            args = list(args)

        if args[0] in ('available', 'avail', 'list',):
            args.insert(0, '--terse')  # run these in terse mode for better machinereading

        originalModulePath = os.environ['MODULEPATH']
        if kwargs.get('mod_paths', None):
            os.environ['MODULEPATH'] = kwargs.get('mod_paths')
        elif kwargs.get('modulePath', None):
            os.environ['MODULEPATH'] = kwargs.get('modulePath')
            self.log.deprecated("Use of 'modulePath' named argument in 'run_module', should use 'mod_paths'.", "2.0")
        self.log.debug('Current MODULEPATH: %s' % os.environ['MODULEPATH'])
        self.log.debug("Running '%s python %s' from %s..." % (self.cmd, ' '.join(args), os.getcwd()))
        # change our LD_LIBRARY_PATH here
        environ = os.environ.copy()
        environ['LD_LIBRARY_PATH'] = LD_LIBRARY_PATH
        self.log.debug("Adjusted LD_LIBRARY_PATH from '%s' to '%s'" %
                       (os.environ.get('LD_LIBRARY_PATH', ''), environ['LD_LIBRARY_PATH']))

        # module command is now getting an outdated LD_LIBRARY_PATH, which will be adjusted on loading a module
        # this needs to be taken into account when updating the environment via produced output, see below
        self.log.debug("Running module cmd '%s python %s'" % (self.cmd, ' '.join(args)))
        proc = subprocess.Popen([self.cmd, 'python'] + args, stdout=PIPE, stderr=PIPE, env=environ)
        # stdout will contain python code (to change environment etc)
        # stderr will contain text (just like the normal module command)
        (stdout, stderr) = proc.communicate()
        os.environ['MODULEPATH'] = originalModulePath

        if kwargs.get('return_output', False):
            return stdout + stderr
        else:
            # keep track of current LD_LIBRARY_PATH, so we can correct the adjusted LD_LIBRARY_PATH below
            prev_ld_library_path = os.environ.get('LD_LIBRARY_PATH', '').split(':')[::-1]

            # Change the environment
            try:
                clean_stdout = '\n'.join([line for line in stdout.split('\n') if line.startswith('os.environ[')])
                exec clean_stdout
            except Exception, err:
                out = "stdout: %s, stderr: %s" % (stdout, stderr)
                raise EasyBuildError("Changing environment as dictated by module failed: %s (%s)" % (err, out))

            # correct LD_LIBRARY_PATH as yielded by the adjustments made
            # make sure we get the order right (reverse lists with [::-1])
            curr_ld_library_path = os.environ.get('LD_LIBRARY_PATH', '').split(':')
            new_ld_library_path = [x for x in nub(prev_ld_library_path + curr_ld_library_path[::-1]) if len(x)][::-1]

            self.log.debug("Correcting paths in LD_LIBRARY_PATH from %s to %s" %
                           (curr_ld_library_path, new_ld_library_path))
            os.environ['LD_LIBRARY_PATH'] = ':'.join(new_ld_library_path)

            # Process stderr
            result = []
            for line in stderr.split('\n'):  # IGNORE:E1103
                if outputMatchers['whitespace'].search(line):
                    continue

                error = outputMatchers['error'].search(line)
                if error:
                    self.log.error(line)
                    raise EasyBuildError(line)

                modules = outputMatchers['available'].finditer(line)
                for module in modules:
                    result.append(module.groupdict())
            return result

    def loaded_modules(self):
        """Return a list of loaded modules."""
        raise NotImplementedError

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

    def __init__(self, *args, **kwargs):
        """Constructor, set modulecmd-specific class variable values."""
        super(EnvironmentModulesC, self).__init__(*args, **kwargs)
        self.cmd = "modulecmd"
        self.check_cmd_avail()

    def module_software_name(self, mod_name):
        """Get the software name for a given module name."""
        # line that specified conflict contains software name
        name_re = re.compile('^conflict\s*(?P<name>[^ ]+).*$', re.M)
        return self.get_value_from_modulefile(mod_name, name_re)

    def loaded_modules(self):
        """Return a list of loaded modules."""

        loaded_modules = []
        mods = []

        # 'modulecmd python list' doesn't yield anything useful, prints to stdout
        # rely on $LOADEDMODULES
        if os.getenv('LOADEDMODULES'):
            # format: name1/version1:name2/version2:...:nameN/versionN
            mods = os.getenv('LOADEDMODULES').split(':')
        else:
            self.log.debug("No way found to determine loaded modules, assuming no modules are loaded.")

        # filter devel modules, since they cannot be split like this
        loaded_modules = [mod for mod in mods if not mod.endswith(DEVEL_MODULE_SUFFIX)]

        return loaded_modules

    def update(self):
        """Update after new modules were added."""
        pass


class Lmod(ModulesTool):
    """Interface to Lmod."""

    # required and optimal version
    REQ_VERSION = LooseVersion('5.0')
    OPT_VERSION = LooseVersion('5.1.5')

    def __init__(self, *args, **kwargs):
        """Constructor, set lmod-specific class variable values."""
        super(Lmod, self).__init__(*args, **kwargs)
        self.cmd = "lmod"
        self.check_cmd_avail()

        # $LMOD_EXPERT needs to be set to avoid EasyBuild tripping over fiddly bits in output
        os.environ['LMOD_EXPERT'] = '1'

        # check Lmod version
        try:
            # 'lmod python update' needs to be run after changing $MODULEPATH
            self.run_module('update')

            fd, fn = tempfile.mkstemp(prefix='lmod_')
            os.close(fd)
            stdout_fn = '%s_stdout.txt' % fn
            stderr_fn = '%s_stderr.txt' % fn
            stdout = open(stdout_fn, 'w')
            stderr = open(stdout_fn, 'w')
            # version is printed in 'lmod help' output
            subprocess.call(["lmod", "help"], stdout=stdout, stderr=stderr)
            stdout.close()
            stderr.close()

            stderr = open(stdout_fn, 'r')
            txt = stderr.read()
            ver_re = re.compile("^Modules based on Lua: Version (?P<version>[0-9.]+) \(.*", re.M)
            res = ver_re.search(txt)
            if res:
                self.version = LooseVersion(res.group('version'))
                self.log.info("Found Lmod version %s" % self.version)
            else:
                self.log.error("Failed to determine Lmod version from 'lmod help' output: %s" % txt)
            stderr.close()
        except (IOError, OSError), err:
            self.log.error("Failed to check Lmod version: %s" % err)

        # we need at least Lmod v5.0
        if self.version >= self.REQ_VERSION:
            # Lmod v5.1.5 is highly recommended
            if self.version < self.OPT_VERSION:
                self.log.warning("Lmod v%s is highly recommended." % self.OPT_VERSION)
        else:
            vers = (self.REQ_VERSION, self.OPT_VERSION, self.version)
            self.log.error("EasyBuild requires Lmod version >= %s (>= %s recommended), found v%s" % vers)

        # we need to run 'lmod python use <path>' to make sure all paths in $MODULEPATH are taken into account
        # note: we're stepping through the mod_paths in reverse order to preserve order in $MODULEPATH in the end
        for modpath in self.mod_paths[::-1]:
            if not os.path.isabs(modpath):
                modpath = os.path.join(os.getcwd(), modpath)
            full_cmd = [self.cmd, 'python', 'use', modpath]
            self.log.debug("Running %s" % ' '.join(full_cmd))
            proc = subprocess.Popen(full_cmd, stdout=PIPE, stderr=PIPE, env=os.environ)
            (stdout, stderr) = proc.communicate()
            exec stdout

        # make sure lmod spider cache is up to date
        self.update()

    def available(self, mod_name=None):
        """
        Return a list of available modules for the given (partial) module name;
        use None to obtain a list of all available modules.

        @param name: a (partial) module name for filtering (default: None)
        """
        # only retain actual modules, exclude module directories
        def is_mod(mod):
            """Determine is given path is an actual module, or just a directory."""
            # trigger error when workaround below can be removed
            fixed_lmod_version = '5.1.5'
            if self.REQ_VERSION >= LooseVersion(fixed_lmod_version):
                self.log.error("Code cleanup required since required Lmod version is >= v%s" % fixed_lmod_version)
            if self.version < self.OPT_VERSION:
                # this is a (potentially bloody slow) workaround for a bug in Lmod 5.x (< 5.1.5)
                for mod_path in self.mod_paths:
                    full_path = os.path.join(mod_path, mod)
                    if os.path.exists(full_path) and os.path.isfile(full_path):
                        return True
                return False
            else:
                # module directories end with a trailing slash in Lmod version >= 5.1.5
                return not mod.endswith('/')

        mods = super(Lmod, self).available(mod_name=mod_name)
        real_mods = [mod for mod in mods if is_mod(mod)]

        # only retain modules that with a <mod_name> prefix
        # Lmod will also returns modules with a matching substring
        correct_real_mods = [mod for mod in real_mods if mod_name is None or mod.startswith(mod_name)]

        return correct_real_mods

    def loaded_modules(self):
        """Return a list of loaded modules."""
        # run_module already returns a list of Python dictionaries for loaded modules
        # only retain 'mod_name' keys, get rid of any other keys
        return [mod['mod_name'] for mod in self.run_module('list')]

    def update(self):
        """Update after new modules were added."""
        cmd = ['spider', '-o', 'moduleT', os.environ['MODULEPATH']]
        proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, env=os.environ)
        (stdout, stderr) = proc.communicate()

        if stderr:
            self.log.error("An error occured when running '%s': %s" % (' '.join(cmd), stderr))

        try:
            cache_filefn = os.path.join(os.path.expanduser('~'), '.lmod.d', '.cache', 'moduleT.lua')
            self.log.debug("Updating lmod spider cache %s with output from '%s'" % (cache_filefn, ' '.join(cmd)))
            cache_dir = os.path.dirname(cache_filefn)
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
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
    return os.environ['MODULEPATH'].split(':')


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
    Return interface to modules tool (environment modules, lmod)
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
