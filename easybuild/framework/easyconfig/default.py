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
Easyconfig module that contains the default EasyConfig configuration parameters.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
"""
from vsc import fancylogger

from easybuild.tools.ordereddict import OrderedDict

_log = fancylogger.getLogger('easyconfig.default', fname=False)


# we use a tuple here so we can sort them based on the numbers
HIDDEN = "HIDDEN"
MANDATORY = "MANDATORY"
CUSTOM = "CUSTOM"
TOOLCHAIN = "TOOLCHAIN"
BUILD = "BUILD"
FILEMANAGEMENT = "FILEMANAGEMENT"
DEPENDENCIES = "DEPENDENCIES"
LICENSE = "LICENSE"
EXTENSIONS = "EXTENSIONS"
MODULES = "MODULES"
OTHER = "OTHER"

ALL_CATEGORIES = {
    HIDDEN: (-1, 'hidden'),
    MANDATORY: (0, 'mandatory'),
    CUSTOM: (1, 'easyblock-specific'),
    TOOLCHAIN: (2, 'toolchain'),
    BUILD: (3, 'build'),
    FILEMANAGEMENT: (4, 'file-management'),
    DEPENDENCIES: (5, 'dependencies'),
    LICENSE: (6, 'license'),
    EXTENSIONS: (7, 'extensions'),
    MODULES: (8, 'modules'),
    OTHER: (9, 'other'),
}

# List of tuples. Each tuple has the following format (key, [default, help text, category])
DEFAULT_CONFIG = {
    # MANDATORY easyconfig parameters
    'description': [None, 'A short description of the software', MANDATORY],
    'homepage': [None, 'The homepage of the software', MANDATORY],
    'name': [None, "Name of software", MANDATORY],
    'toolchain': [None, 'Name and version of toolchain', MANDATORY],
    'version': [None, "Version of software", MANDATORY],
    # TODO not yet in MANDATORY_PARAMS, so not enforced (only enforced in v2)
    'software_license': [None, 'Software license', MANDATORY],
    'software_license_urls': [None, 'List of software license locations', MANDATORY],
    # TODO not yet in MANDATORY_PARAMS, so not enforced  (only enforced in v2)
    'docurls': [None, 'List of urls with documentation of the software (not necessarily on homepage)', MANDATORY],

    # TOOLCHAIN easyconfig parameters
    'onlytcmod': [False, ('Boolean/string to indicate if the toolchain should only load '
                          'the environment with module (True) or also set all other '
                          'variables (False) like compiler CC etc (if string: comma '
                          'separated list of variables that will be ignored).'), TOOLCHAIN],
    'toolchainopts': [None, 'Extra options for compilers', TOOLCHAIN],

    # BUILD easyconfig parameters
    'checksums': [[], "Checksums for sources and patches", BUILD],
    'configopts': ['', 'Extra options passed to configure (default already has --prefix)', BUILD],
    'easyblock': ['ConfigureMake', "EasyBlock to use for building", BUILD],
    'easybuild_version': [None, "EasyBuild-version this spec-file was written for", BUILD],
    'installopts': ['', 'Extra options for installation', BUILD],
    'makeopts': ['', 'Extra options passed to make (default already has -j X)', BUILD],
    'maxparallel': [None, 'Max degree of parallelism', BUILD],
    'parallel': [None, ('Degree of parallelism for e.g. make (default: based on the number of '
                        'cores, active cpuset and restrictions in ulimit)'), BUILD],
    'patches': [[], "List of patches to apply", BUILD],
    'preconfigopts': ['', 'Extra options pre-passed to configure.', BUILD],
    'preinstallopts': ['', 'Extra prefix options for installation.', BUILD],
    'premakeopts': ['', 'Extra options pre-passed to build command.', BUILD],
    'runtest': [None, ('Indicates if a test should be run after make; should specify argument '
                       'after make (for e.g.,"test" for make test)'), BUILD],
    'sanity_check_commands': [[], ("format: [(name, options)] e.g. [('gzip','-h')]. "
                                   "Using a non-tuple is equivalent to (name, '-h')"), BUILD],
    'sanity_check_paths': [{}, ("List of files and directories to check "
                                "(format: {'files':<list>, 'dirs':<list>})"), BUILD],
    'skip': [False, "Skip existing software", BUILD],
    'skipsteps': [[], "Skip these steps", BUILD],
    'source_urls': [[], "List of URLs for source files", BUILD],
    'sources': [[], "List of source files", BUILD],
    'stop': [None, 'Keyword to halt the build process after a certain step.', BUILD],
    'tests': [[], ("List of test-scripts to run after install. A test script should return a "
                   "non-zero exit status to fail"), BUILD],
    'unpack_options': [None, "Extra options for unpacking source", BUILD],
    'unwanted_env_vars': [[], "List of environment variables that shouldn't be set during build", BUILD],
    'versionprefix': ['', ('Additional prefix for software version '
                           '(placed before version and toolchain name)'), BUILD],
    'versionsuffix': ['', 'Additional suffix for software version (placed after toolchain name)', BUILD],

    # FILEMANAGEMENT easyconfig parameters
    'buildininstalldir': [False, ('Boolean to build (True) or not build (False) in the installation directory'),
                          FILEMANAGEMENT],
    'cleanupoldbuild': [True, ('Boolean to remove (True) or backup (False) the previous build '
                               'directory with identical name or not.'), FILEMANAGEMENT],

    'cleanupoldinstall': [True, ('Boolean to remove (True) or backup (False) the previous install '
                                 'directory with identical name or not.'), FILEMANAGEMENT],
    'dontcreateinstalldir': [False, ('Boolean to create (False) or not create (True) the install directory'),
                             FILEMANAGEMENT],
    'keeppreviousinstall': [False, ('Boolean to keep the previous installation with identical '
                                    'name. Experts only!'), FILEMANAGEMENT],
    'keepsymlinks': [False, ('Boolean to determine whether symlinks are to be kept during copying '
                             'or if the content of the files pointed to should be copied'),
                     FILEMANAGEMENT],
    'start_dir': [None, ('Path to start the make in. If the path is absolute, use that path. '
                         'If not, this is added to the guessed path.'), FILEMANAGEMENT],

    # DEPENDENCIES easyconfig parameters
    'allow_system_deps': [[], "Allow listed system dependencies (format: (<name>, <version>))", DEPENDENCIES],
    'builddependencies': [[], "List of build dependencies", DEPENDENCIES],
    'dependencies': [[], "List of dependencies", DEPENDENCIES],
    'osdependencies': [[], "OS dependencies that should be present on the system", DEPENDENCIES],

    # LICENSE easyconfig parameters
    'group': [None, "Name of the user group for which the software should be available", LICENSE],
    'key': [None, 'Key for installing software', LICENSE],
    'license_file': [None, 'License file for software', LICENSE],
    'license_server': [None, 'License server for software', LICENSE],
    'license_server_port': [None, 'Port for license server', LICENSE],

    # EXTENSIONS easyconfig parameters
    'exts_classmap': [{}, "Map of extension name to class for handling build and installation.", EXTENSIONS],
    'exts_defaultclass': [None, "List of module for and name of the default extension class", EXTENSIONS],
    'exts_filter': [None, ("Extension filter details: template for cmd and input to cmd "
                           "(templates for name, version and src)."), EXTENSIONS],
    'exts_list': [[], 'List with extensions added to the base installation', EXTENSIONS],

    # MODULES easyconfig parameters
    'modextrapaths': [{}, "Extra paths to be prepended in module file", MODULES],
    'modextravars': [{}, "Extra environment variables to be added to module file", MODULES],
    'moduleclass': ['base', 'Module class to be used for this software', MODULES],
    'moduleforceunload': [False, 'Force unload of all modules when loading the extension', MODULES],
    'moduleloadnoconflict': [False, "Don't check for conflicts, unload other versions instead ", MODULES],

    # OTHER easyconfig parameters
    'buildstats': [None, "A list of dicts with build statistics", OTHER],
}


def sorted_categories():
    """
    returns the categories in the correct order
    """
    categories = ALL_CATEGORIES.values()
    categories.sort(key=lambda c: c[0])
    return categories


def convert_to_help(opts, has_default=False):
    """
    Converts the given list to a mapping of category -> [(name, help)] (OrderedDict)
        @param: has_default, if False, add the DEFAULT_CONFIG list
    """
    mapping = OrderedDict()
    if isinstance(opts, dict):
        opts = opts.items()
    if not has_default:
        defs = [(k, [def_val, descr, ALL_CATEGORIES[cat]]) for k, (def_val, descr, cat) in DEFAULT_CONFIG.items()]
        opts = defs + opts

    # sort opts
    opts.sort()

    for cat in sorted_categories():
        mapping[cat[1]] = [(opt[0], "%s (default: %s)" % (opt[1][1], opt[1][0]))
                           for opt in opts if opt[1][2] == cat]

    return mapping


def get_easyconfig_parameter_default(param):
    """Get default value for given easyconfig parameter."""
    if param not in DEFAULT_CONFIG:
        _log.error("Unkown easyconfig parameter: %s (known: %s)" % (param, sorted(DEFAULT_CONFIG.keys())))
    else:
        _log.debug("Returning default value for easyconfig parameter %s: %s" % (param, DEFAULT_CONFIG[param][0]))
        return DEFAULT_CONFIG[param][0]
