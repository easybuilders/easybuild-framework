# #
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
# #

"""
The main easyconfig format class

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import copy
import re
from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.framework.easyconfig.format.version import EasyVersion, OrderedVersionOperators
from easybuild.framework.easyconfig.format.version import ToolchainVersionOperator, VersionOperator
from easybuild.framework.easyconfig.format.convert import Dependency
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.configobj import Section


INDENT_4SPACES = ' ' * 4

# format is mandatory major.minor
FORMAT_VERSION_KEYWORD = "EASYCONFIGFORMAT"
FORMAT_VERSION_TEMPLATE = "%(major)s.%(minor)s"
FORMAT_VERSION_HEADER_TEMPLATE = "# %s %s\n" % (FORMAT_VERSION_KEYWORD, FORMAT_VERSION_TEMPLATE)  # must end in newline
FORMAT_VERSION_REGEXP = re.compile(r'^#\s+%s\s*(?P<major>\d+)\.(?P<minor>\d+)\s*$' % FORMAT_VERSION_KEYWORD, re.M)
FORMAT_DEFAULT_VERSION = EasyVersion('1.0')

DEPENDENCY_PARAMETERS = ['builddependencies', 'dependencies', 'hiddendependencies']

# values for these keys will not be templated in dump()
EXCLUDED_KEYS_REPLACE_TEMPLATES = ['description', 'easyblock', 'homepage', 'name', 'toolchain', 'version'] \
                                  + DEPENDENCY_PARAMETERS

# ordered groups of keys to obtain a nice looking easyconfig file
GROUPED_PARAMS = [
    ['easyblock'],
    ['name', 'version', 'versionprefix', 'versionsuffix'],
    ['homepage', 'description'],
    ['toolchain', 'toolchainopts'],
    ['sources', 'source_urls'],
    ['patches'],
    DEPENDENCY_PARAMETERS,
    ['osdependencies'],
    ['preconfigopts', 'configopts'],
    ['prebuildopts', 'buildopts'],
    ['preinstallopts', 'installopts'],
    ['parallel', 'maxparallel'],
]
LAST_PARAMS = ['sanity_check_paths', 'moduleclass']


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
            raise EasyBuildError("Failed to get version from match %s: %s", res.groups(), err)
    return format_version


class NestedDict(dict):
    """A nested dictionary, with tracking of depth and parent"""
    def __init__(self, parent, depth):
        """Initialise NestedDict instance"""
        dict.__init__(self)
        self.depth = depth
        self.parent = parent

    def get_nested_dict(self):
        """Return an instance of NestedDict with this instance as parent"""
        nd = NestedDict(parent=self.parent, depth=self.depth + 1)
        return nd

    def copy(self):
        """Return a copy. Any relation between key and value are deepcopied away."""
        nd = self.__class__(parent=self.parent, depth=self.depth)
        for key, val in self.items():
            cp_key = copy.deepcopy(key)
            if isinstance(val, NestedDict):
                cp_val = val.copy()
            else:
                cp_val = copy.deepcopy(val)
            nd[cp_key] = cp_val
        return nd


class TopNestedDict(NestedDict):
    """The top level nested dictionary (depth 0, parent is itself)"""
    def __init__(self, parent=None, depth=None):
        """Initialise TopNestedDict instance"""
        # parent and depth are ignored; just to support same init for copier
        NestedDict.__init__(self, self, 0)


class Squashed(object):
    """Class to ease the squashing of OrderedVersionOperators and OrderedToolchainVersionOperators"""
    def __init__(self):
        """Initialise Squashed instance"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        # OrderedVersionOperators instances to keep track of the data of the matching
        # version and toolchain version sections
        self.versions = OrderedVersionOperators()
        self.tcversions = OrderedVersionOperators()
        self.result = {}

    def add_toolchain(self, squashed):
        """
        Add squashed instance from a toolchain section
        @param squashed: a Squashed instance
        """
        # TODO unify with add_version, make one .add()
        # data from toolchain
        self.result.update(squashed.result)
        for versop in squashed.versions.versops:
            self.versions.add(versop, squashed.versions.get_data(versop), update=True)

    def add_version(self, section, squashed):
        """
        Add squashed instance from version section
        @param section: the version section versionoperator instance
        @param squashed: a Squashed instance
        """
        # TODO unify with add_toolchain, make one .add()
        # don't update res_sections
        # add this to a orderedversop that has matching versops.
        # data in this matching orderedversop must be updated to the res at the end
        for versop in squashed.versions.versops:
            self.versions.add(versop, squashed.versions.get_data(versop), update=True)
        self.versions.add(section, squashed.result, update=True)

    def final(self):
        """Final squashing of version and toolchainversion operators and return the result"""
        self.log.debug('Pre-final result %s' % self.result)
        self.log.debug('Pre-final versions %s with data %s' % (self.versions, self.versions.datamap))
        self.log.debug('Pre-final tcversions %s with data %s' % (self.tcversions, self.tcversions.datamap))

        # update self.result, most strict matching versionoperator should be first element
        # so update in reversed order
        # also update toolchain data before version data
        for vers in [self.tcversions, self.versions]:
            for versop in vers.versops[::-1]:
                self.result.update(vers.get_data(versop))

        return self.result


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
        self.sections = None  # all other sections
        self.unfiltered_sections = {}  # unfiltered other sections

        if configobj is not None:
            self.parse(configobj)

    def _init_sections(self):
        """Initialise self.sections. Make sure 'default' and 'supported' sections exist."""
        self.sections = TopNestedDict()
        for key in [self.SECTION_MARKER_DEFAULT, self.SECTION_MARKER_SUPPORTED]:
            self.sections[key] = self.sections.get_nested_dict()

    def parse_sections(self, toparse, current):
        """
        Parse Section instance; convert all supported sections, keys and values to their respective representations

        Returns a dict of (nested) Sections

        @param toparse: a Section (or ConfigObj) instance, basically a dict of (unparsed) sections
        @param current: the current NestedDict 
        """
        # note: configobj already converts comma-separated strings in lists
        #
        # list of supported keywords, all else will fail
        special_keys = self.VERSION_OPERATOR_VALUE_TYPES.keys()

        self.log.debug('Processing current depth %s' % current.depth)

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
                    new_value = self.parse_sections(value, current.get_nested_dict())
                    self.log.debug('Converted %s section to new value %s' % (key, new_value))
                    current[key] = new_value

                elif key == self.SECTION_MARKER_DEPENDENCIES:
                    new_key = 'dependencies'
                    new_value = []
                    for dep_name, dep_val in value.items():
                        if isinstance(dep_val, Section):
                            raise EasyBuildError("Unsupported nested section '%s' in dependencies section", dep_name)
                        else:
                            # FIXME: parse the dependency specification for version, toolchain, suffix, etc.
                            dep = Dependency(dep_val, name=dep_name)
                            if dep.name() is None or dep.version() is None:
                                raise EasyBuildError("Failed to find name/version in parsed dependency: %s (dict: %s)",
                                                     dep, dict(dep))
                            new_value.append(dep)

                    tmpl = 'Converted dependency section %s to %s, passed it to parent section (or default)'
                    self.log.debug(tmpl % (key, new_value))
                    if isinstance(current, TopNestedDict):
                        current[self.SECTION_MARKER_DEFAULT].update({new_key: new_value})
                    else:
                        current.parent[new_key] = new_value
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
                        raise EasyBuildError("Unsupported section marker '%s'", key)

                    # parse value as a section, recursively
                    new_value = self.parse_sections(value, current.get_nested_dict())

                    self.log.debug('Converted section key %s value %s in new key %s new value %s' %
                                   (key, value, new_key, new_value))
                    current[new_key] = new_value

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
                        raise EasyBuildError("Failed to parse '%s' as list of %s", value, value_type.__name__)
                else:
                    raise EasyBuildError('Bug: supported but unknown key %s with non-string value: %s, type %s',
                                         key, value, type(value))

                self.log.debug("Converted value '%s' for key '%s' into new value '%s'" % (value, key, new_value))
                current[key] = new_value

        return current

    def parse(self, configobj):
        """
        Parse configobj using using recursive parse_sections. 
        Then split off the default and supported sections. 

        @param configobj: ConfigObj instance
        """
        # keep reference to original (in case it's needed/wanted)
        self.configobj = configobj

        # process the configobj instance
        self._init_sections()
        self.sections = self.parse_sections(self.configobj, self.sections)

        # handle default section
        # no nesting
        #  - add DEFAULT key-value entries to the root of self.sections
        #  - key-value items from other sections will be deeper down
        #  - deepest level is best match and wins, so defaults are on top level
        self.default = self.sections.pop(self.SECTION_MARKER_DEFAULT)
        for key, value in self.default.items():
            self.sections[key] = value

        # handle supported section
        # supported should only have 'versions' and 'toolchains' keys
        self.supported = self.sections.pop(self.SECTION_MARKER_SUPPORTED)
        for key, value in self.supported.items():
            if not key in self.VERSION_OPERATOR_VALUE_TYPES:
                raise EasyBuildError('Unsupported key %s in %s section', key, self.SECTION_MARKER_SUPPORTED)
            self.sections['%s' % key] = value

        for key, supported_key, fn_name in [('version', 'versions', 'get_version_str'),
                                            ('toolchain', 'toolchains', 'as_dict')]:
            if supported_key in self.supported:
                self.log.debug('%s in supported section, trying to determine default for %s' % (supported_key, key))
                first = self.supported[supported_key][0]
                f_val = getattr(first, fn_name)()
                if f_val is None:
                    raise EasyBuildError("First %s %s can't be used as default (%s returned None)", key, first, fn_name)
                else:
                    self.log.debug('Using first %s (%s) as default %s' % (key, first, f_val))
                    self.default[key] = f_val

        # TODO is it verified somewhere that the defaults are supported?

        self.log.debug("(parse) supported: %s" % self.supported)
        self.log.debug("(parse) default: %s" % self.default)
        self.log.debug("(parse) sections: %s" % self.sections)

    def squash(self, version, tcname, tcversion):
        """
        Project the multidimensional easyconfig to single easyconfig
        It (tries to) detect conflicts in the easyconfig.

        @param version: version to keep
        @param tcname: toolchain name to keep
        @param tcversion: toolchain version to keep
        """
        self.log.debug('Start squash with sections %s' % self.sections)

        # dictionary to keep track of all sections, to detect conflicts in the easyconfig
        sanity = {
            'versops': OrderedVersionOperators(),
            'toolchains': {},
        }

        vt_tuple = (version, tcname, tcversion)
        squashed = self._squash(vt_tuple, self.sections, sanity)
        result = squashed.final()

        self.log.debug('End squash with result %s' % result)
        return result

    def _squash(self, vt_tuple, processed, sanity):
        """
        Project the multidimensional easyconfig (or subsection thereof) to single easyconfig
        Returns Squashed instance for the processed block.
        @param vt_tuple: tuple with version (version to keep), tcname (toolchain name to keep) and 
                            tcversion (toolchain version to keep)
        @param processed: easyconfig (Top)NestedDict
        @param sanity: dictionary to keep track of section markers and detect conflicts 
        """
        version, tcname, tcversion = vt_tuple
        res_sections = {}

        # a Squashed instance to keep track of the data of the matching version and toolchainversion sections
        # also contains the intermediate result
        squashed = Squashed()

        self.log.debug('Start processed %s' % processed)
        # walk over dictionary of parsed sections, and check for marker conflicts (using .add())
        for key, value in processed.items():
            if isinstance(value, NestedDict):
                tmp = self._squash_netsed_dict(key, value, squashed, sanity, vt_tuple)
                res_sections.update(tmp)
            elif key in self.VERSION_OPERATOR_VALUE_TYPES:
                self.log.debug("Found VERSION_OPERATOR_VALUE_TYPES entry (%s)" % key)
                tmp = self._squash_versop(key, value, squashed, sanity, vt_tuple)
                if not tmp is None:
                    return tmp
            else:
                self.log.debug('Adding key %s value %s' % (key, value))
                squashed.result[key] = value

        # merge the current attributes with deeper nested ones, deepest nested ones win
        self.log.debug('Current level result %s' % squashed.result)
        self.log.debug('Higher level sections result %s' % res_sections)
        squashed.result.update(res_sections)

        self.log.debug('End processed %s ordered versions %s result %s' %
                       (processed, squashed.versions, squashed.result))
        return squashed

    def _squash_netsed_dict(self, key, nested_dict, squashed, sanity, vt_tuple):
        """
        Squash NestedDict instance, returns dict with already squashed data 
            from possible higher sections 
        @param key: section key
        @param nested_dict: the nested_dict instance
        @param squashed: Squashed instance
        @param sanity: the sanity dict
        @param vt_tuple: version, tc_name, tc_version tuple
        """
        version, tcname, tcversion = vt_tuple
        res_sections = {}

        if isinstance(key, ToolchainVersionOperator):
            # perform sanity check for all toolchains, use .add to check for conflicts
            tc_overops = sanity['toolchains'].setdefault(key.tc_name, OrderedVersionOperators())
            tc_overops.add(key)

            if key.test(tcname, tcversion):
                self.log.debug("Found matching marker for specified toolchain '%s, %s': %s", tcname, tcversion, key)
                # TODO remove when unifying add_toolchina with .add()
                tmp_squashed = self._squash(vt_tuple, nested_dict, sanity)
                res_sections.update(tmp_squashed.result)
                squashed.add_toolchain(tmp_squashed)
            else:
                tmpl = "Found marker for other toolchain or version '%s', ignoring this (nested) section."
                self.log.debug(tmpl % key)
        elif isinstance(key, VersionOperator):
            # keep track of all version operators, and enforce conflict check
            sanity['versops'].add(key)
            if key.test(version):
                self.log.debug('Found matching version marker %s' % key)
                squashed.add_version(key, self._squash(vt_tuple, nested_dict, sanity))
            else:
                self.log.debug('Found non-matching version marker %s. Ignoring this (nested) section.' % key)
        else:
            raise EasyBuildError("Unhandled section marker '%s' (type '%s')", key, type(key))

        return res_sections

    def _squash_versop(self, key, value, squashed, sanity, vt_tuple):
        """
        Squash VERSION_OPERATOR_VALUE_TYPES value 
            return None or new Squashed instance 
        @param key: section key
        @param nested_dict: the nested_dict instance
        @param squashed: Squashed instance
        @param sanity: the sanity dict
        @param vt_tuple: version, tc_name, tc_version tuple
        """
        version, tcname, tcversion = vt_tuple
        if key == 'toolchains':
            # remove any other toolchain from list
            self.log.debug("Filtering 'toolchains' key")

            matching_toolchains = []
            tmp_tc_oversops = {}  # temporary, only for conflict checking
            for tcversop in value:
                tc_overops = tmp_tc_oversops.setdefault(tcversop.tc_name, OrderedVersionOperators())
                self.log.debug("Add tcversop %s to tc_overops %s tcname %s tcversion %s",
                               tcversop, tc_overops, tcname, tcversion)
                tc_overops.add(tcversop)  # test non-conflicting list
                if tcversop.test(tcname, tcversion):
                    matching_toolchains.append(tcversop)

            if matching_toolchains:
                # does this have any use?
                self.log.debug('Matching toolchains %s found (but data not needed)' % matching_toolchains)
            else:
                self.log.debug('No matching toolchains, removing the whole current key %s' % key)
                return Squashed()

        elif key == 'versions':
            self.log.debug("Adding all versions %s from versions key" % value)
            matching_versions = []
            tmp_versops = OrderedVersionOperators()  # temporary, only for conflict checking
            for versop in value:
                tmp_versops.add(versop)  # test non-conflicting list
                if versop.test(version):
                    matching_versions.append(versop)
            if matching_versions:
                # does this have any use?
                self.log.debug('Matching versions %s found (but data not needed)' % matching_versions)
            else:
                self.log.debug('No matching versions, removing the whole current key %s' % key)
                return Squashed()
        else:
            raise EasyBuildError('Unexpected VERSION_OPERATOR_VALUE_TYPES key %s value %s', key, value)

        return None

    def get_version_toolchain(self, version=None, tcname=None, tcversion=None):
        """Return tuple of version, toolchainname and toolchainversion (possibly using defaults)."""
        # make sure that requested version/toolchain are supported by this easyconfig
        versions = [x.get_version_str() for x in self.supported['versions']]
        if version is None:
            if 'version' in self.default:
                version = self.default['version']
                self.log.debug("No version specified, using default %s" % version)
            else:
                raise EasyBuildError("No version specified, no default found.")
        elif version in versions:
            self.log.debug("Version '%s' is supported in easyconfig." % version)
        else:
            raise EasyBuildError("Version '%s' not supported in easyconfig (only %s)", version, versions)

        tcnames = [tc.tc_name for tc in self.supported['toolchains']]
        if tcname is None:
            if 'toolchain' in self.default and 'name' in self.default['toolchain']:
                tcname = self.default['toolchain']['name']
                self.log.debug("No toolchain name specified, using default %s" % tcname)
            else:
                raise EasyBuildError("No toolchain name specified, no default found.")
        elif tcname in tcnames:
            self.log.debug("Toolchain '%s' is supported in easyconfig." % tcname)
        else:
            raise EasyBuildError("Toolchain '%s' not supported in easyconfig (only %s)", tcname, tcnames)

        tcs = [tc for tc in self.supported['toolchains'] if tc.tc_name == tcname]
        if tcversion is None:
            if 'toolchain' in self.default and 'version' in self.default['toolchain']:
                tcversion = self.default['toolchain']['version']
                self.log.debug("No toolchain version specified, using default %s" % tcversion)
            else:
                raise EasyBuildError("No toolchain version specified, no default found.")
        elif any([tc.test(tcname, tcversion) for tc in tcs]):
            self.log.debug("Toolchain '%s' version '%s' is supported in easyconfig" % (tcname, tcversion))
        else:
            raise EasyBuildError("Toolchain '%s' version '%s' not supported in easyconfig (only %s)",
                                 tcname, tcversion, tcs)

        self.log.debug('version %s, tcversion %s, tcname %s', version, tcname, tcversion)

        return (version, tcname, tcversion)

    def get_specs_for(self, version=None, tcname=None, tcversion=None):
        """
        Return dictionary with specifications listed in sections applicable for specified info.
        """

        version, tcname, tcversion = self.get_version_toolchain(version, tcname, tcversion)
        self.log.debug('Squashing with version %s and toolchain %s' % (version, (tcname, tcversion)))
        res = self.squash(version, tcname, tcversion)

        return res


class EasyConfigFormat(object):
    """EasyConfigFormat class"""
    VERSION = EasyVersion('0.0')  # dummy EasyVersion instance (shouldn't be None)
    USABLE = False  # disable this class as usable format

    def __init__(self):
        """Initialise the EasyConfigFormat class"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        if not len(self.VERSION) == len(FORMAT_VERSION_TEMPLATE.split('.')):
            raise EasyBuildError('Invalid version number %s (incorrect length)', self.VERSION)

        self.rawtext = None  # text version of the easyconfig
        self.comments = {}  # comments in easyconfig file
        self.header = None  # easyconfig header (e.g., format version, license, ...)
        self.docstring = None  # easyconfig docstring (e.g., author, maintainer, ...)

        self.specs = {}

    def set_specifications(self, specs):
        """Set specifications."""
        self.log.debug('Set copy of specs %s' % specs)
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

    def dump(self, ecfg, default_values, templ_const, templ_val):
        """Dump easyconfig according to this format. This is higly version specific"""
        raise NotImplementedError

    def extract_comments(self, rawtxt):
        """Extract comments from raw content."""
        raise NotImplementedError


def get_format_version_classes(version=None):
    """Return the (usable) subclasses from EasyConfigFormat that have a matching version."""
    all_classes = get_subclasses(EasyConfigFormat)
    if version is None:
        return all_classes
    else:
        return [x for x in all_classes if x.VERSION == version and x.USABLE]
