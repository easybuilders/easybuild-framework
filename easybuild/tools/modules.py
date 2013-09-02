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
    # matches modules such as "ictce/3.2.1.015.u4(default)"
    # line ending with : is ignored (the modulepath in --terse)
    'available': re.compile(r"^\s*(?P<name>\S+?)/(?P<version>[^\(\s:]+)(?P<default>\(default\))?\s*[^:\S]*$")
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
            self.mod_paths = set(mod_paths)
        else:
            self.mod_paths = None
        # FIXME: deprecate this?
        self.modules = []

        self.check_module_path()

        # actual module command (i.e., not the 'module' wrapper function, but the binary)
        self.cmd = None

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
            os.environ['MODULEPATH'] = ":".join(self.mod_paths)
        else:
            # take module path from environment
            self.mod_paths = os.environ['MODULEPATH'].split(':')

        if not 'LOADEDMODULES' in os.environ:
            os.environ['LOADEDMODULES'] = ''

    # FIXME: mod_paths is never used directly?
    def available(self, name=None, version=None, modulePath=None, mod_paths=None):
        """
        Return list of available modules.
        """
        if name is None:
            name = ''
        if version is None:
            version = ''

        txt = name
        if version:
            txt = "%s/%s" % (name, version)

        if mod_paths is None and modulePath:
            mod_paths = modulePath
            self.log.deprecated("Use of 'modulePath' named argument in 'available', should use 'mod_paths'.", "2.0")
        modules = self.run_module('avail', txt, mod_paths=mod_paths)

        # sort the answers in [name, version] pairs
        # alphabetical order, default last
        modules.sort(key=lambda m: (m['name'] + (m['default'] or ''), m['version']))
        ans = [(mod['name'], mod['version']) for mod in modules]

        self.log.debug("module available name '%s' version '%s' in %s gave %d answers: %s" %
                       (name, version, mod_paths, len(ans), ans))
        return ans

    # FIXME: mod_paths is never used directly
    def exists(self, name, version, modulePath=None, mod_paths=None):
        """
        Check if module is available.
        """
        if mod_paths is None and modulePath:
            mod_paths = modulePath
            self.log.deprecated("Use of 'modulePath' named argument in 'exists', should use 'mod_paths'.", "2.0")
        return (name, version) in self.available(name, version, mod_paths=mod_paths)

    # FIXME: deprecate this?
    def add_module(self, modules):
        """
        Check if module exist, if so add to list.
        """
        for mod in modules:
            if type(mod) == list or type(mod) == tuple:
                name, version = mod[0], mod[1]
            elif type(mod) == str:
                (name, version) = mod.split('/')
            elif type(mod) == dict:
                name = mod['name']
                # deal with toolchain dependency calls
                if 'tc' in mod:
                    version = mod['tc']
                else:
                    version = mod['version']
            else:
                self.log.error("Can't add module %s: unknown type" % str(mod))

            mods = self.available(name, version)
            if (name, version) in mods:
                # ok
                self.modules.append((name, version))
            else:
                if len(mods) == 0:
                    self.log.warning('No module %s available' % str(mod))
                else:
                    self.log.warning('More then one module found for %s: %s' % (mod, mods))
                continue

    # FIXME: deprecate this along with add_module?
    def remove_module(self, modules):
        """
        Remove modules from list.
        """
        for mod in modules:
            self.modules = [m for m in self.modules if not m == mod]

    # FIXME: change this, pass (list of) module(s) to load as argument?
    def load(self, modules=[]):
        """
        Load all requested modules.
        """
        for mod in self.modules:
            self.run_module('load', "/".join(mod))

    def unload(self):
        """
        Unload all requested modules.
        """
        for mod in self.modules:
            self.run_module('unload', "/".join(mod))

    def purge(self):
        """
        Purge loaded modules.
        """
        self.log.debug("List of loaded modules before purge: %s" % os.getenv('_LMFILES_'))
        self.run_module('purge', '')

    def show(self, name, version):
        """
        Run 'module show' for the specified module.
        """
        return self.run_module('show', "%s/%s" % (name, version), return_output=True)

    def modulefile_path(self, name, version):
        """Get the path of the module file for the specified module."""
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
        """Return a list of loaded modules ([{'name': <module name>, 'version': <module version>}]."""
        raise NotImplementedError

    # depth=sys.maxint should be equivalent to infinite recursion depth
    def dependencies_for(self, name, version, depth=sys.maxint):
        """
        Obtain a list of dependencies for the given module, determined recursively, up to a specified depth (optionally)
        """
        modfilepath = self.modulefile_path(name, version)
        self.log.debug("modulefile path %s/%s: %s" % (name, version, modfilepath))

        modtxt = read_file(modfilepath)

        loadregex = re.compile(r"^\s+module load\s+(.*)$", re.M)
        mods = [mod.split('/') for mod in loadregex.findall(modtxt)]

        if depth > 0:
            # recursively determine dependencies for these dependency modules, until depth is non-positive
            moddeps = [self.dependencies_for(modname, modversion, depth=depth - 1) for (modname, modversion) in mods]
        else:
            # ignore any deeper dependencies
            moddeps = []

        deps = [{'name':modname, 'version':modversion} for (modname, modversion) in mods]

        # add dependencies of dependency modules only if they're not there yet
        for moddepdeps in moddeps:
            for dep in moddepdeps:
                if not dep in deps:
                    deps.append(dep)

        return deps

    def update(self):
        """Update after new modules were added."""
        raise NotImplementedError


class EnvironmentModulesC(ModulesTool):
    """Interface to (C) environment modules (modulecmd)."""

    def __init__(self, *args, **kwargs):
        """Constructor, set modulecmd-specific class variable values."""
        super(EnvironmentModulesC, self).__init__(*args, **kwargs)
        self.cmd = "modulecmd"

        which_ec = subprocess.call(["which", "modulecmd"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if which_ec != 0:
            self.log.error("EnvironmentModulesC modules tool can not be used, 'modulecmd' is not available.")

    def modulefile_path(self, name, version):
        """Get the path of the module file for the specified module."""
        if self.exists(name, version):
            modinfo = self.show(name, version)
            self.log.debug("modinfo (split): %s" % modinfo.split('\n'))
            # 2nd line for environment modules show output
            mod_full_path = modinfo.split('\n')[1].replace(':', '')
            return mod_full_path
        else:
            raise EasyBuildError("Can't get module file path for non-existing module %s/%s" % (name, version))

    def loaded_modules(self):
        """Return a list of loaded modules ([{'name': <module name>, 'version': <module version>}]."""

        loaded_modules = []
        mods = []

        # 'modulecmd python list' doesn't yield anything useful, prints to stdout
        # rely on $LOADEDMODULES (or $_LMFILES as fallback)
        # is there any better way to get a list of modules?
        if os.getenv('LOADEDMODULES'):
            # format: name1/version1:name2/version2:...:nameN/versionN
            mods = [mod.split('/') for mod in os.getenv('LOADEDMODULES').split(':')]
        elif os.getenv('_LMFILES_'):
            # format: /path/to/name1/version1:/path/to/name2/version2:...:/path/to/nameN/versionN
            mods = [modfile.split('/')[-2:] for modfile in os.getenv('_LMFILES_').split(':')]
        else:
            self.log.debug("No way found to determine loaded modules, assuming no modules are loaded.")

        # filter devel modules, since they cannot be split like this
        mods = [mod for mod in mods if not ''.join(mod).endswith("easybuild-devel")]
        for mod in mods:
            mod_name = None
            mod_version = None

            if len(mod) == 2:
                # this is what we expect, e.g. GCC/4.7.2
                mod_name = mod[0]
                mod_version = mod[1]
            elif len(mod) > 2:
                # different module naming scheme
                # let's assume first part is name, rest is version
                mod_name = mod[0]
                mod_version = '/'.join(mod[1:])
            elif len(mod) == 1:
                # only name, no version
                mod_name = mod[0]
                mod_version = ''
            else:
                # length after splitting is 0, so empty module name?
                self.log.error("Module with empty name loaded? ('%s')" % mod)

            loaded_modules.append({'name': mod_name, 'version': mod_version})

        return loaded_modules

    def update(self):
        """Update after new modules were added."""
        pass


class Lmod(ModulesTool):
    """Interface to Lmod."""

    def __init__(self, *args, **kwargs):
        """Constructor, set lmod-specific class variable values."""
        super(Lmod, self).__init__(*args, **kwargs)
        self.cmd = "lmod"

        # $LMOD_EXPERT needs to be set to avoid EasyBuild tripping over fiddly bits in output
        os.environ['LMOD_EXPERT'] = '1'

        # ensure Lmod is available
        which_ec = subprocess.call(["which", "lmod"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if which_ec != 0:
            self.log.error("Lmod modules tool can not be used, 'lmod' is not available.")

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
                lmod_ver = res.group('version')
            else:
                self.log.error("Failed to determine Lmod version from 'lmod help' output: %s" % txt)
            stderr.close()
        except (IOError, OSError), err:
            self.log.error("Failed to check Lmod version: %s" % err)

        # we need at least Lmod v5.0
        if LooseVersion(lmod_ver) >= LooseVersion('5.0'):
            # Lmod v5.0.1 is highly recommended
            recommended_version = '5.0.1'
            if LooseVersion(lmod_ver) < LooseVersion(recommended_version):
                self.log.warning("Lmod v%s is highly recommended." % recommended_version)
        else:
            self.log.error("EasyBuild requires Lmod v5.0 or more recent")

        # we need to run 'lmod python add <path>' to make sure all paths in $MODULEPATH are taken into account
        for modpath in self.mod_paths:
            if not os.path.isabs(modpath):
                modpath = os.path.join(os.getcwd(), modpath)
            if modpath not in os.environ['MODULEPATH']:
                proc = subprocess.Popen([self.cmd, 'python', 'use', modpath], stdout=PIPE, stderr=PIPE, env=os.environ)
                (stdout, stderr) = proc.communicate()
                exec stdout

        # make sure lmod spider cache is up to date
        self.update()

    def modulefile_path(self, name, version):
        """Get the path of the module file for the specified module."""
        if self.exists(name, version):
            modinfo = self.show(name, version)
            self.log.debug("modinfo: %s" % modinfo)
            modpath_re = re.compile('^\s*(?P<modpath>/[^ ]*):$', re.M)
            res = modpath_re.search(modinfo)
            if res:
                mod_full_path = res.group('modpath')
            else:
                self.log.error("Failed to determine modfile path from 'show' (pattern: '%s')" % modpath_re.pattern)
            return mod_full_path
        else:
            raise EasyBuildError("Can't get module file path for non-existing module %s/%s" % (name, version))

    def loaded_modules(self):
        """Return a list of loaded modules ([{'name': <module name>, 'version': <module version>}]."""
        # 'lmod python list' already returns a list of Python dictionaries for loaded modules
        # only retain 'name'/'version' keys, get rid of any others (e.g. 'default')
        mods = self.run_module('list')
        return [{'name': mod['name'], 'version': mod['version']} for mod in mods]

    def update(self):
        """Update after new modules were added."""
        cmd = ['spider', '-o', 'moduleT', os.environ['MODULEPATH']]
        proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, env=os.environ)
        (stdout, stderr) = proc.communicate()

        if stderr:
            self.log.error("An error occured when running '%s': %s" % (' '.join(cmd), stderr))

        cache_filefn = os.path.join(os.path.expanduser('~'), '.lmod.d', '.cache', 'moduleT.lua')
        self.log.debug("Updating lmod spider cache %s with output from '%s'" % (cache_filefn, ' '.join(cmd)))
        cache_file = open(cache_filefn, 'w')
        cache_file.write(stdout)
        cache_file.close()


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
