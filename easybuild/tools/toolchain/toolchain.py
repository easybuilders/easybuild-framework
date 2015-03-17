# #
# Copyright 2012-2015 Ghent University
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
The toolchain module with the abstract Toolchain class.

Creating a new toolchain should be as simple as possible.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import os
import re
from vsc.utils import fancylogger

from easybuild.tools.config import build_option, install_path
from easybuild.tools.environment import setvar
from easybuild.tools.modules import get_software_root, get_software_version, modules_tool
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME, DUMMY_TOOLCHAIN_VERSION
from easybuild.tools.toolchain.options import ToolchainOptions
from easybuild.tools.toolchain.toolchainvariables import ToolchainVariables


_log = fancylogger.getLogger('tools.toolchain', fname=False)


class Toolchain(object):
    """General toolchain class"""

    OPTIONS_CLASS = ToolchainOptions
    VARIABLES_CLASS = ToolchainVariables

    NAME = None
    VERSION = None

    # class method
    def _is_toolchain_for(cls, name):
        """see if this class can provide support for toolchain named name"""
        # TODO report later in the initialization the found version
        if name:
            if hasattr(cls, 'NAME') and name == cls.NAME:
                return True
            else:
                return False
        else:
            # is no name is supplied, check whether class can be used as a toolchain
            return hasattr(cls, 'NAME') and cls.NAME

    _is_toolchain_for = classmethod(_is_toolchain_for)

    def __init__(self, name=None, version=None, mns=None):
        """Toolchain constructor."""

        self.base_init()

        self.dependencies = []
        self.toolchain_dep_mods = []

        if name is None:
            name = self.NAME
        if name is None:
            self.log.error("Toolchain init: no name provided")
        self.name = name

        if version is None:
            version = self.VERSION
        if version is None:
            self.log.error("Toolchain init: no version provided")
        self.version = version

        self.vars = None

        self.modules_tool = modules_tool()
        self.mns = mns
        self.mod_full_name = None
        self.mod_short_name = None
        self.init_modpaths = None
        if self.name != DUMMY_TOOLCHAIN_NAME:
            # sometimes no module naming scheme class instance can/will be provided, e.g. with --list-toolchains
            if self.mns is not None:
                tc_dict = self.as_dict()
                self.mod_full_name = self.mns.det_full_module_name(tc_dict)
                self.mod_short_name = self.mns.det_short_module_name(tc_dict)
                self.init_modpaths = self.mns.det_init_modulepaths(tc_dict)

    def base_init(self):
        if not hasattr(self, 'log'):
            self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        if not hasattr(self, 'options'):
            self.options = self.OPTIONS_CLASS()

        if not hasattr(self, 'variables'):
            self.variables = self.VARIABLES_CLASS()
            if hasattr(self, 'LINKER_TOGGLE_START_STOP_GROUP'):
                self.variables.LINKER_TOGGLE_START_STOP_GROUP = self.LINKER_TOGGLE_START_STOP_GROUP
            if hasattr(self, 'LINKER_TOGGLE_STATIC_DYNAMIC'):
                self.variables.LINKER_TOGGLE_STATIC_DYNAMIC = self.LINKER_TOGGLE_STATIC_DYNAMIC

    def get_variable(self, name, typ=str):
        """Get value for specified variable.
        typ: indicates what type of return value is expected"""

        if typ == str:
            return str(self.variables[name])
        elif typ == list:
            return self.variables[name].flatten()
        else:
            self.log.error("get_variable: Don't know how to create value of type %s." % typ)

    def set_variables(self):
        """Do nothing? Everything should have been set by others
            Needs to be defined for super() relations
        """
        if self.options.option('packed-linker-options'):
            self.log.debug("set_variables: toolchain variables. packed-linker-options.")
            self.variables.try_function_on_element('set_packed_linker_options')
        self.log.debug("set_variables: toolchain variables. Do nothing.")

    def generate_vars(self):
        """Convert the variables in simple vars"""
        self.vars = {}
        for k, v in self.variables.items():
            self.vars[k] = str(v)

    def show_variables(self, offset='', sep='\n', verbose=False):
        """Pretty print the variables"""
        if self.vars is None:
            self.generate_vars()

        var_names = self.variables.keys()
        var_names.sort()
        res = []
        for v in var_names:
            res.append("%s=%s" % (v, self.variables[v]))
            if verbose:
                res.append("# type %s" % (type(self.variables[v])))
                res.append("# %s" % (self.variables[v].show_el()))
                res.append("# repr %s" % (self.variables[v].__repr__()))

        if offset is None:
            offset = ''
        txt = sep.join(["%s%s" % (offset, x) for x in res])
        self.log.debug("show_variables:\n%s" % txt)
        return txt

    def get_software_root(self, names):
        """Try to get the software root for all names"""
        return self._get_software_multiple(names, self._get_software_root)

    def get_software_version(self, names):
        """Try to get the software version for all names"""
        return self._get_software_multiple(names, self._get_software_version)

    def _get_software_multiple(self, names, function):
        """Execute function of each of names"""
        if isinstance(names, (str,)):
            names = [names]
        res = []
        for name in names:
            res.append(function(name))
        return res

    def _get_software_root(self, name):
        """Try to get the software root for name"""
        root = get_software_root(name)
        if root is None:
            self.log.error("get_software_root software root for %s was not found in environment" % name)
        else:
            self.log.debug("get_software_root software root %s for %s was found in environment" % (root, name))
        return root

    def _get_software_version(self, name):
        """Try to get the software root for name"""
        version = get_software_version(name)
        if version is None:
            self.log.error("get_software_version software version for %s was not found in environment" % name)
        else:
            self.log.debug("get_software_version software version %s for %s was found in environment" % (version, name))

        return version

    def as_dict(self, name=None, version=None):
        """Return toolchain specification as a dictionary."""
        if name is None:
            name = self.name
        if version is None:
            version = self.version
        return {
            'name': name,
            'version': version,
            'toolchain': {'name': DUMMY_TOOLCHAIN_NAME, 'version': DUMMY_TOOLCHAIN_VERSION},
            'versionsuffix': '',
            'dummy': True,
            'parsed': True,  # pretend this is a parsed easyconfig file, as may be required by det_short_module_name
            'hidden': False,
        }

    def det_short_module_name(self):
        """Determine module name for this toolchain."""
        if self.mod_short_name is None:
            self.log.error("Toolchain module name was not set yet (using set_module_info).")
        return self.mod_short_name

    def _toolchain_exists(self):
        """
        Verify if there exists a toolchain by this name and version
        """
        # short-circuit to returning module name for this (non-dummy) toolchain
        if self.name == DUMMY_TOOLCHAIN_NAME:
            self.log.debug("_toolchain_exists: %s toolchain always exists, returning True" % DUMMY_TOOLCHAIN_NAME)
            return True
        else:
            if self.mod_short_name is None:
                self.log.error("Toolchain module name was not set yet (using set_module_info).")
            # check whether a matching module exists if self.mod_short_name contains a module name
            return self.modules_tool.exist([self.mod_full_name])[0]

    def set_options(self, options):
        """ Process toolchain options """
        for opt in options.keys():
            # Only process supported opts
            if opt in self.options:
                self.options[opt] = options[opt]
            else:
                # used to be warning, but this is a severe error imho
                known_opts = ','.join(self.options.keys())
                self.log.error("Undefined toolchain option %s specified (known options: %s)" % (opt, known_opts))

    def get_dependency_version(self, dependency):
        """ Generate a version string for a dependency on a module using this toolchain """
        # Add toolchain to version string
        toolchain = ''
        if self.name != DUMMY_TOOLCHAIN_NAME:
            toolchain = '-%s-%s' % (self.name, self.version)
        elif self.version != DUMMY_TOOLCHAIN_VERSION:
            toolchain = '%s' % (self.version)

        # Check if dependency is independent of toolchain
        # TODO: assuming dummy here, what about version?
        if DUMMY_TOOLCHAIN_NAME in dependency and dependency[DUMMY_TOOLCHAIN_NAME]:
            toolchain = ''

        suffix = dependency.get('versionsuffix', '')

        if 'version' in dependency:
            version = "".join([dependency['version'], toolchain, suffix])
            self.log.debug("get_dependency_version: version in dependency return %s" % version)
            return version
        else:
            toolchain_suffix = "".join([toolchain, suffix])
            matches = self.modules_tool.available(dependency['name'], toolchain_suffix)
            # Find the most recent (or default) one
            if len(matches) > 0:
                version = matches[-1][-1]
                self.log.debug("get_dependency_version: version not in dependency return %s" % version)
                return
            else:
                tup = (dependency['name'], toolchain_suffix)
                self.log.error("No toolchain version for dependency name %s (suffix %s) found" % tup)

    def add_dependencies(self, dependencies):
        """ Verify if the given dependencies exist and add them """
        self.log.debug("add_dependencies: adding toolchain dependencies %s" % dependencies)
        dep_mod_names = [dep['full_mod_name'] for dep in dependencies]
        deps_exist = self.modules_tool.exist(dep_mod_names)
        for dep, dep_mod_name, dep_exists in zip(dependencies, dep_mod_names, deps_exist):
            self.log.debug("add_dependencies: MODULEPATH: %s" % os.environ['MODULEPATH'])
            if not dep_exists:
                tup = (dep_mod_name, dep)
                self.log.error("add_dependencies: no module '%s' found for dependency %s" % tup)
            else:
                self.dependencies.append(dep)
                self.log.debug('add_dependencies: added toolchain dependency %s' % str(dep))

    def is_required(self, name):
        """Determine whether this is a required toolchain element."""
        # default: assume every element is required
        return True

    def definition(self):
        """
        Determine toolchain elements for given Toolchain instance.
        """
        var_suff = '_MODULE_NAME'
        tc_elems = {}
        for var in dir(self):
            if var.endswith(var_suff):
                tc_elems.update({var[:-len(var_suff)]: getattr(self, var)})

        _log.debug("Toolchain definition for %s: %s" % (self.as_dict(), tc_elems))
        return tc_elems

    def is_dep_in_toolchain_module(self, name):
        """Check whether a specific software name is listed as a dependency in the module for this toolchain."""
        return any(map(lambda m: self.mns.is_short_modname_for(m, name), self.toolchain_dep_mods))

    def prepare(self, onlymod=None):
        """
        Prepare a set of environment parameters based on name/version of toolchain
        - load modules for toolchain and dependencies
        - generate extra variables and set them in the environment

        onlymod: Boolean/string to indicate if the toolchain should only load the environment
        with module (True) or also set all other variables (False) like compiler CC etc
        (If string: comma separated list of variables that will be ignored).
        """
        if self.modules_tool is None:
            self.log.error("No modules tool defined in Toolchain instance.")

        if not self._toolchain_exists():
            self.log.error("No module found for toolchain: %s" % self.mod_short_name)

        
	if self.name == DUMMY_TOOLCHAIN_NAME:
            if self.version == DUMMY_TOOLCHAIN_VERSION:
                self.log.info('prepare: toolchain dummy mode, dummy version; not loading dependencies')
		#@todo I keep this is as, but want dummy to do the same as a regular toolchain. Need to think this through.
        	self.modules_tool.load([dep['short_mod_name'] for dep in self.dependencies])
	    else:
                self.log.info('prepare: toolchain dummy mode and loading dependencies')
                self.modules_tool.load([dep['short_mod_name'] for dep in self.dependencies])
            return

        # Load the toolchain and dependencies modules
        self.log.debug("Loading toolchain module and dependencies...")
        # make sure toolchain is available using short module name by running 'module use' on module path subdir
        if self.init_modpaths:
            mod_path_suffix = build_option('suffix_modules_path')
            for modpath in self.init_modpaths:
                self.modules_tool.prepend_module_path(os.path.join(install_path('mod'), mod_path_suffix, modpath))
        self.modules_tool.load([self.det_short_module_name()])
        self.modules_tool.load([dep['short_mod_name'] for dep in self.dependencies])

        # determine direct toolchain dependencies
        mod_name = self.det_short_module_name()
        self.toolchain_dep_mods = self.modules_tool.dependencies_for(mod_name, depth=0)
        self.log.debug('prepare: list of direct toolchain dependencies: %s' % self.toolchain_dep_mods)

        # only retain names of toolchain elements, excluding toolchain name
        toolchain_definition = set([e for es in self.definition().values() for e in es if not e == self.name])

        # filter out optional toolchain elements if they're not used in the module
        for elem_name in toolchain_definition.copy():
            if self.is_required(elem_name) or self.is_dep_in_toolchain_module(elem_name):
                continue
            # not required and missing: remove from toolchain definition
            self.log.debug("Removing %s from list of optional toolchain elements." % elem_name)
            toolchain_definition.remove(elem_name)

        self.log.debug("List of toolchain dependencies from toolchain module: %s" % self.toolchain_dep_mods)
        self.log.debug("List of toolchain elements from toolchain definition: %s" % toolchain_definition)

        if all(map(self.is_dep_in_toolchain_module, toolchain_definition)):
            self.log.info("List of toolchain dependency modules and toolchain definition match!")
        else:
            self.log.error("List of toolchain dependency modules and toolchain definition do not match " \
                           "(%s vs %s)" % (self.toolchain_dep_mods, toolchain_definition))

        # Generate the variables to be set
        self.set_variables()

        # set the variables
        # onlymod can be comma-separated string of variables not to be set
        if onlymod == True:
            self.log.debug("prepare: do not set additional variables onlymod=%s" % onlymod)
            self.generate_vars()
        else:
            self.log.debug("prepare: set additional variables onlymod=%s" % onlymod)

            # add LDFLAGS and CPPFLAGS from dependencies to self.vars
            self._add_dependency_variables()
            self.generate_vars()
            self._setenv_variables(onlymod)

    def _add_dependency_variables(self, names=None, cpp=None, ld=None):
        """ Add LDFLAGS and CPPFLAGS to the self.variables based on the dependencies
            names should be a list of strings containing the name of the dependency
        """
        cpp_paths = ['include']
        ld_paths = ['lib']
        if not self.options.get('32bit', None):
            ld_paths.insert(0, 'lib64')

        if cpp is not None:
            for p in cpp:
                if not p in cpp_paths:
                    cpp_paths.append(p)
        if ld is not None:
            for p in ld:
                if not p in ld_paths:
                    ld_paths.append(p)

        if not names:
            deps = self.dependencies
        else:
            deps = [{'name': name} for name in names if name is not None]

        for root in self.get_software_root([dep['name'] for dep in deps]):
            self.variables.append_subdirs("CPPFLAGS", root, subdirs=cpp_paths)
            self.variables.append_subdirs("LDFLAGS", root, subdirs=ld_paths)

    def _setenv_variables(self, donotset=None):
        """Actually set the environment variables"""
        self.log.debug("_setenv_variables: setting variables: donotset=%s" % donotset)

        donotsetlist = []
        if isinstance(donotset, str):
            # TODO : more legacy code that should be using proper type
            self.log.error("_setenv_variables: using commas-separated list. should be deprecated.")
            donotsetlist = donotset.split(',')
        elif isinstance(donotset, list):
            donotsetlist = donotset

        for key, val in self.vars.items():
            if key in donotsetlist:
                self.log.debug("_setenv_variables: not setting environment variable %s (value: %s)." % (key, val))
                continue

            self.log.debug("_setenv_variables: setting environment variable %s to %s" % (key, val))
            setvar(key, val)

            # also set unique named variables that can be used in Makefiles
            # - so you can have 'CFLAGS = $(EBVARCFLAGS)'
            # -- 'CLFLAGS = $(CFLAGS)' gives  '*** Recursive variable `CFLAGS'
            # references itself (eventually).  Stop' error
            setvar("EBVAR%s" % key, val)

    def get_flag(self, name):
        """Get compiler flag for a certain option."""
        return "-%s" % self.options.option(name)

    def comp_family(self):
        """ Return compiler family used in this toolchain (abstract method)."""
        raise NotImplementedError

    def mpi_family(self):
        """ Return type of MPI library used in this toolchain or 'None' if MPI is not
            supported.
        """
        return None
