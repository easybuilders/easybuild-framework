#
# Copyright 2013-2025 Ghent University
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
#

"""
Easyconfig templates module that provides templating that can
be used within an Easyconfig file.

Authors:

* Stijn De Weirdt (Ghent University)
* Fotis Georgatos (Uni.Lu, NTUA)
* Kenneth Hoste (Ghent University)
"""
import re
import platform

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.systemtools import get_shared_lib_ext, pick_dep_version
from easybuild.tools.config import build_option


_log = fancylogger.getLogger('easyconfig.templates', fname=False)

# derived from easyconfig, but not from ._config directly
TEMPLATE_NAMES_EASYCONFIG = {
    'module_name': 'Module name',
    'nameletter': 'First letter of software name',
    'toolchain_name': 'Toolchain name',
    'toolchain_version': 'Toolchain version',
    'version_major_minor': "Major.Minor version",
    'version_major': 'Major version',
    'version_minor': 'Minor version',
}
# derived from EasyConfig._config
TEMPLATE_NAMES_CONFIG = [
    'bitbucket_account',
    'github_account',
    'name',
    'version',
    'versionsuffix',
    'versionprefix',
]
# lowercase versions of ._config
TEMPLATE_NAMES_LOWER_TEMPLATE = "%(name)slower"
TEMPLATE_NAMES_LOWER = [
    'name',
    'nameletter',
]
# values taken from the EasyBlock before each step
TEMPLATE_NAMES_EASYBLOCK_RUN_STEP = {
    'builddir': 'Build directory',
    'installdir': 'Installation directory',
    'start_dir': 'Directory in which the build process begins',
}
# software names for which to define <pref>ver, <pref>majver and <pref>shortver templates
TEMPLATE_SOFTWARE_VERSIONS = {
    # software name -> prefix for *ver, *majver and *shortver
    'CUDA': 'cuda',
    'CUDAcore': 'cuda',
    'Java': 'java',
    'Perl': 'perl',
    'Python': 'py',
    'R': 'r',
}
# template values which are only generated dynamically
TEMPLATE_NAMES_DYNAMIC = {
    'arch': 'System architecture (e.g. x86_64, aarch64, ppc64le, ...)',
    'amdgcn_capabilities': "Comma-separated list of AMDGCN capabilities, as specified via "
                           "--amdgcn-capabilities configuration option or "
                           "via amdgcn_capabilities easyconfig parameter",
    'amdgcn_cc_space_sep': "Space-separated list of AMDGCN capabilities",
    'amdgcn_cc_semicolon_sep': "Semicolon-separated list of AMDGCN capabilities",
    'cuda_compute_capabilities': "Comma-separated list of CUDA compute capabilities, as specified via "
                                 "--cuda-compute-capabilities configuration option or "
                                 "via cuda_compute_capabilities easyconfig parameter",
    'cuda_cc_cmake': 'List of CUDA compute capabilities suitable for use with $CUDAARCHS in CMake 3.18+',
    'cuda_cc_space_sep': 'Space-separated list of CUDA compute capabilities',
    'cuda_cc_space_sep_no_period':
    "Space-separated list of CUDA compute capabilities, without periods (e.g. '80 90').",
    'cuda_cc_semicolon_sep': 'Semicolon-separated list of CUDA compute capabilities',
    'cuda_int_comma_sep': 'Comma-separated list of integer CUDA compute capabilities',
    'cuda_int_space_sep': 'Space-separated list of integer CUDA compute capabilities',
    'cuda_int_semicolon_sep': 'Semicolon-separated list of integer CUDA compute capabilities',
    'cuda_sm_comma_sep': 'Comma-separated list of sm_* values that correspond with CUDA compute capabilities',
    'cuda_sm_space_sep': 'Space-separated list of sm_* values that correspond with CUDA compute capabilities',
    'mpi_cmd_prefix': 'Prefix command for running MPI programs (with default number of ranks)',
    'parallel': "Degree of parallelism for e.g. make",
    # can't be a boolean (True/False), must be a string value since it's a string template
    'rpath_enabled': "String value indicating whether or not RPATH linking is used ('true' or 'false')",
    'software_commit': "Git commit id to use for the software as specified by --software-commit command line option",
    'sysroot': "Location root directory of system, prefix for standard paths like /usr/lib and /usr/include"
               "as specify by the --sysroot configuration option",
}

# constant templates that can be used in easyconfigs
# Entry: constant -> (value, doc)
TEMPLATE_CONSTANTS = {
    # source url constants
    'APACHE_SOURCE': ('https://archive.apache.org/dist/%(namelower)s',
                      'apache.org source url'),
    'BITBUCKET_SOURCE': ('https://bitbucket.org/%(bitbucket_account)s/%(namelower)s/get',
                         'bitbucket.org source url '
                         '(namelower is used if bitbucket_account easyconfig parameter is not specified)'),
    'BITBUCKET_DOWNLOADS': ('https://bitbucket.org/%(bitbucket_account)s/%(namelower)s/downloads',
                            'bitbucket.org downloads url '
                            '(namelower is used if bitbucket_account easyconfig parameter is not specified)'),
    'CRAN_SOURCE': ('https://cran.r-project.org/src/contrib',
                    'CRAN (contrib) source url'),
    'FTPGNOME_SOURCE': ('https://ftp.gnome.org/pub/GNOME/sources/%(namelower)s/%(version_major_minor)s',
                        'http download for gnome ftp server'),
    'GITHUB_SOURCE': ('https://github.com/%(github_account)s/%(name)s/archive',
                      'GitHub source URL '
                      '(namelower is used if github_account easyconfig parameter is not specified)'),
    'GITHUB_LOWER_SOURCE': ('https://github.com/%(github_account)s/%(namelower)s/archive',
                            'GitHub source URL with lowercase name '
                            '(namelower is used if github_account easyconfig parameter is not specified)'),
    'GITHUB_RELEASE': ('https://github.com/%(github_account)s/%(name)s/releases/download/v%(version)s',
                       'GitHub release URL '
                       '(namelower is use if github_account easyconfig parameter is not specified)'),
    'GITHUB_LOWER_RELEASE': ('https://github.com/%(github_account)s/%(namelower)s/releases/download/v%(version)s',
                             'GitHub release URL with lowercase name (if github_account easyconfig '
                             'parameter is not specified, namelower is used in its place)'),
    'GNU_SAVANNAH_SOURCE': ('https://download-mirror.savannah.gnu.org/releases/%(namelower)s',
                            'download.savannah.gnu.org source url'),
    'GNU_SOURCE': ('https://ftpmirror.gnu.org/gnu/%(namelower)s',
                   'gnu.org source url (ftp mirror)'),
    'GNU_FTP_SOURCE': ('https://ftp.gnu.org/gnu/%(namelower)s',
                       'gnu.org source url (main ftp)'),
    'GOOGLECODE_SOURCE': ('http://%(namelower)s.googlecode.com/files',
                          'googlecode.com source url'),
    'LAUNCHPAD_SOURCE': ('https://launchpad.net/%(namelower)s/%(version_major_minor)s.x/%(version)s/+download/',
                         'launchpad.net source url'),
    'PYPI_SOURCE': ('https://pypi.python.org/packages/source/%(nameletter)s/%(name)s',
                    'pypi source url'),  # e.g., Cython, Sphinx
    'PYPI_LOWER_SOURCE': ('https://pypi.python.org/packages/source/%(nameletterlower)s/%(namelower)s',
                          'pypi source url (lowercase name)'),  # e.g., Greenlet, PyZMQ
    'R_SOURCE': ('https://cran.r-project.org/src/base/R-%(version_major)s',
                 'cran.r-project.org (base) source url'),
    'SOURCEFORGE_SOURCE': ('https://download.sourceforge.net/%(namelower)s',
                           'sourceforge.net source url'),
    'XORG_DATA_SOURCE': ('https://xorg.freedesktop.org/archive/individual/data/',
                         'xorg data source url'),
    'XORG_LIB_SOURCE': ('https://xorg.freedesktop.org/archive/individual/lib/',
                        'xorg lib source url'),
    'XORG_PROTO_SOURCE': ('https://xorg.freedesktop.org/archive/individual/proto/',
                          'xorg proto source url'),
    'XORG_UTIL_SOURCE': ('https://xorg.freedesktop.org/archive/individual/util/',
                         'xorg util source url'),
    'XORG_XCB_SOURCE': ('https://xorg.freedesktop.org/archive/individual/xcb/',
                        'xorg xcb source url'),

    # TODO, not urgent, yet nice to have:
    # CPAN_SOURCE GNOME KDE_I18N XCONTRIB DEBIAN KDE GENTOO TEX_CTAN MOZILLA_ALL

    # other constants
    'SHLIB_EXT': (get_shared_lib_ext(), 'extension for shared libraries'),
}

# alternative templates, and their equivalents
ALTERNATIVE_EASYCONFIG_TEMPLATES = {
    # <new>: <equivalent_template>,
    'build_dir': 'builddir',
    'cuda_cc_comma_sep': 'cuda_compute_capabilities',
    'cuda_maj_ver': 'cudamajver',
    'cuda_short_ver': 'cudashortver',
    'cuda_ver': 'cudaver',
    'install_dir': 'installdir',
    'java_maj_ver': 'javamajver',
    'java_short_ver': 'javashortver',
    'java_ver': 'javaver',
    'name_letter_lower': 'nameletterlower',
    'name_letter': 'nameletter',
    'name_lower': 'namelower',
    'perl_maj_ver': 'perlmajver',
    'perl_short_ver': 'perlshortver',
    'perl_ver': 'perlver',
    'py_maj_ver': 'pymajver',
    'py_short_ver': 'pyshortver',
    'py_ver': 'pyver',
    'r_maj_ver': 'rmajver',
    'r_short_ver': 'rshortver',
    'r_ver': 'rver',
    'toolchain_ver': 'toolchain_version',
    'ver_maj_min': 'version_major_minor',
    'ver_maj': 'version_major',
    'ver_min': 'version_minor',
    'version_prefix': 'versionprefix',
    'version_suffix': 'versionsuffix',
}

# deprecated templates, and their replacements
DEPRECATED_EASYCONFIG_TEMPLATES = {
    # <old_template>: (<new_template>, <deprecation_version>),
}

# alternative template constants, and their equivalents
ALTERNATIVE_EASYCONFIG_TEMPLATE_CONSTANTS = {
    # <new_template_constant>: <equivalent_template_constant>,
    'APACHE_URL': 'APACHE_SOURCE',
    'BITBUCKET_GET_URL': 'BITBUCKET_SOURCE',
    'BITBUCKET_DOWNLOADS_URL': 'BITBUCKET_DOWNLOADS',
    'CRAN_URL': 'CRAN_SOURCE',
    'FTP_GNOME_URL': 'FTPGNOME_SOURCE',
    'GITHUB_URL': 'GITHUB_SOURCE',
    'GITHUB_URL_LOWER': 'GITHUB_LOWER_SOURCE',
    'GITHUB_RELEASE_URL': 'GITHUB_RELEASE',
    'GITHUB_RELEASE_URL_LOWER': 'GITHUB_LOWER_RELEASE',
    'GNU_SAVANNAH_URL': 'GNU_SAVANNAH_SOURCE',
    'GNU_FTP_URL': 'GNU_FTP_SOURCE',
    'GNU_URL': 'GNU_SOURCE',
    'GOOGLECODE_URL': 'GOOGLECODE_SOURCE',
    'LAUNCHPAD_URL': 'LAUNCHPAD_SOURCE',
    'PYPI_URL': 'PYPI_SOURCE',
    'PYPI_URL_LOWER': 'PYPI_LOWER_SOURCE',
    'R_URL': 'R_SOURCE',
    'SOURCEFORGE_URL': 'SOURCEFORGE_SOURCE',
    'XORG_DATA_URL': 'XORG_DATA_SOURCE',
    'XORG_LIB_URL': 'XORG_LIB_SOURCE',
    'XORG_PROTO_URL': 'XORG_PROTO_SOURCE',
    'XORG_UTIL_URL': 'XORG_UTIL_SOURCE',
    'XORG_XCB_URL': 'XORG_XCB_SOURCE',
    'SOURCE_LOWER_TAR_GZ': 'SOURCELOWER_TAR_GZ',
    'SOURCE_LOWER_TAR_XZ': 'SOURCELOWER_TAR_XZ',
    'SOURCE_LOWER_TAR_BZ2': 'SOURCELOWER_TAR_BZ2',
    'SOURCE_LOWER_TGZ': 'SOURCELOWER_TGZ',
    'SOURCE_LOWER_TXZ': 'SOURCELOWER_TXZ',
    'SOURCE_LOWER_TBZ2': 'SOURCELOWER_TBZ2',
    'SOURCE_LOWER_TB2': 'SOURCELOWER_TB2',
    'SOURCE_LOWER_GTGZ': 'SOURCELOWER_GTGZ',
    'SOURCE_LOWER_ZIP': 'SOURCELOWER_ZIP',
    'SOURCE_LOWER_TAR': 'SOURCELOWER_TAR',
    'SOURCE_LOWER_XZ': 'SOURCELOWER_XZ',
    'SOURCE_LOWER_TAR_Z': 'SOURCELOWER_TAR_Z',
    'SOURCE_LOWER_WHL': 'SOURCELOWER_WHL',
    'SOURCE_LOWER_PY2_WHL': 'SOURCELOWER_PY2_WHL',
    'SOURCE_LOWER_PY3_WHL': 'SOURCELOWER_PY3_WHL',
}

# deprecated template constants, and their replacements
DEPRECATED_EASYCONFIG_TEMPLATE_CONSTANTS = {
    # <old_template_constant>: (<new_template_constant>, <deprecation_version>),
}

EXTENSIONS = ['tar.gz', 'tar.xz', 'tar.bz2', 'tgz', 'txz', 'tbz2', 'tb2', 'gtgz', 'zip', 'tar', 'xz', 'tar.Z']
for ext in EXTENSIONS:
    suffix = ext.replace('.', '_').upper()
    TEMPLATE_CONSTANTS.update({
        'SOURCE_%s' % suffix: ('%(name)s-%(version)s.' + ext, "Source .%s bundle" % ext),
        'SOURCELOWER_%s' % suffix: ('%(namelower)s-%(version)s.' + ext, "Source .%s bundle with lowercase name" % ext),
    })
for pyver in ('py2.py3', 'py2', 'py3'):
    if pyver == 'py2.py3':
        desc = 'Python 2 & Python 3'
        name_infix = ''
    else:
        desc = 'Python ' + pyver[-1]
        name_infix = pyver.upper() + '_'
    TEMPLATE_CONSTANTS.update({
        'SOURCE_%sWHL' % name_infix: ('%%(name)s-%%(version)s-%s-none-any.whl' % pyver,
                                      'Generic (non-compiled) %s wheel package' % desc),
        'SOURCELOWER_%sWHL' % name_infix: ('%%(namelower)s-%%(version)s-%s-none-any.whl' % pyver,
                                           'Generic (non-compiled) %s wheel package with lowercase name' % desc),
    })

# TODO derived config templates
# versionmajor, versionminor, versionmajorminor (eg '.'.join(version.split('.')[:2])) )


def template_constant_dict(config, ignore=None, toolchain=None):
    """Create a dict for templating the values in the easyconfigs.
        - config -- Dict with the structure of EasyConfig._config
        - ignore -- List of template names to ignore
    """
    if ignore is None:
        ignore = []
    # make dict
    template_values = {}

    _log.debug("config: %s", config)

    # set 'arch' for system architecture based on 'machine' (4th) element of platform.uname() return value
    template_values['arch'] = platform.uname()[4]

    # set 'rpath' template based on 'rpath' configuration option, using empty string as fallback
    template_values['rpath_enabled'] = 'true' if build_option('rpath') else 'false'

    # set 'sysroot' template based on 'sysroot' configuration option, using empty string as fallback
    template_values['sysroot'] = build_option('sysroot') or ''

    # set 'software_commit' template based on 'software_commit' configuration option, default to None
    template_values['software_commit'] = build_option('software_commit') or ''

    # step 1: add TEMPLATE_NAMES_EASYCONFIG
    for name in TEMPLATE_NAMES_EASYCONFIG:
        if name in ignore:
            continue

        # check if this template name is already handled
        if template_values.get(name) is not None:
            continue

        if name.startswith('toolchain_'):
            tc = config.get('toolchain')
            if tc is not None:
                template_values['toolchain_name'] = tc.get('name', None)
                template_values['toolchain_version'] = tc.get('version', None)
                # only go through this once
                ignore.extend(['toolchain_name', 'toolchain_version'])

        elif name.startswith('version_'):
            # parse major and minor version numbers
            version = config['version']
            if version is not None:

                _log.debug("version found in easyconfig is %s", version)
                version = version.split('.')
                try:
                    major = version[0]
                    template_values['version_major'] = major
                    minor = version[1]
                    template_values['version_minor'] = minor
                    template_values['version_major_minor'] = '.'.join([major, minor])
                except IndexError:
                    # if there is no minor version, skip it
                    pass
                # only go through this once
                ignore.extend(['version_major', 'version_minor', 'version_major_minor'])

        elif name.endswith('letter'):
            # parse first letters
            if name.startswith('name'):
                softname = config['name']
                if softname is not None:
                    template_values['nameletter'] = softname[0]

        elif name == 'module_name':
            template_values['module_name'] = getattr(config, 'short_mod_name', None)

        else:
            raise EasyBuildError("Undefined name %s from TEMPLATE_NAMES_EASYCONFIG", name)

    # step 2: define *ver and *shortver templates
    name_to_prefix = {name.lower(): prefix for name, prefix in TEMPLATE_SOFTWARE_VERSIONS.items()}
    deps = config.get('dependencies', [])

    # also consider build dependencies for *ver and *shortver templates;
    # we need to be a bit careful here, because for iterative installations
    # (when multi_deps is used for example) the builddependencies value may be a list of lists

    # first, determine if we have an EasyConfig instance
    # (indirectly by checking for 'iterating' and 'iterate_options' attributes,
    #  because we can't import the EasyConfig class here without introducing
    #  a cyclic import...);
    # we need to know to determine whether we're iterating over a list of build dependencies
    is_easyconfig = hasattr(config, 'iterating') and hasattr(config, 'iterate_options')
    if is_easyconfig:
        # if we're iterating over different lists of build dependencies,
        # only consider build dependencies when we're actually in iterative mode!
        if 'builddependencies' in config.iterate_options:
            if config.iterating:
                build_deps = config.get('builddependencies')
            else:
                build_deps = None
        else:
            build_deps = config.get('builddependencies')
        if build_deps:
            # Don't use += to avoid changing original list
            deps = deps + build_deps
        # include all toolchain deps (e.g. CUDAcore component in fosscuda);
        # access Toolchain instance via _toolchain to avoid triggering initialization of the toolchain!
        if config._toolchain is not None and config._toolchain.tcdeps:
            # If we didn't create a new list above do it here
            if build_deps:
                deps.extend(config._toolchain.tcdeps)
            else:
                deps = deps + config._toolchain.tcdeps

    for dep in deps:
        if isinstance(dep, dict):
            dep_name, dep_version = dep['name'], dep['version']

            # take into account dependencies marked as external modules,
            # where name/version may have to be harvested from metadata available for that external module
            if dep.get('external_module', False):
                metadata = dep.get('external_module_metadata', {})
                if dep_name is None:
                    # name is a list in metadata, just take first value (if any)
                    dep_name = metadata.get('name', [None])[0]
                if dep_version is None:
                    # version is a list in metadata, just take first value (if any)
                    dep_version = metadata.get('version', [None])[0]

        elif isinstance(dep, (list, tuple)):
            dep_name, dep_version = dep[0], dep[1]
        else:
            raise EasyBuildError("Unexpected type for dependency: %s", dep)

        if isinstance(dep_name, str) and dep_version:
            pref = name_to_prefix.get(dep_name.lower())
            if pref:
                dep_version = pick_dep_version(dep_version)
                template_values['%sver' % pref] = dep_version
                dep_version_parts = dep_version.split('.')
                template_values['%smajver' % pref] = dep_version_parts[0]
                if len(dep_version_parts) > 1:
                    template_values['%sminver' % pref] = dep_version_parts[1]
                template_values['%sshortver' % pref] = '.'.join(dep_version_parts[:2])

    # step 3: add remaining from config
    for name in TEMPLATE_NAMES_CONFIG:
        if name in ignore:
            continue
        if name in config:
            template_values[name] = config[name]
            _log.debug('name: %s, config: %s', name, config[name])

    # step 4. make lower variants
    for name in TEMPLATE_NAMES_LOWER:
        if name in ignore:
            continue

        value = config.get(name) or template_values.get(name)

        if value is None:
            continue
        try:
            template_values[TEMPLATE_NAMES_LOWER_TEMPLATE % {'name': name}] = value.lower()
        except Exception:
            _log.warning("Failed to get .lower() for name %s value %s (type %s)", name, value, type(value))

    # keep track of names of defined templates until now,
    # so we can check whether names of additional dynamic template values are all known
    common_template_names = set(template_values.keys())

    # step 5. add additional conditional templates
    if toolchain is not None and hasattr(toolchain, 'mpi_cmd_prefix'):
        try:
            # get prefix for commands to be run with mpi runtime using default number of ranks
            mpi_cmd_prefix = toolchain.mpi_cmd_prefix()
            if mpi_cmd_prefix is not None:
                template_values['mpi_cmd_prefix'] = mpi_cmd_prefix
        except EasyBuildError as err:
            # don't fail just because we couldn't resolve this template
            _log.warning("Failed to create mpi_cmd_prefix template, error was:\n%s", err)

    # step 6. CUDA compute capabilities
    #         Use the commandline / easybuild config option if given, else use the value from the EC (as a default)
    cuda_cc = build_option('cuda_compute_capabilities') or config.get('cuda_compute_capabilities')
    if cuda_cc:
        template_values['cuda_compute_capabilities'] = ','.join(cuda_cc)
        template_values['cuda_cc_space_sep'] = ' '.join(cuda_cc)
        template_values['cuda_cc_space_sep_no_period'] = ' '.join(cc.replace('.', '') for cc in cuda_cc)
        template_values['cuda_cc_semicolon_sep'] = ';'.join(cuda_cc)
        template_values['cuda_cc_cmake'] = ';'.join(cc.replace('.', '') for cc in cuda_cc)
        int_values = [cc.replace('.', '') for cc in cuda_cc]
        template_values['cuda_int_comma_sep'] = ','.join(int_values)
        template_values['cuda_int_space_sep'] = ' '.join(int_values)
        template_values['cuda_int_semicolon_sep'] = ';'.join(int_values)
        sm_values = ['sm_' + cc.replace('.', '') for cc in cuda_cc]
        template_values['cuda_sm_comma_sep'] = ','.join(sm_values)
        template_values['cuda_sm_space_sep'] = ' '.join(sm_values)

    # step 7. AMDGCN capabilities
    #         Use the commandline / easybuild config option if given, else use the value from the EC (as a default)
    amdgcn_cc = build_option('amdgcn_capabilities') or config.get('amdgcn_capabilities')
    if amdgcn_cc:
        template_values['amdgcn_capabilities'] = ','.join(amdgcn_cc)
        template_values['amdgcn_cc_space_sep'] = ' '.join(amdgcn_cc)
        template_values['amdgcn_cc_semicolon_sep'] = ';'.join(amdgcn_cc)

    unknown_names = []
    for key in template_values:
        if not (key in common_template_names or key in TEMPLATE_NAMES_DYNAMIC):
            unknown_names.append(key)
    if unknown_names:
        raise EasyBuildError("One or more template values found with unknown name: %s", ','.join(unknown_names))

    return template_values


def to_template_str(key, value, templ_const, templ_val):
    """
    Insert template values where possible

    :param key: name of easyconfig parameter
    :param value: string representing easyconfig parameter value
    :param templ_const: dictionary of template strings (constants)
    :param templ_val: (ordered) dictionary of template strings specific for this easyconfig file
    """
    old_value = None
    while value != old_value:
        old_value = value
        # check for constant values
        for tval, tname in templ_const.items():
            if tval in value:
                value = re.sub(r'(^|\W)' + re.escape(tval) + r'(\W|$)', r'\1' + tname + r'\2', value)

        for tval, tname in templ_val.items():
            # only replace full words with templates: word to replace should be at the beginning of a line
            # or be preceded by a non-alphanumeric (\W). It should end at the end of a line or be succeeded
            # by another non-alphanumeric;
            # avoid introducing self-referencing easyconfig parameter value
            # by taking into account given name of easyconfig parameter ('key')
            if tval in value and tname != key:
                value = re.sub(r'(^|\W)' + re.escape(tval) + r'(\W|$)', r'\1%(' + tname + r')s\2', value)

            # special case of %(pyshortver)s, where we should template 'python2.7' to 'python%(pyshortver)s'
            if tname == 'pyshortver' and ('python' + tval) in value:
                value = re.sub(r'(^|\W)python' + re.escape(tval) + r'(\W|$)', r'\1python%(' + tname + r')s\2', value)

    return value


def template_documentation():
    """Generate the templating documentation"""
    # This has to reflect the methods/steps used in easyconfig _generate_template_values
    indent_l0 = " " * 2
    indent_l1 = indent_l0 + " " * 2
    doc = []

    # step 1: add TEMPLATE_NAMES_EASYCONFIG
    doc.append('Template names/values derived from easyconfig instance')
    for name, cur_doc in TEMPLATE_NAMES_EASYCONFIG.items():
        doc.append("%s%%(%s)s: %s" % (indent_l1, name, cur_doc))

    # step 2: add *ver/*shortver templates for software listed in TEMPLATE_SOFTWARE_VERSIONS
    doc.append("Template names/values for (short) software versions")
    for name, prefix in TEMPLATE_SOFTWARE_VERSIONS.items():
        doc.append("%s%%(%smajver)s: major version for %s" % (indent_l1, prefix, name))
        doc.append("%s%%(%sshortver)s: short version for %s (<major>.<minor>)" % (indent_l1, prefix, name))
        doc.append("%s%%(%sver)s: full version for %s" % (indent_l1, prefix, name))

    # step 3: add remaining self._config
    doc.append('Template names/values as set in easyconfig')
    for name in TEMPLATE_NAMES_CONFIG:
        doc.append("%s%%(%s)s" % (indent_l1, name))

    # step 4. make lower variants
    doc.append('Lowercase values of template values')
    for name in TEMPLATE_NAMES_LOWER:
        namelower = TEMPLATE_NAMES_LOWER_TEMPLATE % {'name': name}
        doc.append("%s%%(%s)s: lower case of value of %s" % (indent_l1, namelower, name))

    # step 5. self.template_values can/should be updated from outside easyconfig
    # (eg the run_setp code in EasyBlock)
    doc.append('Template values set outside EasyBlock runstep')
    for name, cur_doc in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP.items():
        doc.append("%s%%(%s)s: %s" % (indent_l1, name, cur_doc))

    doc.append('Template constants that can be used in easyconfigs')
    for name, (value, cur_doc) in TEMPLATE_CONSTANTS.items():
        doc.append('%s%s: %s (%s)' % (indent_l1, name, cur_doc, value))

    return "\n".join(doc)


# Add template constants to export list
globals().update({name: value for name, (value, _) in TEMPLATE_CONSTANTS.items()})
__all__ = list(TEMPLATE_CONSTANTS.keys())
