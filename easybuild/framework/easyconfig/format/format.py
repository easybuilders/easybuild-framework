# #
# Copyright 2013-2014 Ghent University
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
The main easyconfig format class

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import copy
import re
from vsc import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.framework.easyconfig.format.version import EasyVersion, OrderedVersionOperators
from easybuild.framework.easyconfig.format.version import ToolchainVersionOperator, VersionOperator
from easybuild.framework.easyconfig.format.convert import Dependency
from easybuild.tools.configobj import Section


# format is mandatory major.minor
FORMAT_VERSION_KEYWORD = "EASYCONFIGFORMAT"
FORMAT_VERSION_TEMPLATE = "%(major)s.%(minor)s"
FORMAT_VERSION_HEADER_TEMPLATE = "# %s %s\n" % (FORMAT_VERSION_KEYWORD, FORMAT_VERSION_TEMPLATE)  # must end in newline
FORMAT_VERSION_REGEXP = re.compile(r'^#\s+%s\s*(?P<major>\d+)\.(?P<minor>\d+)\s*$' % FORMAT_VERSION_KEYWORD, re.M)
FORMAT_DEFAULT_VERSION = EasyVersion('1.0')

_log = fancylogger.getLogger('easyconfig.format.format', fname=False)


def get_format_version(txt):
    """Get the easyconfig format version as EasyVersion instance."""
    res = FORMAT_VERSION_REGEXP.search(txt)
    format_version = None
    if res is not None:
        try:
            maj_min = res.groupdict()
            format_version = EasyVersion(FORMAT_VERSION_TEMPLATE % maj_min)
        except (KeyError, TypeError), err:
            _log.error("Failed to get version from match %s: %s" % (res.groups(), err))
    return format_version


class EBConfigObj(object):
    """
    Enhanced ConfigObj, version/toolchain and other easyconfig specific aspects aware

    Given ConfigObj instance, make instance that represents a parser

    Mandatory/minimal (to mimic v1.0 behaviour); first version/toolchain is the default
    [SUPPORTED]
    versions=version_operator
    toolchains=toolchain_version_operator

    Optional
    [DEFAULT]
    ...
    [<operatorX> <versionX>]
    ...
    [<toolchainA> <operatorA> <versionA>]
    [[<operatorY> <versionY>]]
    ...
    ...
    """
    SECTION_MARKER_DEFAULT = 'DEFAULT'
    SECTION_MARKER_DEPENDENCIES = 'DEPENDENCIES'
    SECTION_MARKER_SUPPORTED = 'SUPPORTED'
    # list of known marker types (except default)
    KNOWN_VERSION_MARKER_TYPES = [ToolchainVersionOperator, VersionOperator]  # order matters, see parse_sections
    VERSION_OPERATOR_VALUE_TYPES = {
        # toolchains: comma-separated list of toolchain version operators
        'toolchains': ToolchainVersionOperator,
        # versions: comma-separated list of version operators
        'versions': VersionOperator,
    }

    def __init__(self, configobj=None):
        """
        Initialise EBConfigObj instance
        @param configobj: ConfigObj instance
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.tcname = None

        self.default = {}  # default section
        self.supported = {}  # supported section
        self.sections = {}  # all other sections
        self.unfiltered_sections = {}  # unfiltered other sections

        self.versops = OrderedVersionOperators()
        self.tcversops = OrderedVersionOperators()

        if configobj is not None:
            self.parse(configobj)

    def parse_sections(self, configobj, toparse=None, parent=None, depth=0):
        """
        Parse configobj instance; convert all supported sections, keys and values to their respective representations

        Returns a dict of (nested) Sections

        @param configobj: a ConfigObj instance, basically a dict of (unparsed) sections
        """
        # note: configobj already converts comma-separated strings in lists
        #
        # list of supported keywords, all else will fail
        special_keys = self.VERSION_OPERATOR_VALUE_TYPES.keys()
        if parent is None:
            # no parent, so top sections
            parsed = {}
        else:
            # parent specified, so not a top section
            parsed = Section(parent=parent, depth=depth + 1, main=configobj)

        # start with full configobj initially, and then process subsections recursively
        if toparse is None:
            toparse = configobj

        for key, value in toparse.items():
            if isinstance(value, Section):
                self.log.debug("Enter subsection key %s value %s" % (key, value))
                # only supported types of section keys are:
                # * DEFAULT
                # * SUPPORTED
                # * dependencies
                # * VersionOperator or ToolchainVersionOperator (e.g. [> 2.0], [goolf > 1])
                if key in [self.SECTION_MARKER_DEFAULT, self.SECTION_MARKER_SUPPORTED]:
                    # parse value as a section, recursively
                    new_value = self.parse_sections(configobj, toparse=value, parent=value.parent, depth=value.depth)
                    self.log.debug('Converted %s section to new value %s' % (key, new_value))
                    parsed[key] = new_value

                elif key == self.SECTION_MARKER_DEPENDENCIES:
                    new_key = 'dependencies'
                    new_value = []
                    for dep_name, dep_val in value.items():
                        if isinstance(dep_val, Section):
                            self.log.error("Unsupported nested section '%s' found in dependencies section" % dep_name)
                        else:
                            # FIXME: parse the dependency specification for version, toolchain, suffix, etc.
                            dep = Dependency(dep_val, name=dep_name)
                            if dep.name() is None or dep.version() is None:
                                self.log.error("Failed to find name/version in parsed dependency: %s (dict: %s)" % (dep, dict(dep)))
                            new_value.append(dep)

                    self.log.debug('Converted %s section to %s, passed it to parent section (or default)' % (key, new_value))
                    if isinstance(parsed, Section):
                        parsed.parent[new_key] = new_value
                    else:
                        parsed[self.SECTION_MARKER_DEFAULT].update({new_key: new_value})
                else:
                    # try parsing key as toolchain version operator first
                    # try parsing as version operator if it's not a toolchain version operator
                    for marker_type in self.KNOWN_VERSION_MARKER_TYPES:
                        new_key = marker_type(key)
                        if new_key:
                            self.log.debug("'%s' was parsed as a %s section marker" % (key, marker_type.__name__))
                            break
                        else:
                            self.log.debug("Not a %s section marker" % marker_type.__name__)
                    if not new_key:
                        self.log.error("Unsupported section marker '%s'" % key)

                    # parse value as a section, recursively
                    new_value = self.parse_sections(configobj, toparse=value, parent=value.parent, depth=value.depth)

                    self.log.debug('Converted key %s value %s in new key %s new value %s' % (key, value, new_key, new_value))
                    parsed[new_key] = new_value

            else:
                # simply pass down any non-special key-value items
                if not key in special_keys:
                    self.log.debug('Passing down key %s with value %s' % (key, value))
                    new_value = value

                # parse individual key-value assignments
                elif key in self.VERSION_OPERATOR_VALUE_TYPES:
                    value_type = self.VERSION_OPERATOR_VALUE_TYPES[key]
                    # list of supported toolchains/versions
                    # first one is default
                    if isinstance(value, basestring):
                        # so the split should be unnecessary
                        # (if it's not a list already, it's just one value)
                        # TODO this is annoying. check if we can force this in configobj
                        value = value.split(',')
                    # remove possible surrounding whitespace (some people add space after comma)
                    new_value = [value_type(x.strip()) for x in value]
                    if False in [x.is_valid() for x in new_value]:
                        self.log.error("Failed to parse '%s' as list of %s" % (value, value_type.__name__))
                else:
                    tup = (key, value, type(value))
                    self.log.error('Bug: supported but unknown key %s with non-string value: %s, type %s' % tup)

                self.log.debug("Converted value '%s' for key '%s' into new value '%s'" % (value, key, new_value))
                parsed[key] = new_value

        return parsed

    def validate_and_filter_by_toolchain(self, tcname, processed=None, filtered_sections=None, other_sections=None):
        """
        Build the ordered version operator and toolchain version operator, ignoring all other toolchains
        @param tcname: toolchain name to keep
        @param processed: a processed dict of sections to filter
        @param path: list of keys to identify the path in the dict
        """
        top_call = False
        if processed is None:
            processed = self.sections
            top_call = True
        if filtered_sections is None:
            filtered_sections = {}
        if other_sections is None:
            other_sections = {}

        # walk over dictionary of parsed sections, and check for marker conflicts (using .add())
        # add section markers relevant to specified toolchain to self.tcversops
        for key, value in processed.items():
            if isinstance(value, Section):
                if isinstance(key, ToolchainVersionOperator):
                    if not key.tc_name == tcname:
                        self.log.debug("Found marker for other toolchain '%s'" % key.tc_name)
                        # also perform sanity check for other toolchains, make add check for conflicts
                        tc_overops = other_sections.setdefault(key.tc_name, OrderedVersionOperators())
                        tc_overops.add(key)
                        # nothing more to do here, just continue with other sections
                        continue
                    else:
                        self.log.debug("Found marker for specified toolchain '%s': %s" % (tcname, key))
                        # add marker to self.tcversops (which triggers a conflict check)
                        self.tcversops.add(key, value)
                        filtered_sections[key] = value
                elif isinstance(key, VersionOperator):
                    self.log.debug("Found marker for version '%s'" % key)
                    # keep track of all version operators, and enforce conflict check
                    self.versops.add(key, value)
                    filtered_sections[key] = value
                else:
                    self.log.error("Unhandled section marker '%s' (type '%s')" % (key, type(key)))

                # recursively go deeper for (relevant) sections
                self.validate_and_filter_by_toolchain(tcname, processed=value, filtered_sections=filtered_sections,
                                                      other_sections=other_sections)

            elif key in self.VERSION_OPERATOR_VALUE_TYPES:
                self.log.debug("Found version operator key-value entry (%s)" % key)
                if key == 'toolchains':
                    # remove any other toolchain from list
                    filtered_sections[key] = [tcversop for tcversop in value if tcversop.tc_name == tcname]
                else:
                    # retain all other values
                    filtered_sections[key] = value
            else:
                self.log.debug("Found non-special key-value entry (key %s), skipping it" % key)

        if top_call:
            self.unfiltered_sections = self.sections
            self.sections = filtered_sections

    def parse(self, configobj):
        """
        First parse the configobj instance
        Then build the structure to support the versionoperators and all other parts of the structure

        @param configobj: ConfigObj instance
        """
        # keep reference to original (in case it's needed/wanted)
        self.configobj = configobj

        # process the configobj instance
        self.sections = self.parse_sections(self.configobj)

        # handle default section
        # no nesting
        #  - add DEFAULT key-value entries to the root of self.sections
        #  - key-value items from other sections will be deeper down
        #  - deepest level is best match and wins, so defaults are on top level
        self.default = self.sections.pop(self.SECTION_MARKER_DEFAULT, {})
        for key, value in self.default.items():
            self.sections[key] = value

        # handle supported section
        # supported should only have 'versions' and 'toolchains' keys
        self.supported = self.sections.pop(self.SECTION_MARKER_SUPPORTED, {})
        for key, value in self.supported.items():
            if not key in self.VERSION_OPERATOR_VALUE_TYPES:
                self.log.error('Unsupported key %s in %s section' % (key, self.SECTION_MARKER_SUPPORTED))
            self.sections['%s' % key] = value

        if 'versions' in self.supported:
            # first of list is special: it is the default
            self.default['version'] = self.supported['versions'][0].get_version_str()
        if 'toolchains' in self.supported:
            # first of list is special: it is the default
            self.default['toolchain'] = self.supported['toolchains'][0].as_dict()

        tup = (self.default, self.supported, self.sections)
        self.log.debug("(parse) default: %s; supported: %s, sections: %s" % tup)

    def get_specs_for(self, version=None, tcname=None, tcversion=None):
        """
        Return dictionary with specifications listed in sections applicable for specified info.
        """
        if isinstance(self.default, Section):
            cfg = self.default.dict()
        else:
            cfg = copy.deepcopy(self.default)

        # make sure that requested version/toolchain are supported by this easyconfig
        versions = [x.get_version_str() for x in self.supported['versions']]
        if version is None:
            self.log.debug("No version specified")
        elif version in versions:
            self.log.debug("Version '%s' is supported in easyconfig." % version)
        else:
            self.log.error("Version '%s' not supported in easyconfig (only %s)" % (version, versions))

        tcnames = [tc.tc_name for tc in self.supported['toolchains']]
        if tcname is None:
            self.log.debug("Toolchain name not specified.")
        elif tcname in tcnames:
            self.log.debug("Toolchain '%s' is supported in easyconfig." % tcname)
            tcversions = [tc.get_version_str() for tc in self.supported['toolchains'] if tc.tc_name == tcname]
            if tcversion is None:
                self.log.debug("Toolchain version not specified.")
            elif tcversion in tcversions:
                self.log.debug("Toolchain '%s' version '%s' is supported in easyconfig" % (tcname, tcversion))
            else:
                tup = (tcname, tcversion, tcversions)
                self.log.error("Toolchain '%s' version '%s' not supported in easyconfig (only %s)" % tup)
        else:
            self.log.error("Toolchain '%s' not supported in easyconfig (only %s)" % (tcname, tcnames))

        # TODO: determine 'path' to take in sections based on version and toolchain version
        # SDW: ask the versionoperator
        self.log.debug("self.versops: %s" % self.versops)
        self.log.debug("self.tcversops: %s" % self.tcversops)

        return cfg


class EasyConfigFormat(object):
    """EasyConfigFormat class"""
    VERSION = EasyVersion('0.0')  # dummy EasyVersion instance (shouldn't be None)
    USABLE = False  # disable this class as usable format

    def __init__(self):
        """Initialise the EasyConfigFormat class"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        if not len(self.VERSION) == len(FORMAT_VERSION_TEMPLATE.split('.')):
            self.log.error('Invalid version number %s (incorrect length)' % self.VERSION)

        self.rawtext = None  # text version of the easyconfig
        self.header = None  # easyconfig header (e.g., format version, license, ...)
        self.docstring = None  # easyconfig docstring (e.g., author, maintainer, ...)

        self.specs = {}

    def set_specifications(self, specs):
        """Set specifications."""
        self.specs = copy.deepcopy(specs)

    def get_config_dict(self):
        """Returns a single easyconfig dictionary."""
        raise NotImplementedError

    def validate(self):
        """Verify the easyconfig format"""
        raise NotImplementedError

    def parse(self, txt, **kwargs):
        """Parse the txt according to this format. This is highly version specific"""
        raise NotImplementedError

    def dump(self):
        """Dump easyconfig according to this format. This is higly version specific"""
        raise NotImplementedError


def get_format_version_classes(version=None):
    """Return the (usable) subclasses from EasyConfigFormat that have a matching version."""
    all_classes = get_subclasses(EasyConfigFormat)
    if version is None:
        return all_classes
    else:
        return [x for x in all_classes if x.VERSION == version and x.USABLE]
