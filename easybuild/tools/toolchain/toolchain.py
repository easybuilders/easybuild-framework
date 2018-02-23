# #
# Copyright 2012-2018 Ghent University
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

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
import copy
import os
import stat
import sys
import tempfile
from vsc.utils import fancylogger
from vsc.utils.missing import nub

import easybuild.tools.toolchain
from easybuild.tools.build_log import EasyBuildError, dry_run_msg
from easybuild.tools.config import build_option, install_path
from easybuild.tools.environment import setvar
from easybuild.tools.filetools import adjust_permissions, find_eb_script, mkdir, read_file, which, write_file
from easybuild.tools.module_generator import dependencies_for
from easybuild.tools.modules import get_software_root, get_software_root_env_var_name
from easybuild.tools.modules import get_software_version, get_software_version_env_var_name
from easybuild.tools.systemtools import LINUX, get_os_type
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME, DUMMY_TOOLCHAIN_VERSION
from easybuild.tools.toolchain.options import ToolchainOptions
from easybuild.tools.toolchain.toolchainvariables import ToolchainVariables
from easybuild.tools.utilities import trace_msg


_log = fancylogger.getLogger('tools.toolchain', fname=False)

CCACHE = 'ccache'
F90CACHE = 'f90cache'

RPATH_WRAPPERS_SUBDIR = 'rpath_wrappers'


class Toolchain(object):
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
            if hasattr(cls, 'NAME') and name == cls.NAME:
                return True
            else:
                return False
        else:
            # is no name is supplied, check whether class can be used as a toolchain
            return hasattr(cls, 'NAME') and cls.NAME

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

        self.tcdeps = tcdeps

        # toolchain instances are created before initiating build options sometimes, e.g. for --list-toolchains
        self.dry_run = build_option('extended_dry_run', default=False)
        hidden_toolchains = build_option('hide_toolchains', default=None) or []
        self.hidden = hidden or (name in hidden_toolchains)

        self.modules_tool = modtool

        self.use_rpath = False

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
        """Initialise missing class attributes (log, options, variables)."""
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
                if hasattr(self, cst):
                    self.CLASS_CONSTANT_COPIES[key][cst] = copy.deepcopy(getattr(self, cst))
                else:
                    raise EasyBuildError("Class constant '%s' to be restored does not exist in %s", cst, self)

            self.log.devel("Copied class constants: %s", self.CLASS_CONSTANT_COPIES[key])

    def _restore_class_constants(self):
        """Restored class constants that need to be restored when a new instance is created."""
        key = self.__class__
        for cst in self.CLASS_CONSTANT_COPIES[key]:
            newval = copy.deepcopy(self.CLASS_CONSTANT_COPIES[key][cst])
            if hasattr(self, cst):
                self.log.devel("Restoring class constant '%s' to %s (was: %s)", cst, newval, getattr(self, cst))
            else:
                self.log.devel("Restoring (currently undefined) class constant '%s' to %s", cst, newval)

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
        """Do nothing? Everything should have been set by others
            Needs to be defined for super() relations
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
        self.log.debug("show_variables:\n%s", txt)
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
            raise EasyBuildError("get_software_root software root for %s was not found in environment", name)
        else:
            self.log.debug("get_software_root software root %s for %s was found in environment", root, name)
        return root

    def _get_software_version(self, name):
        """Try to get the software version for name"""
        version = get_software_version(name)
        if version is None:
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
            'toolchain': {'name': DUMMY_TOOLCHAIN_NAME, 'version': DUMMY_TOOLCHAIN_VERSION},
            'versionsuffix': '',
            'dummy': True,
            'parsed': True,  # pretend this is a parsed easyconfig file, as may be required by det_short_module_name
            'hidden': self.hidden,
            'full_mod_name': self.mod_full_name,
            'short_mod_name': self.mod_short_name,
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
        # short-circuit to returning module name for this (non-dummy) toolchain
        if self.name == DUMMY_TOOLCHAIN_NAME:
            self.log.devel("_toolchain_exists: %s toolchain always exists, returning True", DUMMY_TOOLCHAIN_NAME)
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

    def add_dependencies(self, dependencies):
        """ Verify if the given dependencies exist and add them """
        self.log.debug("add_dependencies: adding toolchain dependencies %s", dependencies)

        # use *full* module name to check existence of dependencies, since the modules may not be available in the
        # current $MODULEPATH without loading the prior dependencies in a module hierarchy
        # (e.g. OpenMPI module may only be available after loading GCC module);
        # when actually loading the modules for the dependencies, the *short* module name is used,
        # see _load_dependencies_modules()
        dep_mod_names = [dep['full_mod_name'] for dep in dependencies]

        # check whether modules exist
        self.log.debug("add_dependencies: MODULEPATH: %s", os.environ['MODULEPATH'])
        if self.dry_run:
            deps_exist = [True] * len(dep_mod_names)
        else:
            deps_exist = self.modules_tool.exist(dep_mod_names)

        missing_dep_mods = []
        for dep, dep_mod_name, dep_exists in zip(dependencies, dep_mod_names, deps_exist):
            if dep_exists:
                self.dependencies.append(dep)
                self.log.devel("add_dependencies: added toolchain dependency %s", str(dep))
            else:
                missing_dep_mods.append(dep_mod_name)

        if missing_dep_mods:
            raise EasyBuildError("Missing modules for one or more dependencies: %s", ', '.join(missing_dep_mods))

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

        self.log.debug("Toolchain definition for %s: %s", self.as_dict(), tc_elems)
        return tc_elems

    def is_dep_in_toolchain_module(self, name):
        """Check whether a specific software name is listed as a dependency in the module for this toolchain."""
        return any(map(lambda m: self.mns.is_short_modname_for(m, name), self.toolchain_dep_mods))

    def _simulated_load_dependency_module(self, name, version, metadata, verbose=False):
        """
        Set environment variables picked up by utility functions for dependencies specified as external modules.

        :param name: software name
        :param version: software version
        :param metadata: dictionary with software metadata ('prefix' for software installation prefix)
        """

        self.log.debug("Defining $EB* environment variables for software named %s", name)

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

                self.log.debug("Derived prefix for software named %s from $%s (rel path: %s): %s",
                               name, env_var, rel_path, prefix)
            else:
                self.log.debug("Using specified path as prefix for software named %s: %s", name, prefix)

            setvar(get_software_root_env_var_name(name), prefix, verbose=verbose)

        # define $EBVERSION env var for software version, picked up by get_software_version
        if version is not None:
            setvar(get_software_version_env_var_name(name), version, verbose=verbose)

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
                if self.tcdeps is not None:
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
                    self.modules_tool.prepend_module_path(os.path.join(install_path('mod'), mod_path_suffix, modpath))

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

        if self.name == DUMMY_TOOLCHAIN_NAME:
            if self.version == DUMMY_TOOLCHAIN_VERSION:
                self.log.info('prepare: toolchain dummy mode, dummy version; not loading dependencies')
                if self.dry_run:
                    dry_run_msg("(no modules are loaded for a dummy-dummy toolchain)", silent=silent)
            else:
                self.log.info('prepare: toolchain dummy mode and loading dependencies')
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
                    dry_run_msg("  %d) %s" % (i+1, mod_name), silent=silent)
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
        toolchain_definition = set([e for es in self.definition().values() for e in es if not e == self.name])

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

        if self.name == DUMMY_TOOLCHAIN_NAME:
            c_comps = ['gcc', 'g++']
            fortran_comps =  ['gfortran']
        else:
            c_comps = [self.COMPILER_CC, self.COMPILER_CXX]
            fortran_comps = [self.COMPILER_F77, self.COMPILER_F90, self.COMPILER_FC]

        return (c_comps, fortran_comps)

    def prepare(self, onlymod=None, silent=False, loadmod=True, rpath_filter_dirs=None, rpath_include_dirs=None):
        """
        Prepare a set of environment parameters based on name/version of toolchain
        - load modules for toolchain and dependencies
        - generate extra variables and set them in the environment

        :param onlymod: boolean/string to indicate if the toolchain should only load the environment
                         with module (True) or also set all other variables (False) like compiler CC etc
                         (If string: comma separated list of variables that will be ignored).
        :param silent: keep quiet, or not (mostly relates to extended dry run output)
        :param loadmod: whether or not to (re)load the toolchain module, and the modules for the dependencies
        :param rpath_filter_dirs: extra directories to include in RPATH filter (e.g. build dir, tmpdir, ...)
        :param rpath_include_dirs: extra directories to include in RPATH
        """
        if loadmod:
            self._load_modules(silent=silent)

        if self.name != DUMMY_TOOLCHAIN_NAME:

            trace_msg("defining build environment for %s/%s toolchain" % (self.name, self.version))

            if not self.dry_run:
                self._verify_toolchain()

            # Generate the variables to be set
            self.set_variables()

            # set the variables
            # onlymod can be comma-separated string of variables not to be set
            if onlymod == True:
                self.log.debug("prepare: do not set additional variables onlymod=%s", onlymod)
                self.generate_vars()
            else:
                self.log.debug("prepare: set additional variables onlymod=%s", onlymod)

                # add LDFLAGS and CPPFLAGS from dependencies to self.vars
                self._add_dependency_variables()
                self.generate_vars()
                self._setenv_variables(onlymod, verbose=not silent)

        # consider f90cache first, since ccache can also wrap Fortran compilers
        for cache_tool in [F90CACHE, CCACHE]:
            if build_option('use_%s' % cache_tool):
                self.prepare_compiler_cache(cache_tool)

        if build_option('rpath'):
            if self.options.get('rpath', True):
                self.prepare_rpath_wrappers(rpath_filter_dirs, rpath_include_dirs)
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
            # recent versions of ccache (>=3.3) also support caching of Fortran compilations
            comps = c_comps + fortran_comps
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
            raise EasyBuildError("%s binary not found in $PATH, required by --use-compiler-cache", cache_tool)
        else:
            self.symlink_commands({cache_tool: (cache_path, compilers)})

        self.cached_compilers.update(compilers)
        self.log.debug("Cached compilers (after preparing for %s): %s", cache_tool, self.cached_compilers)

    @staticmethod
    def is_rpath_wrapper(path):
        """
        Check whether command at specified location already is an RPATH wrapper script rather than the actual command
        """
        in_rpath_wrappers_dir = os.path.basename(os.path.dirname(os.path.dirname(path))) == RPATH_WRAPPERS_SUBDIR
        calls_rpath_args = 'rpath_args.py $CMD' in read_file(path)
        return in_rpath_wrappers_dir and calls_rpath_args

    def prepare_rpath_wrappers(self, rpath_filter_dirs=None, rpath_include_dirs=None):
        """
        Put RPATH wrapper script in place for compiler and linker commands

        :param rpath_filter_dirs: extra directories to include in RPATH filter (e.g. build dir, tmpdir, ...)
        """
        if get_os_type() == LINUX:
            self.log.info("Putting RPATH wrappers in place...")
        else:
            raise EasyBuildError("RPATH linking is currently only supported on Linux")

        # directory where all wrappers will be placed
        wrappers_dir = os.path.join(tempfile.mkdtemp(), RPATH_WRAPPERS_SUBDIR)

        # must also wrap compilers commands, required e.g. for Clang ('gcc' on OS X)?
        c_comps, fortran_comps = self.compilers()

        rpath_args_py = find_eb_script('rpath_args.py')
        rpath_wrapper_template = find_eb_script('rpath_wrapper_template.sh.in')

        # figure out list of patterns to use in rpath filter
        rpath_filter = build_option('rpath_filter')
        if rpath_filter is None:
            rpath_filter = ['/lib.*', '/usr.*']
            self.log.debug("No general RPATH filter specified, falling back to default: %s", rpath_filter)
        rpath_filter = ','.join(rpath_filter + ['%s.*' % d for d in rpath_filter_dirs or []])
        self.log.debug("Combined RPATH filter: '%s'", rpath_filter)

        rpath_include = ','.join(rpath_include_dirs or [])
        self.log.debug("Combined RPATH include paths: '%s'", rpath_include)

        # create wrappers
        for cmd in nub(c_comps + fortran_comps + ['ld', 'ld.gold', 'ld.bfd']):
            orig_cmd = which(cmd)

            if orig_cmd:
                # bail out early if command already is a wrapped;
                # this may occur when building extensions
                if self.is_rpath_wrapper(orig_cmd):
                    self.log.info("%s already seems to be an RPATH wrapper script, not wrapping it again!", orig_cmd)
                    continue

                # determine location for this wrapper
                # each wrapper is placed in its own subdirectory to enable $PATH filtering per wrapper separately
                wrapper_dir = os.path.join(wrappers_dir, '%s_wrapper' % cmd)

                cmd_wrapper = os.path.join(wrapper_dir, cmd)

                # make *very* sure we don't wrap around ourselves and create a fork bomb...
                if os.path.exists(cmd_wrapper) and os.path.exists(orig_cmd) and os.path.samefile(orig_cmd, cmd_wrapper):
                    raise EasyBuildError("Refusing the create a fork bomb, which(%s) == %s", cmd, orig_cmd)

                # enable debug mode in wrapper script by specifying location for log file
                if build_option('debug'):
                    rpath_wrapper_log = os.path.join(tempfile.gettempdir(), 'rpath_wrapper_%s.log' % cmd)
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
                write_file(cmd_wrapper, cmd_wrapper_txt)
                adjust_permissions(cmd_wrapper, stat.S_IXUSR)
                self.log.info("Wrapper script for %s: %s (log: %s)", orig_cmd, which(cmd), rpath_wrapper_log)

                # prepend location to this wrapper to $PATH
                setvar('PATH', '%s:%s' % (wrapper_dir, os.getenv('PATH')))
            else:
                self.log.debug("Not installing RPATH wrapper for non-existing command '%s'", cmd)

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

        # collect software install prefixes for dependencies
        roots = []
        for dep in deps:
            if dep.get('external_module', False):
                # for software names provided via external modules, install prefix may be unknown
                names = dep['external_module_metadata'].get('name', [])
                roots.extend([root for root in self.get_software_root(names) if root is not None])
            else:
                roots.extend(self.get_software_root(dep['name']))

        for root in roots:
            self.variables.append_subdirs("CPPFLAGS", root, subdirs=cpp_paths)
            self.variables.append_subdirs("LDFLAGS", root, subdirs=ld_paths)

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
        """Get compiler flag for a certain option."""
        return "-%s" % self.options.option(name)

    def toolchain_family(self):
        """Return toolchain family for this toolchain."""
        return self.TOOLCHAIN_FAMILY

    def comp_family(self):
        """ Return compiler family used in this toolchain (abstract method)."""
        raise NotImplementedError

    def blas_family(self):
        "Return type of BLAS library used in this toolchain, or 'None' if BLAS is not supported."
        return None

    def lapack_family(self):
        "Return type of LAPACK library used in this toolchain, or 'None' if LAPACK is not supported."
        return None

    def mpi_family(self):
        "Return type of MPI library used in this toolchain, or 'None' if MPI is not supported."
        return None

    def cleanup(self):
        """Clean up after using this toolchain"""
        pass
