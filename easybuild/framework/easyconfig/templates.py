#
# Copyright 2013-2013 Ghent University
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
#

"""
Easyconfig templates module that provides templating that can
be used within an Easyconfig file.

@author: Stijn De Weirdt (Ghent University)
"""

from vsc import fancylogger

_log = fancylogger.getLogger('easyconfig.templates', fname=False)

# derived from easyconfig, but not from ._config directly
TEMPLATE_NAMES_EASYCONFIG = [
                             ('toolchain_name', "Toolchain name"),
                             ('toolchain_version', "Toolchain version"),
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
                        ]
# values taken from the EasyBlock before each step
TEMPLATE_NAMES_EASYBLOCK_RUN_STEP = [
                                     ('installdir', "Installation directory"),
                                     ('builddir', "Build directory"),
                                     ]
# constant templates that can be used in easyconfigs
TEMPLATE_CONSTANTS = [
                      ('SOURCE_TAR_GZ', '%(name)s-%(version)s.tar.gz', "Source .tar.gz tarball"),
                      ('SOURCELOWER_TAR_GZ', '%(namelower)s-%(version)s.tar.gz',
                       "Source .tar.gz tarball with lowercase name"),

                      ('GOOGLECODE_SOURCE', 'http://%(namelower)s.googlecode.com/files/',
                       'googlecode.com source url'),
                      ('SOURCEFORGE_SOURCE', 'http://download.sourceforge.net/%(namelower)s/',
                       'sourceforge.net source url'),
                      ]

# TODO derived config templates
# versionmajor, verisonminor, versionmajorminor (eg '.'.join(version.split('.')[:2])) )

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

    # step 1: add TEMPLATE_NAMES_EASYCONFIG
    for name in TEMPLATE_NAMES_EASYCONFIG:
        if name in ignore:
            continue
        if name[0].startswith('toolchain_'):
            tc = config.get('toolchain')[0]
            if tc is not None:
                template_values['toolchain_name'] = tc.get('name', None)
                template_values['toolchain_version'] = tc.get('version', None)
        else:
            _log.error("Undefined name %s from TEMPLATE_NAMES_EASYCONFIG" % name)

    # step 2: add remaining from config
    for name in TEMPLATE_NAMES_CONFIG:
        if name in ignore:
            continue
        if name in config:
            template_values[name] = config[name][0]

    # step 3. make lower variants if not skip_lower
    if not skip_lower:
        for name in TEMPLATE_NAMES_LOWER:
            if name in ignore:
                continue
            t_v = template_values.get(name, None)
            if t_v is None:
                continue
            try:
                template_values[TEMPLATE_NAMES_LOWER_TEMPLATE % {'name':name}] = t_v.lower()
            except:
                _log.debug("_getitem_string: can't get .lower() for name %s value %s (type %s)" %
                           (name, t_v, type(t_v)))

    return template_values

def template_documentation():
    """Generate the templating documentation"""
    # This has to reflect the methods/steps used in easyconfig _generate_template_values
    indent_l0 = " "*2
    indent_l1 = indent_l0 + " "*2
    doc = []

    # step 1: add TEMPLATE_NAMES_EASYCONFIG
    doc.append('Template names/values derived from easyconfig instance')
    for name in TEMPLATE_NAMES_EASYCONFIG:
        doc.append("%s%s: %s" % (indent_l1, name[0], name[1]))

    # step 2: add remaining self._config
    doc.append('Template names/values as set in easyconfig')
    for name in TEMPLATE_NAMES_CONFIG:
        doc.append("%s%s" % (indent_l1, name))

    # step 3. make lower variants
    doc.append('Lowercase values of template values')
    for name in TEMPLATE_NAMES_LOWER:
        doc.append("%s%s: lower case of value of %s" % (indent_l1, TEMPLATE_NAMES_LOWER_TEMPLATE % {'name':name}, name))

    # step 4. self.template_values can/should be updated from outside easyconfig
    # (eg the run_setp code in EasyBlock)
    doc.append('Template values set outside EasyBlock runstep')
    for name in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP:
        doc.append("%s%s: %s" % (indent_l1, name[0], name[1]))

    doc.append('Template constants that can be used in easyconfigs')
    for cst in TEMPLATE_CONSTANTS:
        doc.append('%s%s: %s (%s)' % (indent_l1, cst[0], cst[2], cst[1]))

    return "\n".join(doc)

