# #
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
Easyconfig module that contains the EasyConfig class.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
"""

import copy
import difflib
import os
import re
from vsc import fancylogger
from vsc.utils.missing import nub

import easybuild.tools.environment as env
from easybuild.tools.filetools import run_cmd
from easybuild.tools.modules import get_software_root_env_var_name, get_software_version_env_var_name
from easybuild.tools.systemtools import get_shared_lib_ext
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.framework.easyconfig.default import DEFAULT_CONFIG, ALL_CATEGORIES
from easybuild.framework.easyconfig.constants import EASYCONFIG_CONSTANTS
from easybuild.framework.easyconfig.licenses import EASYCONFIG_LICENSES_DICT, License
from easybuild.framework.easyconfig.templates import TEMPLATE_CONSTANTS, template_constant_dict


_log = fancylogger.getLogger('easyconfig.easyconfig', fname=False)


# add license here to make it really MANDATORY (remove comment in default)
_log.deprecated('Mandatory license not enforced', '2.0')
MANDATORY_PARAMS = ['name', 'version', 'homepage', 'description', 'toolchain']

# set of configure/build/install options that can be provided as lists for an iterated build
ITERATE_OPTIONS = ['preconfigopts', 'configopts', 'premakeopts', 'makeopts', 'preinstallopts', 'installopts']


class EasyConfig(object):
    """
    Class which handles loading, reading, validation of easyconfigs
    """

    def __init__(self, path, extra_options=None, validate=True, valid_module_classes=None, valid_stops=None):
        """
        initialize an easyconfig.
        path should be a path to a file that can be parsed
        extra_options is a dict of extra variables that can be set in this specific instance
        validate specifies whether validations should happen
        """

        self.template_values = None
        self.enable_templating = True  # a boolean to control templating

        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.valid_module_classes = None
        if valid_module_classes:
            self.valid_module_classes = valid_module_classes
            self.log.info("Obtained list of valid module classes: %s" % self.valid_module_classes)
        else:
            self.valid_module_classes = ['base', 'compiler', 'lib']  # legacy module classes

        # replace the category name with the category
        self._config = {}
        for k, [def_val, descr, cat] in copy.deepcopy(DEFAULT_CONFIG).items():
            self._config[k] = [def_val, descr, ALL_CATEGORIES[cat]]

        if extra_options is None:
            extra_options = {}
        elif isinstance(extra_options, (list, tuple,)):
            # TODO legacy behaviour. should be more strictly enforced. do we log here?
            extra_options = dict(extra_options)

        self._legacy_license(extra_options)

        self._config.update(extra_options)

        self.path = path
        self.mandatory = MANDATORY_PARAMS[:]

        # extend mandatory keys
        for key, value in extra_options.items():
            if value[2] == ALL_CATEGORIES['MANDATORY']:
                self.mandatory.append(key)

        # set valid stops
        self.valid_stops = []
        if valid_stops:
            self.valid_stops = valid_stops
            self.log.debug("List of valid stops obtained: %s" % self.valid_stops)

        # store toolchain
        self._toolchain = None

        if not os.path.isfile(path):
            self.log.error("EasyConfig __init__ expected a valid path")

        self.validations = {
                            'moduleclass': self.valid_module_classes,
                            'stop': self.valid_stops,
                            }

        # parse easyconfig file
        self.parse(path)

        # handle allowed system dependencies
        self.handle_allowed_system_deps()

        # perform validations
        self.validation = validate
        if self.validation:
            self.validate()

    def _legacy_license(self, extra_options):
        """Function to help migrate away from old custom license parameter to new mandatory one"""
        self.log.deprecated('_legacy_license does not have to be checked', '2.0')
        if 'license' in extra_options:
            lic = extra_options['license']
            if not isinstance(lic, License):
                self.log.deprecated('license type has to be License subclass', '2.0')
                typ_lic = type(lic)

                class LicenseLegacy(License, typ_lic):
                    """A special License class to deal with legacy license paramters"""
                    DESCRICPTION = ("Internal-only, legacy closed license class to deprecate license parameter."
                                    " (DO NOT USE).")
                    HIDDEN = False

                    def __init__(self, *args):
                        if len(args) > 0:
                            typ_lic.__init__(self, args[0])
                        License.__init__(self)
                lic = LicenseLegacy(lic)
                EASYCONFIG_LICENSES_DICT[lic.name] = lic
                extra_options['license'] = lic

    def copy(self):
        """
        Return a copy of this EasyConfig instance.
        """
        # create a new EasyConfig instance
        ec = EasyConfig(self.path, extra_options={}, validate=self.validation, valid_stops=self.valid_stops,
                        valid_module_classes=copy.deepcopy(self.valid_module_classes))
        # take a copy of the actual config dictionary (which already contains the extra options)
        ec._config = copy.deepcopy(self._config)

        return ec

    def update(self, key, value):
        """
        Update a string configuration value with a value (i.e. append to it).
        """
        prev_value = self[key]
        if not isinstance(prev_value, basestring):
            self.log.error("Can't update configuration value for %s, because it's not a string." % key)

        self[key] = '%s %s ' % (prev_value, value)

    def parse(self, path):
        """
        Parse the file and set options
        mandatory requirements are checked here
        """
        global_vars = {"shared_lib_ext": get_shared_lib_ext()}
        const_dict = build_easyconfig_constants_dict()
        global_vars.update(const_dict)
        local_vars = {}

        try:
            execfile(path, global_vars, local_vars)
        except IOError, err:
            self.log.exception("Unexpected IOError during execfile(): %s" % err)
        except SyntaxError, err:
            self.log.exception("SyntaxError in easyblock %s: %s" % (path, err))

        # validate mandatory keys
        missing_keys = [key for key in self.mandatory if key not in local_vars]
        if missing_keys:
            self.log.error("mandatory variables %s not provided in %s" % (missing_keys, path))

        # provide suggestions for typos
        possible_typos = [(key, difflib.get_close_matches(key.lower(), self._config.keys(), 1, 0.85))
                          for key in local_vars if key not in self._config]

        typos = [(key, guesses[0]) for (key, guesses) in possible_typos if len(guesses) == 1]
        if typos:
            self.log.error("You may have some typos in your easyconfig file: %s" %
                            ', '.join(["%s -> %s" % typo for typo in typos]))

        self._legacy_license(local_vars)

        for key in local_vars:
            # validations are skipped, just set in the config
            # do not store variables we don't need
            if key in self._config:
                self[key] = local_vars[key]
                self.log.info("setting config option %s: value %s" % (key, self[key]))

            else:
                self.log.debug("Ignoring unknown config option %s (value: %s)" % (key, local_vars[key]))

    def handle_allowed_system_deps(self):
        """Handle allowed system dependencies."""
        for (name, version) in self['allow_system_deps']:
            env.setvar(get_software_root_env_var_name(name), name)  # root is set to name, not an actual path
            env.setvar(get_software_version_env_var_name(name), version)  # version is expected to be something that makes sense

    def validate(self):
        """
        Validate this EasyConfig
        - check certain variables
        TODO: move more into here
        """
        self.log.info("Validating easy block")
        for attr in self.validations:
            self._validate(attr, self.validations[attr])

        self.log.info("Checking OS dependencies")
        self.validate_os_deps()

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
        lic = self._config['license'][0]
        if lic is None:
            self.log.deprecated('Mandatory license not enforced', '2.0')
            # when mandatory, remove this possibility
            if 'license' in self.mandatory:
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
            if not self._os_dependency_check(dep):
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
        dependency = {'name': '', 'version': '', 'dummy': (False|True), 'suffix': ''}
        """

        deps = []

        for dep in self['dependencies']:
            deps.append(self._parse_dependency(dep))

        return deps + self.builddependencies()

    def builddependencies(self):
        """
        return the parsed build dependencies
        """
        deps = []

        for dep in self['builddependencies']:
            deps.append(self._parse_dependency(dep))

        return deps

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
        if self['toolchainopts']:
            tc.set_options(self['toolchainopts'])

        self._toolchain = tc
        return self._toolchain

    def get_installversion(self):
        """
        return the installation version
        """
        return det_installversion(self['version'], self.toolchain.name, self.toolchain.version,
                                  self['versionprefix'], self['versionsuffix'])

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
        if self[attr] and self[attr] not in values:
            self.log.error("%s provided '%s' is not valid: %s" % (attr, self[attr], values))

    # private method
    def _os_dependency_check(self, dep):
        """
        Check if dependency is available from OS.
        """
        # - uses rpm -q and dpkg -s --> can be run as non-root!!
        # - fallback on which
        # - should be extended to files later?
        if run_cmd('which rpm', simple=True, log_ok=False):
            cmd = "rpm -q %s" % dep
        elif run_cmd('which dpkg', simple=True, log_ok=False):
            cmd = "dpkg -s %s" % dep
        else:
            cmd = "exit 1"

        found = run_cmd(cmd, simple=True, log_all=False, log_ok=False)

        if not found:
            # fallback for when os-dependency is a binary/library
            cmd = 'which %(dep)s || locate --regexp "/%(dep)s$"' % {'dep': dep}

            found = run_cmd(cmd, simple=True, log_all=False, log_ok=False)

        return found

    # private method
    def _parse_dependency(self, dep):
        """
        parses the dependency into a usable dict with a common format
        dep can be a dict, a tuple or a list.
        if it is a tuple or a list the attributes are expected to be in the following order:
        ['name', 'version', 'suffix', 'dummy']
        of these attributes, 'name' and 'version' are mandatory

        output dict contains these attributes:
        ['name', 'version', 'suffix', 'dummy', 'tc']
        """
        # convert tuple to string otherwise python might complain about the formatting
        self.log.debug("Parsing %s as a dependency" % str(dep))

        attr = ['name', 'version', 'suffix', 'dummy']
        dependency = {'name': '', 'version': '', 'suffix': '', 'dummy': False}
        if isinstance(dep, dict):
            dependency.update(dep)
        # Try and convert to list
        elif isinstance(dep, (list, tuple)):
            dep = list(dep)
            dependency.update(dict(zip(attr, dep)))
        else:
            self.log.error('Dependency %s from unsupported type: %s.' % (dep, type(dep)))

        # Validations
        if not dependency['name']:
            self.log.error("Dependency without name given")

        if not dependency['version']:
            self.log.error('Dependency without version.')

        if not 'tc' in dependency:
            dependency['tc'] = self.toolchain.get_dependency_version(dependency)

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
        template_values = template_constant_dict(self._config.copy(),
                                                 ignore=ignore, skip_lower=skip_lower)

        # update the template_values dict
        self.template_values.update(template_values)

        # cleanup None values
        for k, v in self.template_values.items():
            if v is None:
                del self.template_values[k]

    def _resolve_template(self, value):
        """Given a value, try to susbstitute the templated strings with actual values.
            - value: some python object (supported are string, tuple/list, dict or some mix thereof)
        """
        if self.template_values is None or len(self.template_values) == 0:
            self.generate_template_values()

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
                value = value % self.template_values
            except KeyError:
                self.log.warning("Unable to resolve template value %s with dict %s" %
                                 (value, self.template_values))
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
                value = [self._resolve_template(val) for val in value]
            elif isinstance(value, tuple):
                value = tuple(self._resolve_template(list(value)))
            elif isinstance(value, dict):
                value = dict([(key, self._resolve_template(val)) for key, val in value.items()])

        return value

    def __getitem__(self, key):
        """
        will return the value without the help text
        """
        value = self._config[key][0]
        if self.enable_templating:
            return self._resolve_template(value)
        else:
            return value

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


def build_easyconfig_constants_dict():
    """Make a dictionary with all constants that can be used"""
    # sanity check
    all_consts = [
                  (dict([(x[0], x[1]) for x in TEMPLATE_CONSTANTS]), 'TEMPLATE_CONSTANTS'),
                  (dict([(x[0], x[1]) for x in EASYCONFIG_CONSTANTS]), 'EASYCONFIG_CONSTANTS'),
                  (EASYCONFIG_LICENSES_DICT, 'EASYCONFIG_LICENSES')
                  ]
    err = []
    const_dict = {}

    for (csts, name) in all_consts:
        for cst_key, cst_val in csts.items():
            ok = True
            for (other_csts, other_name) in all_consts:
                if name == other_name:
                    continue
                if cst_key in other_csts:
                    err.append('Found name %s from %s also in %s' % (cst_key, name, other_name))
                    ok = False
            if ok:
                const_dict[cst_key] = cst_val

    if len(err) > 0:
        _log.error("EasyConfig constants sanity check failed: %s" % ("\n".join(err)))
    else:
        return const_dict


def det_installversion(version, toolchain_name, toolchain_version, prefix, suffix):
    """
    Determine exact install version, based on supplied parameters.
    e.g. 1.2.3-goalf-1.1.0-no-OFED or 1.2.3 (for dummy toolchains)
    """

    installversion = None

    # determine main install version based on toolchain
    if toolchain_name == 'dummy':
        installversion = version
    else:
        installversion = "%s-%s-%s" % (version, toolchain_name, toolchain_version)

    # prepend/append prefix/suffix
    installversion = ''.join([x for x in [prefix, installversion, suffix] if x])

    return installversion


