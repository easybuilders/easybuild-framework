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
Easyconfig module that contains the EasyConfig class.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
"""

import copy
import difflib
import os
import re
from vsc.utils import fancylogger
from vsc.utils.missing import any, nub

import easybuild.tools.environment as env
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.filetools import decode_class_name, encode_class_name, read_file
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.module_generator import det_full_module_name as _det_full_module_name
from easybuild.tools.modules import get_software_root_env_var_name, get_software_version_env_var_name
from easybuild.tools.systemtools import check_os_dependency
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME, DUMMY_TOOLCHAIN_VERSION
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.utilities import remove_unwanted_chars
from easybuild.framework.easyconfig import MANDATORY
from easybuild.framework.easyconfig.default import DEFAULT_CONFIG, ALL_CATEGORIES, get_easyconfig_parameter_default
from easybuild.framework.easyconfig.format.convert import Dependency
from easybuild.framework.easyconfig.format.one import retrieve_blocks_in_spec
from easybuild.framework.easyconfig.licenses import EASYCONFIG_LICENSES_DICT, License
from easybuild.framework.easyconfig.parser import EasyConfigParser
from easybuild.framework.easyconfig.templates import template_constant_dict


_log = fancylogger.getLogger('easyconfig.easyconfig', fname=False)


# add license here to make it really MANDATORY (remove comment in default)
_log.deprecated('Mandatory license not enforced', '2.0')
MANDATORY_PARAMS = ['name', 'version', 'homepage', 'description', 'toolchain']

# set of configure/build/install options that can be provided as lists for an iterated build
ITERATE_OPTIONS = ['preconfigopts', 'configopts', 'prebuildopts', 'buildopts', 'preinstallopts', 'installopts']

# map of deprecated easyconfig parameters, and their replacements
DEPRECATED_OPTIONS = {
    'license': ('software_license', '2.0'),
    'makeopts': ('buildopts', '2.0'),
    'premakeopts': ('prebuildopts', '2.0'),
}


def handle_deprecated_easyconfig_parameter(ec_method):
    """Decorator to handle deprecated easyconfig parameters."""
    def new_ec_method(self, key, *args, **kwargs):
        """Map deprecated easyconfig parameters to the new correct parameter."""
        # map name of deprecated easyconfig parameter to new name
        if key in DEPRECATED_OPTIONS:
            depr_key = key
            key, ver = DEPRECATED_OPTIONS[depr_key]
            _log.deprecated("Easyconfig parameter '%s' is deprecated, use '%s' instead." % (depr_key, key), ver)

        # make sure that value for software_license has correct type, convert if needed
        if key == 'software_license':
            # key 'license' will already be mapped to 'software_license' above
            lic = self._config['software_license']
            if not isinstance(lic, License):
                self.log.deprecated('Type for software_license must to be instance of License (sub)class', '2.0')
                lic_type = type(lic)

                class LicenseLegacy(License, lic_type):
                    """A special License class to deal with legacy license paramters"""
                    DESCRICPTION = ("Internal-only, legacy closed license class to deprecate license parameter."
                                    " (DO NOT USE).")
                    HIDDEN = False

                    def __init__(self, *args):
                        if len(args) > 0:
                            lic_type.__init__(self, args[0])
                        License.__init__(self)
                lic = LicenseLegacy(lic)
                EASYCONFIG_LICENSES_DICT[lic.name] = lic
                self._config['software_license'] = lic

        return ec_method(self, key, *args, **kwargs)

    return new_ec_method


class EasyConfig(object):
    """
    Class which handles loading, reading, validation of easyconfigs
    """

    def __init__(self, path, extra_options=None, build_specs=None, validate=True):
        """
        initialize an easyconfig.
        @param path: path to easyconfig file to be parsed
        @param extra_options: dictionary with extra variables that can be set for this specific instance
        @param build_specs: dictionary of build specifications (see EasyConfig class, default: {})
        @param validate: indicates whether validation should be performed (note: combined with 'validate' build option)
        """
        self.template_values = None
        self.enable_templating = True  # a boolean to control templating

        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        if not os.path.isfile(path):
            self.log.error("EasyConfig __init__ expected a valid path")

        # use legacy module classes as default
        self.valid_module_classes = build_option('valid_module_classes')
        if self.valid_module_classes is not None:
            self.log.info("Obtained list of valid module classes: %s" % self.valid_module_classes)

        # replace the category name with the category
        self._config = {}
        for k, [def_val, descr, cat] in copy.deepcopy(DEFAULT_CONFIG).items():
            self._config[k] = [def_val, descr, ALL_CATEGORIES[cat]]

        if extra_options is None:
            name = fetch_parameter_from_easyconfig_file(path, 'name')
            easyblock = fetch_parameter_from_easyconfig_file(path, 'easyblock')
            app_class = get_easyblock_class(easyblock, name=name)
            self.extra_options = app_class.extra_options()
        else:
            self.extra_options = extra_options

        if not isinstance(self.extra_options, dict):
            if isinstance(self.extra_options, (list, tuple,)):
                typ = type(self.extra_options)
                self.log.deprecated("Specified extra_options should be of type 'dict', found type '%s'" % typ, '2.0')
                tup = (self.extra_options, type(self.extra_options))
                self.log.debug("Converting extra_options value '%s' of type '%s' to a dict" % tup)
                self.extra_options = dict(self.extra_options)
            else:
                tup = (type(self.extra_options), self.extra_options)
                self.log.error("extra_options parameter passed is of incorrect type: %s ('%s')" % tup)

        # map deprecated params to new names if they occur in extra_options
        for key, val in self.extra_options.items():
            if key in DEPRECATED_OPTIONS:
                new_key, depr_ver = DEPRECATED_OPTIONS[key]
                self.log.deprecated("Found deprecated key '%s', should use '%s' instead." % (key, new_key), depr_ver)
                self.extra_options[new_key] = self.extra_options[key]
                self.log.debug("Set '%s' with value of deprecated '%s': %s" % (new_key, key, self.extra_options[key]))
                del self.extra_options[key]
        self._config.update(self.extra_options)

        self.path = path
        self.mandatory = MANDATORY_PARAMS[:]

        # extend mandatory keys
        for key, value in self.extra_options.items():
            if value[2] == MANDATORY:
                self.mandatory.append(key)

        # set valid stops
        self.valid_stops = build_option('valid_stops')
        self.log.debug("List of valid stops obtained: %s" % self.valid_stops)

        # store toolchain
        self._toolchain = None

        self.validations = {
            'moduleclass': self.valid_module_classes,
            'stop': self.valid_stops,
        }

        # parse easyconfig file
        self.build_specs = build_specs
        self.parse()

        # handle allowed system dependencies
        self.handle_allowed_system_deps()

        # perform validations
        self.validation = build_option('validate') and validate
        if self.validation:
            self.validate(check_osdeps=build_option('check_osdeps'))

    def copy(self):
        """
        Return a copy of this EasyConfig instance.
        """
        # create a new EasyConfig instance
        ec = EasyConfig(self.path, validate=self.validation)
        # take a copy of the actual config dictionary (which already contains the extra options)
        ec._config = copy.deepcopy(self._config)

        return ec

    def update(self, key, value):
        """
        Update a string configuration value with a value (i.e. append to it).
        """
        prev_value = self[key]
        if isinstance(prev_value, basestring):
            self[key] = '%s %s ' % (prev_value, value)
        elif isinstance(prev_value, list):
            self[key] = prev_value + value
        else:
            self.log.error("Can't update configuration value for %s, because it's not a string or list." % key)

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
            self.log.error("Specifications should be specified using a dictionary, got %s" % type(self.build_specs))
        self.log.debug("Obtained specs dict %s" % arg_specs)

        parser = EasyConfigParser(self.path)
        parser.set_specifications(arg_specs)
        local_vars = parser.get_config_dict()
        self.log.debug("Parsed easyconfig as a dictionary: %s" % local_vars)

        # validate mandatory keys
        # TODO: remove this code. this is now (also) checked in the format (see validate_pyheader)
        missing_keys = [key for key in self.mandatory if key not in local_vars]
        if missing_keys:
            self.log.error("mandatory variables %s not provided in %s" % (missing_keys, self.path))

        # provide suggestions for typos
        possible_typos = [(key, difflib.get_close_matches(key.lower(), self._config.keys(), 1, 0.85))
                          for key in local_vars if key not in self._config]

        typos = [(key, guesses[0]) for (key, guesses) in possible_typos if len(guesses) == 1]
        if typos:
            self.log.error("You may have some typos in your easyconfig file: %s" %
                            ', '.join(["%s -> %s" % typo for typo in typos]))

        # we need toolchain to be set when we call _parse_dependency
        for key in ['toolchain'] + local_vars.keys():
            # validations are skipped, just set in the config
            # do not store variables we don't need
            if key in self._config.keys() + DEPRECATED_OPTIONS.keys():
                if key in ['builddependencies', 'dependencies']:
                    self[key] = [self._parse_dependency(dep) for dep in local_vars[key]]
                else:
                    self[key] = local_vars[key]
                tup = (key, self[key], type(self[key]))
                self.log.info("setting config option %s: value %s (type: %s)" % tup)

            else:
                self.log.debug("Ignoring unknown config option %s (value: %s)" % (key, local_vars[key]))

        # update templating dictionary
        self.generate_template_values()

        # indicate that this is a parsed easyconfig
        self._config['parsed'] = [True, "This is a parsed easyconfig", "HIDDEN"]

    def handle_allowed_system_deps(self):
        """Handle allowed system dependencies."""
        for (name, version) in self['allow_system_deps']:
            env.setvar(get_software_root_env_var_name(name), name)  # root is set to name, not an actual path
            env.setvar(get_software_version_env_var_name(name), version)  # version is expected to be something that makes sense

    def validate(self, check_osdeps=True):
        """
        Validate this EasyConfig
        - check certain variables
        TODO: move more into here
        """
        self.log.info("Validating easy block")
        for attr in self.validations:
            self._validate(attr, self.validations[attr])

        if check_osdeps:
            self.log.info("Checking OS dependencies")
            self.validate_os_deps()
        else:
            self.log.info("Not checking OS dependencies")

        self.log.info("Checking skipsteps")
        if not isinstance(self._config['skipsteps'][0], (list, tuple,)):
            self.log.error('Invalid type for skipsteps. Allowed are list or tuple, got %s (%s)' %
                           (type(self._config['skipsteps'][0]), self._config['skipsteps'][0]))

        self.log.info("Checking build option lists")
        self.validate_iterate_opts_lists()

        self.log.info("Checking licenses")
        self.validate_license()

    def validate_license(self):
        """Validate the license"""
        lic = self._config['software_license'][0]
        if lic is None:
            self.log.deprecated('Mandatory license not enforced', '2.0')
            # when mandatory, remove this possibility
            if 'software_license' in self.mandatory:
                self.log.error('License is mandatory')
        elif not isinstance(lic, License):
            self.log.error('License %s has to be a License subclass instance, found classname %s.' %
                           (lic, lic.__class__.__name__))
        elif not lic.name in EASYCONFIG_LICENSES_DICT:
            self.log.error('Invalid license %s (classname: %s).' % (lic.name, lic.__class__.__name__))

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
            if isinstance(dep, basestring):
                dep = (dep,)
            elif not isinstance(dep, tuple):
                self.log.error("Non-tuple value type for OS dependency specification: %s (type %s)" % (dep, type(dep)))

            if not any([check_os_dependency(cand_dep) for cand_dep in dep]):
                not_found.append(dep)

        if not_found:
            self.log.error("One or more OS dependencies were not found: %s" % not_found)
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

            # anticipate changes in available easyconfig parameters (e.g. makeopts -> buildopts?)
            if self.get(opt, None) is None:
                self.log.error("%s not available in self.cfg (anymore)?!" % opt)

            # keep track of list, supply first element as first option to handle
            if isinstance(self[opt], (list, tuple)):
                opt_counts.append((opt, len(self[opt])))

        # make sure that options that specify lists have the same length
        list_opt_lengths = [length for (opt, length) in opt_counts if length > 1]
        if len(nub(list_opt_lengths)) > 1:
            self.log.error("Build option lists for iterated build should have same length: %s" % opt_counts)

        return True

    def dependencies(self):
        """
        returns an array of parsed dependencies
        dependency = {'name': '', 'version': '', 'dummy': (False|True), 'versionsuffix': '', 'toolchain': ''}
        """
        return self['dependencies'] + self.builddependencies()

    def builddependencies(self):
        """
        return the parsed build dependencies
        """
        return self['builddependencies']

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
        if self._toolchain:
            return self._toolchain

        tcname = self['toolchain']['name']
        tc, all_tcs = search_toolchain(tcname)
        if not tc:
            all_tcs_names = ",".join([x.NAME for x in all_tcs])
            self.log.error("Toolchain %s not found, available toolchains: %s" % (tcname, all_tcs_names))
        tc = tc(version=self['toolchain']['version'])
        if self['toolchainopts'] is None:
            # set_options should always be called, even if no toolchain options are specified
            # this is required to set the default options
            tc.set_options({})
        else:
            tc.set_options(self['toolchainopts'])

        self._toolchain = tc
        return self._toolchain

    def dump(self, fp):
        """
        Dump this easyconfig to file, with the given filename.
        """
        eb_file = file(fp, "w")

        def to_str(x):
            """Return quoted version of x"""
            if isinstance(x, basestring):
                if '\n' in x or ('"' in x and "'" in x):
                    return '"""%s"""' % x
                elif "'" in x:
                    return '"%s"' % x
                else:
                    return "'%s'" % x
            else:
                return "%s" % x

        # ordered groups of keys to obtain a nice looking easyconfig file
        grouped_keys = [
                        ["name", "version", "versionprefix", "versionsuffix"],
                        ["homepage", "description"],
                        ["toolchain", "toolchainopts"],
                        ["source_urls", "sources"],
                        ["patches"],
                        ["dependencies"],
                        ["parallel", "maxparallel"],
                        ["osdependencies"]
                        ]

        # print easyconfig parameters ordered and in groups specified above
        ebtxt = []
        printed_keys = []
        for group in grouped_keys:
            for key1 in group:
                val = self._config[key1][0]
                for key2, [def_val, _, _] in DEFAULT_CONFIG.items():
                    # only print parameters that are different from the default value
                    if key1 == key2 and val != def_val:
                        ebtxt.append("%s = %s" % (key1, to_str(val)))
                        printed_keys.append(key1)
            ebtxt.append("")

        # print other easyconfig parameters at the end
        for key, [val, _, _] in DEFAULT_CONFIG.items():
            if not key in printed_keys and val != self._config[key][0]:
                ebtxt.append("%s = %s" % (key, to_str(self._config[key][0])))

        eb_file.write('\n'.join(ebtxt))
        eb_file.close()

    def _validate(self, attr, values):  # private method
        """
        validation helper method. attr is the attribute it will check, values are the possible values.
        if the value of the attribute is not in the is array, it will report an error
        """
        if values is None:
            values = []
        if self[attr] and self[attr] not in values:
            self.log.error("%s provided '%s' is not valid: %s" % (attr, self[attr], values))

    # private method
    def _parse_dependency(self, dep):
        """
        parses the dependency into a usable dict with a common format
        dep can be a dict, a tuple or a list.
        if it is a tuple or a list the attributes are expected to be in the following order:
        ('name', 'version', 'versionsuffix', 'toolchain')
        of these attributes, 'name' and 'version' are mandatory

        output dict contains these attributes:
        ['name', 'version', 'versionsuffix', 'dummy', 'toolchain', 'mod_name']
        """
        # convert tuple to string otherwise python might complain about the formatting
        self.log.debug("Parsing %s as a dependency" % str(dep))

        attr = ['name', 'version', 'versionsuffix', 'toolchain']
        dependency = {
            'dummy': False,
            'mod_name': None,  # module name
            'name': '',  # software name
            'toolchain': None,
            'version': '',
            'versionsuffix': '',
        }
        if isinstance(dep, dict):
            dependency.update(dep)
            # make sure 'dummy' key is handled appropriately
            if 'dummy' in dep and not 'toolchain' in dep:
                dependency['toolchain'] = dep['dummy']
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
            # try and convert to list
            dep = list(dep)
            dependency.update(dict(zip(attr, dep)))
        else:
            self.log.error('Dependency %s of unsupported type: %s.' % (dep, type(dep)))

        # dependency inherits toolchain, unless it's specified to have a custom toolchain
        tc = copy.deepcopy(self['toolchain'])
        tc_spec = dependency['toolchain']
        if tc_spec is not None:
            # (true) boolean value simply indicates that a dummy toolchain is used
            if isinstance(tc_spec, bool) and tc_spec:
                tc = {'name': DUMMY_TOOLCHAIN_NAME, 'version': DUMMY_TOOLCHAIN_VERSION}
            # two-element list/tuple value indicates custom toolchain specification
            elif isinstance(tc_spec, (list, tuple,)):
                if len(tc_spec) == 2:
                    tc = {'name': tc_spec[0], 'version': tc_spec[1]}
                else:
                    self.log.error("List/tuple value for toolchain should have two elements (%s)" % str(tc_spec))
            elif isinstance(tc_spec, dict):
                if 'name' in tc_spec and 'version' in tc_spec:
                    tc = copy.deepcopy(tc_spec)
                else:
                    self.log.error("Found toolchain spec as dict with required 'name'/'version' keys: %s" % tc_spec)
            else:
                self.log.error("Unsupported type for toolchain spec encountered: %s => %s" % (tc_spec, type(tc_spec)))

        dependency['toolchain'] = tc

        # make sure 'dummy' value is set correctly
        dependency['dummy'] = dependency['toolchain']['name'] == DUMMY_TOOLCHAIN_NAME

        # validations
        if not dependency['name']:
            self.log.error("Dependency specified without name: %s" % dependency)

        if not dependency['version']:
            self.log.error("Dependency specified without version: %s" % dependency)

        dependency['mod_name'] = det_full_module_name(dependency)

        return dependency

    def generate_template_values(self):
        """Try to generate all template values."""
        # TODO proper recursive code https://github.com/hpcugent/easybuild-framework/issues/474
        self._generate_template_values(skip_lower=True)
        self._generate_template_values(skip_lower=False)

    def _generate_template_values(self, ignore=None, skip_lower=True):
        """Actual code to generate the template values"""
        if self.template_values is None:
            self.template_values = {}

        # step 0. self.template_values can/should be updated from outside easyconfig
        # (eg the run_setp code in EasyBlock)

        # step 1-3 work with easyconfig.templates constants
        # use a copy to make sure the original is not touched/modified
        template_values = template_constant_dict(copy.deepcopy(self._config),
                                                 ignore=ignore, skip_lower=skip_lower)

        # update the template_values dict
        self.template_values.update(template_values)

        # cleanup None values
        for k, v in self.template_values.items():
            if v is None:
                del self.template_values[k]

    @handle_deprecated_easyconfig_parameter
    def __getitem__(self, key):
        """
        will return the value without the help text
        """
        value = self._config[key][0]
        if self.enable_templating:
            if self.template_values is None or len(self.template_values) == 0:
                self.generate_template_values()
            return resolve_template(value, self.template_values)
        else:
            return value

    @handle_deprecated_easyconfig_parameter
    def __setitem__(self, key, value):
        """
        sets the value of key in config.
        help text is untouched
        """
        self._config[key][0] = value

    def get(self, key, default=None):
        """
        Gets the value of a key in the config, with 'default' as fallback.
        """
        if key in self._config:
            return self.__getitem__(key)
        else:
            return default

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


def det_installversion(version, toolchain_name, toolchain_version, prefix, suffix):
    """Deprecated 'det_installversion' function, to determine exact install version, based on supplied parameters."""
    old_fn = 'framework.easyconfig.easyconfig.det_installversion'
    _log.deprecated('Use module_generator.det_full_ec_version instead of %s' % old_fn, '2.0')
    cfg = {
        'version': version,
        'toolchain': {'name': toolchain_name, 'version': toolchain_version},
        'versionprefix': prefix,
        'versionsuffix': suffix,
    }
    return det_full_ec_version(cfg)


def fetch_parameter_from_easyconfig_file(path, param):
    """Fetch parameter specification from given easyconfig file."""
    # check whether easyblock is specified in easyconfig file
    # note: we can't rely on value for 'easyblock' in parsed easyconfig, it may be the default value
    reg = re.compile(r"^\s*%s\s*=\s*(?P<param>\S.*)\s*$" % param, re.M)
    txt = read_file(path)
    res = reg.search(txt)
    if res:
        return res.group('param').strip("'\"")
    else:
        return None


def get_class_for(modulepath, class_name):
    """
    Get class for a given class name and easyblock module path.
    """
    # try to import specified module path, reraise ImportError if it occurs
    try:
        m = __import__(modulepath, globals(), locals(), [''])
    except ImportError, err:
        raise ImportError(err)
    # try to import specified class name from specified module path, throw ImportError if this fails
    try:
        c = getattr(m, class_name)
    except AttributeError, err:
        raise ImportError("Failed to import %s from %s: %s" % (class_name, modulepath, err))
    return c


def get_easyblock_class(easyblock, name=None):
    """
    Get class for a particular easyblock (or use default)
    """

    def_class = get_easyconfig_parameter_default('easyblock')
    def_mod_path = get_module_path(def_class, generic=True)

    try:
        if easyblock:
            # something was specified, lets parse it
            es = easyblock.split('.')
            class_name = es.pop(-1)
            # figure out if full path was specified or not
            if es:
                modulepath = '.'.join(es)
                tup = (class_name, modulepath)
                _log.info("Assuming that full easyblock module path was specified (class: %s, modulepath: %s)" % tup)
                cls = get_class_for(modulepath, class_name)
            else:
                # if we only get the class name, most likely we're dealing with a generic easyblock
                try:
                    modulepath = get_module_path(easyblock, generic=True)
                    cls = get_class_for(modulepath, class_name)
                except ImportError, err:
                    # we might be dealing with a non-generic easyblock, e.g. with --easyblock is used
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
            modulepath = get_module_path(class_name)
            if not os.path.exists("%s.py" % modulepath):
                _log.deprecated("Determine module path based on software name", "2.0")
                modulepath = get_module_path(name, decode=False)

            # try and find easyblock
            try:
                _log.debug("getting class for %s.%s" % (modulepath, class_name))
                cls = get_class_for(modulepath, class_name)
                _log.info("Successfully obtained %s class instance from %s" % (class_name, modulepath))
            except ImportError, err:

                # when an ImportError occurs, make sure that it's caused by not finding the easyblock module,
                # and not because of a broken import statement in the easyblock module
                error_re = re.compile(r"No module named %s" % modulepath.replace("easybuild.easyblocks.", ''))
                _log.debug("error regexp: %s" % error_re.pattern)
                if error_re.match(str(err)):
                    # no easyblock could be found, so fall back to default class.
                    _log.warning("Failed to import easyblock for %s, falling back to default class %s: error: %s" % \
                                (class_name, (def_mod_path, def_class), err))
                    cls = get_class_for(def_mod_path, def_class)
                else:
                    _log.error("Failed to import easyblock for %s because of module issue: %s" % (class_name, err))

        tup = (cls.__name__, easyblock, name)
        _log.info("Successfully obtained class '%s' for easyblock '%s' (software name '%s')" % tup)
        return cls

    except Exception, err:
        _log.error("Failed to obtain class for %s easyblock (not available?): %s" % (easyblock, err))


def get_module_path(name, generic=False, decode=True):
    """
    Determine the module path for a given easyblock or software name,
    based on the encoded class name.
    """
    if name is None:
        return None

    # example: 'EB_VSC_minus_tools' should result in 'vsc_tools'
    if decode:
        name = decode_class_name(name)
    module_name = remove_unwanted_chars(name.replace('-', '_')).lower()

    modpath = ['easybuild', 'easyblocks']
    if generic:
        modpath.append('generic')

    return '.'.join(modpath + [module_name])


def resolve_template(value, tmpl_dict):
    """Given a value, try to susbstitute the templated strings with actual values.
        - value: some python object (supported are string, tuple/list, dict or some mix thereof)
        - tmpl_dict: template dictionary
    """
    if isinstance(value, basestring):
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
        value = re.sub(r'(%)(?!%*\(\w+\)s)', r'\1\1', value)

        try:
            value = value % tmpl_dict
        except KeyError:
            _log.warning("Unable to resolve template value %s with dict %s" %
                             (value, tmpl_dict))
    else:
        # this block deals with references to objects and returns other references
        # for reading this is ok, but for self['x'] = {}
        # self['x']['y'] = z does not work
        # self['x'] is a get, will return a reference to a templated version of self._config['x']
        # and the ['y] = z part will be against this new reference
        # you will need to do
        # self.enable_templating = False
        # self['x']['y'] = z
        # self.enable_templating = True
        # or (direct but evil)
        # self._config['x']['y'] = z
        # it can not be intercepted with __setitem__ because the set is done at a deeper level
        if isinstance(value, list):
            value = [resolve_template(val, tmpl_dict) for val in value]
        elif isinstance(value, tuple):
            value = tuple(resolve_template(list(value), tmpl_dict))
        elif isinstance(value, dict):
            value = dict([(key, resolve_template(val, tmpl_dict)) for key, val in value.items()])

    return value


def process_easyconfig(path, build_specs=None, validate=True):
    """
    Process easyconfig, returning some information for each block
    @param path: path to easyconfig file
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    @param validate: whether or not to perform validation
    """
    blocks = retrieve_blocks_in_spec(path, build_option('only_blocks'))

    easyconfigs = []
    for spec in blocks:
        # process for dependencies and real installversionname
        _log.debug("Processing easyconfig %s" % spec)

        # create easyconfig
        try:
            ec = EasyConfig(spec, build_specs=build_specs, validate=validate)
        except EasyBuildError, err:
            msg = "Failed to process easyconfig %s:\n%s" % (spec, err.msg)
            _log.exception(msg)

        name = ec['name']

        # this app will appear as following module in the list
        easyconfig = {
            'ec': ec,
            'spec': spec,
            'module': det_full_module_name(ec),
            'dependencies': [],
            'builddependencies': [],
        }
        if len(blocks) > 1:
            easyconfig['original_spec'] = path

        # add build dependencies
        for dep in ec.builddependencies():
            _log.debug("Adding build dependency %s for app %s." % (dep, name))
            easyconfig['builddependencies'].append(dep)

        # add dependencies (including build dependencies)
        for dep in ec.dependencies():
            _log.debug("Adding dependency %s for app %s." % (dep, name))
            easyconfig['dependencies'].append(dep)

        # add toolchain as dependency too
        if ec.toolchain.name != DUMMY_TOOLCHAIN_NAME:
            dep = ec.toolchain.as_dict()
            _log.debug("Adding toolchain %s as dependency for app %s." % (dep, name))
            easyconfig['dependencies'].append(dep)

        del ec

        # this is used by the parallel builder
        easyconfig['unresolved_deps'] = copy.deepcopy(easyconfig['dependencies'])

        easyconfigs.append(easyconfig)

    return easyconfigs


def create_paths(path, name, version):
    """
    Returns all the paths where easyconfig could be located
    <path> is the basepath
    <name> should be a string
    <version> can be a '*' if you use glob patterns, or an install version otherwise
    """
    cand_paths = [
        (name, version),  # e.g. <path>/GCC/4.8.2.eb
        (name, "%s-%s" % (name, version)),  # e.g. <path>/GCC/GCC-4.8.2.eb
        (name.lower()[0], name, "%s-%s" % (name, version)),  # e.g. <path>/g/GCC/GCC-4.8.2.eb
        ("%s-%s" % (name, version),),  # e.g. <path>/GCC-4.8.2.eb
    ]
    return ["%s.eb" % os.path.join(path, *cand_path) for cand_path in cand_paths]


def robot_find_easyconfig(paths, name, version):
    """
    Find an easyconfig for module in path
    """
    if not isinstance(paths, (list, tuple)):
        paths = [paths]
    # candidate easyconfig paths
    for path in paths:
        easyconfigs_paths = create_paths(path, name, version)
        for easyconfig_path in easyconfigs_paths:
            _log.debug("Checking easyconfig path %s" % easyconfig_path)
            if os.path.isfile(easyconfig_path):
                _log.debug("Found easyconfig file for name %s, version %s at %s" % (name, version, easyconfig_path))
                return os.path.abspath(easyconfig_path)

    return None


def det_full_module_name(ec, eb_ns=False):
    """
    Determine full module name following the currently active module naming scheme.

    First try to pass 'parsed' easyconfig as supplied,
    try and find a matching easyconfig file, parse it and supply it in case of a KeyError.
    """
    try:
        mod_name = _det_full_module_name(ec, eb_ns=eb_ns)

    except KeyError, err:
        _log.debug("KeyError '%s' when determining module name for %s, trying fallback procedure..." % (err, ec))
        # for dependencies, only name/version/versionsuffix/toolchain easyconfig parameters are available;
        # when a key error occurs, try and find an easyconfig file to parse via the robot,
        # and retry with the parsed easyconfig file (which will contains a full set of keys)
        robot = build_option('robot_path')
        eb_file = robot_find_easyconfig(robot, ec['name'], det_full_ec_version(ec))
        if eb_file is None:
            _log.error("Failed to find an easyconfig file when determining module name for: %s" % ec)
        else:
            parsed_ec = process_easyconfig(eb_file)
            if len(parsed_ec) > 1:
                _log.warning("More than one parsed easyconfig obtained from %s, only retaining first" % eb_file)
            try:
                mod_name = _det_full_module_name(parsed_ec[0]['ec'], eb_ns=eb_ns)
            except KeyError, err:
                _log.error("A KeyError '%s' occured when determining a module name for %s." % parsed_ec['ec'])

    return mod_name
