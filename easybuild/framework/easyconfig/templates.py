#
# Copyright 2013-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
#

"""
Easyconfig templates module that provides templating that can
be used within an Easyconfig file.

@author: Stijn De Weirdt (Ghent University)
@author: Fotis Georgatos (Uni.Lu, NTUA)
"""
import re
from vsc.utils import fancylogger
from distutils.version import LooseVersion

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.systemtools import get_shared_lib_ext


_log = fancylogger.getLogger('easyconfig.templates', fname=False)

# derived from easyconfig, but not from ._config directly
TEMPLATE_NAMES_EASYCONFIG = [
    ('nameletter', "First letter of software name"),
    ('toolchain_name', "Toolchain name"),
    ('toolchain_version', "Toolchain version"),
    ('version_major_minor', "Major.Minor version"),
    ('version_major', "Major version"),
    ('version_minor', "Minor version"),
]
# derived from EasyConfig._config
TEMPLATE_NAMES_CONFIG = [
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
TEMPLATE_NAMES_EASYBLOCK_RUN_STEP = [
    ('installdir', "Installation directory"),
    ('builddir', "Build directory"),
]
# software names for which to define <pref>ver and <pref>shortver templates
TEMPLATE_SOFTWARE_VERSIONS = [
    # software name, prefix for *ver and *shortver
    ('Java', 'java'),
    ('Perl', 'perl'),
    ('Python', 'py'),
    ('R', 'r'),
]
# constant templates that can be used in easyconfigs
TEMPLATE_CONSTANTS = [
    # source url constants
    ('APACHE_SOURCE', 'http://archive.apache.org/dist/%(namelower)s',
     'apache.org source url'),
    ('BITBUCKET_SOURCE', 'http://bitbucket.org/%(namelower)s/%(namelower)s/get',
     'bitbucket.org source url'),
    ('BITBUCKET_DOWNLOADS', 'http://bitbucket.org/%(namelower)s/%(namelower)s/downloads',
     'bitbucket.org downloads url'),
    ('CRAN_SOURCE', 'http://cran.r-project.org/src/contrib',
     'CRAN (contrib) source url'),
    ('FTPGNOME_SOURCE', 'http://ftp.gnome.org/pub/GNOME/sources/%(namelower)s/%(version_major_minor)s',
     'http download for gnome ftp server'),
    ('GNU_SAVANNAH_SOURCE', 'http://download-mirror.savannah.gnu.org/releases/%(namelower)s',
     'download.savannah.gnu.org source url'),
    ('GNU_SOURCE', 'http://ftpmirror.gnu.org/%(namelower)s',
     'gnu.org source url'),
    ('GOOGLECODE_SOURCE', 'http://%(namelower)s.googlecode.com/files',
     'googlecode.com source url'),
    ('LAUNCHPAD_SOURCE', 'https://launchpad.net/%(namelower)s/%(version_major_minor)s.x/%(version)s/+download/',
     'launchpad.net source url'),
    ('PYPI_SOURCE', 'https://pypi.python.org/packages/source/%(nameletter)s/%(name)s',
     'pypi source url'),  # e.g., Cython, Sphinx
    ('PYPI_LOWER_SOURCE', 'https://pypi.python.org/packages/source/%(nameletterlower)s/%(namelower)s',
     'pypi source url (lowercase name)'),  # e.g., Greenlet, PyZMQ
    ('R_SOURCE', 'http://cran.r-project.org/src/base/R-%(version_major)s',
     'cran.r-project.org (base) source url'),
    ('SOURCEFORGE_SOURCE', 'http://download.sourceforge.net/%(namelower)s',
     'sourceforge.net source url'),
    ('XORG_DATA_SOURCE', 'http://xorg.freedesktop.org/archive/individual/data/',
     'xorg data source url'),
    ('XORG_LIB_SOURCE', 'http://xorg.freedesktop.org/archive/individual/lib/',
     'xorg lib source url'),
    ('XORG_PROTO_SOURCE', 'http://xorg.freedesktop.org/archive/individual/proto/',
     'xorg proto source url'),
    ('XORG_UTIL_SOURCE', 'http://xorg.freedesktop.org/archive/individual/util/',
     'xorg util source url'),
    ('XORG_XCB_SOURCE', 'http://xorg.freedesktop.org/archive/individual/xcb/',
     'xorg xcb source url'),

    # TODO, not urgent, yet nice to have:
    # CPAN_SOURCE GNOME KDE_I18N XCONTRIB DEBIAN KDE GENTOO TEX_CTAN MOZILLA_ALL

    # other constants
    ('SHLIB_EXT', get_shared_lib_ext(), 'extension for shared libraries'),
]

extensions = ['tar.gz', 'tar.xz', 'tar.bz2', 'tgz', 'txz', 'tbz2', 'tb2', 'gtgz', 'zip', 'tar', 'xz', 'tar.Z']
for ext in extensions:
    suffix = ext.replace('.', '_').upper()
    TEMPLATE_CONSTANTS += [
        ('SOURCE_%s' % suffix, '%(name)s-%(version)s.' + ext, "Source .%s bundle" % ext),
        ('SOURCELOWER_%s' % suffix, '%(namelower)s-%(version)s.' + ext, "Source .%s bundle with lowercase name" % ext),
    ]

# TODO derived config templates
# versionmajor, versionminor, versionmajorminor (eg '.'.join(version.split('.')[:2])) )


def template_constant_dict(config, ignore=None, skip_lower=True):
    """Create a dict for templating the values in the easyconfigs.
        - config is a dict with the structure of EasyConfig._config
    """
    # TODO find better name
    # ignore
    if ignore is None:
        ignore = []

    # make dict
    template_values = {}

    _log.debug("config: %s", config)

    # step 1: add TEMPLATE_NAMES_EASYCONFIG
    for name in TEMPLATE_NAMES_EASYCONFIG:
        if name in ignore:
            continue

        # check if this template name is already handled
        if template_values.get(name[0]) is not None:
            continue

        if name[0].startswith('toolchain_'):
            tc = config.get('toolchain')[0]
            if tc is not None:
                template_values['toolchain_name'] = tc.get('name', None)
                template_values['toolchain_version'] = tc.get('version', None)
                # only go through this once
                ignore.extend(['toolchain_name', 'toolchain_version'])

        elif name[0].startswith('version_'):
            # parse major and minor version numbers
            version = config['version'][0]
            if version is not None:

                _log.debug("version found in easyconfig is %s", version)
                version = LooseVersion(version).version
                try:
                    major = str(version[0])
                    template_values['version_major'] = major
                    minor = str(version[1])
                    template_values['version_minor'] = minor
                    template_values['version_major_minor'] = ".".join([major, minor])
                except IndexError:
                    # if there is no minor version, skip it
                    pass
                # only go through this once
                ignore.extend(['version_major', 'version_minor', 'version_major_minor'])

        elif name[0].endswith('letter'):
            # parse first letters
            if name[0].startswith('name'):
                softname = config['name'][0]
                if softname is not None:
                    template_values['nameletter'] = softname[0]
        else:
            raise EasyBuildError("Undefined name %s from TEMPLATE_NAMES_EASYCONFIG", name)

    # step 2: define *ver and *shortver templates
    for name, pref in TEMPLATE_SOFTWARE_VERSIONS:
        for dep in config['dependencies'][0]:
            if isinstance(dep['name'], basestring) and dep['name'].lower() == name.lower():
                template_values['%sver' % pref] = dep['version']
                template_values['%sshortver' % pref] = '.'.join(dep['version'].split('.')[:2])
                break

    # step 3: add remaining from config
    for name in TEMPLATE_NAMES_CONFIG:
        if name in ignore:
            continue
        if name in config:
            template_values[name] = config[name][0]
            _log.debug('name: %s, config: %s', name, config[name][0])

    # step 4. make lower variants if not skip_lower
    if not skip_lower:
        for name in TEMPLATE_NAMES_LOWER:
            if name in ignore:
                continue
            t_v = template_values.get(name, None)
            if t_v is None:
                continue
            try:
                template_values[TEMPLATE_NAMES_LOWER_TEMPLATE % {'name': name}] = t_v.lower()
            except:
                _log.debug("_getitem_string: can't get .lower() for name %s value %s (type %s)" %
                           (name, t_v, type(t_v)))

    return template_values


def to_template_str(value, templ_const, templ_val):
    """
    Insert template values where possible
        - value is a string
        - templ_const is a dictionary of template strings (constants)
        - templ_val is an ordered dictionary of template strings specific for this easyconfig file
    """
    old_value = None
    while value != old_value:
        old_value = value
        # check for constant values
        for tval, tname in templ_const.items():
            value = re.sub(r'(^|\W)' + re.escape(tval) + r'(\W|$)', r'\1' + tname + r'\2', value)

        for tval, tname in templ_val.items():
            # only replace full words with templates: word to replace should be at the beginning of a line
            # or be preceded by a non-alphanumeric (\W). It should end at the end of a line or be succeeded
            # by another non-alphanumeric.
            value = re.sub(r'(^|\W)' + re.escape(tval) + r'(\W|$)', r'\1%(' + tname + r')s\2', value)

    return value


def template_documentation():
    """Generate the templating documentation"""
    # This has to reflect the methods/steps used in easyconfig _generate_template_values
    indent_l0 = " " * 2
    indent_l1 = indent_l0 + " " * 2
    doc = []

    # step 1: add TEMPLATE_NAMES_EASYCONFIG
    doc.append('Template names/values derived from easyconfig instance')
    for name in TEMPLATE_NAMES_EASYCONFIG:
        doc.append("%s%%(%s)s: %s" % (indent_l1, name[0], name[1]))

    # step 2: add *ver/*shortver templates for software listed in TEMPLATE_SOFTWARE_VERSIONS
    doc.append("Template names/values for (short) software versions")
    for name, pref in TEMPLATE_SOFTWARE_VERSIONS:
        doc.append("%s%%(%sshortver)s: short version for %s (<major>.<minor>)" % (indent_l1, pref, name))
        doc.append("%s%%(%sver)s: full version for %s" % (indent_l1, pref, name))

    # step 3: add remaining self._config
    doc.append('Template names/values as set in easyconfig')
    for name in TEMPLATE_NAMES_CONFIG:
        doc.append("%s%%(%s)s" % (indent_l1, name))

    # step 4. make lower variants
    doc.append('Lowercase values of template values')
    for name in TEMPLATE_NAMES_LOWER:
        doc.append("%s%%(%s)s: lower case of value of %s" % (indent_l1, TEMPLATE_NAMES_LOWER_TEMPLATE % {'name': name}, name))

    # step 5. self.template_values can/should be updated from outside easyconfig
    # (eg the run_setp code in EasyBlock)
    doc.append('Template values set outside EasyBlock runstep')
    for name in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP:
        doc.append("%s%%(%s)s: %s" % (indent_l1, name[0], name[1]))

    doc.append('Template constants that can be used in easyconfigs')
    for cst in TEMPLATE_CONSTANTS:
        doc.append('%s%s: %s (%s)' % (indent_l1, cst[0], cst[2], cst[1]))

    return "\n".join(doc)
