# #
# Copyright 2012-2025 Ghent University
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
# #
"""
The toolchain module with the abstract Toolchain class.

Creating a new toolchain should be as simple as possible.

Toolchain terminology
---------------------

Toolchain: group of development related utilities (eg compiler) and libraries (eg MPI, linear algebra)
    -> eg tc=Toolchain()


Toolchain options : options passed to the toolchain through the easyconfig file
    -> eg tc.options

Options : all options passed to an executable
    Flags: specific subset of options, typically involved with compilation
        -> eg tc.variables.CFLAGS
    LinkOptions: specific subset of options, typically involved with linking
        -> eg tc.variables.LIBBLAS

TooclchainVariables: list of environment variables that are set when the toolchain is initialised
           and the toolchain options have been parsed.
    -> eg tc.variables['X'] will be available as os.environ['X']

Authors:

* Stijn De Weirdt (Ghent University)
* Kenneth Hoste (Ghent University)
"""
import copy
import os
import stat
import sys
import tempfile

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError, dry_run_msg, print_warning
from easybuild.tools.config import build_option, install_path
from easybuild.tools.environment import setvar
from easybuild.tools.filetools import adjust_permissions, copy_file, find_eb_script, mkdir, read_file, which, write_file
from easybuild.tools.module_generator import dependencies_for
from easybuild.tools.modules import get_software_root, get_software_root_env_var_name
from easybuild.tools.modules import get_software_version, get_software_version_env_var_name
from easybuild.tools.systemtools import LINUX, get_os_type
from easybuild.tools.toolchain.options import ToolchainOptions
from easybuild.tools.toolchain.toolchainvariables import ToolchainVariables
from easybuild.tools.utilities import nub, unique_ordered_extend, trace_msg


_log = fancylogger.getLogger('tools.toolchain', fname=False)

SYSTEM_TOOLCHAIN_NAME = 'system'

CCACHE = 'ccache'
F90CACHE = 'f90cache'

RPATH_WRAPPERS_SUBDIR = 'rpath_wrappers'

# available capabilities of toolchains
# values match method names supported by Toolchain class (except for 'cuda')
TOOLCHAIN_CAPABILITY_BLAS_FAMILY = 'blas_family'
TOOLCHAIN_CAPABILITY_COMP_FAMILY = 'comp_family'
TOOLCHAIN_CAPABILITY_CUDA = 'cuda'
TOOLCHAIN_CAPABILITY_LAPACK_FAMILY = 'lapack_family'
TOOLCHAIN_CAPABILITY_MPI_FAMILY = 'mpi_family'
TOOLCHAIN_CAPABILITIES = [
    TOOLCHAIN_CAPABILITY_BLAS_FAMILY,
    TOOLCHAIN_CAPABILITY_COMP_FAMILY,
    TOOLCHAIN_CAPABILITY_CUDA,
    TOOLCHAIN_CAPABILITY_LAPACK_FAMILY,
    TOOLCHAIN_CAPABILITY_MPI_FAMILY,
]
# modes to handle header and linker search paths
# see: https://gcc.gnu.org/onlinedocs/cpp/Environment-Variables.html
# supported on Linux by: GCC, GFortran, oneAPI C/C++ Compilers, oneAPI Fortran Compiler, LLVM-based
SEARCH_PATH = {
    "cpp_headers": {
        "flags": ["CPPFLAGS"],
        "cpath": ["CPATH"],
        "include_paths": ["C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH"],
    },
    "linker": {
        "flags": ["LDFLAGS"],
        "library_path": ["LIBRARY_PATH"],
    },
}
DEFAULT_SEARCH_PATH_CPP_HEADERS = "flags"
DEFAULT_SEARCH_PATH_LINKER = "flags"


def is_system_toolchain(tc_name):
    """Return whether toolchain with specified name is a system toolchain or not."""
    return tc_name in [SYSTEM_TOOLCHAIN_NAME]


def env_vars_external_module(name, version, metadata):
    """
    Determine $EBROOT* and/or $EBVERSION* environment variables that can be set for external module,
    based on the provided name, version and metadata.
    """
    env_vars = {}

    # define $EBROOT env var for install prefix, picked up by get_software_root
    prefix = metadata.get('prefix')
    if prefix is not None:
        # the prefix can be specified in a number of ways
        # * name of environment variable (+ optional relative path to combine it with; format: <name>/<relpath>
        # * filepath (assumed if environment variable is not defined)
        parts = prefix.split(os.path.sep)
        env_var = parts[0]
        if env_var in os.environ:
            prefix = os.environ[env_var]
            rel_path = os.path.sep.join(parts[1:])
            if rel_path:
                prefix = os.path.join(prefix, rel_path, '')

            _log.debug("Derived prefix for software named %s from $%s (rel path: %s): %s",
                       name, env_var, rel_path, prefix)
        else:
            _log.debug("Using specified path as prefix for software named %s: %s", name, prefix)

        env_vars[get_software_root_env_var_name(name)] = prefix

    # define $EBVERSION env var for software version, picked up by get_software_version
    if version is not None:
        env_vars[get_software_version_env_var_name(name)] = version

    return env_vars


class Toolchain:
    """General toolchain class"""

    OPTIONS_CLASS = ToolchainOptions
    VARIABLES_CLASS = ToolchainVariables

    NAME = None
    VERSION = None
    SUBTOOLCHAIN = None
    TOOLCHAIN_FAMILY = None

    # list of class 'constants' that should be restored for every new instance of this class
    CLASS_CONSTANTS_TO_RESTORE = None
    CLASS_CONSTANT_COPIES = {}

    # class method
    def _is_toolchain_for(cls, name):
        """see if this class can provide support for toolchain named name"""
        # TODO report later in the initialization the found version
        if name:
            try:
                return name == cls.NAME
            except AttributeError:
                return False
        else:
            # is no name is supplied, check whether class can be used as a toolchain
            return bool(getattr(cls, 'NAME', None))

    _is_toolchain_for = classmethod(_is_toolchain_for)

    def __init__(self, name=None, version=None, mns=None, class_constants=None, tcdeps=None, modtool=None,
                 hidden=False):
        """
        Toolchain constructor.

        :param name: toolchain name
        :param version: toolchain version
        :param mns: module naming scheme to use
        :param class_constants: toolchain 'constants' to define
        :param tcdeps: list of toolchain 'dependencies' (i.e., the toolchain components)
        :param modtool: ModulesTool instance to use
        :param hidden: bool indicating whether toolchain is hidden or not
        """
        self.base_init()

        self.dependencies = []
        self.toolchain_dep_mods = []
        self.cached_compilers = set()

        if name is None:
            name = self.NAME
        if name is None:
            raise EasyBuildError("Toolchain init: no name provided")
        self.name = name

        if version is None:
            version = self.VERSION
        if version is None:
            raise EasyBuildError("Toolchain init: no version provided")
        self.version = version

        self.modules = []
        self.vars = None

        self._init_class_constants(class_constants)

        self.tcdeps = tcdeps if tcdeps else []

        # toolchain instances are created before initiating build options sometimes, e.g. for --list-toolchains
        self.dry_run = build_option('extended_dry_run', default=False)
        hidden_toolchains = build_option('hide_toolchains', default=None) or []
        self.hidden = hidden or (name in hidden_toolchains)

        self.modules_tool = modtool

        self.use_rpath = False

        self.search_path = {
            "cpp_headers": DEFAULT_SEARCH_PATH_CPP_HEADERS,
            "linker": DEFAULT_SEARCH_PATH_LINKER,
        }

        self.mns = mns
        self.mod_full_name = None
        self.mod_short_name = None
        self.init_modpaths = None
        if not self.is_system_toolchain():
            # sometimes no module naming scheme class instance can/will be provided, e.g. with --list-toolchains
            if self.mns is not None:
                tc_dict = self.as_dict()
                self.mod_full_name = self.mns.det_full_module_name(tc_dict)
                self.mod_short_name = self.mns.det_short_module_name(tc_dict)
                self.init_modpaths = self.mns.det_init_modulepaths(tc_dict)

    @property
    def search_path_vars_headers(self):
        """Return list of environment variables used as search paths for headers"""
        return self._search_path_vars('cpp_headers')

    @property
    def search_path_vars_linker(self):
        """Return list of environment variables used as search paths by the linker"""
        return self._search_path_vars('linker')

    def _search_path_vars(self, search_object):
        """Return list of environment variables used as search paths for the given object"""
        try:
            search_path_opt = self.search_path[search_object]
        except KeyError:
            raise EasyBuildError("Failed to retrieve search path options for '%s'", search_object)

        # default 'flags' option does not use search paths in the build environment
        if search_path_opt == 'flags':
            return []

        return SEARCH_PATH[search_object][search_path_opt]

    def is_system_toolchain(self):
        """Return boolean to indicate whether this toolchain is a system toolchain."""
        return is_system_toolchain(self.name)

    def set_minimal_build_env(self):
        """Set up a minimal build environment, by setting (only) the $CC and $CXX environment variables."""

        # this is only relevant when using a system toolchain,
        # for proper toolchains these variables will get set via the call to set_variables()

        minimal_build_env_raw = build_option('minimal_build_env')

        minimal_build_env = {}
        for key_val in minimal_build_env_raw.split(','):
            parts = key_val.split(':')
            if len(parts) == 2:
                key, val = parts
                minimal_build_env[key] = val
            else:
                raise EasyBuildError("Incorrect mapping in --minimal-build-env value: '%s'", key_val)

        env_vars = {}
        for key, val in minimal_build_env.items():
            # for key environment variables like $CC and $CXX we are extra careful,
            # by making sure the specified command is actually available
            if key in ['CC', 'CXX']:
                warning_msg = None
                if os.path.isabs(val):
                    if os.path.exists(val):
                        self.log.info("Specified path for $%s exists: %s", key, val)
                        env_vars.update({key: val})
                    else:
                        warning_msg = "Specified path '%s' does not exist"
                else:
                    cmd_path = which(val)
                    if cmd_path:
                        self.log.info("Found compiler command %s at %s, so setting $%s in minimal build environment",
                                      val, cmd_path, key)
                        env_vars.update({key: val})
                    else:
                        warning_msg = "'%s' command not found in $PATH" % val

                if warning_msg:
                    print_warning(warning_msg + ", not setting $%s in minimal build environment" % key, log=self.log)
            else:
                # no checking for environment variables other than $CC or $CXX
                env_vars.update({key: val})

        # set specified environment variables, but print a warning
        # if we're redefining anything that was already set to a *different* value
        for key, new_value in env_vars.items():
            curr_value = os.getenv(key)
            if curr_value and curr_value != new_value:
                print_warning("$%s was defined as '%s', but is now set to '%s' in minimal build environment",
                              key, curr_value, new_value)
            setvar(key, new_value)

    def base_init(self):
        """Initialise missing class attributes (log, options, variables)."""
        if not hasattr(self, 'log'):
            self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        if not hasattr(self, 'options'):
            self.options = self.OPTIONS_CLASS()

        if not hasattr(self, 'variables'):
            self.variables_init()

    def variables_init(self):
        """Initialise toolchain variables."""
        self.variables = self.VARIABLES_CLASS()
        if hasattr(self, 'LINKER_TOGGLE_START_STOP_GROUP'):
            self.variables.LINKER_TOGGLE_START_STOP_GROUP = self.LINKER_TOGGLE_START_STOP_GROUP
        if hasattr(self, 'LINKER_TOGGLE_STATIC_DYNAMIC'):
            self.variables.LINKER_TOGGLE_STATIC_DYNAMIC = self.LINKER_TOGGLE_STATIC_DYNAMIC

    def _init_class_constants(self, class_constants):
        """Initialise class 'constants'."""
        # make sure self.CLASS_CONSTANTS_TO_RESTORE is initialised
        if class_constants is None:
            self.CLASS_CONSTANTS_TO_RESTORE = []
        else:
            self.CLASS_CONSTANTS_TO_RESTORE = class_constants[:]

        self._copy_class_constants()
        self._restore_class_constants()

    def _copy_class_constants(self):
        """Copy class constants that needs to be restored again when a new instance is created."""
        # this only needs to be done the first time (for this class, taking inheritance into account is key)
        key = self.__class__
        if key not in self.CLASS_CONSTANT_COPIES:
            self.CLASS_CONSTANT_COPIES[key] = {}
            for cst in self.CLASS_CONSTANTS_TO_RESTORE:
                try:
                    value = getattr(self, cst)
                except AttributeError:
                    raise EasyBuildError("Class constant '%s' to be restored does not exist in %s", cst, self)
                else:
                    self.CLASS_CONSTANT_COPIES[key][cst] = copy.deepcopy(value)

            self.log.devel("Copied class constants: %s", self.CLASS_CONSTANT_COPIES[key])

    def _restore_class_constants(self):
        """Restored class constants that need to be restored when a new instance is created."""
        key = self.__class__
        for cst in self.CLASS_CONSTANT_COPIES[key]:
            newval = copy.deepcopy(self.CLASS_CONSTANT_COPIES[key][cst])
            try:
                oldval = getattr(self, cst)
            except AttributeError:
                self.log.devel("Restoring (currently undefined) class constant '%s' to %s", cst, newval)
            else:
                self.log.devel("Restoring class constant '%s' to %s (was: %s)", cst, newval, oldval)

            setattr(self, cst, newval)

    def get_variable(self, name, typ=str):
        """Get value for specified variable.
        typ: indicates what type of return value is expected"""

        if typ == str:
            res = str(self.variables.get(name, ''))

        elif typ == list:
            if name in self.variables:
                res = self.variables[name].flatten()
            else:
                res = []
        else:
            raise EasyBuildError("get_variable: Don't know how to create value of type %s.", typ)

        return res

    def set_variables(self):
        """
        No generic toolchain variables set.
        Post-process variables set by child Toolchain classes.
        """

        if self.options.option('packed-linker-options'):
            self.log.devel("set_variables: toolchain variables. packed-linker-options.")
            self.variables.try_function_on_element('set_packed_linker_options')
        self.log.devel("set_variables: toolchain variables. Do nothing.")

    def generate_vars(self):
        """Convert the variables in simple vars"""
        self.vars = {}
        for k, v in self.variables.items():
            self.vars[k] = str(v)

    def show_variables(self, offset='', sep='\n', verbose=False):
        """Pretty print the variables"""
        if self.vars is None:
            self.generate_vars()

        var_names = sorted(self.variables.keys())
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
        self.log.debug("show_variables:\n%s", txt)
        return txt

    def get_software_root(self, names):
        """Try to get the software root for all names"""
        return self._get_software_multiple(names, self._get_software_root)

    def get_software_version(self, names, required=True):
        """Try to get the software version for all names"""
        return self._get_software_multiple(names, self._get_software_version, required=required)

    def _get_software_multiple(self, names, function, required=True):
        """Execute function of each of names"""
        if isinstance(names, (str,)):
            names = [names]
        res = []
        for name in names:
            res.append(function(name, required=required))
        return res

    def _get_software_root(self, name, required=True):
        """Try to get the software root for name"""
        root = get_software_root(name)
        if root is None:
            if required:
                raise EasyBuildError("get_software_root software root for %s was not found in environment", name)
        else:
            self.log.debug("get_software_root software root %s for %s was found in environment", root, name)
        return root

    def _get_software_version(self, name, required=True):
        """Try to get the software version for name"""
        version = get_software_version(name)
        if version is None:
            if required:
                raise EasyBuildError("get_software_version software version for %s was not found in environment", name)
        else:
            self.log.debug("get_software_version software version %s for %s was found in environment", version, name)

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
            'toolchain': {'name': SYSTEM_TOOLCHAIN_NAME, 'version': ''},
            'versionsuffix': '',
            'parsed': True,  # pretend this is a parsed easyconfig file, as may be required by det_short_module_name
            'hidden': self.hidden,
            'full_mod_name': self.mod_full_name,
            'short_mod_name': self.mod_short_name,
            SYSTEM_TOOLCHAIN_NAME: True,
        }

    def det_short_module_name(self):
        """Determine module name for this toolchain."""
        if self.mod_short_name is None:
            raise EasyBuildError("Toolchain module name was not set yet")
        return self.mod_short_name

    def _toolchain_exists(self):
        """
        Verify if there exists a toolchain by this name and version
        """
        # short-circuit to returning module name for this (non-system) toolchain
        if self.is_system_toolchain():
            self.log.devel("_toolchain_exists: system toolchain always exists, returning True")
            return True
        else:
            if self.mod_short_name is None:
                raise EasyBuildError("Toolchain module name was not set yet")
            # check whether a matching module exists if self.mod_short_name contains a module name
            return self.modules_tool.exist([self.mod_full_name], skip_avail=True)[0]

    def set_options(self, options):
        """ Process toolchain options """
        for opt in options.keys():
            # Only process supported opts
            if opt in self.options:
                self.options[opt] = options[opt]
            else:
                # used to be warning, but this is a severe error imho
                known_opts = ','.join(self.options.keys())
                raise EasyBuildError("Undefined toolchain option %s specified (known options: %s)", opt, known_opts)

    def get_dependency_version(self, dependency):
        """ Generate a version string for a dependency on a module using this toolchain """
        # add toolchain to version string (only for non-system toolchain)
        if self.is_system_toolchain():
            toolchain = ''
        else:
            toolchain = '-%s-%s' % (self.name, self.version)

        # check if dependency is independent of toolchain (i.e. whether is was built with system compiler)
        if SYSTEM_TOOLCHAIN_NAME in dependency and dependency[SYSTEM_TOOLCHAIN_NAME]:
            toolchain = ''

        suffix = dependency.get('versionsuffix', '')

        if 'version' in dependency:
            version = ''.join([dependency['version'], toolchain, suffix])
            self.log.devel("get_dependency_version: version in dependency return %s", version)
            return version
        else:
            toolchain_suffix = ''.join([toolchain, suffix])
            matches = self.modules_tool.available(dependency['name'], toolchain_suffix)
            # Find the most recent (or default) one
            if len(matches) > 0:
                version = matches[-1][-1]
                self.log.devel("get_dependency_version: version not in dependency return %s", version)
                return
            else:
                raise EasyBuildError("No toolchain version for dependency name %s (suffix %s) found",
                                     dependency['name'], toolchain_suffix)

    def _check_dependencies(self, dependencies, check_modules=True):
        """ Verify if the given dependencies exist and return them """
        self.log.debug("_check_dependencies: adding toolchain dependencies %s", dependencies)

        # use *full* module name to check existence of dependencies, since the modules may not be available in the
        # current $MODULEPATH without loading the prior dependencies in a module hierarchy
        # (e.g. OpenMPI module may only be available after loading GCC module);
        # when actually loading the modules for the dependencies, the *short* module name is used,
        # see _load_dependencies_modules()
        dep_mod_names = [dep['full_mod_name'] for dep in dependencies]

        # check whether modules exist
        self.log.debug("_check_dependencies: MODULEPATH: %s", os.environ['MODULEPATH'])
        if self.dry_run or not check_modules:
            deps_exist = [True] * len(dep_mod_names)
        else:
            deps_exist = self.modules_tool.exist(dep_mod_names)

        missing_dep_mods = []
        deps = []
        for dep, dep_mod_name, dep_exists in zip(dependencies, dep_mod_names, deps_exist):
            if dep_exists:
                deps.append(dep)
                self.log.devel("_check_dependencies: added toolchain dependency %s", str(dep))
            elif dep['external_module']:
                # external modules may be organised hierarchically,
                # so not all modules may be directly available for loading;
                # we assume here that the required modules are either provided by the toolchain,
                # or are listed earlier as dependency
                # examples from OpenHPC:
                # - openmpi3 module provided by OpenHPC requires that gnu7, gnu8 or intel module is loaded first
                # - fftw module provided by OpenHPC requires that compiler + MPI module are loaded first
                self.log.info("Assuming non-visible external module %s is available", dep['full_mod_name'])
                deps.append(dep)
            else:
                missing_dep_mods.append(dep_mod_name)

        if missing_dep_mods:
            raise EasyBuildError("Missing modules for dependencies (use --robot?): %s", ', '.join(missing_dep_mods))

        return deps

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
            if var.endswith(var_suff) and getattr(self, var) is not None:
                tc_elems.update({var[:-len(var_suff)]: getattr(self, var)})

        self.log.debug("Toolchain definition for %s: %s", self.as_dict(), tc_elems)
        return tc_elems

    def is_dep_in_toolchain_module(self, name):
        """Check whether a specific software name is listed as a dependency in the module for this toolchain."""
        return any(self.mns.is_short_modname_for(m, name) for m in self.toolchain_dep_mods)

    def _simulated_load_dependency_module(self, name, version, metadata, verbose=False):
        """
        Set environment variables picked up by utility functions for dependencies specified as external modules.

        :param name: software name
        :param version: software version
        :param metadata: dictionary with software metadata ('prefix' for software installation prefix)
        """

        self.log.debug("Defining $EB* environment variables for software named %s", name)

        env_vars = env_vars_external_module(name, version, metadata)
        for var, value in env_vars.items():
            setvar(var, value, verbose=verbose)

    def _load_toolchain_module(self, silent=False):
        """Load toolchain module."""

        tc_mod = self.det_short_module_name()

        if self.dry_run:
            dry_run_msg("Loading toolchain module...\n", silent=silent)

            # load toolchain module, or simulate load of toolchain components if it is not available
            if self.modules_tool.exist([tc_mod], skip_avail=True)[0]:
                self.modules_tool.load([tc_mod])
                dry_run_msg("module load %s" % tc_mod, silent=silent)
            else:
                # first simulate loads for toolchain dependencies, if required information is available
                for tcdep in self.tcdeps:
                    modname = tcdep['short_mod_name']
                    dry_run_msg("module load %s [SIMULATED]" % modname, silent=silent)
                    # 'use '$EBROOTNAME' as value for dep install prefix (looks nice in dry run output)
                    deproot = '$%s' % get_software_root_env_var_name(tcdep['name'])
                    self._simulated_load_dependency_module(tcdep['name'], tcdep['version'], {'prefix': deproot})

                dry_run_msg("module load %s [SIMULATED]" % tc_mod, silent=silent)
                # use name of $EBROOT* env var as value for $EBROOT* env var (results in sensible dry run output)
                tcroot = '$%s' % get_software_root_env_var_name(self.name)
                self._simulated_load_dependency_module(self.name, self.version, {'prefix': tcroot})
        else:
            # make sure toolchain is available using short module name by running 'module use' on module path subdir
            if self.init_modpaths:
                mod_path_suffix = build_option('suffix_modules_path')
                for modpath in self.init_modpaths:
                    modpath = os.path.join(install_path('mod'), mod_path_suffix, modpath)
                    if os.path.exists(modpath):
                        self.modules_tool.prepend_module_path(modpath)

            # load modules for all dependencies
            self.log.debug("Loading module for toolchain: %s", tc_mod)
            trace_msg("loading toolchain module: " + tc_mod)
            self.modules_tool.load([tc_mod])

        # append toolchain module to list of modules
        self.modules.append(tc_mod)

    def _load_dependencies_modules(self, silent=False):
        """Load modules for dependencies, and handle special cases like external modules."""
        dep_mods = [dep['short_mod_name'] for dep in self.dependencies]

        if self.dry_run:
            dry_run_msg("\nLoading modules for dependencies...\n", silent=silent)

            mods_exist = self.modules_tool.exist(dep_mods)

            # load available modules for dependencies, simulate load for others
            for dep, dep_mod_exists in zip(self.dependencies, mods_exist):
                mod_name = dep['short_mod_name']
                if dep_mod_exists:
                    self.modules_tool.load([mod_name])
                    dry_run_msg("module load %s" % mod_name, silent=silent)
                else:
                    dry_run_msg("module load %s [SIMULATED]" % mod_name, silent=silent)
                    # 'use '$EBROOTNAME' as value for dep install prefix (looks nice in dry run output)
                    if not dep['external_module']:
                        deproot = '$%s' % get_software_root_env_var_name(dep['name'])
                        self._simulated_load_dependency_module(dep['name'], dep['version'], {'prefix': deproot})
        else:
            # load modules for all dependencies
            self.log.debug("Loading modules for dependencies: %s", dep_mods)
            self.modules_tool.load(dep_mods)

            if self.dependencies:
                build_dep_mods = [dep['short_mod_name'] for dep in self.dependencies if dep['build_only']]
                if build_dep_mods:
                    trace_msg("loading modules for build dependencies:")
                    for dep_mod in build_dep_mods:
                        trace_msg(' * ' + dep_mod)
                else:
                    trace_msg("(no build dependencies specified)")

                run_dep_mods = [dep['short_mod_name'] for dep in self.dependencies if not dep['build_only']]
                if run_dep_mods:
                    trace_msg("loading modules for (runtime) dependencies:")
                    for dep_mod in run_dep_mods:
                        trace_msg(' * ' + dep_mod)
                else:
                    trace_msg("(no (runtime) dependencies specified)")

        # append dependency modules to list of modules
        self.modules.extend(dep_mods)

        # define $EBROOT* and $EBVERSION* for external modules, if metadata is available
        for dep in [d for d in self.dependencies if d['external_module']]:
            mod_name = dep['full_mod_name']
            metadata = dep['external_module_metadata']
            self.log.debug("Metadata for external module %s: %s", mod_name, metadata)

            names = metadata.get('name', [])
            versions = metadata.get('version', [None] * len(names))
            self.log.debug("Defining $EB* environment variables for external module %s using names %s, versions %s",
                           mod_name, names, versions)

            for name, version in zip(names, versions):
                self._simulated_load_dependency_module(name, version, metadata, verbose=True)

    def _load_modules(self, silent=False):
        """Load modules for toolchain and dependencies."""
        if self.modules_tool is None:
            raise EasyBuildError("No modules tool defined in Toolchain instance.")

        if not self._toolchain_exists() and not self.dry_run:
            raise EasyBuildError("No module found for toolchain: %s", self.mod_short_name)

        if self.is_system_toolchain():
            self.log.info("Loading dependencies using system toolchain...")
            self._load_dependencies_modules(silent=silent)
        else:
            # load the toolchain and dependencies modules
            self.log.debug("Loading toolchain module and dependencies...")
            self._load_toolchain_module(silent=silent)
            self._load_dependencies_modules(silent=silent)

        # include list of loaded modules in dry run output
        if self.dry_run:
            loaded_mods = self.modules_tool.list()
            dry_run_msg("\nFull list of loaded modules:", silent=silent)
            if loaded_mods:
                for i, mod_name in enumerate([m['mod_name'] for m in loaded_mods]):
                    dry_run_msg("  %d) %s" % (i + 1, mod_name), silent=silent)
            else:
                dry_run_msg("  (none)", silent=silent)
            dry_run_msg('', silent=silent)

    def _verify_toolchain(self):
        """Verify toolchain: check toolchain definition against dependencies of toolchain module."""
        # determine direct toolchain dependencies
        mod_name = self.det_short_module_name()
        self.toolchain_dep_mods = dependencies_for(mod_name, self.modules_tool, depth=0)
        self.log.debug("List of toolchain dependencies from toolchain module: %s", self.toolchain_dep_mods)

        # only retain names of toolchain elements, excluding toolchain name
        toolchain_definition = {e for es in self.definition().values() for e in es if not e == self.name}

        # filter out optional toolchain elements if they're not used in the module
        for elem_name in toolchain_definition.copy():
            if self.is_required(elem_name) or self.is_dep_in_toolchain_module(elem_name):
                continue
            # not required and missing: remove from toolchain definition
            self.log.debug("Removing %s from list of optional toolchain elements.", elem_name)
            toolchain_definition.remove(elem_name)

        self.log.debug("List of toolchain elements from toolchain definition: %s", toolchain_definition)

        if all(map(self.is_dep_in_toolchain_module, toolchain_definition)):
            self.log.info("List of toolchain dependency modules and toolchain definition match!")
        else:
            raise EasyBuildError("List of toolchain dependency modules and toolchain definition do not match "
                                 "(found %s vs expected %s)", self.toolchain_dep_mods, toolchain_definition)

    def _validate_search_path(self):
        """
        Validate search path toolchain options.
        Toolchain option has precedence over build option
        """
        for search_path in self.search_path:
            sp_build_opt = f"search_path_{search_path}"
            sp_toolchain_opt = sp_build_opt.replace("_", "-")
            if self.options.get(sp_toolchain_opt) is not None:
                self.search_path[search_path] = self.options.option(sp_toolchain_opt)
            elif build_option(sp_build_opt) is not None:
                self.search_path[search_path] = build_option(sp_build_opt)

            if self.search_path[search_path] not in SEARCH_PATH[search_path]:
                raise EasyBuildError(
                    "Unknown value selected for toolchain option %s: %s. Choose one of: %s",
                    sp_toolchain_opt, self.search_path[search_path], ", ".join(SEARCH_PATH[search_path])
                )

            self.log.debug("%s toolchain option set to: %s", sp_toolchain_opt, self.search_path[search_path])

    def symlink_commands(self, paths):
        """
        Create a symlink for each command to binary/script at specified path.

        :param paths: dictionary containing one or mappings, each one specified as a tuple:
                      (<path/to/script>, <list of commands to symlink to the script>)
        """
        symlink_dir = tempfile.mkdtemp()

        # prepend location to symlinks to $PATH
        setvar('PATH', '%s:%s' % (symlink_dir, os.getenv('PATH')))

        for (path, cmds) in paths.values():
            for cmd in cmds:
                cmd_s = os.path.join(symlink_dir, cmd)
                if not os.path.exists(cmd_s):
                    try:
                        os.symlink(path, cmd_s)
                    except OSError as err:
                        raise EasyBuildError("Failed to symlink %s to %s: %s", path, cmd_s, err)

                cmd_path = which(cmd)
                self.log.debug("which(%s): %s -> %s", cmd, cmd_path, os.path.realpath(cmd_path))

            self.log.info("Commands symlinked to %s via %s: %s", path, symlink_dir, ', '.join(cmds))

    def compilers(self):
        """Return list of relevant compilers for this toolchain"""

        if self.is_system_toolchain():
            c_comps = ['gcc', 'g++']
            fortran_comps = ['gfortran']
        else:
            c_comps = [self.COMPILER_CC, self.COMPILER_CXX]
            fortran_comps = [self.COMPILER_F77, self.COMPILER_F90, self.COMPILER_FC]

        return (c_comps, fortran_comps)

    def linkers(self):
        """Return list of relevant linkers for this toolchain"""

        if self.is_system_toolchain():
            linkers = ['ld', 'ld.gold', 'ld.bfd']
        else:
            linkers = list(self.LINKERS or [])

        return linkers

    def is_deprecated(self):
        """Return whether or not this toolchain is deprecated."""
        return False

    def reset(self):
        """Reset this toolchain instance."""
        self.variables_init()

    def prepare(self, onlymod=None, deps=None, silent=False, loadmod=True,
                rpath_filter_dirs=None, rpath_include_dirs=None, rpath_wrappers_dir=None):
        """
        Prepare a set of environment parameters based on name/version of toolchain
        - load modules for toolchain and dependencies
        - generate extra variables and set them in the environment

        :param deps: list of dependencies
        :param onlymod: boolean/string to indicate if the toolchain should only load the environment
                         with module (True) or also set all other variables (False) like compiler CC etc
                         (If string: comma separated list of variables that will be ignored).
        :param silent: keep quiet, or not (mostly relates to extended dry run output)
        :param loadmod: whether or not to (re)load the toolchain module, and the modules for the dependencies
        :param rpath_filter_dirs: extra directories to include in RPATH filter (e.g. build dir, tmpdir, ...)
        :param rpath_include_dirs: extra directories to include in RPATH
        :param rpath_wrappers_dir: directory in which to create RPATH wrappers
        """

        # take into account --sysroot configuration setting
        self.handle_sysroot()

        # do all dependencies have a toolchain version?
        if deps is None:
            deps = []
        self.dependencies = self._check_dependencies(deps, check_modules=loadmod)
        if not len(deps) == len(self.dependencies):
            self.log.debug("dep %s (%s)" % (len(deps), deps))
            self.log.debug("tc.dep %s (%s)" % (len(self.dependencies), self.dependencies))
            raise EasyBuildError('Not all dependencies have a matching toolchain version')

        if loadmod:
            self._load_modules(silent=silent)

        if self.is_system_toolchain():
            # define minimal build environment when using system toolchain;
            # this is mostly done to try controlling which compiler commands are being used,
            # cfr. https://github.com/easybuilders/easybuild-framework/issues/3398
            self.set_minimal_build_env()

        else:
            trace_msg("defining build environment for %s/%s toolchain" % (self.name, self.version))

            if not self.dry_run:
                self._verify_toolchain()

            # Generate the variables to be set
            self._validate_search_path()
            self.set_variables()

            # set the variables
            # onlymod can be comma-separated string of variables not to be set
            if onlymod is True:
                self.log.debug("prepare: do not set additional variables onlymod=%s", onlymod)
                self.generate_vars()
            else:
                self.log.debug("prepare: set additional variables onlymod=%s", onlymod)

                # add linker and preprocessor paths of dependencies to self.vars
                self._add_dependency_variables()
                self.generate_vars()
                self._setenv_variables(onlymod, verbose=not silent)

        # consider f90cache first, since ccache can also wrap Fortran compilers
        for cache_tool in [F90CACHE, CCACHE]:
            if build_option('use_%s' % cache_tool):
                self.prepare_compiler_cache(cache_tool)

        if build_option('rpath'):
            if self.options.get('rpath', True):
                self.prepare_rpath_wrappers(
                    rpath_filter_dirs=rpath_filter_dirs,
                    rpath_include_dirs=rpath_include_dirs,
                    rpath_wrappers_dir=rpath_wrappers_dir
                    )
                self.use_rpath = True
            else:
                self.log.info("Not putting RPATH wrappers in place, disabled via 'rpath' toolchain option")

    def comp_cache_compilers(self, cache_tool):
        """
        Determine list of relevant compilers for specified compiler caching tool.
        :param cache_tool: name of compiler caching tool
        :return: list of names of relevant compilers
        """
        c_comps, fortran_comps = self.compilers()

        if cache_tool == CCACHE:
            # some version of ccache support caching of Fortran compilations,
            # but it doesn't work with Fortran modules (https://github.com/ccache/ccache/issues/342),
            # and support was dropped in recent ccache versions;
            # as a result, we only use ccache for C/C++ compilers
            comps = c_comps
        elif cache_tool == F90CACHE:
            comps = fortran_comps
        else:
            raise EasyBuildError("Uknown compiler caching tool specified: %s", cache_tool)

        # filter out compilers that are already cached;
        # Fortran compilers could already be cached by f90cache when preparing for ccache
        for comp in comps[:]:
            if comp in self.cached_compilers:
                self.log.debug("Not caching compiler %s, it's already being cached", comp)
                comps.remove(comp)

        self.log.info("Using %s for these compiler commands: %s", cache_tool, ', '.join(comps))

        return comps

    def prepare_compiler_cache(self, cache_tool):
        """
        Prepare for using specified compiler caching tool (e.g., ccache, f90cache)

        :param cache_tool: name of compiler caching tool to prepare for
        """
        compilers = self.comp_cache_compilers(cache_tool)
        self.log.debug("Using compiler cache tool '%s' for compilers: %s", cache_tool, compilers)

        # set paths that should be used by compiler caching tool
        comp_cache_path = build_option('use_%s' % cache_tool)
        setvar('%s_DIR' % cache_tool.upper(), comp_cache_path)
        setvar('%s_TEMPDIR' % cache_tool.upper(), tempfile.mkdtemp())

        cache_path = which(cache_tool)
        if cache_path is None:
            raise EasyBuildError("%s binary not found in $PATH, required by --use-ccache", cache_tool)
        else:
            self.symlink_commands({cache_tool: (cache_path, compilers)})

        self.cached_compilers.update(compilers)
        self.log.debug("Cached compilers (after preparing for %s): %s", cache_tool, self.cached_compilers)

    @staticmethod
    def is_rpath_wrapper(path):
        """
        Check whether command at specified location already is an RPATH wrapper script rather than the actual command
        """
        if os.path.basename(os.path.dirname(os.path.dirname(path))) != RPATH_WRAPPERS_SUBDIR:
            return False
        # Check if `rpath_args`` is called in the file
        # need to use binary mode to read the file, since it may be an actual compiler command (which is a binary file)
        return b'rpath_args.py $CMD' in read_file(path, mode='rb')

    def prepare_rpath_wrappers(self, rpath_filter_dirs=None, rpath_include_dirs=None, rpath_wrappers_dir=None):
        """
        Put RPATH wrapper script in place for compiler and linker commands

        :param rpath_filter_dirs: extra directories to include in RPATH filter (e.g. build dir, tmpdir, ...)
        :param rpath_include_dirs: extra directories to include in RPATH
        :param rpath_wrappers_dir: directory in which to create RPATH wrappers (tmpdir is created if None)
        """
        if get_os_type() == LINUX:
            self.log.info("Putting RPATH wrappers in place...")
        else:
            raise EasyBuildError("RPATH linking is currently only supported on Linux")

        if rpath_filter_dirs is None:
            rpath_filter_dirs = []

        # only enable logging by RPATH wrapper scripts in debug mode
        enable_wrapper_log = build_option('debug')

        copy_rpath_args_py = False

        # always include filter for 'stubs' library directory,
        # cfr. https://github.com/easybuilders/easybuild-framework/issues/2683
        # (since CUDA 11.something the stubs are in $EBROOTCUDA/stubs/lib64)
        lib_stubs_patterns = ['.*/lib(64)?/stubs/?', '.*/stubs/lib(64)?/?']
        for lib_stubs_pattern in lib_stubs_patterns:
            if lib_stubs_pattern not in rpath_filter_dirs:
                rpath_filter_dirs.append(lib_stubs_pattern)

        # directory where all RPATH wrapper script will be placed;
        if rpath_wrappers_dir is None:
            wrappers_dir = tempfile.mkdtemp()
        else:
            wrappers_dir = rpath_wrappers_dir
            # disable logging in RPATH wrapper scripts when they may be exported for use outside of EasyBuild
            enable_wrapper_log = False
            # copy rpath_args.py script to sit alongside RPATH wrapper scripts
            copy_rpath_args_py = True

        # it's important to honor RPATH_WRAPPERS_SUBDIR, see is_rpath_wrapper method
        wrappers_dir = os.path.join(wrappers_dir, RPATH_WRAPPERS_SUBDIR)
        mkdir(wrappers_dir, parents=True)

        # must also wrap compilers commands, required e.g. for Clang ('gcc' on OS X)?
        c_comps, fortran_comps = self.compilers()
        linkers = self.linkers()

        rpath_args_py = find_eb_script('rpath_args.py')

        # copy rpath_args.py script along RPATH wrappers, if desired
        if copy_rpath_args_py:
            copy_file(rpath_args_py, wrappers_dir)
            # use path for %(rpath_args)s template value relative to location of the RPATH wrapper script,
            # to avoid that the RPATH wrapper scripts rely on a script that's located elsewhere;
            # that's mostly important when RPATH wrapper scripts are retained to be used outside of EasyBuild;
            # we assume that each RPATH wrapper script is created in a separate subdirectory (see wrapper_dir below);
            # ${TOPDIR} is defined in template for RPATH wrapper scripts, refers to parent dir of RPATH wrapper script
            rpath_args_py = os.path.join('${TOPDIR}', '..', os.path.basename(rpath_args_py))

        rpath_wrapper_template = find_eb_script('rpath_wrapper_template.sh.in')

        # figure out list of patterns to use in rpath filter
        rpath_filter = build_option('rpath_filter')
        if rpath_filter is None:
            rpath_filter = ['/lib.*', '/usr.*']
            self.log.debug("No general RPATH filter specified, falling back to default: %s", rpath_filter)
        rpath_filter = ','.join(rpath_filter + ['%s.*' % d for d in rpath_filter_dirs])
        self.log.debug("Combined RPATH filter: '%s'", rpath_filter)

        rpath_include = ','.join(rpath_include_dirs or [])
        self.log.debug("Combined RPATH include paths: '%s'", rpath_include)

        # create wrappers
        for cmd in nub(c_comps + fortran_comps + ['ld', 'ld.gold', 'ld.bfd'] + linkers):
            # Not all toolchains have fortran compilers (e.g. Clang), in which case they are 'None'
            if cmd is None:
                continue
            orig_cmd = which(cmd)

            if orig_cmd:
                # bail out early if command already is a wrapped;
                # this may occur when building extensions
                if self.is_rpath_wrapper(orig_cmd):
                    self.log.info("%s already seems to be an RPATH wrapper script, not wrapping it again!", orig_cmd)
                    continue

                # determine location for this wrapper
                # each wrapper is placed in its own subdirectory to enable $PATH filtering per wrapper separately
                # avoid '+' character in directory name (for example with 'g++' command), which can cause trouble
                # (see https://github.com/easybuilders/easybuild-easyconfigs/issues/7339)
                wrapper_dir_name = '%s_wrapper' % cmd.replace('+', 'x')
                wrapper_dir = os.path.join(wrappers_dir, wrapper_dir_name)

                cmd_wrapper = os.path.join(wrapper_dir, cmd)

                # make *very* sure we don't wrap around ourselves and create a fork bomb...
                if os.path.exists(cmd_wrapper) and os.path.exists(orig_cmd) and os.path.samefile(orig_cmd, cmd_wrapper):
                    raise EasyBuildError("Refusing to create a fork bomb, which(%s) == %s", cmd, orig_cmd)

                # enable debug mode in wrapper script by specifying location for log file
                if enable_wrapper_log:
                    rpath_wrapper_log = os.path.join(tempfile.gettempdir(), f'rpath_wrapper_{cmd}.log')
                else:
                    rpath_wrapper_log = '/dev/null'

                # complete template script and put it in place
                cmd_wrapper_txt = read_file(rpath_wrapper_template) % {
                    'orig_cmd': orig_cmd,
                    'python': sys.executable,
                    'rpath_args_py': rpath_args_py,
                    'rpath_filter': rpath_filter,
                    'rpath_include': rpath_include,
                    'rpath_wrapper_log': rpath_wrapper_log,
                    'wrapper_dir': wrapper_dir,
                }

                # it may be the case that the wrapper already exists if the user provides a fixed location to store
                # the RPATH wrappers, in this case the wrappers will be overwritten as they do not yet appear in the
                # PATH (`which(cmd)` does not "see" them). Warn that they will be overwritten.
                if os.path.exists(cmd_wrapper):
                    _log.warning(f"Overwriting existing RPATH wrapper {cmd_wrapper}")
                    write_file(cmd_wrapper, cmd_wrapper_txt, always_overwrite=True)
                else:
                    write_file(cmd_wrapper, cmd_wrapper_txt)
                adjust_permissions(cmd_wrapper, stat.S_IXUSR)

                # prepend location to this wrapper to $PATH
                setvar('PATH', '%s:%s' % (wrapper_dir, os.getenv('PATH')))

                self.log.info("RPATH wrapper script for %s: %s (log: %s)", orig_cmd, which(cmd), rpath_wrapper_log)
            else:
                self.log.debug("Not installing RPATH wrapper for non-existing command '%s'", cmd)

    def handle_sysroot(self):
        """
        Extra stuff to be done when alternative system root is specified via --sysroot EasyBuild configuration option.

        * Update $PKG_CONFIG_PATH to include sysroot location to pkg-config files (*.pc).
        """
        sysroot = build_option('sysroot')
        if sysroot:
            # update $PKG_CONFIG_PATH to include sysroot location to pkg-config files (*.pc)
            sysroot_pc_paths = [os.path.join(sysroot, 'usr', libdir, 'pkgconfig') for libdir in ['lib', 'lib64']]

            pkg_config_path = [p for p in os.getenv('PKG_CONFIG_PATH', '').split(os.pathsep) if p]

            for sysroot_pc_path in sysroot_pc_paths:
                if os.path.exists(sysroot_pc_path):
                    # avoid adding duplicate paths
                    if not any(os.path.exists(x) and os.path.samefile(x, sysroot_pc_path) for x in pkg_config_path):
                        pkg_config_path.append(sysroot_pc_path)

            if pkg_config_path:
                setvar('PKG_CONFIG_PATH', os.pathsep.join(pkg_config_path))

    def _add_dependency_variables(self, names=None, cpp=None, ld=None):
        """
        Add linker and preprocessor paths of dependencies to self.variables
        :names: list of strings containing the name of the dependency
        """
        # collect dependencies
        deps = self.dependencies if names is None else [{'name': name} for name in names if name]

        # collect software install prefixes for toolchain components + dependencies
        dep_roots = []
        for dep in deps + self.tcdeps:
            if dep.get('external_module', False):
                # for software names provided via external modules, install prefix may be unknown
                names = dep['external_module_metadata'].get('name', [])
                dep_roots.extend([x for x in self.get_software_root(names) if x is not None])
            else:
                dep_roots.extend(self.get_software_root(dep['name']))

        for dep_root in dep_roots:
            self._add_dependency_cpp_headers(dep_root, extra_dirs=cpp)
            self._add_dependency_linker_paths(dep_root, extra_dirs=ld)

    def _add_dependency_cpp_headers(self, dep_root, extra_dirs=None):
        """
        Append prepocessor paths for given dependency root directory
        """
        if extra_dirs is None:
            extra_dirs = ()

        for env_var in SEARCH_PATH['cpp_headers'][self.search_path['cpp_headers']]:
            header_dirs = []
            # take into account all $*PATH environment variables for dependencies
            for key in [y for x in SEARCH_PATH['cpp_headers'].values() for y in x if y.endswith('PATH')]:
                val = os.getenv(key)
                if val:
                    self.log.debug(f"${key} when determining subdirs of {dep_root} to retain for ${env_var}: {val}")
                    paths = val.split(':')
                    matching_paths = [p for p in paths if p.startswith(dep_root)]
                    subdirs = [os.path.relpath(p, dep_root) for p in matching_paths]
                    self.log.debug(f"Subdirectories of {dep_root} to add to ${env_var}: {subdirs}")
                    header_dirs.extend(os.path.relpath(p, dep_root) for p in matching_paths)
                else:
                    self.log.debug(f"${key} not defined, not used to find subdirs of {dep_root} to use for ${env_var}")

            # take into account extra_dirs + only retain unique entries
            header_dirs = unique_ordered_extend(header_dirs, extra_dirs)

            self.log.info(f"Adding header paths to toolchain variable '{env_var}': {dep_root} (subdirs: {header_dirs})")
            self.variables.append_subdirs(env_var, dep_root, subdirs=header_dirs)

    def _add_dependency_linker_paths(self, dep_root, extra_dirs=None):
        """
        Append linker paths for given dependency root directory
        """
        if extra_dirs is None:
            extra_dirs = ()

        lib_dirs = ["lib64", "lib"]
        lib_dirs = unique_ordered_extend(lib_dirs, extra_dirs)

        for env_var in SEARCH_PATH["linker"][self.search_path["linker"]]:
            self.log.debug("Adding lib paths to toolchain variable '%s': %s", env_var, dep_root)
            self.variables.append_subdirs(env_var, dep_root, subdirs=lib_dirs)

    def _setenv_variables(self, donotset=None, verbose=True):
        """Actually set the environment variables"""

        self.log.devel("_setenv_variables: setting variables: donotset=%s", donotset)
        if self.dry_run:
            dry_run_msg("Defining build environment...\n", silent=not verbose)

        donotsetlist = []
        if isinstance(donotset, str):
            # TODO : more legacy code that should be using proper type
            raise EasyBuildError("_setenv_variables: using commas-separated list. should be deprecated.")
        elif isinstance(donotset, list):
            donotsetlist = donotset

        for key, val in sorted(self.vars.items()):
            if key in donotsetlist:
                self.log.debug("_setenv_variables: not setting environment variable %s (value: %s).", key, val)
                continue

            self.log.debug("_setenv_variables: setting environment variable %s to %s", key, val)
            setvar(key, val, verbose=verbose)

            # also set unique named variables that can be used in Makefiles
            # - so you can have 'CFLAGS = $(EBVARCFLAGS)'
            # -- 'CLFLAGS = $(CFLAGS)' gives  '*** Recursive variable `CFLAGS'
            # references itself (eventually).  Stop' error
            setvar("EBVAR%s" % key, val, verbose=False)

    def get_flag(self, name):
        """Get compiler flag(s) for a certain option."""
        if isinstance(self.options.option(name), list):
            return " ".join(self.options.option(name))
        else:
            return self.options.option(name)

    def toolchain_family(self):
        """Return toolchain family for this toolchain."""
        return self.TOOLCHAIN_FAMILY

    def comp_family(self):
        """ Return compiler family used in this toolchain (abstract method)."""
        raise NotImplementedError

    def blas_family(self):
        """Return type of BLAS library used in this toolchain, or 'None' if BLAS is not supported."""
        return None

    def lapack_family(self):
        """Return type of LAPACK library used in this toolchain, or 'None' if LAPACK is not supported."""
        return None

    def mpi_family(self):
        """Return type of MPI library used in this toolchain, or 'None' if MPI is not supported."""
        return None

    def banned_linked_shared_libs(self):
        """
        List of shared libraries (names, file names, paths) which are
        not allowed to be linked in any installed binary/library.
        """
        return []

    def required_linked_shared_libs(self):
        """
        List of shared libraries (names, file names, paths) which
        must be linked in all installed binaries/libraries.
        """
        return []

    def cleanup(self):
        """Clean up after using this toolchain"""
        pass
