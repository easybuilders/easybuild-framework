##
# Copyright 2009-2012 Ghent University
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
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
##
"""
Modules functionality: loading modules, checking for available modules, ...
"""
import os
import re
import subprocess
import sys

from easybuild.tools.build_log import get_log, EasyBuildError
from easybuild.tools.filetools import convert_name, run_cmd


outputMatchers = {
    # matches whitespace and module-listing headers
    'whitespace': re.compile(r"^\s*$|^(-+).*(-+)$"),
    # matches errors such as "cmdTrace.c(713):ERROR:104: 'asdfasdf' is an unrecognized subcommand"
    'error': re.compile(r"^\S+:(?P<level>\w+):(?P<code>\d+):\s+(?P<msg>.*)$"),
    # matches modules such as "... ictce/3.2.1.015.u4(default) ..."
    'available': re.compile(r"\b(?P<name>\S+?)/(?P<version>[^\(\s]+)(?P<default>\(default\))?(?:\s|$)")
}

class Modules(object):
    """
    Interact with modules.
    """
    def __init__(self, modulePath=None):
        """
        Create a Modules object
        @param modulePath: A list of paths where the modules can be located
        @type modulePath: list
        """
        self.log = get_log(self.__class__.__name__)
        # make sure we don't have the same path twice
        if modulePath:
            self.modulePath = set(modulePath)
        else:
            self.modulePath = None
        self.modules = []

        self.check_module_path()

        # make sure environment-modules is installed
        ec = subprocess.call(["which", "modulecmd"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if ec:
            msg = "Could not find the modulecmd command, environment-modules is not installed?\n"
            msg += "Exit code of 'which modulecmd': %d" % ec
            self.log.error(msg)
            raise EasyBuildError(msg)

    def check_module_path(self):
        """
        Check if MODULEPATH is set and change it if necessary.
        """
        if not 'MODULEPATH' in os.environ:
            errormsg = 'MODULEPATH not found in environment'
            # check if environment-modules is found
            module_regexp = re.compile("^module is a function\s*\nmodule\s*()")
            cmd = "type module"
            (out, ec) = run_cmd(cmd, log_all=False, log_ok=False)
            if ec != 0 or not module_regexp.match(out):
                errormsg += "; environment-modules doesn't seem to be installed: "
                errormsg += "'%s' failed with exit code %s and output: '%s'" % (cmd, ec, out.strip('\n'))
            self.log.error(errormsg)

        if self.modulePath:
            ## set the module path environment accordingly
            os.environ['MODULEPATH'] = ":".join(self.modulePath)
        else:
            ## take module path from environment
            self.modulePath = os.environ['MODULEPATH'].split(':')

        if not 'LOADEDMODULES' in os.environ:
            os.environ['LOADEDMODULES'] = ''

    def available(self, name=None, version=None, modulePath=None):
        """
        Return list of available modules.
        """
        if not name: name = ''
        if not version: version = ''

        txt = name
        if version:
            txt = "%s/%s" % (name, version)

        modules = self.run_module('available', txt, modulePath=modulePath)

        ## sort the answers in [name, version] pairs
        ## alphabetical order, default last
        modules.sort(key=lambda m: (m['name'] + (m['default'] or ''), m['version']))
        ans = [(mod['name'], mod['version']) for mod in modules]

        self.log.debug("module available name '%s' version '%s' in %s gave %d answers: %s" %
            (name, version, modulePath, len(ans), ans))
        return ans

    def exists(self, name, version, modulePath=None):
        """
        Check if module is available.
        """
        return (name, version) in self.available(name, version, modulePath)

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
                ## deal with toolchain dependency calls
                if 'tc' in mod:
                    version = mod['tc']
                else:
                    version = mod['version']
            else:
                self.log.error("Can't add module %s: unknown type" % str(mod))

            mods = self.available(name, version)
            if (name, version) in mods:
                ## ok
                self.modules.append((name, version))
            else:
                if len(mods) == 0:
                    self.log.warning('No module %s available' % mod)
                else:
                    self.log.warning('More then one module found for %s: %s' % (mod, mods))
                continue

    def load(self):
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
        """
        Get the path of the module file for the specified module
        """
        if not self.exists(name, version):
            return None
        else:
            modinfo = self.show(name, version)

            self.log.debug("modinfo (split): %s" % modinfo.split('\n'))

            # second line of module show output contains full path of module file
            return modinfo.split('\n')[1].replace(':', '')

    def run_module(self, *args, **kwargs):
        """
        Run module command.
        """
        if type(args[0]) == list:
            args = args[0]
        else:
            args = list(args)

        originalModulePath = os.environ['MODULEPATH']
        if kwargs.get('modulePath', None):
            os.environ['MODULEPATH'] = kwargs.get('modulePath')
        self.log.debug('Current MODULEPATH: %s' % os.environ['MODULEPATH'])

        self.log.debug("Running 'modulecmd python %s' from %s..." % (' '.join(args), os.getcwd()))
        proc = subprocess.Popen(['modulecmd', 'python'] + args,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # stdout will contain python code (to change environment etc)
        # stderr will contain text (just like the normal module command)
        (stdout, stderr) = proc.communicate()
        os.environ['MODULEPATH'] = originalModulePath

        if kwargs.get('return_output', False):
            return (stdout + stderr)

        else:
            # Change the environment
            try:
                exec stdout
            except Exception, err:
                raise EasyBuildError("Changing environment as dictated by module failed: %s" % err)

            # Process stderr
            result = []
            for line in stderr.split('\n'):  #IGNORE:E1103
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

        loaded_modules = []
        mods = []

        if os.getenv('LOADEDMODULES'):
            mods = os.getenv('LOADEDMODULES').split(':')

        elif os.getenv('_LMFILES_'):
            mods = ['/'.join(modfile.split('/')[-2:]) for modfile in os.getenv('_LMFILES_').split(':')]

        else:
            self.log.debug("No environment variable found to determine loaded modules, assuming no modules are loaded.")

        # filter devel modules, since they cannot be split like this
        mods = [mod for mod in mods if not mod.endswith("easybuild-devel")]
        for mod in mods:
            mod_name = None
            mod_version = None
            modparts = mod.split('/')

            if len(modparts) == 2:
                # this is what we expect, e.g. GCC/4.7.2
                mod_name = modparts[0]
                mod_version = modparts[1]

            elif len(modparts) > 2:
                # different module naming scheme
                # let's assume first part is name, rest is version
                mod_name = modparts[0]
                mod_version = '/'.join(modparts[1:])

            elif len(modparts) == 1:
                # only name, no version
                mod_name = modparts[0]
                mod_version = ''

            else:
                # length after splitting is 0, so empty module name?
                self.log.error("Module with empty name loaded? ('%s')" % mod)

            loaded_modules.append({
                                   'name': mod_name,
                                   'version': mod_version
                                   })

        return loaded_modules

    # depth=sys.maxint should be equivalent to infinite recursion depth
    def dependencies_for(self, name, version, depth=sys.maxint):
        """
        Obtain a list of dependencies for the given module, determined recursively, up to a specified depth (optionally)
        """
        modfilepath = self.modulefile_path(name, version)
        self.log.debug("modulefile path %s/%s: %s" % (name, version, modfilepath))

        try:
            f = open(modfilepath, "r")
            modtxt = f.read()
            f.close()
        except IOError, err:
            self.log.error("Failed to read module file %s to determine toolchain dependencies: %s" % (modfilepath, err))

        loadregex = re.compile("^\s+module load\s+(.*)$", re.M)
        mods = [mod.split('/') for mod in loadregex.findall(modtxt)]

        if depth > 0:
            # recursively determine dependencies for these dependency modules, until depth is non-positive
            moddeps = [self.dependencies_for(modname, modversion, depth=depth-1) for (modname, modversion) in mods]
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


def search_module(path, query):
    """
    Search for a particular module (only prints)
    """
    print "Searching for %s in %s " % (query.lower(), path)

    query = query.lower()
    for (dirpath, dirnames, filenames) in os.walk(path):
        for filename in filenames:
            filename = os.path.join(dirpath, filename)
            if filename.lower().find(query) != -1:
                print "- %s" % filename

        # TODO: get directories to ignore from  easybuild.tools.repository ?
        # remove all hidden directories?:
        #dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        try:
            dirnames.remove('.svn')
        except ValueError:
            pass

        try:
            dirnames.remove('.git')
        except ValueError:
            pass

def get_software_root(name, with_env_var=False):
    """
    Return the software root set for a particular software name.
    """
    name = convert_name(name, upper=True)
    environment_key = "EBROOT%s" % name
    legacy_key = "SOFTROOT%s" % name

    # keep on supporting legacy installations
    if environment_key in os.environ:
        env_var = environment_key
    else:
        env_var = legacy_key

    root = os.getenv(env_var)

    if with_env_var:
        return (root, env_var)
    else:
        return root

def get_software_version(name):
    """
    Return the software version set for a particular software name.
    """
    name = convert_name(name, upper=True)
    environment_key = "EBVERSION%s" % name
    legacy_key = "SOFTVERSION%s" % name

    # keep on supporting legacy installations
    if environment_key in os.environ:
        return os.getenv(environment_key)
    else:
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
