# #
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
# #

"""
Easyconfig module that contains the EasyConfig class.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
:author: Alan O'Cais (Juelich Supercomputing Centre)
:author: Bart Oldeman (McGill University, Calcul Quebec, Compute Canada)
:author: Maxime Boissonneault (Universite Laval, Calcul Quebec, Compute Canada)
:author: Victor Holanda (CSCS, ETH Zurich)
"""

import copy
import difflib
import functools
import os
import re
from distutils.version import LooseVersion
from contextlib import contextmanager

import easybuild.tools.filetools as filetools
from easybuild.base import fancylogger
from easybuild.framework.easyconfig import MANDATORY
from easybuild.framework.easyconfig.constants import EXTERNAL_MODULE_MARKER
from easybuild.framework.easyconfig.default import DEFAULT_CONFIG
from easybuild.framework.easyconfig.format.convert import Dependency
from easybuild.framework.easyconfig.format.format import DEPENDENCY_PARAMETERS
from easybuild.framework.easyconfig.format.one import EB_FORMAT_EXTENSION, retrieve_blocks_in_spec
from easybuild.framework.easyconfig.format.yeb import YEB_FORMAT_EXTENSION, is_yeb_format
from easybuild.framework.easyconfig.licenses import EASYCONFIG_LICENSES_DICT
from easybuild.framework.easyconfig.parser import DEPRECATED_PARAMETERS, REPLACED_PARAMETERS
from easybuild.framework.easyconfig.parser import EasyConfigParser, fetch_parameters_from_easyconfig
from easybuild.framework.easyconfig.templates import TEMPLATE_CONSTANTS, TEMPLATE_NAMES_DYNAMIC, template_constant_dict
from easybuild.tools.build_log import EasyBuildError, print_warning, print_msg
from easybuild.tools.config import GENERIC_EASYBLOCK_PKG, LOCAL_VAR_NAMING_CHECK_ERROR, LOCAL_VAR_NAMING_CHECK_LOG
from easybuild.tools.config import LOCAL_VAR_NAMING_CHECK_WARN
from easybuild.tools.config import Singleton, build_option, get_module_naming_scheme
from easybuild.tools.filetools import convert_name, copy_file, create_index, decode_class_name, encode_class_name
from easybuild.tools.filetools import find_backup_name_candidate, find_easyconfigs, load_index
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.hooks import PARSE, load_hooks, run_hook
from easybuild.tools.module_naming_scheme.mns import DEVEL_MODULE_SUFFIX
from easybuild.tools.module_naming_scheme.utilities import avail_module_naming_schemes, det_full_ec_version
from easybuild.tools.module_naming_scheme.utilities import det_hidden_modname, is_valid_module_name
from easybuild.tools.modules import modules_tool
from easybuild.tools.py2vs3 import OrderedDict, create_base_metaclass, string_type
from easybuild.tools.systemtools import check_os_dependency, pick_dep_version
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME, is_system_toolchain
from easybuild.tools.toolchain.toolchain import TOOLCHAIN_CAPABILITIES, TOOLCHAIN_CAPABILITY_CUDA
from easybuild.tools.toolchain.utilities import get_toolchain, search_toolchain
from easybuild.tools.utilities import flatten, get_class_for, nub, quote_py_str, remove_unwanted_chars
from easybuild.tools.version import VERSION
from easybuild.toolchains.compiler.cuda import Cuda

_log = fancylogger.getLogger('easyconfig.easyconfig', fname=False)

# add license here to make it really MANDATORY (remove comment in default)
MANDATORY_PARAMS = ['name', 'version', 'homepage', 'description', 'toolchain']

# set of configure/build/install options that can be provided as lists for an iterated build
ITERATE_OPTIONS = ['builddependencies',
                   'preconfigopts', 'configopts', 'prebuildopts', 'buildopts', 'preinstallopts', 'installopts']

# name of easyconfigs archive subdirectory
EASYCONFIGS_ARCHIVE_DIR = '__archive__'

# prefix for names of local variables in easyconfig files
LOCAL_VAR_PREFIX = 'local_'


try:
    import autopep8
    HAVE_AUTOPEP8 = True
except ImportError as err:
    _log.warning("Failed to import autopep8, dumping easyconfigs with reformatting enabled will not work: %s", err)
    HAVE_AUTOPEP8 = False


_easyconfig_files_cache = {}
_easyconfigs_cache = {}
_path_indexes = {}


def handle_deprecated_or_replaced_easyconfig_parameters(ec_method):
    """Decorator to handle deprecated/replaced easyconfig parameters."""

    def new_ec_method(self, key, *args, **kwargs):
        """Check whether any replace easyconfig parameters are still used"""
        # map deprecated parameters to their replacements, issue deprecation warning(/error)
        if key in DEPRECATED_PARAMETERS:
            depr_key = key
            key, ver = DEPRECATED_PARAMETERS[depr_key]
            _log.deprecated("Easyconfig parameter '%s' is deprecated, use '%s' instead." % (depr_key, key), ver)
        if key in REPLACED_PARAMETERS:
            _log.nosupport("Easyconfig parameter '%s' is replaced by '%s'" % (key, REPLACED_PARAMETERS[key]), '2.0')
        return ec_method(self, key, *args, **kwargs)

    return new_ec_method


def is_local_var_name(name):
    """
    Determine whether provided variable name can be considered as the name of a local variable:

    One of the following suffices to be considered a name of a local variable:
    * name starts with 'local_' or '_'
    * name consists of a single letter
    * name is __builtins__ (which is always defined)
    """
    res = False
    if name.startswith(LOCAL_VAR_PREFIX) or name.startswith('_'):
        res = True
    # __builtins__ is always defined as a 'local' variables
    # single-letter local variable names are allowed (mainly for use in list comprehensions)
    # in Python 2, variables defined in list comprehensions leak to the outside (no longer the case in Python 3)
    elif name in ['__builtins__']:
        res = True
    # single letters are acceptable names for local variables
    elif re.match('^[a-zA-Z]$', name):
        res = True

    return res


def triage_easyconfig_params(variables, ec):
    """
    Triage supplied variables into known easyconfig parameters and other variables.

    Unknown easyconfig parameters that have a single-letter name, or of which the name starts with 'local_'
    are considered to be local variables.

    :param variables: dictionary with names/values of variables that should be triaged
    :param ec: dictionary with set of known easyconfig parameters

    :return: 2-tuple with dict of names/values for known easyconfig parameters + unknown (non-local) variables
    """

    # first make sure that none of the known easyconfig parameters have a name that makes it look like a local variable
    wrong_params = []
    for key in ec:
        if is_local_var_name(key):
            wrong_params.append(key)
    if wrong_params:
        raise EasyBuildError("Found %d easyconfig parameters that are considered local variables: %s",
                             len(wrong_params), ', '.join(sorted(wrong_params)))

    ec_params, unknown_keys = {}, []

    for key in variables:
        # validations are skipped, just set in the config
        if key in ec:
            ec_params[key] = variables[key]
            _log.debug("setting config option %s: value %s (type: %s)", key, ec_params[key], type(ec_params[key]))
        elif key in REPLACED_PARAMETERS:
            _log.nosupport("Easyconfig parameter '%s' is replaced by '%s'" % (key, REPLACED_PARAMETERS[key]), '2.0')

        # anything else is considered to be a local variable in the easyconfig file;
        # to catch mistakes (using unknown easyconfig parameters),
        # and to protect against using a local variable name that may later become a known easyconfig parameter,
        # we require that non-single letter names of local variables start with 'local_'
        elif is_local_var_name(key):
            _log.debug("Ignoring local variable '%s' (value: %s)", key, variables[key])

        else:
            unknown_keys.append(key)

    return ec_params, unknown_keys


def toolchain_hierarchy_cache(func):
    """Function decorator to cache (and retrieve cached) toolchain hierarchy queries."""
    cache = {}

    @functools.wraps(func)
    def cache_aware_func(toolchain, incl_capabilities=False):
        """Look up toolchain hierarchy in cache first, determine and cache it if not available yet."""
        cache_key = (toolchain['name'], toolchain['version'], incl_capabilities)

        # fetch from cache if available, cache it if it's not
        if cache_key in cache:
            _log.debug("Using cache to return hierarchy for toolchain %s: %s", str(toolchain), cache[cache_key])
            return cache[cache_key]
        else:
            toolchain_hierarchy = func(toolchain, incl_capabilities)
            cache[cache_key] = toolchain_hierarchy
            return cache[cache_key]

    # Expose clear method of cache to wrapped function
    cache_aware_func.clear = cache.clear

    return cache_aware_func


def det_subtoolchain_version(current_tc, subtoolchain_names, optional_toolchains, cands, incl_capabilities=False):
    """
    Returns unique version for subtoolchain, in tc dict.
    If there is no unique version:
    * use '' for system, if system is not skipped.
    * return None for skipped subtoolchains, that is,
      optional toolchains or system toolchain without add_system_to_minimal_toolchains.
    * in all other cases, raises an exception.
    """
    # init with "skipped"
    subtoolchain_version = None

    # ensure we always have a tuple of alternative subtoolchain names, which makes things easier below
    if isinstance(subtoolchain_names, string_type):
        subtoolchain_names = (subtoolchain_names,)

    system_subtoolchain = False

    for subtoolchain_name in subtoolchain_names:

        uniq_subtc_versions = set([subtc['version'] for subtc in cands if subtc['name'] == subtoolchain_name])

        # system toolchain: bottom of the hierarchy
        if is_system_toolchain(subtoolchain_name):
            add_system_to_minimal_toolchains = build_option('add_system_to_minimal_toolchains')
            if not add_system_to_minimal_toolchains and build_option('add_dummy_to_minimal_toolchains'):
                depr_msg = "Use --add-system-to-minimal-toolchains instead of --add-dummy-to-minimal-toolchains"
                _log.deprecated(depr_msg, '5.0')
                add_system_to_minimal_toolchains = True

            system_subtoolchain = True

            if add_system_to_minimal_toolchains and not incl_capabilities:
                subtoolchain_version = ''
        elif len(uniq_subtc_versions) == 1:
            subtoolchain_version = list(uniq_subtc_versions)[0]
        elif len(uniq_subtc_versions) > 1:
            raise EasyBuildError("Multiple versions of %s found in dependencies of toolchain %s: %s",
                                 subtoolchain_name, current_tc['name'], ', '.join(sorted(uniq_subtc_versions)))

        if subtoolchain_version is not None:
            break

    if not system_subtoolchain and subtoolchain_version is None:
        if not all(n in optional_toolchains for n in subtoolchain_names):
            subtoolchain_names = ' or '.join(subtoolchain_names)
            # raise error if the subtoolchain considered now is not optional
            raise EasyBuildError("No version found for subtoolchain %s in dependencies of %s",
                                 subtoolchain_names, current_tc['name'])

    return subtoolchain_version


@toolchain_hierarchy_cache
def get_toolchain_hierarchy(parent_toolchain, incl_capabilities=False):
    r"""
    Determine list of subtoolchains for specified parent toolchain.
    Result starts with the most minimal subtoolchains first, ends with specified toolchain.

    The system toolchain is considered the most minimal subtoolchain only if the add_system_to_minimal_toolchains
    build option is enabled.

    The most complex hierarchy we have now is goolfc which works as follows:

        goolfc
        /     \
     gompic    golfc(*)
          \    /   \      (*) optional toolchains, not compulsory for backwards compatibility
          gcccuda golf(*)
              \   /
               GCC
              /  |
      GCCcore(*) |
              \  |
             (system: only considered if --add-system-to-minimal-toolchains configuration option is enabled)

    :param parent_toolchain: dictionary with name/version of parent toolchain
    :param incl_capabilities: also register toolchain capabilities in result
    """
    # obtain list of all possible subtoolchains
    _, all_tc_classes = search_toolchain('')
    subtoolchains = dict((tc_class.NAME, getattr(tc_class, 'SUBTOOLCHAIN', None)) for tc_class in all_tc_classes)
    optional_toolchains = set(tc_class.NAME for tc_class in all_tc_classes if getattr(tc_class, 'OPTIONAL', False))
    composite_toolchains = set(tc_class.NAME for tc_class in all_tc_classes if len(tc_class.__bases__) > 1)

    # the parent toolchain is at the top of the hierarchy,
    # we need a copy so that adding capabilities (below) doesn't affect the original object
    toolchain_hierarchy = [copy.copy(parent_toolchain)]
    # use a queue to handle a breadth-first-search of the hierarchy,
    # which is required to take into account the potential for multiple subtoolchains
    bfs_queue = [parent_toolchain]
    visited = set()

    while bfs_queue:
        current_tc = bfs_queue.pop()
        current_tc_name, current_tc_version = current_tc['name'], current_tc['version']
        subtoolchain_names = subtoolchains[current_tc_name]
        # if current toolchain has no subtoolchains, consider next toolchain in queue
        if subtoolchain_names is None:
            continue
        # make sure we always have a list of subtoolchains, even if there's only one
        if not isinstance(subtoolchain_names, list):
            subtoolchain_names = [subtoolchain_names]
        # grab the easyconfig of the current toolchain and search the dependencies for a version of the subtoolchain
        path = robot_find_easyconfig(current_tc_name, current_tc_version)
        if path is None:
            raise EasyBuildError("Could not find easyconfig for %s toolchain version %s",
                                 current_tc_name, current_tc_version)

        # parse the easyconfig
        parsed_ec = process_easyconfig(path, validate=False)[0]

        # search for version of the subtoolchain in dependencies
        # considers deps + toolchains of deps + deps of deps + toolchains of deps of deps
        # consider both version and versionsuffix for dependencies
        cands = []
        for dep in parsed_ec['ec'].dependencies():
            # skip dependencies that are marked as external modules
            if dep['external_module']:
                continue

            # include dep and toolchain of dep as candidates
            cands.extend([
                {'name': dep['name'], 'version': dep['version'] + dep['versionsuffix']},
                dep['toolchain'],
            ])

            # find easyconfig file for this dep and parse it
            ecfile = robot_find_easyconfig(dep['name'], det_full_ec_version(dep))
            if ecfile is None:
                raise EasyBuildError("Could not find easyconfig for dependency %s with version %s",
                                     dep['name'], det_full_ec_version(dep))
            easyconfig = process_easyconfig(ecfile, validate=False)[0]['ec']

            # include deps and toolchains of deps of this dep, but skip dependencies marked as external modules
            for depdep in easyconfig.dependencies():
                if depdep['external_module']:
                    continue

                cands.append({'name': depdep['name'], 'version': depdep['version'] + depdep['versionsuffix']})
                cands.append(depdep['toolchain'])

        for dep in subtoolchain_names:
            # try to find subtoolchains with the same version as the parent
            # only do this for composite toolchains, not single-compiler toolchains, whose
            # versions match those of the component instead of being e.g. "2018a".
            if dep in composite_toolchains:
                ecfile = robot_find_easyconfig(dep, current_tc_version)
                if ecfile is not None:
                    cands.append({'name': dep, 'version': current_tc_version})

        # only retain candidates that match subtoolchain names
        cands = [c for c in cands if any(c['name'] == x or c['name'] in x for x in subtoolchain_names)]

        for subtoolchain_name in subtoolchain_names:
            subtoolchain_version = det_subtoolchain_version(current_tc, subtoolchain_name, optional_toolchains, cands,
                                                            incl_capabilities=incl_capabilities)

            # narrow down alternative subtoolchain names to a single one, based on the selected version
            if isinstance(subtoolchain_name, tuple):
                subtoolchain_name = [cand['name'] for cand in cands if cand['version'] == subtoolchain_version][0]

            # add to hierarchy and move to next
            if subtoolchain_version is not None and subtoolchain_name not in visited:
                tc = {'name': subtoolchain_name, 'version': subtoolchain_version}
                toolchain_hierarchy.insert(0, tc)
                bfs_queue.insert(0, tc)
                visited.add(subtoolchain_name)

    # also add toolchain capabilities
    if incl_capabilities:
        for toolchain in toolchain_hierarchy:
            toolchain_class, _ = search_toolchain(toolchain['name'])
            tc = toolchain_class(version=toolchain['version'])
            for capability in TOOLCHAIN_CAPABILITIES:
                # cuda is the special case which doesn't have a family attribute
                if capability == TOOLCHAIN_CAPABILITY_CUDA:
                    # use None rather than False, useful to have it consistent with the rest
                    toolchain[capability] = isinstance(tc, Cuda) or None
                elif hasattr(tc, capability):
                    toolchain[capability] = getattr(tc, capability)()

    _log.info("Found toolchain hierarchy for toolchain %s: %s", parent_toolchain, toolchain_hierarchy)
    return toolchain_hierarchy


@contextmanager
def disable_templating(ec):
    """Temporarily disable templating on the given EasyConfig

    Usage:
        with disable_templating(ec):
            # Do what you want without templating
        # Templating set to previous value
    """
    _log.deprecated("disable_templating(ec) was replaced by ec.disable_templating()", '5.0')
    with ec.disable_templating() as old_value:
        yield old_value


class EasyConfig(object):
    """
    Class which handles loading, reading, validation of easyconfigs
    """

    def __init__(self, path, extra_options=None, build_specs=None, validate=True, hidden=None, rawtxt=None,
                 auto_convert_value_types=True, local_var_naming_check=None):
        """
        initialize an easyconfig.
        :param path: path to easyconfig file to be parsed (ignored if rawtxt is specified)
        :param extra_options: dictionary with extra variables that can be set for this specific instance
        :param build_specs: dictionary of build specifications (see EasyConfig class, default: {})
        :param validate: indicates whether validation should be performed (note: combined with 'validate' build option)
        :param hidden: indicate whether corresponding module file should be installed hidden ('.'-prefixed)
        :param rawtxt: raw contents of easyconfig file
        :param auto_convert_value_types: indicates wether types of easyconfig values should be automatically converted
                                         in case they are wrong
        :param local_var_naming_check: mode to use when checking if local variables use the recommended naming scheme
        """
        self.template_values = None
        self.enable_templating = True  # a boolean to control templating

        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        if path is not None and not os.path.isfile(path):
            raise EasyBuildError("EasyConfig __init__ expected a valid path")

        # read easyconfig file contents (or use provided rawtxt), so it can be passed down to avoid multiple re-reads
        self.path = None
        if rawtxt is None:
            self.path = path
            self.rawtxt = read_file(path)
            self.log.debug("Raw contents from supplied easyconfig file %s: %s", path, self.rawtxt)
        else:
            self.rawtxt = rawtxt
            self.log.debug("Supplied raw easyconfig contents: %s" % self.rawtxt)

        # constructing easyconfig parser object includes a "raw" parse,
        # which serves as a check to see whether supplied easyconfig file is an actual easyconfig...
        self.log.info("Performing quick parse to check for valid easyconfig file...")
        self.parser = EasyConfigParser(filename=self.path, rawcontent=self.rawtxt,
                                       auto_convert_value_types=auto_convert_value_types)

        self.modules_tool = modules_tool()

        # use legacy module classes as default
        self.valid_module_classes = build_option('valid_module_classes')
        if self.valid_module_classes is not None:
            self.log.info("Obtained list of valid module classes: %s" % self.valid_module_classes)

        self._config = copy.deepcopy(DEFAULT_CONFIG)

        # obtain name and easyblock specifications from raw easyconfig contents
        self.software_name, self.easyblock = fetch_parameters_from_easyconfig(self.rawtxt, ['name', 'easyblock'])

        # determine line of extra easyconfig parameters
        if extra_options is None:
            easyblock_class = get_easyblock_class(self.easyblock, name=self.software_name)
            self.extra_options = easyblock_class.extra_options()
        else:
            self.extra_options = extra_options

        if not isinstance(self.extra_options, dict):
            tup = (type(self.extra_options), self.extra_options)
            self.log.nosupport("extra_options return value should be of type 'dict', found '%s': %s" % tup, '2.0')

        self.mandatory = MANDATORY_PARAMS[:]

        # deep copy to make sure self.extra_options remains unchanged
        self.extend_params(copy.deepcopy(self.extra_options))

        # set valid stops
        self.valid_stops = build_option('valid_stops')
        self.log.debug("List of valid stops obtained: %s" % self.valid_stops)

        # store toolchain
        self._toolchain = None

        self.validations = {
            'moduleclass': self.valid_module_classes,
            'stop': self.valid_stops,
        }

        self.external_modules_metadata = build_option('external_modules_metadata')

        # list of all options to iterate over
        self.iterate_options = []
        self.iterating = False

        # parse easyconfig file
        self.build_specs = build_specs
        self.parse()

        self.local_var_naming(local_var_naming_check)

        # check whether this easyconfig file is deprecated, and act accordingly if so
        self.check_deprecated(self.path)

        # perform validations
        self.validation = build_option('validate') and validate
        if self.validation:
            self.validate(check_osdeps=build_option('check_osdeps'))

        # filter hidden dependencies from list of dependencies
        self.filter_hidden_deps()

        self._all_dependencies = None

        # keep track of whether the generated module file should be hidden
        if hidden is None:
            hidden = self['hidden'] or build_option('hidden')
        self.hidden = hidden

        # set installdir/module info
        mns = ActiveMNS()
        self.full_mod_name = mns.det_full_module_name(self)
        self.short_mod_name = mns.det_short_module_name(self)
        self.mod_subdir = mns.det_module_subdir(self)

        self.set_default_module = False

        self.software_license = None

    @contextmanager
    def disable_templating(self):
        """Temporarily disable templating on the given EasyConfig

        Usage:
            with ec.disable_templating():
                # Do what you want without templating
            # Templating set to previous value
        """
        old_enable_templating = self.enable_templating
        self.enable_templating = False
        try:
            yield old_enable_templating
        finally:
            self.enable_templating = old_enable_templating

    def __str__(self):
        """Return a string representation of this EasyConfig instance"""
        if self.path:
            return '%s EasyConfig @ %s' % (self.name, self.path)
        else:
            return 'Raw %s EasyConfig' % self.name

    def filename(self):
        """Determine correct filename for this easyconfig file."""

        if is_yeb_format(self.path, self.rawtxt):
            ext = YEB_FORMAT_EXTENSION
        else:
            ext = EB_FORMAT_EXTENSION

        return '%s-%s%s' % (self.name, det_full_ec_version(self), ext)

    def extend_params(self, extra, overwrite=True):
        """Extend list of known parameters via provided list of extra easyconfig parameters."""

        self.log.debug("Extending list of known easyconfig parameters with: %s", ' '.join(extra.keys()))

        if overwrite:
            self._config.update(extra)
        else:
            for key in extra:
                if key not in self._config:
                    self._config[key] = extra[key]
                    self.log.debug("Added new easyconfig parameter: %s", key)
                else:
                    self.log.debug("Easyconfig parameter %s already known, not overwriting", key)

        # extend mandatory keys
        for key, value in extra.items():
            if value[2] == MANDATORY:
                self.mandatory.append(key)
        self.log.debug("Updated list of mandatory easyconfig parameters: %s", self.mandatory)

    def copy(self, validate=None):
        """
        Return a copy of this EasyConfig instance.
        """
        if validate is None:
            validate = self.validation

        # create a new EasyConfig instance
        ec = EasyConfig(self.path, validate=validate, hidden=self.hidden, rawtxt=self.rawtxt)
        # take a copy of the actual config dictionary (which already contains the extra options)
        ec._config = copy.deepcopy(self._config)
        # since rawtxt is defined, self.path may not get inherited, make sure it does
        if self.path:
            ec.path = self.path

        # also copy template values, since re-generating them may not give the same set of template values straight away
        ec.template_values = copy.deepcopy(self.template_values)

        return ec

    def update(self, key, value, allow_duplicate=True):
        """
        Update an easyconfig parameter with the specified value (i.e. append to it).
        Note: For dictionary easyconfig parameters, 'allow_duplicate' is ignored (since it's meaningless).
        """
        if isinstance(value, string_type):
            inval = [value]
        elif isinstance(value, (list, dict, tuple)):
            inval = value
        else:
            msg = "Can't update configuration value for %s, because the attempted"
            msg += " update value, '%s', is not a string, list, tuple or dictionary."
            raise EasyBuildError(msg, key, value)

        # For easyconfig parameters that are dictionaries, input value must also be a dictionary
        if isinstance(self[key], dict) and not isinstance(value, dict):
            msg = "Can't update configuration value for %s, because the attempted"
            msg += "update value (%s), is not a dictionary (type: %s)."
            raise EasyBuildError(msg, key, value, type(value))

        # Grab current parameter value so we can modify it
        param_value = copy.deepcopy(self[key])

        if isinstance(param_value, string_type):
            for item in inval:
                # re.search: only add value to string if it's not there yet (surrounded by whitespace)
                if allow_duplicate or (not re.search(r'(^|\s+)%s(\s+|$)' % re.escape(item), param_value)):
                    param_value = param_value + ' %s ' % item

        elif isinstance(param_value, (list, tuple)):
            # make sure we have a list value so we can just append to it
            param_value = list(param_value)
            for item in inval:
                if allow_duplicate or item not in param_value:
                    param_value.append(item)
            # cast back to tuple if original value was a tuple
            if isinstance(self[key], tuple):
                param_value = tuple(param_value)

        elif isinstance(param_value, dict):
            param_value.update(inval)
        else:
            msg = "Can't update configuration value for %s, because it's not a string, list, tuple or dictionary."
            raise EasyBuildError(msg, key)

        # Overwrite easyconfig parameter value with updated value, preserving type
        self[key] = param_value

    def set_keys(self, params):
        """
        Set keys in this EasyConfig instance based on supplied easyconfig parameter values.

        If any unknown easyconfig parameters are encountered here, an error is raised.

        :param params: a dict value with names/values of easyconfig parameters to set
        """
        # disable templating when setting easyconfig parameters
        # required to avoid problems with values that need more parsing to be done (e.g. dependencies)
        with self.disable_templating():
            for key in sorted(params.keys()):
                # validations are skipped, just set in the config
                if key in self._config.keys():
                    self[key] = params[key]
                    self.log.info("setting easyconfig parameter %s: value %s (type: %s)",
                                  key, self[key], type(self[key]))
                else:
                    raise EasyBuildError("Unknown easyconfig parameter: %s (value '%s')", key, params[key])

    def parse(self):
        """
        Parse the file and set options
        mandatory requirements are checked here
        """
        if self.build_specs is None:
            arg_specs = {}
        elif isinstance(self.build_specs, dict):
            # build a new dictionary with only the expected keys, to pass as named arguments to get_config_dict()
            arg_specs = self.build_specs
        else:
            raise EasyBuildError("Specifications should be specified using a dictionary, got %s",
                                 type(self.build_specs))
        self.log.debug("Obtained specs dict %s" % arg_specs)

        self.log.info("Parsing easyconfig file %s with rawcontent: %s", self.path, self.rawtxt)
        self.parser.set_specifications(arg_specs)
        ec_vars = self.parser.get_config_dict()
        self.log.debug("Parsed easyconfig as a dictionary: %s" % ec_vars)

        # make sure all mandatory parameters are defined
        # this includes both generic mandatory parameters and software-specific parameters defined via extra_options
        missing_mandatory_keys = [key for key in self.mandatory if key not in ec_vars]
        if missing_mandatory_keys:
            raise EasyBuildError("mandatory parameters not provided in %s: %s", self.path, missing_mandatory_keys)

        # provide suggestions for typos. Local variable names are excluded from this check
        possible_typos = [(key, difflib.get_close_matches(key.lower(), self._config.keys(), 1, 0.85))
                          for key in ec_vars if not is_local_var_name(key) and key not in self]

        typos = [(key, guesses[0]) for (key, guesses) in possible_typos if len(guesses) == 1]
        if typos:
            raise EasyBuildError("You may have some typos in your easyconfig file: %s",
                                 ', '.join(["%s -> %s" % typo for typo in typos]))

        # set keys in current EasyConfig instance based on dict obtained by parsing easyconfig file
        known_ec_params, self.unknown_keys = triage_easyconfig_params(ec_vars, self._config)

        self.set_keys(known_ec_params)

        # templating is disabled when parse_hook is called to allow for easy updating of mutable easyconfig parameters
        # (see also comment in resolve_template)
        with self.disable_templating():
            # if any lists of dependency versions are specified over which we should iterate,
            # deal with them now, before calling parse hook, parsing of dependencies & iterative easyconfig parameters
            self.handle_multi_deps()

            parse_hook_msg = None
            if self.path:
                parse_hook_msg = "Running %s hook for %s..." % (PARSE, os.path.basename(self.path))

            # trigger parse hook
            hooks = load_hooks(build_option('hooks'))
            run_hook(PARSE, hooks, args=[self], msg=parse_hook_msg)

            # parse dependency specifications
            # it's important that templating is still disabled at this stage!
            self.log.info("Parsing dependency specifications...")

            def remove_false_versions(deps):
                return [dep for dep in deps if not (isinstance(dep, dict) and dep['version'] is False)]

            self['dependencies'] = remove_false_versions(self._parse_dependency(dep) for dep in self['dependencies'])
            self['hiddendependencies'] = remove_false_versions(self._parse_dependency(dep, hidden=True) for dep in
                                                               self['hiddendependencies'])

            # need to take into account that builddependencies may need to be iterated over,
            # i.e. when the value is a list of lists of tuples
            builddeps = self['builddependencies']
            if builddeps and all(isinstance(x, (list, tuple)) for b in builddeps for x in b):
                self.iterate_options.append('builddependencies')
                builddeps = [[self._parse_dependency(dep, build_only=True) for dep in x] for x in builddeps]
            else:
                builddeps = [self._parse_dependency(dep, build_only=True) for dep in builddeps]
            self['builddependencies'] = remove_false_versions(builddeps)

            # keep track of parsed multi deps, they'll come in handy during sanity check & module steps...
            self.multi_deps = self.get_parsed_multi_deps()

        # update templating dictionary
        self.generate_template_values()

        # finalize dependencies w.r.t. minimal toolchains & module names
        self._finalize_dependencies()

        # indicate that this is a parsed easyconfig
        self._config['parsed'] = [True, "This is a parsed easyconfig", "HIDDEN"]

    def local_var_naming(self, local_var_naming_check):
        """Deal with local variables that do not follow the recommended naming scheme (if any)."""

        if local_var_naming_check is None:
            local_var_naming_check = build_option('local_var_naming_check')

        if self.unknown_keys:
            cnt = len(self.unknown_keys)
            if self.path:
                in_fn = "in %s" % os.path.basename(self.path)
            else:
                in_fn = ''
            unknown_keys_msg = ', '.join(sorted(self.unknown_keys))

            msg = "Use of %d unknown easyconfig parameters detected %s: %s\n" % (cnt, in_fn, unknown_keys_msg)
            msg += "If these are just local variables please rename them to start with '%s', " % LOCAL_VAR_PREFIX
            msg += "or try using --fix-deprecated-easyconfigs to do this automatically.\nFor more information, see "
            msg += "https://easybuild.readthedocs.io/en/latest/Easyconfig-files-local-variables.html ."

            # always log a warning if local variable that don't follow recommended naming scheme are found
            self.log.warning(msg)

            if local_var_naming_check == LOCAL_VAR_NAMING_CHECK_ERROR:
                raise EasyBuildError(msg)
            elif local_var_naming_check == LOCAL_VAR_NAMING_CHECK_WARN:
                print_warning(msg, silent=build_option('silent'))
            elif local_var_naming_check != LOCAL_VAR_NAMING_CHECK_LOG:
                raise EasyBuildError("Unknown mode for checking local variable names: %s", local_var_naming_check)

    def check_deprecated(self, path):
        """Check whether this easyconfig file is deprecated."""

        depr_msgs = []

        deprecated = self['deprecated']
        if deprecated:
            if isinstance(deprecated, string_type):
                depr_msgs.append("easyconfig file '%s' is marked as deprecated:\n%s\n" % (path, deprecated))
            else:
                raise EasyBuildError("Wrong type for value of 'deprecated' easyconfig parameter: %s", type(deprecated))

        if self.toolchain.is_deprecated():
            depr_msgs.append("toolchain '%(name)s/%(version)s' is marked as deprecated" % self['toolchain'])

        if depr_msgs:
            depr_msg = ', '.join(depr_msgs)

            depr_maj_ver = int(str(VERSION).split('.')[0]) + 1
            depr_ver = '%s.0' % depr_maj_ver

            more_info_depr_ec = " (see also http://easybuild.readthedocs.org/en/latest/Deprecated-easyconfigs.html)"

            self.log.deprecated(depr_msg, depr_ver, more_info=more_info_depr_ec, silent=build_option('silent'))

    def validate(self, check_osdeps=True):
        """
        Validate this easyonfig
        - ensure certain easyconfig parameters are set to a known value (see self.validations)
        - check OS dependencies
        - check license
        """
        self.log.info("Validating easyconfig")
        for attr in self.validations:
            self._validate(attr, self.validations[attr])

        if check_osdeps:
            self.log.info("Checking OS dependencies")
            self.validate_os_deps()
        else:
            self.log.info("Not checking OS dependencies")

        self.log.info("Checking skipsteps")
        if not isinstance(self._config['skipsteps'][0], (list, tuple,)):
            raise EasyBuildError('Invalid type for skipsteps. Allowed are list or tuple, got %s (%s)',
                                 type(self._config['skipsteps'][0]), self._config['skipsteps'][0])

        self.log.info("Checking build option lists")
        self.validate_iterate_opts_lists()

        self.log.info("Checking licenses")
        self.validate_license()

    def validate_license(self):
        """Validate the license"""
        lic = self['software_license']
        if lic is None:
            # when mandatory, remove this possibility
            if 'software_license' in self.mandatory:
                raise EasyBuildError("Software license is mandatory, but 'software_license' is undefined")
        elif lic in EASYCONFIG_LICENSES_DICT:
            # create License instance
            self.software_license = EASYCONFIG_LICENSES_DICT[lic]()
        else:
            known_licenses = ', '.join(sorted(EASYCONFIG_LICENSES_DICT.keys()))
            raise EasyBuildError("Invalid license %s (known licenses: %s)", lic, known_licenses)

        # TODO, when GROUP_SOURCE and/or GROUP_BINARY is True
        #  check the owner of source / binary (must match 'group' parameter from easyconfig)

        return True

    def validate_os_deps(self):
        """
        validate presence of OS dependencies
        osdependencies should be a single list
        """
        not_found = []
        for dep in self['osdependencies']:
            # make sure we have a tuple
            if isinstance(dep, string_type):
                dep = (dep,)
            elif not isinstance(dep, tuple):
                raise EasyBuildError("Non-tuple value type for OS dependency specification: %s (type %s)",
                                     dep, type(dep))

            if not any(check_os_dependency(cand_dep) for cand_dep in dep):
                not_found.append(dep)

        if not_found:
            raise EasyBuildError("One or more OS dependencies were not found: %s", not_found)
        else:
            self.log.info("OS dependencies ok: %s" % self['osdependencies'])

        return True

    def validate_iterate_opts_lists(self):
        """
        Configure/build/install options specified as lists should have same length.
        """

        # configure/build/install options may be lists, in case of an iterated build
        # when lists are used, they should be all of same length
        # list of length 1 are treated as if it were strings in EasyBlock
        opt_counts = []
        for opt in ITERATE_OPTIONS:

            # only when builddependencies is a list of lists are we iterating over them
            if opt == 'builddependencies' and not all(isinstance(e, list) for e in self.get_ref(opt)):
                continue

            opt_value = self.get(opt, None, resolve=False)
            # anticipate changes in available easyconfig parameters (e.g. makeopts -> buildopts?)
            if opt_value is None:
                raise EasyBuildError("%s not available in self.cfg (anymore)?!", opt)

            # keep track of list, supply first element as first option to handle
            if isinstance(opt_value, (list, tuple)):
                opt_counts.append((opt, len(opt_value)))

        # make sure that options that specify lists have the same length
        list_opt_lengths = [length for (opt, length) in opt_counts if length > 1]
        if len(nub(list_opt_lengths)) > 1:
            raise EasyBuildError("Build option lists for iterated build should have same length: %s", opt_counts)

        return True

    def start_iterating(self):
        """Start iterative mode."""

        for opt in ITERATE_OPTIONS:
            # builddpendencies is already handled, see __init__
            if opt == 'builddependencies':
                continue

            # list of values indicates that this is a value to iterate over
            if isinstance(self[opt], (list, tuple)):
                self.iterate_options.append(opt)

        # keep track of when we're iterating (used by builddependencies())
        self.iterating = True

    def stop_iterating(self):
        """Stop iterative mode."""

        self.iterating = False

    def filter_hidden_deps(self):
        """
        Replace dependencies by hidden dependencies in list of (build) dependencies, where appropriate.
        """
        faulty_deps = []

        # obtain reference to original lists, so their elements can be changed in place
        deps = dict([(key, self.get_ref(key)) for key in ['dependencies', 'builddependencies', 'hiddendependencies']])

        if 'builddependencies' in self.iterate_options:
            deplists = copy.deepcopy(deps['builddependencies'])
        else:
            deplists = [deps['builddependencies']]

        deplists.append(deps['dependencies'])

        for hidden_idx, hidden_dep in enumerate(deps['hiddendependencies']):
            hidden_mod_name = ActiveMNS().det_full_module_name(hidden_dep)
            visible_mod_name = ActiveMNS().det_full_module_name(hidden_dep, force_visible=True)

            # replace (build) dependencies with their equivalent hidden (build) dependency (if any)
            replaced = False
            for deplist in deplists:
                for idx, dep in enumerate(deplist):
                    dep_mod_name = dep['full_mod_name']
                    if dep_mod_name in [visible_mod_name, hidden_mod_name]:

                        # track whether this hidden dep is listed as a build dep
                        hidden_dep = deps['hiddendependencies'][hidden_idx]
                        hidden_dep['build_only'] = dep['build_only']

                        # actual replacement
                        deplist[idx] = hidden_dep

                        replaced = True
                        if dep_mod_name == visible_mod_name:
                            msg = "Replaced (build)dependency matching hidden dependency %s"
                        else:
                            msg = "Hidden (build)dependency %s is already marked to be installed as a hidden module"
                        self.log.debug(msg, hidden_dep)

            if not replaced:
                # hidden dependencies must also be included in list of dependencies;
                # this is done to try and make easyconfigs portable w.r.t. site-specific policies with minimal effort,
                # i.e. by simply removing the 'hiddendependencies' specification
                self.log.warning("Hidden dependency %s not in list of (build)dependencies", visible_mod_name)
                faulty_deps.append(visible_mod_name)

        if faulty_deps:
            dep_mod_names = [dep['full_mod_name'] for dep in self['dependencies'] + self['builddependencies']]
            raise EasyBuildError("Hidden deps with visible module names %s not in list of (build)dependencies: %s",
                                 faulty_deps, dep_mod_names)

    def parse_version_range(self, version_spec):
        """Parse provided version specification as a version range."""
        res = {}
        range_sep = ':'  # version range separator (e.g. ]1.0:2.0])

        if range_sep in version_spec:
            # remove range characters ('[' and ']') to obtain lower/upper version limits
            version_limits = re.sub(r'[\[\]]', '', version_spec).split(range_sep)
            if len(version_limits) == 2:
                res['lower'], res['upper'] = version_limits
                if res['lower'] and res['upper'] and LooseVersion(res['lower']) > LooseVersion(res['upper']):
                    raise EasyBuildError("Incorrect version range, found lower limit > higher limit: %s", version_spec)
            else:
                raise EasyBuildError("Incorrect version range, expected lower/upper limit: %s", version_spec)

            res['excl_lower'] = version_spec[0] == ']'
            res['excl_upper'] = version_spec[-1] == '['

        else:  # strict version spec (not a range)
            res['lower'] = res['upper'] = version_spec
            res['excl_lower'] = res['excl_upper'] = False

        return res

    def parse_filter_deps(self):
        """Parse specifications for which dependencies should be filtered."""
        res = {}

        separator = '='
        for filter_dep_spec in build_option('filter_deps') or []:
            if separator in filter_dep_spec:
                dep_specs = filter_dep_spec.split(separator)
                if len(dep_specs) == 2:
                    dep_name, dep_version_spec = dep_specs
                else:
                    raise EasyBuildError("Incorrect specification for dependency to filter: %s", filter_dep_spec)

                res[dep_name] = self.parse_version_range(dep_version_spec)
            else:
                res[filter_dep_spec] = {'always_filter': True}

        return res

    def dep_is_filtered(self, dep, filter_deps_specs):
        """Returns True if a dependency is filtered according to the filter_deps_specs"""
        filter_dep = False
        if dep['name'] in filter_deps_specs:
            filter_spec = filter_deps_specs[dep['name']]

            if filter_spec.get('always_filter', False):
                filter_dep = True
            else:
                version = LooseVersion(dep['version'])
                lower = LooseVersion(filter_spec['lower']) if filter_spec['lower'] else None
                upper = LooseVersion(filter_spec['upper']) if filter_spec['upper'] else None

                # assume dep is filtered before checking version range
                filter_dep = True

                # if version is lower than lower limit: no filtering
                if lower:
                    if version < lower or (filter_spec['excl_lower'] and version == lower):
                        filter_dep = False

                # if version is higher than upper limit: no filtering
                if upper:
                    if version > upper or (filter_spec['excl_upper'] and version == upper):
                        filter_dep = False

        return filter_dep

    def filter_deps(self, deps):
        """Filter dependencies according to 'filter-deps' configuration setting."""

        retained_deps = []
        filter_deps_specs = self.parse_filter_deps()
        for dep in deps:
            # figure out whether this dependency should be filtered
            if self.dep_is_filtered(dep, filter_deps_specs):
                self.log.info("filtered out dependency %s", dep)
            else:
                retained_deps.append(dep)

        return retained_deps

    def dependencies(self, build_only=False):
        """
        Returns an array of parsed dependencies (after filtering, if requested)
        dependency = {'name': '', 'version': '', 'system': (False|True), 'versionsuffix': '', 'toolchain': ''}
        Iterable builddependencies are flattened when not iterating.

        :param build_only: only return build dependencies, discard others
        """
        deps = self.builddependencies()

        if not build_only:
            # use += rather than .extend to get a new list rather than updating list of build deps in place...
            deps += self['dependencies']

        # if filter-deps option is provided we "clean" the list of dependencies for
        # each processed easyconfig to remove the unwanted dependencies
        self.log.debug("Dependencies BEFORE filtering: %s", deps)

        retained_deps = self.filter_deps(deps)
        self.log.debug("Dependencies AFTER filtering: %s", retained_deps)

        return retained_deps

    def builddependencies(self):
        """
        Return a flat list of the parsed build dependencies
        When builddependencies are iterable they are flattened lists with
        duplicates removed outside of the iterating process, because the callers
        want simple lists.
        """
        builddeps = self['builddependencies']

        if 'builddependencies' in self.iterate_options and not self.iterating:
            # flatten and remove duplicates (can't use 'nub', since dict values are not hashable)
            all_builddeps = flatten(builddeps)
            builddeps = []
            for dep in all_builddeps:
                if dep not in builddeps:
                    builddeps.append(dep)

        return builddeps

    @property
    def name(self):
        """
        returns name
        """
        return self['name']

    @property
    def version(self):
        """
        returns version
        """
        return self['version']

    @property
    def toolchain(self):
        """
        returns the Toolchain used
        """
        if self._toolchain is None:
            # provide list of (direct) toolchain dependencies (name & version), if easyconfig can be found for toolchain
            tcdeps = None
            tcname, tcversion = self['toolchain']['name'], self['toolchain']['version']

            if not is_system_toolchain(tcname):
                tc_ecfile = robot_find_easyconfig(tcname, tcversion)
                if tc_ecfile is None:
                    self.log.debug("No easyconfig found for toolchain %s version %s, can't determine dependencies",
                                   tcname, tcversion)
                else:
                    self.log.debug("Found easyconfig for toolchain %s version %s: %s", tcname, tcversion, tc_ecfile)
                    tc_ec = process_easyconfig(tc_ecfile)[0]
                    tcdeps = tc_ec['ec'].dependencies()
                    self.log.debug("Toolchain dependencies based on easyconfig: %s", tcdeps)

            self._toolchain = get_toolchain(self['toolchain'], self['toolchainopts'],
                                            mns=ActiveMNS(), tcdeps=tcdeps, modtool=self.modules_tool)
            tc_dict = self._toolchain.as_dict()
            self.log.debug("Initialized toolchain: %s (opts: %s)" % (tc_dict, self['toolchainopts']))
        return self._toolchain

    @property
    def all_dependencies(self):
        """Return list of all dependencies, incl. hidden/build deps & toolchain, but excluding filtered deps."""
        if self._all_dependencies is None:
            self.log.debug("Composing list of all dependencies (incl. toolchain)")
            self._all_dependencies = copy.deepcopy(self.dependencies())
            if not is_system_toolchain(self['toolchain']['name']):
                self._all_dependencies.append(self.toolchain.as_dict())

        return self._all_dependencies

    def dump(self, fp, always_overwrite=True, backup=False, explicit_toolchains=False):
        """
        Dump this easyconfig to file, with the given filename.

        :param always_overwrite: overwrite existing file at specified location without use of --force
        :param backup: create backup of existing file before overwriting it
        """
        # templated values should be dumped unresolved
        with self.disable_templating():
            # build dict of default values
            default_values = dict([(key, DEFAULT_CONFIG[key][0]) for key in DEFAULT_CONFIG])
            default_values.update(dict([(key, self.extra_options[key][0]) for key in self.extra_options]))

            self.generate_template_values()
            templ_const = dict([(quote_py_str(const[1]), const[0]) for const in TEMPLATE_CONSTANTS])

            # create reverse map of templates, to inject template values where possible
            # longer template values are considered first, shorter template keys get preference over longer ones
            sorted_keys = sorted(self.template_values, key=lambda k: (len(self.template_values[k]), -len(k)),
                                 reverse=True)
            templ_val = OrderedDict([])
            for key in sorted_keys:
                # shortest template 'key' is retained in case of duplicates
                # ('namelower' is preferred over 'github_account')
                # only template values longer than 2 characters are retained
                if self.template_values[key] not in templ_val and len(self.template_values[key]) > 2:
                    templ_val[self.template_values[key]] = key

            toolchain_hierarchy = None
            if not explicit_toolchains:
                try:
                    toolchain_hierarchy = get_toolchain_hierarchy(self['toolchain'])
                except EasyBuildError as err:
                    # don't fail hard just because we can't get the hierarchy
                    self.log.warning('Could not generate toolchain hierarchy for %s to use in easyconfig dump method, '
                                     'error:\n%s', self['toolchain'], str(err))

            try:
                ectxt = self.parser.dump(self, default_values, templ_const, templ_val,
                                         toolchain_hierarchy=toolchain_hierarchy)
            except NotImplementedError as err:
                raise NotImplementedError(err)

            self.log.debug("Dumped easyconfig: %s", ectxt)

            if build_option('dump_autopep8'):
                autopep8_opts = {
                    'aggressive': 1,  # enable non-whitespace changes, but don't be too aggressive
                    'max_line_length': 120,
                }
                self.log.info("Reformatting dumped easyconfig using autopep8 (options: %s)", autopep8_opts)
                ectxt = autopep8.fix_code(ectxt, options=autopep8_opts)
                self.log.debug("Dumped easyconfig after autopep8 reformatting: %s", ectxt)

            if not ectxt.endswith('\n'):
                ectxt += '\n'

            write_file(fp, ectxt, always_overwrite=always_overwrite, backup=backup, verbose=backup)

    def _validate(self, attr, values):  # private method
        """
        validation helper method. attr is the attribute it will check, values are the possible values.
        if the value of the attribute is not in the is array, it will report an error
        """
        if values is None:
            values = []
        if self[attr] and self[attr] not in values:
            raise EasyBuildError("%s provided '%s' is not valid: %s", attr, self[attr], values)

    def probe_external_module_metadata(self, mod_name, existing_metadata=None):
        """
        Helper function for handle_external_module_metadata.

        Tries to determine metadata for external module when there is not entry in the metadata file,
        by looking at the variables defined by the module file.

        This is mainly intended for modules provided in the Cray Programming Environment,
        but it could also be useful in other contexts.

        The following pairs of variables are considered (in order, first hit wins),
        where 'XXX' is the software name in capitals:
          1. $CRAY_XXX_PREFIX and $CRAY_XXX_VERSION
          1. $CRAY_XXX_PREFIX_DIR and $CRAY_XXX_VERSION
          2. $CRAY_XXX_DIR and $CRAY_XXX_VERSION
          2. $CRAY_XXX_ROOT and $CRAY_XXX_VERSION
          5. $XXX_PREFIX and $XXX_VERSION
          4. $XXX_DIR and $XXX_VERSION
          5. $XXX_ROOT and $XXX_VERSION
          3. $XXX_HOME and $XXX_VERSION

        If none of the pairs is found, then an empty dictionary is returned.

        :param mod_name: name of the external module
        :param metadata: already available metadata for this external module (if any)
        """
        res = {}

        if existing_metadata is None:
            existing_metadata = {}

        soft_name = existing_metadata.get('name')
        if soft_name:
            # software name is a list of names in metadata, just grab first one
            soft_name = soft_name[0]
        else:
            # if the software name is not known yet, use the first part of the module name as software name,
            # but strip off the leading 'cray-' part first (examples: cray-netcdf/4.6.1.3,  cray-fftw/3.3.8.2)
            soft_name = mod_name.split('/')[0]

            cray_prefix = 'cray-'
            if soft_name.startswith(cray_prefix):
                soft_name = soft_name[len(cray_prefix):]

        # determine software name to use in names of environment variables (upper case, '-' becomes '_')
        soft_name_env_var_infix = convert_name(soft_name.replace('-', '_'), upper=True)

        var_name_pairs_templates = [
            ('CRAY_%s_PREFIX', 'CRAY_%s_VERSION'),
            ('CRAY_%s_PREFIX_DIR', 'CRAY_%s_VERSION'),
            ('CRAY_%s_DIR', 'CRAY_%s_VERSION'),
            ('CRAY_%s_ROOT', 'CRAY_%s_VERSION'),
            ('%s_PREFIX', '%s_VERSION'),
            ('%s_DIR', '%s_VERSION'),
            ('%s_ROOT', '%s_VERSION'),
            ('%s_HOME', '%s_VERSION'),
        ]

        def mk_var_name_pair(var_name_pair, name):
            """Complete variable name pair template using provided name."""
            return (var_name_pair[0] % name, var_name_pair[1] % name)

        var_name_pairs = [mk_var_name_pair(x, soft_name_env_var_infix) for x in var_name_pairs_templates]

        # also consider name based on module name for environment variables to check
        # for example, for the cray-netcdf-hdf5parallel module we should also check $CRAY_NETCDF_HDF5PARALLEL_VERSION
        mod_name_env_var_infix = convert_name(mod_name.split('/')[0].replace('-', '_'), upper=True)

        if mod_name_env_var_infix != soft_name_env_var_infix:
            var_name_pairs.extend([mk_var_name_pair(x, mod_name_env_var_infix) for x in var_name_pairs_templates])

        for prefix_var_name, version_var_name in var_name_pairs:
            prefix = self.modules_tool.get_setenv_value_from_modulefile(mod_name, prefix_var_name)
            version = self.modules_tool.get_setenv_value_from_modulefile(mod_name, version_var_name)

            # we only have a hit when values for *both* variables are found
            if prefix and version:

                if 'name' not in existing_metadata:
                    res['name'] = [soft_name]

                # if a version is already set in the available metadata, we retain it
                if 'version' not in existing_metadata:
                    # Use name of environment variable as value, not the current value of that environment variable.
                    # This is important in case the value of the environment variables changes by the time we really
                    # use it, for example by a loaded module being swapped with another version of that module.
                    # This is particularly important w.r.t. integration with the Cray Programming Environment,
                    # cfr. https://github.com/easybuilders/easybuild-framework/pull/3559.
                    res['version'] = [version_var_name]
                    self.log.info('setting external module %s version to be %s', mod_name, version)

                # if a prefix is already set in the available metadata, we retain it
                if 'prefix' not in existing_metadata:
                    # Use name of environment variable as value, not the current value of that environment variable.
                    # (see above for more info)
                    res['prefix'] = prefix_var_name
                    self.log.info('setting external module %s prefix to be %s', mod_name, prefix_var_name)
                break

        return res

    def handle_external_module_metadata(self, mod_name):
        """
        Helper function for _parse_dependency; collects metadata for external module dependencies.

        :param mod_name: name of external module to collect metadata for
        """
        partial_mod_name = mod_name.split('/')[0]

        # check whether existing metadata for external modules already has metadata for this module;
        # first using full module name (as it is provided), for example 'cray-netcdf/4.6.1.3',
        # then with partial module name, for example 'cray-netcdf'
        metadata = self.external_modules_metadata.get(mod_name, {})
        self.log.info("Available metadata for external module %s: %s", mod_name, metadata)

        partial_mod_name_metadata = self.external_modules_metadata.get(partial_mod_name, {})
        self.log.info("Available metadata for external module using partial module name %s: %s",
                      partial_mod_name, partial_mod_name_metadata)

        for key in partial_mod_name_metadata:
            if key not in metadata:
                metadata[key] = partial_mod_name_metadata[key]

        self.log.info("Combined available metadata for external module %s: %s", mod_name, metadata)

        # if not all metadata is available (name/version/prefix), probe external module to collect more metadata;
        # first with full module name, and then with partial module name if first probe didn't return anything;
        # note: result of probe_external_module_metadata only contains metadata for keys that were not set yet
        if not all(key in metadata for key in ['name', 'prefix', 'version']):
            self.log.info("Not all metadata found yet for external module %s, probing module...", mod_name)
            probed_metadata = self.probe_external_module_metadata(mod_name, existing_metadata=metadata)
            if probed_metadata:
                self.log.info("Extra metadata found by probing external module %s: %s", mod_name, probed_metadata)
                metadata.update(probed_metadata)
            else:
                self.log.info("No extra metadata found by probing %s, trying with partial module name...", mod_name)
                probed_metadata = self.probe_external_module_metadata(partial_mod_name, existing_metadata=metadata)
                self.log.info("Extra metadata for external module %s found by probing partial module name %s: %s",
                              mod_name, partial_mod_name, probed_metadata)
                metadata.update(probed_metadata)

            self.log.info("Obtained metadata after module probing: %s", metadata)

        return {'external_module_metadata': metadata}

    def handle_multi_deps(self):
        """
        Handle lists of dependency versions of which we should iterate specified in 'multi_deps' easyconfig parameter.

        This is basically just syntactic sugar to prevent having to specify a list of lists in 'builddependencies'.
        """

        multi_deps = self['multi_deps']
        if multi_deps:

            # first, make sure all lists have same length, otherwise we're dealing with invalid input...
            multi_dep_cnts = nub([len(dep_vers) for dep_vers in multi_deps.values()])
            if len(multi_dep_cnts) == 1:
                multi_dep_cnt = multi_dep_cnts[0]
            else:
                raise EasyBuildError("Not all the dependencies listed in multi_deps have the same number of versions!")

            self.log.info("Found %d lists of %d dependency versions to iterate over", len(multi_deps), multi_dep_cnt)

            # make sure that build dependencies is not a list of lists to iterate over already...
            if self['builddependencies'] and all(isinstance(bd, list) for bd in self['builddependencies']):
                raise EasyBuildError("Can't combine multi_deps with builddependencies specified as list of lists")

            # now make builddependencies a list of lists to iterate over
            builddeps = self['builddependencies']
            self['builddependencies'] = []

            keys = sorted(multi_deps.keys())
            for idx in range(multi_dep_cnt):
                self['builddependencies'].append([(key, multi_deps[key][idx]) for key in keys] + builddeps)

            self.log.info("Original list of build dependencies: %s", builddeps)
            self.log.info("List of lists of build dependencies to iterate over: %s", self['builddependencies'])

    def get_parsed_multi_deps(self):
        """Get list of lists of parsed dependencies that correspond with entries in multi_deps easyconfig parameter."""

        multi_deps = []

        if self['multi_deps']:

            builddeps = self['builddependencies']

            # all multi_deps entries should be listed in builddependencies (if not, something is very wrong)
            if isinstance(builddeps, list) and all(isinstance(x, list) for x in builddeps):

                for iter_id in range(len(builddeps)):

                    # only build dependencies that correspond to multi_deps entries should be loaded as extra modules
                    # (other build dependencies should not be required to make sanity check pass for this iteration)
                    iter_deps = []
                    for key in self['multi_deps']:
                        hits = [d for d in builddeps[iter_id] if d['name'] == key]
                        if len(hits) == 1:
                            iter_deps.append(hits[0])
                        else:
                            raise EasyBuildError("Failed to isolate %s dep during iter #%d: %s", key, iter_id, hits)

                    multi_deps.append(iter_deps)
            else:
                error_msg = "builddependencies should be a list of lists when calling get_parsed_multi_deps(): %s"
                raise EasyBuildError(error_msg, builddeps)

        return multi_deps

    # private method
    def _parse_dependency(self, dep, hidden=False, build_only=False):
        """
        parses the dependency into a usable dict with a common format
        dep can be a dict, a tuple or a list.
        if it is a tuple or a list the attributes are expected to be in the following order:
        ('name', 'version', 'versionsuffix', 'toolchain')
        of these attributes, 'name' and 'version' are mandatory

        output dict contains these attributes:
        ['name', 'version', 'versionsuffix', 'system', 'toolchain', 'short_mod_name', 'full_mod_name', 'hidden',
         'external_module']

        :param hidden: indicate whether corresponding module file should be installed hidden ('.'-prefixed)
        :param build_only: indicate whether this is a build-only dependency
        """
        # convert tuple to string otherwise python might complain about the formatting
        self.log.debug("Parsing %s as a dependency" % str(dep))

        attr = ['name', 'version', 'versionsuffix', 'toolchain']
        dependency = {
            # full/short module names
            'full_mod_name': None,
            'short_mod_name': None,
            # software name, version, versionsuffix
            'name': None,
            'version': None,
            'versionsuffix': '',
            # toolchain with which this dependency is installed
            'toolchain': None,
            'toolchain_inherited': False,
            # boolean indicating whether we're dealing with a system toolchain for this dependency
            SYSTEM_TOOLCHAIN_NAME: False,
            # boolean indicating whether the module for this dependency is (to be) installed hidden
            'hidden': hidden,
            # boolean indicating whether this this a build-only dependency
            'build_only': build_only,
            # boolean indicating whether this dependency should be resolved via an external module
            'external_module': False,
            # metadata in case this is an external module;
            # provides information on what this module represents (software name/version, install prefix, ...)
            'external_module_metadata': {},
        }

        if isinstance(dep, dict):
            dependency.update(dep)

            # make sure 'system' key is handled appropriately
            if SYSTEM_TOOLCHAIN_NAME in dep and 'toolchain' not in dep:
                dependency['toolchain'] = dep[SYSTEM_TOOLCHAIN_NAME]

            if dep.get('external_module', False):
                dependency.update(self.handle_external_module_metadata(dep['full_mod_name']))

        elif isinstance(dep, Dependency):
            dependency['name'] = dep.name()
            dependency['version'] = dep.version()
            versionsuffix = dep.versionsuffix()
            if versionsuffix is not None:
                dependency['versionsuffix'] = versionsuffix
            toolchain = dep.toolchain()
            if toolchain is not None:
                dependency['toolchain'] = toolchain

        elif isinstance(dep, (list, tuple)):
            if dep and dep[-1] == EXTERNAL_MODULE_MARKER:
                if len(dep) == 2:
                    dependency['external_module'] = True
                    dependency['short_mod_name'] = dep[0]
                    dependency['full_mod_name'] = dep[0]
                    dependency.update(self.handle_external_module_metadata(dep[0]))
                else:
                    raise EasyBuildError("Incorrect external dependency specification: %s", dep)
            else:
                # non-external dependency: tuple (or list) that specifies name/version(/versionsuffix(/toolchain))
                dependency.update(dict(zip(attr, dep)))

        else:
            raise EasyBuildError("Dependency %s of unsupported type: %s", dep, type(dep))

        # Find the version to use on this system
        dependency['version'] = pick_dep_version(dependency['version'])

        if dependency['external_module']:
            # check whether the external module is hidden
            if dependency['full_mod_name'].split('/')[-1].startswith('.'):
                dependency['hidden'] = True

            self.log.debug("Returning parsed external dependency: %s", dependency)
            return dependency

        # check whether this dependency should be hidden according to --hide-deps
        if build_option('hide_deps'):
            dependency['hidden'] |= dependency['name'] in build_option('hide_deps')

        # dependency inherits toolchain, unless it's specified to have a custom toolchain
        tc = copy.deepcopy(self['toolchain'])
        tc_spec = dependency['toolchain']
        if tc_spec is None:
            self.log.debug("Inheriting parent toolchain %s for dep %s (until deps are finalised)", tc, dependency)
            dependency['toolchain_inherited'] = True

        # (true) boolean value simply indicates that a system toolchain is used
        elif isinstance(tc_spec, bool) and tc_spec:
            tc = {'name': SYSTEM_TOOLCHAIN_NAME, 'version': ''}

        # two-element list/tuple value indicates custom toolchain specification
        elif isinstance(tc_spec, (list, tuple,)):
            if len(tc_spec) == 2:
                tc = {'name': tc_spec[0], 'version': tc_spec[1]}
            else:
                raise EasyBuildError("List/tuple value for toolchain should have two elements (%s)", str(tc_spec))

        elif isinstance(tc_spec, dict):
            if 'name' in tc_spec and 'version' in tc_spec:
                tc = copy.deepcopy(tc_spec)
            else:
                raise EasyBuildError("Found toolchain spec as dict with wrong keys (no name/version): %s", tc_spec)

        else:
            raise EasyBuildError("Unsupported type for toolchain spec encountered: %s (%s)", tc_spec, type(tc_spec))

        self.log.debug("Derived toolchain to use for dependency %s, based on toolchain spec %s: %s", dep, tc_spec, tc)
        dependency['toolchain'] = tc

        # validations
        if dependency['name'] is None:
            raise EasyBuildError("Dependency specified without name: %s", dependency)

        if dependency['version'] is None:
            raise EasyBuildError("Dependency specified without version: %s", dependency)

        return dependency

    def _finalize_dependencies(self):
        """Finalize dependency parameters, after initial parsing."""

        filter_deps_specs = self.parse_filter_deps()

        for key in DEPENDENCY_PARAMETERS:
            # loop over a *copy* of dependency dicts (with resolved templates);
            deps = self[key]

            # to update the original dep dict, we need to get a reference with templating disabled...
            deps_ref = self.get_ref(key)

            # take into account that this *dependencies parameter may be iterated over
            if key in self.iterate_options:
                deps = flatten(deps)
                deps_ref = flatten(deps_ref)

            for idx, dep in enumerate(deps):

                # reference to original dep dict, this is the one we should be updating
                orig_dep = deps_ref[idx]

                if self.dep_is_filtered(orig_dep, filter_deps_specs):
                    self.log.debug("Skipping filtered dependency %s when finalising dependencies", orig_dep['name'])
                    continue

                # handle dependencies with inherited (non-system) toolchain
                # this *must* be done after parsing all dependencies, to avoid problems with templates like %(pyver)s
                if dep['toolchain_inherited'] and not is_system_toolchain(dep['toolchain']['name']):
                    tc = None
                    dep_str = '%s %s%s' % (dep['name'], dep['version'], dep['versionsuffix'])
                    self.log.debug("Figuring out toolchain to use for dep %s...", dep)
                    if build_option('minimal_toolchains'):
                        # determine 'smallest' subtoolchain for which a matching easyconfig file is available
                        self.log.debug("Looking for minimal toolchain for dependency %s (parent toolchain: %s)...",
                                       dep_str, dep['toolchain'])
                        tc = robot_find_subtoolchain_for_dep(dep, self.modules_tool)
                        if tc is None:
                            raise EasyBuildError("Failed to determine minimal toolchain for dep %s", dep_str)
                    else:
                        # try to determine subtoolchain for dep;
                        # this is done considering both available modules and easyconfigs (in that order)
                        tc = robot_find_subtoolchain_for_dep(dep, self.modules_tool, parent_first=True)
                        self.log.debug("Using subtoolchain %s for dep %s", tc, dep_str)

                    if tc is None:
                        self.log.debug("Inheriting toolchain %s from parent for dep %s", dep['toolchain'], dep_str)
                    else:
                        # put derived toolchain in place
                        self.log.debug("Figured out toolchain to use for dep %s: %s", dep_str, tc)
                        dep['toolchain'] = orig_dep['toolchain'] = tc
                        dep['toolchain_inherited'] = orig_dep['toolchain_inherited'] = False

                if not dep['external_module']:
                    # make sure 'system' is set correctly
                    orig_dep[SYSTEM_TOOLCHAIN_NAME] = is_system_toolchain(dep['toolchain']['name'])

                    # set module names
                    orig_dep['short_mod_name'] = ActiveMNS().det_short_module_name(dep)
                    orig_dep['full_mod_name'] = ActiveMNS().det_full_module_name(dep)

    def generate_template_values(self):
        """Try to generate all template values."""

        self.log.info("Generating template values...")
        self._generate_template_values()

        # recursive call, until there are no more changes to template values;
        # important since template values may include other templates
        cont = True
        while cont:
            cont = False
            for key in self.template_values:
                try:
                    curr_val = self.template_values[key]
                    new_val = str(curr_val) % self.template_values
                    if new_val != curr_val:
                        cont = True
                    self.template_values[key] = new_val
                except KeyError:
                    # KeyError's may occur when not all templates are defined yet, but these are safe to ignore
                    pass

        self.log.info("Template values: %s", ', '.join("%s='%s'" % x for x in sorted(self.template_values.items())))

    def _generate_template_values(self, ignore=None):
        """Actual code to generate the template values"""

        # step 0. self.template_values can/should be updated from outside easyconfig
        # (eg the run_step code in EasyBlock)

        # step 1-3 work with easyconfig.templates constants
        # disable templating with creating dict with template values to avoid looping back to here via __getitem__
        with self.disable_templating():
            if self.template_values is None:
                # if no template values are set yet, initiate with a minimal set of template values;
                # this is important for easyconfig that use %(version_minor)s to define 'toolchain',
                # which is a pretty weird use case, but fine...
                self.template_values = template_constant_dict(self, ignore=ignore)

        # grab toolchain instance with templating support enabled,
        # which is important in case the Toolchain instance was not created yet
        toolchain = self.toolchain

        # get updated set of template values, now with toolchain instance
        # (which is used to define the %(mpi_cmd_prefix)s template)
        with self.disable_templating():
            template_values = template_constant_dict(self, ignore=ignore, toolchain=toolchain)

        # update the template_values dict
        self.template_values.update(template_values)

        # cleanup None values
        for key in list(self.template_values):
            if self.template_values[key] is None:
                del self.template_values[key]

    @handle_deprecated_or_replaced_easyconfig_parameters
    def __contains__(self, key):
        """Check whether easyconfig parameter is defined"""
        return key in self._config

    @handle_deprecated_or_replaced_easyconfig_parameters
    def __getitem__(self, key):
        """Return value of specified easyconfig parameter (without help text, etc.)"""
        value = None
        if key in self._config:
            value = self._config[key][0]
        else:
            raise EasyBuildError("Use of unknown easyconfig parameter '%s' when getting parameter value", key)

        if self.enable_templating:
            if self.template_values is None or len(self.template_values) == 0:
                self.generate_template_values()
            value = resolve_template(value, self.template_values)

        return value

    def is_mandatory_param(self, key):
        """Check whether specified easyconfig parameter is mandatory."""
        return key in self.mandatory

    def get_ref(self, key):
        """
        Obtain reference to original/untemplated value of specified easyconfig parameter
        rather than a copied value with templated values.
        """
        # see also comments in resolve_template

        # temporarily disable templating
        with self.disable_templating():
            ref = self[key]

        return ref

    @handle_deprecated_or_replaced_easyconfig_parameters
    def __setitem__(self, key, value):
        """Set value of specified easyconfig parameter (help text & co is left untouched)"""
        if key in self._config:
            self._config[key][0] = value
        else:
            raise EasyBuildError("Use of unknown easyconfig parameter '%s' when setting parameter value to '%s'",
                                 key, value)

    @handle_deprecated_or_replaced_easyconfig_parameters
    def get(self, key, default=None, resolve=True):
        """
        Gets the value of a key in the config, with 'default' as fallback.
        :param resolve: if False, disables templating via calling get_ref, else resolves template values
        """
        if key in self:
            return self[key] if resolve else self.get_ref(key)
        else:
            return default

    # *both* __eq__ and __ne__ must be implemented for == and != comparisons to work correctly
    # see also https://docs.python.org/2/reference/datamodel.html#object.__eq__
    def __eq__(self, ec):
        """Is this EasyConfig instance equivalent to the provided one?"""
        return self.asdict() == ec.asdict()

    def __ne__(self, ec):
        """Is this EasyConfig instance equivalent to the provided one?"""
        return self.asdict() != ec.asdict()

    def __hash__(self):
        """Return hash value for a hashable representation of this EasyConfig instance."""
        def make_hashable(val):
            """Make a hashable value of the given value."""
            if isinstance(val, list):
                val = tuple([make_hashable(x) for x in val])
            elif isinstance(val, dict):
                val = tuple([(key, make_hashable(val)) for (key, val) in sorted(val.items())])
            return val

        lst = []
        for (key, val) in sorted(self.asdict().items()):
            lst.append((key, make_hashable(val)))

        # a list is not hashable, but a tuple is
        return hash(tuple(lst))

    def asdict(self):
        """
        Return dict representation of this EasyConfig instance.
        """
        res = {}
        for key, tup in self._config.items():
            value = tup[0]
            if self.enable_templating:
                if not self.template_values:
                    self.generate_template_values()
                value = resolve_template(value, self.template_values)
            res[key] = value
        return res

    def get_cuda_cc_template_value(self, key):
        """
        Get template value based on --cuda-compute-capabilities EasyBuild configuration option
        and cuda_compute_capabilities easyconfig parameter.
        Returns user-friendly error message in case neither are defined,
        or if an unknown key is used.
        """
        if key.startswith('cuda_') and any(x[0] == key for x in TEMPLATE_NAMES_DYNAMIC):
            try:
                return self.template_values[key]
            except KeyError:
                error_msg = "Template value '%s' is not defined!\n"
                error_msg += "Make sure that either the --cuda-compute-capabilities EasyBuild configuration "
                error_msg += "option is set, or that the cuda_compute_capabilities easyconfig parameter is defined."
                raise EasyBuildError(error_msg, key)
        else:
            error_msg = "%s is not a template value based on --cuda-compute-capabilities/cuda_compute_capabilities"
            raise EasyBuildError(error_msg, key)


def det_installversion(version, toolchain_name, toolchain_version, prefix, suffix):
    """Deprecated 'det_installversion' function, to determine exact install version, based on supplied parameters."""
    old_fn = 'framework.easyconfig.easyconfig.det_installversion'
    _log.nosupport('Use det_full_ec_version from easybuild.tools.module_generator instead of %s' % old_fn, '2.0')


def get_easyblock_class(easyblock, name=None, error_on_failed_import=True, error_on_missing_easyblock=None, **kwargs):
    """
    Get class for a particular easyblock (or use default)
    """
    if 'default_fallback' in kwargs:
        msg = "Named argument 'default_fallback' for get_easyblock_class is deprecated, "
        msg += "use 'error_on_missing_easyblock' instead"
        _log.deprecated(msg, '4.0')
        if error_on_missing_easyblock is None:
            error_on_missing_easyblock = kwargs['default_fallback']
    elif error_on_missing_easyblock is None:
        error_on_missing_easyblock = True

    cls = None
    try:
        if easyblock:
            # something was specified, lets parse it
            es = easyblock.split('.')
            class_name = es.pop(-1)
            # figure out if full path was specified or not
            if es:
                modulepath = '.'.join(es)
                _log.info("Assuming that full easyblock module path was specified (class: %s, modulepath: %s)",
                          class_name, modulepath)
                cls = get_class_for(modulepath, class_name)
            else:
                modulepath = get_module_path(easyblock)
                cls = get_class_for(modulepath, class_name)
                _log.info("Derived full easyblock module path for %s: %s" % (class_name, modulepath))
        else:
            # if no easyblock specified, try to find if one exists
            if name is None:
                name = "UNKNOWN"
            # The following is a generic way to calculate unique class names for any funny software title
            class_name = encode_class_name(name)
            # modulepath will be the namespace + encoded modulename (from the classname)
            modulepath = get_module_path(class_name, generic=False)
            modulepath_imported = False
            try:
                __import__(modulepath, globals(), locals(), [''])
                modulepath_imported = True
            except ImportError as err:
                _log.debug("Failed to import module '%s': %s" % (modulepath, err))

            # check if determining module path based on software name would have resulted in a different module path
            if modulepath_imported:
                _log.debug("Module path '%s' found" % modulepath)
            else:
                _log.debug("No module path '%s' found" % modulepath)
                modulepath_bis = get_module_path(name, generic=False, decode=False)
                _log.debug("Module path determined based on software name: %s" % modulepath_bis)
                if modulepath_bis != modulepath:
                    _log.nosupport("Determining module path based on software name", '2.0')

            # try and find easyblock
            try:
                _log.debug("getting class for %s.%s" % (modulepath, class_name))
                cls = get_class_for(modulepath, class_name)
                _log.info("Successfully obtained %s class instance from %s" % (class_name, modulepath))
            except ImportError as err:
                # when an ImportError occurs, make sure that it's caused by not finding the easyblock module,
                # and not because of a broken import statement in the easyblock module
                modname = modulepath.replace('easybuild.easyblocks.', '')
                error_re = re.compile(r"No module named '?.*/?%s'?" % modname)
                _log.debug("error regexp for ImportError on '%s' easyblock: %s", modname, error_re.pattern)
                if error_re.match(str(err)):
                    if error_on_missing_easyblock:
                        raise EasyBuildError("No software-specific easyblock '%s' found for %s", class_name, name)
                elif error_on_failed_import:
                    raise EasyBuildError("Failed to import %s easyblock: %s", class_name, err)
                else:
                    _log.debug("Failed to import easyblock for %s, but ignoring it: %s" % (class_name, err))

        if cls is not None:
            _log.info("Successfully obtained class '%s' for easyblock '%s' (software name '%s')",
                      cls.__name__, easyblock, name)
        else:
            _log.debug("No class found for easyblock '%s' (software name '%s')", easyblock, name)

        return cls

    except EasyBuildError as err:
        # simply reraise rather than wrapping it into another error
        raise err
    except Exception as err:
        raise EasyBuildError("Failed to obtain class for %s easyblock (not available?): %s", easyblock, err)


def is_generic_easyblock(easyblock):
    """Return whether specified easyblock name is a generic easyblock or not."""
    _log.deprecated("is_generic_easyblock function was moved to easybuild.tools.filetools", '5.0')
    return filetools.is_generic_easyblock(easyblock)


def get_module_path(name, generic=None, decode=True):
    """
    Determine the module path for a given easyblock or software name,
    based on the encoded class name.

    :param generic: whether or not the easyblock is generic (if None: auto-derive from specified class name)
    :param decode: whether or not to decode the provided class name
    """
    if name is None:
        return None

    if generic is None:
        generic = filetools.is_generic_easyblock(name)

    # example: 'EB_VSC_minus_tools' should result in 'vsc_tools'
    if decode:
        name = decode_class_name(name)
    module_name = remove_unwanted_chars(name.replace('-', '_')).lower()

    modpath = ['easybuild', 'easyblocks']
    if generic:
        modpath.append(GENERIC_EASYBLOCK_PKG)

    return '.'.join(modpath + [module_name])


def resolve_template(value, tmpl_dict):
    """Given a value, try to susbstitute the templated strings with actual values.
        - value: some python object (supported are string, tuple/list, dict or some mix thereof)
        - tmpl_dict: template dictionary
    """
    if isinstance(value, string_type):
        # simple escaping, making all '%foo', '%%foo', '%%%foo' post-templates values available,
        #         but ignore a string like '%(name)s'
        # behaviour of strings like '%(name)s',
        #   make sure that constructs like %%(name)s are preserved
        #   higher order escaping in the original text is considered advanced users only,
        #   and a big no-no otherwise. It indicates that want some new functionality
        #   in easyconfigs, so just open an issue for it.
        #   detailed behaviour:
        #     if a an odd number of % prefixes the (name)s,
        #     we assume that templating is assumed and the behaviour is as follows
        #     '%(name)s' -> '%(name)s', and after templating with {'name':'x'} -> 'x'
        #     '%%%(name)s' -> '%%%(name)s', and after templating with {'name':'x'} -> '%x'
        #     if a an even number of % prefixes the (name)s,
        #     we assume that no templating is desired and the behaviour is as follows
        #     '%%(name)s' -> '%%(name)s', and after templating with {'name':'x'} -> '%(name)s'
        #     '%%%%(name)s' -> '%%%%(name)s', and after templating with {'name':'x'} -> '%%(name)s'
        # examples:
        # '10%' -> '10%%'
        # '%s' -> '%%s'
        # '%%' -> '%%%%'
        # '%(name)s' -> '%(name)s'
        # '%%(name)s' -> '%%(name)s'
        if '%' in value:
            value = re.sub(re.compile(r'(%)(?!%*\(\w+\)s)'), r'\1\1', value)

            try:
                value = value % tmpl_dict
            except KeyError:
                _log.warning("Unable to resolve template value %s with dict %s", value, tmpl_dict)
    else:
        # this block deals with references to objects and returns other references
        # for reading this is ok, but for self['x'] = {}
        # self['x']['y'] = z does not work
        # self['x'] is a get, will return a reference to a templated version of self._config['x']
        # and the ['y] = z part will be against this new reference
        # you will need to do
        # with self.disable_templating():
        #     self['x']['y'] = z
        # or (direct but evil)
        # self._config['x']['y'] = z
        # it can not be intercepted with __setitem__ because the set is done at a deeper level
        if isinstance(value, list):
            value = [resolve_template(val, tmpl_dict) for val in value]
        elif isinstance(value, tuple):
            value = tuple(resolve_template(list(value), tmpl_dict))
        elif isinstance(value, dict):
            value = dict((resolve_template(k, tmpl_dict), resolve_template(v, tmpl_dict)) for k, v in value.items())

    return value


def process_easyconfig(path, build_specs=None, validate=True, parse_only=False, hidden=None):
    """
    Process easyconfig, returning some information for each block
    :param path: path to easyconfig file
    :param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    :param validate: whether or not to perform validation
    :param parse_only: only parse easyconfig superficially (faster, but results in partial info)
    :param hidden: indicate whether corresponding module file should be installed hidden ('.'-prefixed)
    """
    blocks = retrieve_blocks_in_spec(path, build_option('only_blocks'))

    if hidden is None:
        hidden = build_option('hidden')

    # only cache when no build specifications are involved (since those can't be part of a dict key)
    cache_key = None
    if build_specs is None:
        cache_key = (path, validate, hidden, parse_only)
        if cache_key in _easyconfigs_cache:
            return [e.copy() for e in _easyconfigs_cache[cache_key]]

    easyconfigs = []
    for spec in blocks:
        # process for dependencies and real installversionname
        _log.debug("Processing easyconfig %s" % spec)

        # create easyconfig
        try:
            ec = EasyConfig(spec, build_specs=build_specs, validate=validate, hidden=hidden)
        except EasyBuildError as err:
            raise EasyBuildError("Failed to process easyconfig %s: %s", spec, err.msg)

        name = ec['name']

        easyconfig = {
            'ec': ec,
        }
        easyconfigs.append(easyconfig)

        if not parse_only:
            # also determine list of dependencies, module name (unless only parsed easyconfigs are requested)
            easyconfig.update({
                'spec': ec.path,
                'short_mod_name': ec.short_mod_name,
                'full_mod_name': ec.full_mod_name,
                'dependencies': [],
                'builddependencies': [],
                'hiddendependencies': [],
                'hidden': ec.hidden,
            })
            if len(blocks) > 1:
                easyconfig['original_spec'] = path

            # add build dependencies
            for dep in ec['builddependencies']:
                _log.debug("Adding build dependency %s for app %s." % (dep, name))
                easyconfig['builddependencies'].append(dep)

            # add dependencies (including build & hidden dependencies)
            for dep in ec.dependencies():
                _log.debug("Adding dependency %s for app %s." % (dep, name))
                easyconfig['dependencies'].append(dep)

            # add toolchain as dependency too
            if not is_system_toolchain(ec['toolchain']['name']):
                tc = ec.toolchain.as_dict()
                _log.debug("Adding toolchain %s as dependency for app %s." % (tc, name))
                easyconfig['dependencies'].append(tc)

    if cache_key is not None:
        _easyconfigs_cache[cache_key] = [e.copy() for e in easyconfigs]

    return easyconfigs


def letter_dir_for(name):
    """
    Determine 'letter' directory for specified software name.
    This usually just the 1st letter of the software name (in lowercase),
    except for funky software names, e.g. ones starting with a digit.
    """
    # wildcard name should result in wildcard letter
    if name == '*':
        letter = '*'
    else:
        letter = name.lower()[0]
        # outside of a-z range, use '0'
        if letter < 'a' or letter > 'z':
            letter = '0'

    return letter


def create_paths(path, name, version):
    """
    Returns all the paths where easyconfig could be located
    <path> is the basepath
    <name> should be a string
    <version> can be a '*' if you use glob patterns, or an install version otherwise
    """
    cand_paths = [
        (name, version),  # e.g. <path>/GCC/4.8.2.eb
        (name, '%s-%s' % (name, version)),  # e.g. <path>/GCC/GCC-4.8.2.eb
        (letter_dir_for(name), name, '%s-%s' % (name, version)),  # e.g. <path>/g/GCC/GCC-4.8.2.eb
        ('%s-%s' % (name, version),),  # e.g. <path>/GCC-4.8.2.eb
    ]
    return ['%s.eb' % os.path.join(path, *cand_path) for cand_path in cand_paths]


def robot_find_easyconfig(name, version):
    """
    Find an easyconfig for module in path, returns (absolute) path to easyconfig file (or None, if none is found).
    """
    key = (name, version)
    if key in _easyconfig_files_cache:
        _log.debug("Obtained easyconfig path from cache for %s: %s" % (key, _easyconfig_files_cache[key]))
        return _easyconfig_files_cache[key]

    paths = build_option('robot_path')
    if paths is None:
        paths = []
    elif not isinstance(paths, (list, tuple)):
        paths = [paths]

    # if we should also consider archived easyconfigs, duplicate paths list with archived equivalents
    if build_option('consider_archived_easyconfigs'):
        paths = paths + [os.path.join(p, EASYCONFIGS_ARCHIVE_DIR) for p in paths]

    res = None
    for path in paths:

        if build_option('ignore_index'):
            _log.info("Ignoring index for %s...", path)
            path_index = []
        elif path in _path_indexes:
            path_index = _path_indexes[path]
            _log.info("Found loaded index for %s", path)
        elif os.path.exists(path):
            path_index = load_index(path)
            if path_index is None:
                _log.info("No index found for %s, so creating it...", path)
                path_index = create_index(path)
            else:
                _log.info("Loaded index for %s", path)

            _path_indexes[path] = path_index
        else:
            path_index = []

        easyconfigs_paths = create_paths(path, name, version)
        for easyconfig_path in easyconfigs_paths:
            _log.debug("Checking easyconfig path %s" % easyconfig_path)
            if easyconfig_path in path_index or os.path.isfile(easyconfig_path):
                _log.debug("Found easyconfig file for name %s, version %s at %s" % (name, version, easyconfig_path))
                _easyconfig_files_cache[key] = os.path.abspath(easyconfig_path)
                res = _easyconfig_files_cache[key]
                break
        if res:
            break

    return res


def verify_easyconfig_filename(path, specs, parsed_ec=None):
    """
    Check whether parsed easyconfig at specified path matches expected specs;
    this basically verifies whether the easyconfig filename corresponds to its contents

    :param path: path to easyconfig file
    :param specs: expected specs (dict with easyconfig parameter values)
    :param parsed_ec: (list of) EasyConfig instance(s) corresponding to easyconfig file
    """
    if isinstance(parsed_ec, EasyConfig):
        ecs = [{'ec': parsed_ec}]
    elif isinstance(parsed_ec, (list, tuple)):
        ecs = parsed_ec
    elif parsed_ec is None:
        ecs = process_easyconfig(path)
    else:
        raise EasyBuildError("Unexpected value type for parsed_ec: %s (%s)", type(parsed_ec), parsed_ec)

    fullver = det_full_ec_version(specs)

    expected_filename = '%s-%s.eb' % (specs['name'], fullver)
    if os.path.basename(path) != expected_filename:
        # only retain relevant specs to produce a more useful error message
        specstr = ''
        for key in ['name', 'version', 'versionsuffix']:
            specstr += "%s: %s; " % (key, quote_py_str(specs.get(key)))
        toolchain = specs.get('toolchain')
        if toolchain:
            tcname, tcver = quote_py_str(toolchain.get('name')), quote_py_str(toolchain.get('version'))
            specstr += "toolchain name, version: %s, %s" % (tcname, tcver)
        else:
            specstr += "toolchain: None"

        raise EasyBuildError("Easyconfig filename '%s' does not match with expected filename '%s' (specs: %s)",
                             os.path.basename(path), expected_filename, specstr)

    for ec in ecs:
        found_fullver = det_full_ec_version(ec['ec'])
        if ec['ec']['name'] != specs['name'] or found_fullver != fullver:
            subspec = dict((key, specs[key]) for key in ['name', 'toolchain', 'version', 'versionsuffix'])
            error_msg = "Contents of %s does not match with filename" % path
            error_msg += "; expected filename based on contents: %s-%s.eb" % (ec['ec']['name'], found_fullver)
            error_msg += "; expected (relevant) parameters based on filename %s: %s" % (os.path.basename(path), subspec)
            raise EasyBuildError(error_msg)

    _log.info("Contents of %s verified against easyconfig filename, matches %s", path, specs)


def robot_find_subtoolchain_for_dep(dep, modtool, parent_tc=None, parent_first=False):
    """
    Find the subtoolchain to use for a dependency

    :param dep: dependency target dict (long and short module names may not exist yet)
    :param parent_tc: toolchain from which to derive the toolchain hierarchy to search (default: use dep's toolchain)
    :param parent_first: reverse order in which subtoolchains are considered: parent toolchain, then subtoolchains
    :return: minimal toolchain for which an easyconfig exists for this dependency (and matches build_options)
    """
    if parent_tc is None:
        parent_tc = dep['toolchain']

    retain_all_deps = build_option('retain_all_deps')
    use_existing_modules = build_option('use_existing_modules') and not retain_all_deps

    if parent_first or use_existing_modules:
        avail_modules = modtool.available()
    else:
        avail_modules = []

    newdep = copy.deepcopy(dep)

    # try to determine toolchain hierarchy
    # this may fail if not all easyconfig files that define this toolchain are available,
    # but that's not always fatal: it's mostly irrelevant under --review-pr for example
    try:
        toolchain_hierarchy = get_toolchain_hierarchy(parent_tc)
    except EasyBuildError as err:
        warning_msg = "Failed to determine toolchain hierarchy for %(name)s/%(version)s when determining " % parent_tc
        warning_msg += "subtoolchain for dependency '%s': %s" % (dep['name'], err)
        _log.warning(warning_msg)
        print_warning(warning_msg, silent=build_option('silent'))
        toolchain_hierarchy = []

    # start with subtoolchains first, i.e. first (system or) compiler-only toolchain, etc.,
    # unless parent toolchain should be considered first
    if parent_first:
        toolchain_hierarchy = toolchain_hierarchy[::-1]

    cand_subtcs = []

    for tc in toolchain_hierarchy:
        # try to determine module name using this particular subtoolchain;
        # this may fail if no easyconfig is available in robot search path
        # and the module naming scheme requires an easyconfig file
        newdep['toolchain'] = tc
        mod_name = ActiveMNS().det_full_module_name(newdep, require_result=False)

        # if the module name can be determined, subtoolchain is an actual candidate
        if mod_name:
            # check whether module already exists or not (but only if that info will actually be used)
            mod_exists = None
            if parent_first or use_existing_modules:
                mod_exists = mod_name in avail_modules
                # fallback to checking with modtool.exist is required,
                # for hidden modules and external modules where module name may be partial
                if not mod_exists:
                    maybe_partial = dep.get('external_module', True)
                    mod_exists = modtool.exist([mod_name], skip_avail=True, maybe_partial=maybe_partial)[0]

            # add the subtoolchain to list of candidates
            cand_subtcs.append({'toolchain': tc, 'mod_exists': mod_exists})

    _log.debug("List of possible subtoolchains for %s: %s", dep, cand_subtcs)

    cand_subtcs_with_mod = [tc for tc in cand_subtcs if tc.get('mod_exists', False)]

    # scenario I:
    # - regardless of whether minimal toolchains mode is enabled or not
    # - try to pick subtoolchain based on available easyconfigs (first hit wins)
    minimal_toolchain = None
    for cand_subtc in cand_subtcs:
        newdep['toolchain'] = cand_subtc['toolchain']
        ec_file = robot_find_easyconfig(newdep['name'], det_full_ec_version(newdep))
        if ec_file:
            minimal_toolchain = cand_subtc['toolchain']
            break

    if cand_subtcs_with_mod:
        if parent_first:
            # scenario II:
            # - parent toolchain first (minimal toolchains mode *not* enabled)
            # - module for dependency is already available for one of the subtoolchains
            # - only used as fallback in case subtoolchain could not be determined via easyconfigs (scenario I)
            # If so, we retain the subtoolchain closest to the parent (so top of the list of candidates)
            if minimal_toolchain is None or use_existing_modules:
                minimal_toolchain = cand_subtcs_with_mod[0]['toolchain']

        elif use_existing_modules:
            # scenario III:
            # - minimal toolchains mode + --use-existing-modules
            # - reconsider subtoolchain based on already available modules for dependency
            # - this may overrule subtoolchain picked in scenario II

            # take the last element, i.e. the maximum toolchain where a module exists already
            # (allows for potentially better optimisation)
            minimal_toolchain = cand_subtcs_with_mod[-1]['toolchain']

    if minimal_toolchain is None:
        _log.info("Irresolvable dependency found (even with minimal toolchains): %s", dep)

    _log.info("Minimally resolving dependency %s using toolchain %s", dep, minimal_toolchain)
    return minimal_toolchain


def det_location_for(path, target_dir, soft_name, target_file):
    """
    Determine path to easyconfigs directory for specified software name, using specified target file name.

    :param path: path of file to copy
    :param target_dir: (parent) target directory, should contain easybuild/easyconfigs subdirectory
    :param soft_name: software name (to determine location to copy to)
    :param target_file: target file name
    :return: full path to the right location
    """
    subdir = os.path.join('easybuild', 'easyconfigs')

    if os.path.exists(os.path.join(target_dir, subdir)):
        target_path = os.path.join('easybuild', 'easyconfigs', letter_dir_for(soft_name), soft_name, target_file)
        _log.debug("Target path for %s: %s", path, target_path)

        target_path = os.path.join(target_dir, target_path)

    else:
        raise EasyBuildError("Subdirectory %s not found in %s", subdir, target_dir)

    return target_path


def clean_up_easyconfigs(paths):
    """
    Clean up easyconfigs (in place) by filtering out comments/buildstats included by EasyBuild in archived easyconfigs
    (cfr. FileRepository.add_easyconfig in easybuild.tools.repository.filerepo)

    :param paths: list of paths to easyconfigs to clean up
    """
    regexs = [
        re.compile(r"^# Built with EasyBuild.*\n", re.M),
        re.compile(r"^# Build statistics.*\n", re.M),
        # consume buildstats as a whole, i.e. all lines until closing '}]'
        re.compile(r"\n*buildstats\s*=(.|\n)*\n}\]\s*\n?", re.M),
    ]

    for path in paths:
        ectxt = read_file(path)
        for regex in regexs:
            ectxt = regex.sub('', ectxt)
        write_file(path, ectxt, forced=True)


def det_file_info(paths, target_dir):
    """
    Determine useful information on easyconfig files relative to a target directory,
    before any actual operation (e.g. copying) is performed

    :param paths: list of paths to easyconfig files
    :param target_dir: target directory
    :return: dict with useful information on easyconfig files (corresponding EasyConfig instances, paths, status)
             relative to a target directory
    """
    file_info = {
        'ecs': [],
        'paths': [],
        'paths_in_repo': [],
        'new': [],
        'new_folder': [],
        'new_file_in_existing_folder': [],
    }

    for path in paths:
        ecs = process_easyconfig(path, validate=False)
        if len(ecs) == 1:
            file_info['paths'].append(path)
            file_info['ecs'].append(ecs[0]['ec'])

            soft_name = file_info['ecs'][-1].name
            ec_filename = file_info['ecs'][-1].filename()

            target_path = det_location_for(path, target_dir, soft_name, ec_filename)

            new_file = not os.path.exists(target_path)
            new_folder = not os.path.exists(os.path.dirname(target_path))
            file_info['new'].append(new_file)
            file_info['new_folder'].append(new_folder)
            file_info['new_file_in_existing_folder'].append(new_file and not new_folder)
            file_info['paths_in_repo'].append(target_path)

        else:
            raise EasyBuildError("Multiple EasyConfig instances obtained from easyconfig file %s", path)

    return file_info


def copy_easyconfigs(paths, target_dir):
    """
    Copy easyconfig files to specified directory, in the 'right' location and using the filename expected by robot.

    :param paths: list of paths to copy to git working dir
    :param target_dir: target directory
    :return: dict with useful information on copied easyconfig files (corresponding EasyConfig instances, paths, status)
    """
    file_info = det_file_info(paths, target_dir)

    for path, target_path in zip(file_info['paths'], file_info['paths_in_repo']):
        copy_file(path, target_path, force_in_dry_run=True)

    if build_option('cleanup_easyconfigs'):
        clean_up_easyconfigs(file_info['paths_in_repo'])

    return file_info


def copy_patch_files(patch_specs, target_dir):
    """
    Copy patch files to specified directory, in the 'right' location according to the software name they relate to.

    :param patch_specs: list of tuples with patch file location and name of software they are for
    :param target_dir: target directory
    """
    patched_files = {
        'paths_in_repo': [],
    }
    for patch_path, soft_name in patch_specs:
        target_path = det_location_for(patch_path, target_dir, soft_name, os.path.basename(patch_path))
        copy_file(patch_path, target_path, force_in_dry_run=True)
        patched_files['paths_in_repo'].append(target_path)

    return patched_files


def fix_deprecated_easyconfigs(paths):
    """Fix use of deprecated functionality in easyconfigs at specified locations."""

    dummy_tc_regex = re.compile(r'^toolchain\s*=\s*{.*name.*dummy.*}', re.M)

    easyconfig_paths = []
    for path in paths:
        easyconfig_paths.extend(find_easyconfigs(path))

    cnt, idx, fixed_cnt = len(easyconfig_paths), 0, 0
    for path in easyconfig_paths:
        ectxt = read_file(path)
        idx += 1
        print_msg("* [%d/%d] fixing %s... ", idx, cnt, path, prefix=False, newline=False)

        fixed = False

        # fix use of 'dummy' toolchain, use SYSTEM constant instead
        if dummy_tc_regex.search(ectxt):
            ectxt = dummy_tc_regex.sub("toolchain = SYSTEM", ectxt)
            fixed = True

        # fix use of local variables with a name other than a single letter or 'local_*'
        ec = EasyConfig(path, local_var_naming_check=LOCAL_VAR_NAMING_CHECK_LOG)
        for key in ec.unknown_keys:
            regexp = re.compile(r'\b(%s)\b' % key)
            ectxt = regexp.sub(LOCAL_VAR_PREFIX + key, ectxt)
            fixed = True

        if fixed:
            fixed_cnt += 1
            backup_path = find_backup_name_candidate(path + '.orig')
            copy_file(path, backup_path)
            write_file(path, ectxt)
            print_msg('FIXED!', prefix=False)
            print_msg("  (changes made in place, original copied to %s)", backup_path, prefix=False)
        else:
            print_msg("(no changes made)", prefix=False)

    print_msg("\nAll done! Fixed %d easyconfigs (out of %d found).\n", fixed_cnt, cnt, prefix=False)


# singleton metaclass: only one instance is created
BaseActiveMNS = create_base_metaclass('BaseActiveMNS', Singleton, object)


class ActiveMNS(BaseActiveMNS):
    """Wrapper class for active module naming scheme."""

    def __init__(self, *args, **kwargs):
        """Initialize logger."""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        # determine active module naming scheme
        avail_mnss = avail_module_naming_schemes()
        self.log.debug("List of available module naming schemes: %s" % avail_mnss.keys())
        sel_mns = get_module_naming_scheme()
        if sel_mns in avail_mnss:
            self.mns = avail_mnss[sel_mns]()
        else:
            raise EasyBuildError("Selected module naming scheme %s could not be found in %s",
                                 sel_mns, avail_mnss.keys())

    def requires_full_easyconfig(self, keys):
        """Check whether specified list of easyconfig parameters is sufficient for active module naming scheme."""
        return self.mns.requires_toolchain_details() or not self.mns.is_sufficient(keys)

    def check_ec_type(self, ec, raise_error=True):
        """
        Obtain a full parsed easyconfig file to pass to naming scheme methods if provided keys are insufficient.

        :param ec: available easyconfig parameter specifications (EasyConfig instance or dict value)
        :param raise_error: boolean indicating whether or not an error should be raised
                            if a full easyconfig is required but not found
        """
        if not isinstance(ec, EasyConfig) and self.requires_full_easyconfig(ec.keys()):

            self.log.debug("A parsed easyconfig is required by the module naming scheme, so finding one for %s" % ec)

            # fetch/parse easyconfig file if deemed necessary
            eb_file = robot_find_easyconfig(ec['name'], det_full_ec_version(ec))

            if eb_file is not None:
                parsed_ec = process_easyconfig(eb_file, parse_only=True, hidden=ec['hidden'])
                if len(parsed_ec) > 1:
                    self.log.warning("More than one parsed easyconfig obtained from %s, only retaining first" % eb_file)
                    self.log.debug("Full list of parsed easyconfigs: %s" % parsed_ec)
                ec = parsed_ec[0]['ec']

            elif raise_error:
                raise EasyBuildError("Failed to find easyconfig file '%s-%s.eb' when determining module name for: %s",
                                     ec['name'], det_full_ec_version(ec), ec)
            else:
                self.log.info("No easyconfig found as required by module naming scheme, but not considered fatal")
                ec = None

        return ec

    def _det_module_name_with(self, mns_method, ec, force_visible=False, require_result=True):
        """
        Determine module name using specified module naming scheme method, based on supplied easyconfig.
        Returns a string representing the module name, e.g. 'GCC/4.6.3', 'Python/2.7.5-ictce-4.1.13',
        with the following requirements:
            - module name is specified as a relative path
            - string representing module name has length > 0
            - module name only contains printable characters (string.printable, except carriage-control chars)
        """
        mod_name = None
        ec = self.check_ec_type(ec, raise_error=require_result)

        if ec:
            # replace software name with desired replacement (if specified)
            orig_name = None
            if ec.get('modaltsoftname', None):
                orig_name = ec['name']
                ec['name'] = ec['modaltsoftname']
                self.log.info("Replaced software name '%s' with '%s' when determining module name",
                              orig_name, ec['name'])
            else:
                self.log.debug("No alternative software name specified to determine module name with")

            mod_name = mns_method(ec)

            # restore original software name if it was tampered with
            if orig_name is not None:
                ec['name'] = orig_name

            if not is_valid_module_name(mod_name):
                raise EasyBuildError("%s is not a valid module name", str(mod_name))

            # check whether module name should be hidden or not
            # ec may be either a dict or an EasyConfig instance, 'force_visible' argument overrules
            if (ec.get('hidden', False) or getattr(ec, 'hidden', False)) and not force_visible:
                mod_name = det_hidden_modname(mod_name)

        elif require_result:
            raise EasyBuildError("Failed to determine module name for %s using %s", ec, mns_method)

        return mod_name

    def det_full_module_name(self, ec, force_visible=False, require_result=True):
        """Determine full module name by selected module naming scheme, based on supplied easyconfig."""
        self.log.debug("Determining full module name for %s (force_visible: %s)" % (ec, force_visible))
        if ec.get('external_module', False):
            # external modules have the module name readily available, and may lack the info required by the MNS
            mod_name = ec['full_mod_name']
            self.log.debug("Full module name for external module: %s", mod_name)
        else:
            mod_name = self._det_module_name_with(self.mns.det_full_module_name, ec, force_visible=force_visible,
                                                  require_result=require_result)
            self.log.debug("Obtained valid full module name %s", mod_name)
        return mod_name

    def det_install_subdir(self, ec):
        """Determine name of software installation subdirectory."""
        self.log.debug("Determining software installation subdir for %s", ec)
        if build_option('fixed_installdir_naming_scheme'):
            subdir = os.path.join(ec['name'], det_full_ec_version(ec))
            self.log.debug("Using fixed naming software installation subdir: %s", subdir)
        else:
            subdir = self.mns.det_install_subdir(self.check_ec_type(ec))
            self.log.debug("Obtained subdir %s", subdir)
        return subdir

    def det_devel_module_filename(self, ec, force_visible=False):
        """Determine devel module filename."""
        modname = self.det_full_module_name(ec, force_visible=force_visible)
        return modname.replace(os.path.sep, '-') + DEVEL_MODULE_SUFFIX

    def det_short_module_name(self, ec, force_visible=False):
        """Determine short module name according to module naming scheme."""
        self.log.debug("Determining short module name for %s (force_visible: %s)" % (ec, force_visible))
        mod_name = self._det_module_name_with(self.mns.det_short_module_name, ec, force_visible=force_visible)
        self.log.debug("Obtained valid short module name %s" % mod_name)

        # sanity check: obtained module name should pass the 'is_short_modname_for' check
        if 'modaltsoftname' in ec and not self.is_short_modname_for(mod_name, ec['modaltsoftname'] or ec['name']):
            raise EasyBuildError("is_short_modname_for('%s', '%s') for active module naming scheme returns False",
                                 mod_name, ec['name'])
        return mod_name

    def det_module_subdir(self, ec):
        """Determine module subdirectory according to module naming scheme."""
        self.log.debug("Determining module subdir for %s" % ec)
        mod_subdir = self.mns.det_module_subdir(self.check_ec_type(ec))
        self.log.debug("Obtained subdir %s" % mod_subdir)
        return mod_subdir

    def det_module_symlink_paths(self, ec):
        """
        Determine list of paths in which symlinks to module files must be created.
        """
        return self.mns.det_module_symlink_paths(ec)

    def det_modpath_extensions(self, ec):
        """Determine modulepath extensions according to module naming scheme."""
        self.log.debug("Determining modulepath extensions for %s" % ec)
        modpath_extensions = self.mns.det_modpath_extensions(self.check_ec_type(ec))
        self.log.debug("Obtained modulepath extensions: %s" % modpath_extensions)
        return modpath_extensions

    def det_user_modpath_extensions(self, ec):
        """Determine user-specific modulepath extensions according to module naming scheme."""
        self.log.debug("Determining user modulepath extensions for %s", ec)
        modpath_extensions = self.mns.det_user_modpath_extensions(self.check_ec_type(ec))
        self.log.debug("Obtained user modulepath extensions: %s", modpath_extensions)
        return modpath_extensions

    def det_init_modulepaths(self, ec):
        """Determine initial modulepaths according to module naming scheme."""
        self.log.debug("Determining initial module paths for %s" % ec)
        init_modpaths = self.mns.det_init_modulepaths(self.check_ec_type(ec))
        self.log.debug("Obtained initial module paths: %s" % init_modpaths)
        return init_modpaths

    def expand_toolchain_load(self, ec=None):
        """
        Determine whether load statements for a toolchain should be expanded to load statements for its dependencies.
        This is useful when toolchains are not exposed to users.
        """
        return self.mns.expand_toolchain_load(ec=ec)

    def is_short_modname_for(self, short_modname, name):
        """
        Determine whether the specified (short) module name is a module for software with the specified name.
        """
        return self.mns.is_short_modname_for(short_modname, name)
