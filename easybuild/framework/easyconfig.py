##
# Copyright 2009-2012 Ghent University
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
# Copyright 2012 Toon Willems
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

import copy
import difflib
import glob
import os
import re
import sys
import tempfile
from distutils.version import LooseVersion

from easybuild.tools.build_log import EasyBuildError, get_log
from easybuild.tools.systemtools import get_shared_lib_ext
from easybuild.tools.filetools import run_cmd
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.toolchain.utilities import search_toolchain

# we use a tuple here so we can sort them based on the numbers
MANDATORY = (0, 'mandatory')
CUSTOM = (1, 'easyblock-specific')
TOOLCHAIN = (2, 'toolchain')
BUILD = (3, 'build')
FILEMANAGEMENT = (4, 'file-management')
DEPENDENCIES = (5, 'dependencies')
LICENSE = (6, 'license')
EXTENSIONS = (7, 'extensions')
MODULES = (8, 'modules')
OTHER = (9, 'other')


class EasyConfig(object):
    """
    Class which handles loading, reading, validation of easyconfigs
    """

    # List of tuples. Each tuple has the following format (key, [default, help text, category])
    default_config = [
          ('name', [None, "Name of software", MANDATORY]),
          ('version', [None, "Version of software", MANDATORY]),
          ('toolchain', [None, 'Name and version of toolchain', MANDATORY]),
          ('description', [None, 'A short description of the software', MANDATORY]),
          ('homepage', [None, 'The homepage of the software', MANDATORY]),

          ('toolchainopts', ['', 'Extra options for compilers', TOOLCHAIN]),
          ('onlytcmod', [False, 'Boolean/string to indicate if the toolchain should only load ' \
                                'the environment with module (True) or also set all other ' \
                                'variables (False) like compiler CC etc (if string: comma ' \
                                'separated list of variables that will be ignored).', TOOLCHAIN]),

          ('easybuild_version', [None, "EasyBuild-version this spec-file was written for", BUILD]),
          ('versionsuffix', ['', 'Additional suffix for software version (placed after toolchain name)', BUILD]),
          ('versionprefix', ['', 'Additional prefix for software version ' \
                                 '(placed before version and toolchain name)', BUILD]),
          ('runtest', [None, 'Indicates if a test should be run after make; should specify argument after make ' \
                             '(for e.g.,"test" for make test)', BUILD]),
          ('preconfigopts', ['', 'Extra options pre-passed to configure.', BUILD]),
          ('configopts', ['', 'Extra options passed to configure (default already has --prefix)', BUILD]),
          ('premakeopts', ['', 'Extra options pre-passed to build command.', BUILD]),
          ('makeopts', ['', 'Extra options passed to make (default already has -j X)', BUILD]),
          ('preinstallopts', ['', 'Extra prefix options for installation.', BUILD]),
          ('installopts', ['', 'Extra options for installation', BUILD]),
          ('unpack_options', [None, "Extra options for unpacking source", BUILD]),
          ('stop', [None, 'Keyword to halt the build process after a certain step.', BUILD]),
          ('skip', [False, "Skip existing software", BUILD]),
          ('parallel', [None, 'Degree of parallelism for e.g. make (default: based on the number of ' \
                              'cores and restrictions in ulimit)', BUILD]),
          ('maxparallel', [None, 'Max degree of parallelism', BUILD]),
          ('sources', [[], "List of source files", BUILD]),
          ('source_urls', [[], "List of URLs for source files", BUILD]),
          ('patches', [[], "List of patches to apply", BUILD]),
          ('tests', [[], "List of test-scripts to run after install. A test script should return a " \
                         "non-zero exit status to fail", BUILD]),
          ('sanity_check_paths', [{}, "List of files and directories to check (format: {'files':<list>, " \
                                    "'dirs':<list>})", BUILD]),
          ('sanity_check_commands', [[], "format: [(name, options)] e.g. [('gzip','-h')]. " \
                                       "Using a non-tuple is equivalent to (name, '-h')", BUILD]),

          ('start_dir', [None, 'Path to start the make in. If the path is absolute, use that path. ' \
                               'If not, this is added to the guessed path.', FILEMANAGEMENT]),
          ('keeppreviousinstall', [False, 'Boolean to keep the previous installation with identical ' \
                                          'name. Experts only!', FILEMANAGEMENT]),
          ('cleanupoldbuild', [True, 'Boolean to remove (True) or backup (False) the previous build ' \
                                     'directory with identical name or not.', FILEMANAGEMENT]),
          ('cleanupoldinstall', [True, 'Boolean to remove (True) or backup (False) the previous install ' \
                                       'directory with identical name or not.',
                                       FILEMANAGEMENT]),
          ('dontcreateinstalldir', [False, 'Boolean to create (False) or not create (True) the install ' \
                                           'directory', FILEMANAGEMENT]),
          ('keepsymlinks', [False, 'Boolean to determine whether symlinks are to be kept during copying ' \
                                   'or if the content of the files pointed to should be copied',
                                   FILEMANAGEMENT]),

          ('dependencies', [[], "List of dependencies", DEPENDENCIES]),
          ('builddependencies', [[], "List of build dependencies", DEPENDENCIES]),
          ('osdependencies', [[], "OS dependencies that should be present on the system", DEPENDENCIES]),

          ('license_server', [None, 'License server for software', LICENSE]),
          ('license_serverPort', [None, 'Port for license server', LICENSE]),
          ('key', [None, 'Key for installing software', LICENSE]),
          ('group', [None, "Name of the user group for which the software should be available",  LICENSE]),

          ('exts_list', [[], 'List with extensions added to the base installation', EXTENSIONS]),
          ('exts_defaultclass', [None, "List of module for and name of the default extension class",
                                 EXTENSIONS]),
          ('exts_classmap', [{}, "Map of extension name to class for handling build and installation.",
                             EXTENSIONS]),
          ('exts_filter', [None, "Extension filter details: template for cmd and input to cmd " \
                                 "(templates for name, version and src).", EXTENSIONS]),

          ('modextravars', [{}, "Extra environment variables to be added to module file", MODULES]),
          ('moduleclass', ['base', 'Module class to be used for this software', MODULES]),
          ('moduleforceunload', [False, 'Force unload of all modules when loading the extension', MODULES]),
          ('moduleloadnoconflict', [False, "Don't check for conflicts, unload other versions instead ", MODULES]),

          ('buildstats', [None, "A list of dicts with build statistics", OTHER]),
        ]

    def __init__(self, path, extra_options=[], validate=True, valid_module_classes=None, valid_stops=None):
        """
        initialize an easyconfig.
        path should be a path to a file that can be parsed
        extra_options is a dict of extra variables that can be set in this specific instance
        validate specifies whether validations should happen
        """

        self.log = get_log("EasyConfig")

        self.valid_module_classes = None
        if valid_module_classes:
            self.valid_module_classes = valid_module_classes
            self.log.info("Obtained list of valid module classes: %s" % self.valid_module_classes)
        else:
            self.valid_module_classes = ['base', 'compiler', 'lib']  # legacy module classes

        # perform a deepcopy of the default_config found in the easybuild.tools.easyblock module
        self.config = dict(copy.deepcopy(self.default_config))
        self.config.update(extra_options)
        self.path = path
        self.mandatory = ['name', 'version', 'homepage', 'description', 'toolchain']

        # extend mandatory keys
        for (key, value) in extra_options:
            if value[2] == MANDATORY:
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
                            'stop': self.valid_stops
                           }

        self.parse(path)

        # perform validations
        self.validation = validate
        if self.validation:
            self.validate()

    def copy(self):
        """
        Return a copy of this EasyConfig instance.
        """
        # create a new EasyConfig instance
        ec = EasyConfig(self.path, extra_options={}, validate=self.validation, valid_stops=self.valid_stops,
                        valid_module_classes=copy.deepcopy(self.valid_module_classes))
        # take a copy of the actual config dictionary (which already contains the extra options)
        ec.config = dict(copy.deepcopy(self.config))

        return ec

    def update(self, key, value):
        """
        Update a string configuration value with a value (i.e. append to it).
        """
        prev_value = self[key]
        if not type(prev_value) == str:
            self.log.error("Can't update configuration value for %s, because it's not a string." % key)

        self[key] = '%s %s ' % (prev_value, value)

    def parse(self, path):
        """
        Parse the file and set options
        mandatory requirements are checked here
        """
        global_vars = {"shared_lib_ext": get_shared_lib_ext()}
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
        possible_typos = [(key, difflib.get_close_matches(key.lower(), self.config.keys(), 1, 0.85))
                          for key in local_vars if key not in self.config]

        typos = [(key, guesses[0]) for (key, guesses) in possible_typos if len(guesses) == 1]
        if typos:
            self.log.error("You may have some typos in your easyconfig file: %s" %
                            ', '.join(["%s -> %s" % typo for typo in typos]))

        for key in local_vars:
            # validations are skipped, just set in the config
            # do not store variables we don't need
            if key in self.config:
                self[key] = local_vars[key]
                self.log.info("setting config option %s: value %s" % (key, self[key]))

            else:
                self.log.debug("Ignoring unknown config option %s (value: %s)" % (key, local_vars[key]))

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
            all_tcs_names = ",".join([x.__name__ for x in all_tcs])
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
            if type(x) == str:
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
                val = self.config[key1][0]
                for (key2, [def_val, _, _]) in self.default_config:
                    # only print parameters that are different from the default value
                    if key1 == key2 and val != def_val:
                        ebtxt.append("%s = %s" % (key1, to_str(val)))
                        printed_keys.append(key1)
            ebtxt.append("")

        # print other easyconfig parameters at the end
        for (key, [val, _, _]) in self.default_config:
            if not key in printed_keys and val != self.config[key][0]:
                ebtxt.append("%s = %s" % (key, to_str(self.config[key][0])))

        eb_file.write('\n'.join(ebtxt))
        eb_file.close()

    def _validate(self, attr, values):     # private method
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
        elif isinstance(dep, list) or isinstance(dep, tuple):
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

    def __getitem__(self, key):
        """
        will return the value without the help text
        """
        return self.config[key][0]

    def __setitem__(self, key, value):
        """
        sets the value of key in config.
        help text is untouched
        """
        self.config[key][0] = value


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

def sorted_categories():
    """
    returns the categories in the correct order
    """
    categories = [MANDATORY, CUSTOM , TOOLCHAIN, BUILD, FILEMANAGEMENT,
                  DEPENDENCIES, LICENSE , EXTENSIONS, MODULES, OTHER]
    categories.sort(key = lambda c: c[0])
    return categories

def convert_to_help(opts):
    """
    Converts the given list to a mapping of category -> [(name, help)] (OrderedDict)
    """
    mapping = OrderedDict()

    for cat in sorted_categories():
        mapping[cat[1]] = [(opt[0], "%s (default: %s)" % (opt[1][1], opt[1][0]))
                           for opt in opts if opt[1][2] == cat]

    return mapping

def ec_filename_for(path):
    """
    Return a suiting file name for the easyconfig file at <path>,
    as determined by its contents.
    """
    ec = EasyConfig(path, validate=False)

    fn = "%s-%s.eb" % (ec['name'], det_installversion(ec['version'], ec['toolchain']['name'],
                                                      ec['toolchain']['version'], ec['versionprefix'],
                                                      ec['versionsuffix']))

    return fn

def pick_version(req_ver, avail_vers, log):
    """Pick version based on an optionally desired version and available versions.

    If a desired version is specifed, the most recent version that is less recent
    than the desired version will be picked; else, the most recent version will be picked.

    This function returns both the version to be used, which is equal to the desired version
    if it was specified, and the version picked that matches that closest.
    """

    if not avail_vers:
        log.error("Empty list of available versions passed.")

    selected_ver = None
    if req_ver:
        # if a desired version is specified,
        # retain the most recent version that's less recent than the desired version

        ver = req_ver

        if len(avail_vers) == 1:
            selected_ver = avail_vers[0]
        else:
            retained_vers = [v for v in avail_vers if v < LooseVersion(ver)]
            if retained_vers:
                selected_ver = retained_vers[-1]
            else:
                # if no versions are available that are less recent, take the least recent version
                selected_ver = sorted([LooseVersion(v) for v in avail_vers])[0]

    else:
        # if no desired version is specified, just use last version
        ver = avail_vers[-1]
        selected_ver = ver

    return (ver, selected_ver)

def create_paths(path, name, version):
    """
    Returns all the paths where easyconfig could be located
    <path> is the basepath
    <name> should be a string
    <version> can be a '*' if you use glob patterns, or an install version otherwise
    """
    return [os.path.join(path, name, version + ".eb"),
            os.path.join(path, name, "%s-%s.eb" % (name, version)),
            os.path.join(path, name.lower()[0], name, "%s-%s.eb" % (name, version)),
            os.path.join(path, "%s-%s.eb" % (name, version)),
           ]

def obtain_ec_for(specs, ecs_path, fp, log):
    """
    Obtain an easyconfig file to the given specifications.

    Either select between available ones, or use the best suited available one
    to generate a new easyconfig file.

    <ecs_path> is a path where easyconfig files can be found
    <fp> is the desired file name
    <log> is an EasyBuildLog instance
    """

    # ensure that at least name is specified
    if not specs.get('name'):
        log.error("Supplied 'specs' dictionary doesn't even contain a name of a software package?")

    # collect paths to search in
    paths = []
    if ecs_path:
        paths.append(ecs_path)

    if not paths:
        log.error("No paths to look for easyconfig files, specify a path with --robot.")

    # create glob patterns based on supplied info

    # figure out the install version
    installver = det_installversion(specs.get('version', '*'), specs.get('toolchain_name', '*'),
                                    specs.get('toolchain_version', '*'), specs.get('versionprefix', '*'),
                                    specs.get('versionsuffix', '*'))

    # find easyconfigs that match a pattern
    easyconfig_files = []
    for path in paths:
        patterns = create_paths(path, specs['name'], installver)
        for pattern in patterns:
            easyconfig_files.extend(glob.glob(pattern))

    cnt = len(easyconfig_files)

    log.debug("List of obtained easyconfig files (%d): %s" % (cnt, easyconfig_files))

    # select best easyconfig, or try to generate one that fits the requirements
    res = select_or_generate_ec(fp, paths, specs, log)

    if res:
        return res
    else:
        log.error("No easyconfig found for requested software, and also failed to generate one.")

def select_or_generate_ec(fp, paths, specs, log):
    """
    Select or generate an easyconfig file with the given requirements, from existing easyconfig files.

    If easyconfig files are available for the specified software package,
    then this function will first try to determine which toolchain to use.
     * if a toolchain is given, it will use it (possible using a template easyconfig file as base);
     * if not, and only a single toolchain is available, is will assume it can use that toolchain
     * else, it fails -- EasyBuild doesn't select between multiple available toolchains

    Next, it will trim down the selected easyconfig files to a single one,
    based on the following requirements (in order of preference):
     * toolchain version
     * software version
     * other parameters (e.g. versionprefix, versionsuffix, etc.)

    If a complete match is found, it will return that easyconfig.
    Else, it will generate a new easyconfig file based on the selected 'best matching' easyconfig file.
    """

    specs = copy.deepcopy(specs)

    # ensure that at least name is specified
    if not specs.get('name'):
        log.error("Supplied 'specs' dictionary doesn't even contain a name of a software package?")
    name = specs['name']
    handled_params = ['name']

    # find ALL available easyconfig files for specified software
    ec_files = []
    installver = det_installversion('*', 'dummy', '*', '*', '*')
    for path in paths:
        patterns = create_paths(path, name, installver)
        for pattern in patterns:
            ec_files.extend(glob.glob(pattern))

    # we need at least one config file to start from
    if len(ec_files) == 0:
        # look for a template file if no easyconfig for specified software name is available
        for path in paths:
            templ_file = os.path.join(path, "TEMPLATE.eb")

            if os.path.isfile(templ_file):
                ec_files = [templ_file]
                break
            else:
                log.debug("No template found at %s." % templ_file)

        if len(ec_files) == 0:
            log.error("No easyconfig files found for software %s, and no templates available. I'm all out of ideas." % name)

    log.debug("ec_files: %s" % ec_files)

    # we can't rely on set, because we also need to be able to obtain a list of unique lists
    def unique(l):
        """Retain unique elements in a sorted list."""
        l = sorted(l)
        if len(l) > 1:
            l2 = [l[0]]
            for x in l:
                if not x == l2[-1]:
                    l2.append(x)
            return l2
        else:
            return l

    ecs_and_files = [(EasyConfig(f, validate=False), f) for f in ec_files]

    # TOOLCHAIN NAME

    # determine list of unique toolchain names
    tcnames = unique([x[0]['toolchain']['name'] for x in ecs_and_files])
    log.debug("Found %d unique toolchain names: %s" % (len(tcnames), tcnames))

    # if a toolchain was selected, and we have no easyconfig files for it, try and use a template
    if specs.get('toolchain_name') and not specs['toolchain_name'] in tcnames:
        if "TEMPLATE" in tcnames:
            log.info("No easyconfig file for specified toolchain, but template is available.")
        else:
            log.error("No easyconfig file for %s with toolchain %s, " \
                      "and no template available." % (name, specs['toolchain_name']))

    tcname = specs.pop('toolchain_name', None)
    handled_params.append('toolchain_name')

    # trim down list according to selected toolchain
    if tcname in tcnames:
        # known toolchain, so only retain those
        selected_tcname = tcname
    else:
        if len(tcnames) == 1 and not tcnames[0] == "TEMPLATE":
            # only one (non-template) toolchain availble, so use that
            tcname = tcnames[0]
            selected_tcname = tcname
        elif len(tcnames) == 1 and tcnames[0] == "TEMPLATE":
            selected_tcname = tcnames[0]
        else:
            # fall-back: use template toolchain if a toolchain name was specified
            if tcname:
                selected_tcname = "TEMPLATE"
            else:
                # if multiple toolchains are available, and none is specified, we quit
                # we can't just pick one, how would we prefer one over the other?
                log.error("No toolchain name specified, and more than one available: %s." % tcnames)

    ecs_and_files = [x for x in ecs_and_files if x[0]['toolchain']['name'] == selected_tcname]

    log.debug("Filtered easyconfigs: %s" % [x[1] for x in ecs_and_files])

    # TOOLCHAIN VERSION

    tcvers = unique([x[0]['toolchain']['version'] for x in ecs_and_files])
    log.debug("Found %d unique toolchain versions: %s" % (len(tcvers), tcvers))

    tcver = specs.pop('toolchain_version', None)
    handled_params.append('toolchain_version')
    (tcver, selected_tcver) = pick_version(tcver, tcvers, log)

    log.debug("Filtering easyconfigs based on toolchain version '%s'..." % selected_tcver)
    ecs_and_files = [x for x in ecs_and_files if x[0]['toolchain']['version'] == selected_tcver]
    log.debug("Filtered easyconfigs: %s" % [x[1] for x in ecs_and_files])

    # add full toolchain specification to specs
    if tcname and tcver:
        specs.update({'toolchain': {'name': tcname, 'version': tcver}})
        handled_params.append('toolchain')
    else:
        if tcname:
            specs.update({'toolchain_name': tcname})
        if tcver:
            specs.update({'toolchain_version': tcver})

    # SOFTWARE VERSION

    vers = unique([x[0]['version'] for x in ecs_and_files])
    log.debug("Found %d unique software versions: %s" % (len(vers), vers))

    ver = specs.pop('version', None)
    handled_params.append('version')
    (ver, selected_ver) = pick_version(ver, vers, log)
    if ver:
        specs.update({'version': ver})

    log.debug("Filtering easyconfigs based on software version '%s'..." % selected_ver)
    ecs_and_files = [x for x in ecs_and_files if x[0]['version'] == selected_ver]
    log.debug("Filtered easyconfigs: %s" % [x[1] for x in ecs_and_files])

    # go through parameters specified via --amend
    # always include versionprefix/suffix, because we might need it to generate a file name
    verpref = None
    versuff = None
    other_params = {'versionprefix': None, 'versionsuffix': None}
    for (param, val) in specs.items():
        if not param in handled_params:
            other_params.update({param: val})

    log.debug("Filtering based on other parameters (specified via --amend): %s" % other_params)
    for (param, val) in other_params.items():

        if param in ecs_and_files[0][0].config:
            vals = unique([x[0][param] for x in ecs_and_files])
        else:
            vals = []

        filter_ecs = False
        # try and select a value from the available ones, or fail if we can't
        if val in vals:
            # if the specified value is available, use it
            selected_val = val
            log.debug("Specified %s is available, so using it: %s" % (param, selected_val))
            filter_ecs = True
        elif val:
            # if a value is specified, use that, even if it's not available yet
            selected_val = val
            log.debug("%s is specified, so using it (even though it's not available yet): %s" % (param, selected_val))
        elif len(vals) == 1:
            # if only one value is available, use that
            selected_val = vals[0]
            log.debug("Only one %s available ('%s'), so picking that" % (param, selected_val))
            filter_ecs = True
        else:
            # otherwise, we fail, because we don't know how to pick between different fixes
            log.error("No %s specified, and can't pick from available %ses %s" % (param,
                                                                                  param,
                                                                                  vals))

        if filter_ecs:
            log.debug("Filtering easyconfigs based on %s '%s'..." % (param, selected_val))
            ecs_and_files = [x for x in ecs_and_files if x[0][param] == selected_val]
            log.debug("Filtered easyconfigs: %s" % [x[1] for x in ecs_and_files])

        # keep track of versionprefix/suffix
        if param == "versionprefix":
            verpref = selected_val
        elif param == "versionsuffix":
            versuff = selected_val

    cnt = len(ecs_and_files)
    if not cnt == 1:
        fs = [x[1] for x in ecs_and_files]
        log.error("Failed to select a single easyconfig from available ones, %s left: %s" % (cnt, fs))

    else:

        (selected_ec, selected_ec_file) = ecs_and_files[0]

        # check whether selected easyconfig matches requirements
        match = True
        for (key, val) in specs.items():
            if key in selected_ec.config:
                # values must be equal to hve a full match
                if not selected_ec[key] == val:
                    match = False
            else:
                # if we encounter a key that is not set in the selected easyconfig, we don't have a full match
                match = False

        # if it matches, no need to tweak
        if match:
            log.info("Perfect match found: %s" % selected_ec_file)
            return (False, selected_ec_file)

        # GENERATE

        # if no file path was specified, generate a file name
        if not fp:
            installver = det_installversion(ver, tcname, tcver, verpref, versuff)
            fp= "%s-%s.eb" % (name, installver)

        # generate tweaked easyconfig file
        tweak(selected_ec_file, fp, specs, log)

        log.info("Generated easyconfig file %s, and using it to build the requested software." % fp)

        return (True, fp)

def tweak(src_fn, target_fn, tweaks, log):
    """
    Tweak an easyconfig file with the given list of tweaks, using replacement via regular expressions.
    Note: this will only work 'well-written' easyconfig files, i.e. ones that e.g. set the version
    once and then use the 'version' variable to construct the list of sources, and possibly other
    parameters that depend on the version (e.g. list of patch files, dependencies, version suffix, ...)

    The tweaks should be specified in a dictionary, with parameters and keys that map to the values
    to be set.

    Reads easyconfig file at path <src_fn>, and writes the tweaked easyconfig file to <target_fn>.

    If no target filename is provided, a target filepath is generated based on the contents of
    the tweaked easyconfig file.
    """

    # read easyconfig file
    ectxt = None
    try:
        f = open(src_fn, "r")
        ectxt = f.read()
        f.close()
    except IOError, err:
        log.error("Failed to read easyconfig file %s: %s" % (src_fn, err))

    log.debug("Contents of original easyconfig file, prior to tweaking:\n%s" % ectxt)

    # determine new toolchain if it's being changed
    keys = tweaks.keys()
    if 'toolchain_name' in keys or 'toolchain_version' in keys:

        tc_regexp = re.compile("^\s*toolchain\s*=\s*(.*)$", re.M)

        res = tc_regexp.search(ectxt)
        if not res:
            log.error("No toolchain found in easyconfig file %s?" % src_fn)

        toolchain = eval(res.group(1))

        for key in ['name', 'version']:
            tc_key = "toolchain_%s" % key
            if tc_key in keys:
                toolchain.update({key: tweaks[tc_key]})
                tweaks.pop(tc_key)

        tweaks.update({'toolchain': {'name': toolchain['name'], 'version': toolchain['version']}})

        log.debug("New toolchain constructed: %s" % tweaks['toolchain'])

    additions = []

    # we need to treat list values seperately, i.e. we prepend to the current value (if any)
    for (key, val) in tweaks.items():

        if type(val) == list:

            regexp = re.compile("^\s*%s\s*=\s*(.*)$" % key, re.M)

            res = regexp.search(ectxt)
            if res:
                newval = "%s + %s" % (val, res.group(1))
                ectxt = regexp.sub("%s = %s # tweaked by EasyBuild (was: %s)" % (key, newval, res.group(1)), ectxt)
                log.info("Tweaked %s list to '%s'" % (key, newval))
            else:
                additions.append("%s = %s # added by EasyBuild" % (key, val))

            tweaks.pop(key)

    def quoted(x):
        """Obtain a new value to be used in string replacement context.

        For non-string values, it just returns the exact same value.

        For string values, it tries to escape the string in quotes, e.g.,
        foo becomes 'foo', foo'bar becomes "foo'bar",
        foo'bar"baz becomes \"\"\"foo'bar"baz\"\"\", etc.
        """
        if type(x) == str:
            if "'" in x and '"' in x:
                return '"""%s"""' % x
            elif "'" in x:
                return '"%s"' % x
            else:
                return "'%s'" % x
        else:
            return x

    # add parameters or replace existing ones
    for (key,val) in tweaks.items():

        regexp = re.compile("^\s*%s\s*=\s*(.*)$" % key, re.M)
        log.debug("Regexp pattern for replacing '%s': %s" % (key, regexp.pattern))

        res = regexp.search(ectxt)
        if res:
            # only tweak if the value is different
            diff = True
            try:
                log.debug("eval(%s): %s" % (res.group(1), eval(res.group(1))))
                diff = not eval(res.group(1)) == val
            except (NameError, SyntaxError):
                # if eval fails, just fall back to string comparison
                log.debug("eval failed for \"%s\", falling back to string comparison against \"%s\"..." % (res.group(1), val))
                diff = not res.group(1) == val

            if diff:
                ectxt = regexp.sub("%s = %s # tweaked by EasyBuild (was: %s)" % (key, quoted(val), res.group(1)), ectxt)
                log.info("Tweaked '%s' to '%s'" % (key, quoted(val)))
        else:
            additions.append("%s = %s" % (key, quoted(val)))


    if additions:
        log.info("Adding additional parameters to tweaked easyconfig file: %s")
        ectxt += "\n\n# added by EasyBuild as dictated by command line options\n"
        ectxt += '\n'.join(additions) + '\n'

    log.debug("Contents of tweaked easyconfig file:\n%s" % ectxt)

    # come up with suiting file name for tweaked easyconfig file if none was specified
    if not target_fn:

        fn = None

        try:
            # obtain temporary filename
            fd, tmpfn = tempfile.mkstemp()
            os.close(fd)

            # write easyconfig to temporary file
            f = open(tmpfn, "w")
            f.write(ectxt)
            f.close()

            # determine suiting filename
            fn = ec_filename_for(tmpfn)

            # get rid of temporary file
            os.remove(tmpfn)

        except (IOError, OSError), err:
            log.error("Failed to determine suiting filename for tweaked easyconfig file: %s" % err)

        target_fn = os.path.join(tempfile.gettempdir(), fn)
        log.debug("Generated file name for tweaked easyconfig file: %s" % target_fn)

    # write out tweaked easyconfig file
    try:
        f = open(target_fn, "w")
        f.write(ectxt)
        f.close()
        log.info("Tweaked easyconfig file written to %s" % target_fn)
    except IOError, err:
        log.error("Failed to write tweaked easyconfig file to %s: %s" % (target_fn, err))

    return target_fn

def get_paths_for(log, subdir="easyconfigs", robot_path=None):
    """
    Return a list of absolute paths where the specified subdir can be found, determined by the PYTHONPATH
    """

    paths = []

    # primary search path is robot path
    path_list = []
    if not robot_path is None:
        path_list.append(robot_path)

    # consider Python search path, e.g. setuptools install path for easyconfigs
    path_list.extend(sys.path)

    # figure out installation prefix, e.g. distutils install path for easyconfigs
    (out, ec) = run_cmd("which eb", simple=False)
    if ec:
        log.warning("eb not found (%s), failed to determine installation prefix" % out)
    else:
        # eb should reside in <install_prefix>/bin/eb
        install_prefix = os.path.dirname(os.path.dirname(out))
        path_list.append(install_prefix)
        log.debug("Also considering installation prefix %s..." % install_prefix)

    # look for desired subdirs
    for path in path_list:
        path = os.path.join(path, "easybuild", subdir)
        log.debug("Looking for easybuild/%s in path %s" % (subdir, path))
        try:
            if os.path.exists(path):
                paths.append(os.path.abspath(path))
                log.debug("Added %s to list of paths for easybuild/%s" % (path, subdir))
        except OSError, err:
            raise EasyBuildError(str(err))

    return paths

def stats_to_str(stats, log):
    """
    Pretty print build statistics to string.
    """
    if not (type(stats) == OrderedDict or type(stats) == dict):
        log.error("Can only pretty print build stats in dictionary form, not of type %s" % type(stats))

    txt = "{\n"

    pref = "    "

    def tostr(x):
        if type(x) == str:
            return "'%s'" % x
        else:
            return str(x)

    for (k,v) in stats.items():
        txt += "%s%s: %s,\n" % (pref, tostr(k), tostr(v))

    txt += "}"
    return txt
