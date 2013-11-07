# #
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
# #

"""
This describes the easyconfig version class. To be used in EasyBuild for anything related to version checking

@author: Stijn De Weirdt (Ghent University)
"""

import operator as op
import re
from distutils.version import LooseVersion
from vsc import fancylogger

from easybuild.tools.configobj import Section
from easybuild.tools.toolchain.utilities import search_toolchain


class EasyVersion(LooseVersion):
    """Exact LooseVersion. No modifications needed (yet)"""
    # TODO: replace all LooseVersion with EasyVersion in eb, after moving EasyVersion to easybuild/tools?
    # TODO: is dummy some magic version? (ie do we need special attributes for dummy versions?)

    def __len__(self):
        """Determine length of this EasyVersion instance."""
        return len(self.version)


class VersionOperator(object):
    """
    VersionOperator class represents a version expression that includes an operator.
    """
    SEPARATOR = ' '  # single space as (mandatory) separator in section markers, excellent readability
    OPERATOR_MAP = {
        '==': op.eq,  # no !=, exceptions to the default should be handled with a dedicated section using ==
        '>': op.gt,
        '>=': op.ge,
        '<': op.lt,
        '<=': op.le,
    }
    REVERSE_OPERATOR_MAP = dict([(v, k) for k, v in OPERATOR_MAP.items()])
    INCLUDE_OPERATORS = ['==', '>=', '<=']  # these operators *include* the (version) boundary
    ORDERED_OPERATORS = ['==', '>', '>=', '<', '<=']  # ordering by strictness
    OPERATOR_FAMILIES = [['>', '>='], ['<', '<=']]  # similar operators
    DEFAULT_UNDEFINED_VERSION = EasyVersion('0.0.0')
    DEFAULT_UNDEFINED_OPERATOR = OPERATOR_MAP['>']

    def __init__(self, versop_str=None, error_on_parse_failure=False):
        """
        Initialise VersionOperator instance.
        @param versop_str: intialise with version operator string
        @param error_on_parse_failure: log.error in case of parse error
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.versop_str = None
        self.operator_str = None
        self.version_str = None
        self.version = None
        self.operator = None
        self.regex = self.versop_regex()

        self.error_on_parse_failure = error_on_parse_failure
        if not versop_str is None:
            self.set(versop_str)

    def parse_error(self, msg):
        """Special function to deal with parse errors"""
        # TODO major issue what to do in case of misparse. error or not?
        if self.error_on_parse_failure:
            self.log.error(msg)
        else:
            self.log.debug(msg)

    def __bool__(self):
        """Interpretation of a VersionOperator instance as a boolean expression: is it valid?"""
        return self.is_valid()

    # Python 2.x compatibility
    __nonzero__ = __bool__

    def is_valid(self):
        """Check if this is a valid VersionOperator"""
        return not(self.version is None or self.operator is None)

    def set(self, versop_str):
        """
        Parse argument and set attributes.
        Returns None in case of failure (e.g. if supplied string doesn't parse), True in case of success.
        """
        versop_dict = self.parse_versop_str(versop_str)
        if versop_dict is None:
            self.log.warning("set('%s'): Failed to parse argument" % versop_str)
            return None
        else:
            for k, v in versop_dict.items():
                setattr(self, k, v)
            return True

    def test(self, test_version):
        """
        Convert argument to an EasyVersion instance if needed, and return self.operator(<argument>, self.version)
        @param test_version: a version string or EasyVersion instance
        """
        # checks whether this VersionOperator instance is valid using __bool__ function
        if not self:
            self.log.error('Not a valid VersionOperator. Not initialised yet?')

        if isinstance(test_version, basestring):
            test_version = self._convert(test_version)
        elif not isinstance(test_version, EasyVersion):
            self.log.error("test: argument should be a basestring or EasyVersion (type %s)" % (type(test_version)))

        res = self.operator(test_version, self.version)
        tup = (test_version, self.REVERSE_OPERATOR_MAP[self.operator], self.version, res)
        self.log.debug("result of testing expression '%s %s %s': %s" % tup)

        return res

    def __str__(self):
        """Return string representation of this VersionOperator instance"""
        if self.operator is None:
            operator = self.DEFAULT_UNDEFINED_OPERATOR
        else:
            operator = self.operator
        operator_str = self.REVERSE_OPERATOR_MAP[operator]
        return ''.join(map(str, [operator_str, self.SEPARATOR, self.version]))

    def __repr__(self):
        """Return instance as string (ignores begin_end)"""
        return "%s('%s')" % (self.__class__.__name__, self)

    def __eq__(self, versop):
        """Compare this instance to supplied argument."""
        if not isinstance(versop, self.__class__):
            self.log.error("Types don't match in comparison: %s, expected %s" % (type(versop), self.__class__))
        return self.version == versop.version and self.operator == versop.operator

    def __ne__(self, versop):
        """Is self not equal to versop"""
        return not self.__eq__(versop)

    def versop_regex(self, begin_end=True):
        """
        Create the version regular expression with operator support.
        This supports version expressions like '> 5' (anything strict larger than 5),
        or '<= 1.2' (anything smaller than or equal to 1.2)
        @param begin_end: boolean, create a regex with begin/end match
        """
        # construct escaped operator symbols, e.g. '\<\='
        operators = []
        for operator in self.OPERATOR_MAP.keys():
            operators.append(re.sub(r'(.)', r'\\\1', operator))

        # regex to parse version expression
        # - operator_str part is optional
        # - version_str should start/end with any word character except separator
        # - minimal version_str length is 1
        reg_text = r"(?:(?P<operator_str>%(ops)s)%(sep)s)?(?P<version_str>[^%(sep)s\W](?:\S*[^%(sep)s\W])?)" % {
            'sep': self.SEPARATOR,
            'ops': '|'.join(operators),
        }
        if begin_end:
            reg_text = r"^%s$" % reg_text
        reg = re.compile(reg_text)

        self.log.debug("versop regex pattern '%s' (begin_end: %s)" % (reg.pattern, begin_end))
        return reg

    def _convert(self, version_str):
        """Convert string to EasyVersion instance that can be compared"""
        version = None
        if version_str is None:
            version = self.DEFAULT_UNDEFINED_VERSION
            self.log.warning('_convert: version_str None, set it to DEFAULT_UNDEFINED_VERSION %s' % version)
        else:
            try:
                version = EasyVersion(version_str)
            except (AttributeError, ValueError), err:
                self.parse_error('Failed to convert %s to an EasyVersion instance: %s' % (version_str, err))

        self.log.debug('converted string %s to version %s' % (version_str, version))
        return version

    def _convert_operator(self, operator_str):
        """Return the operator"""
        operator = None
        if operator_str is None:
            operator = self.DEFAULT_UNDEFINED_OPERATOR
            self.log.warning('_convert: operator_str None, set it to DEFAULT_UNDEFINED_OPERATOR %s' % operator)
        elif operator_str in self.OPERATOR_MAP:
            operator = self.OPERATOR_MAP[operator_str]
        else:
            self.parse_error('Failed to match specified operator %s to operator function' % operator_str)
        return operator

    def parse_versop_str(self, versop_str, versop_dict=None):
        """
        If argument contains a version operator, returns a dict with version and operator; returns None otherwise
        @param versop_str: the string to parse
        @param versop_dict: advanced usage: pass intialised versop_dict (eg for ToolchainVersionOperator)
        """
        if versop_dict is None:
            versop_dict = {}

        if versop_str is not None:
            res = self.regex.search(versop_str)
            if not res:
                self.parse_error('No regex match for versop expression %s' % versop_str)
                return None

            versop_dict.update(res.groupdict())
            versop_dict['versop_str'] = versop_str

        if not 'versop_str' in versop_dict:
            self.log.error('Missing versop_str in versop_dict %s' % versop_dict)

        versop_dict['version'] = self._convert(versop_dict['version_str'])
        versop_dict['operator'] = self._convert_operator(versop_dict['operator_str'])
        self.log.debug('versop expression %s parsed into versop_dict %s' % (versop_dict['versop_str'], versop_dict))

        return versop_dict

    def test_overlap_and_conflict(self, versop_other):
        """
        Test if there is any overlap between this instance and versop_other, and if so, if there is a conflict or not.
        
        Returns 2 booleans: has_overlap, is_conflict
        
        @param versop_other: a VersionOperator instance
        
        Examples:
            '> 3' and '> 3' : equal, and thus overlap (no conflict)
            '> 3' and '< 2' : no overlap
            '< 3' and '> 2' : overlap, and conflict (region between 2 and 3 is ambiguous)
            '> 3' and '== 3' : no overlap
            '>= 3' and '== 3' : overlap, and conflict (boundary 3 is ambigous)
            '> 3' and '>= 3' : overlap, no conflict ('> 3' is more strict then '>= 3')
        """
        versop_msg = "this versop %s and versop_other %s" % (self, versop_other)

        if self == versop_other:
            self.log.debug("%s are equal. Return overlap True, conflict False." % versop_msg)
            return True, False
        # from here on, this versop and versop_other are not equal

        same_boundary = self.version == versop_other.version
        boundary_self_in_other = versop_other.test(self.version)
        boundary_other_in_self = self.test(versop_other.version)

        same_family = False
        for fam in self.OPERATOR_FAMILIES:
            fam_op = [self.OPERATOR_MAP[x] for x in fam]
            if self.operator in fam_op and versop_other.operator in fam_op:
                same_family = True

        include_ops = [self.OPERATOR_MAP[x] for x in self.INCLUDE_OPERATORS]
        self_includes_boundary = self.operator in include_ops
        other_includes_boundary = versop_other.operator in include_ops

        if boundary_self_in_other and boundary_other_in_self:
            msg = "Both %s are in each others range" % versop_msg
            if same_boundary:
                if op.xor(self_includes_boundary, other_includes_boundary):
                    self.log.debug("%s, one includes boundary and one is strict => overlap, no conflict" % msg)
                    return True, False
                else:
                    # conflict
                    self.log.debug("%s, and both include the boundary => overlap and conflict" % msg)
                    return True, True
            else:
                # conflict
                self.log.debug("%s, and different boundaries => overlap and conflict" % msg)
                return True, True
        else:
            # both boundaries not included in one other version expression
            # => never a conflict, only possible overlap
            msg = 'same boundary %s, same family %s;' % (same_boundary, same_family)
            if same_boundary:
                if same_family:
                    # overlap if one includes the boundary
                    overlap = self_includes_boundary or other_includes_boundary
                else:
                    # overlap if they both include the boundary
                    overlap = self_includes_boundary and other_includes_boundary
            else:
                # overlap if boundary of one is in other
                overlap = boundary_self_in_other or boundary_other_in_self
            self.log.debug("No conflict between %s; %s overlap %s, no conflict" % (versop_msg, msg, overlap))
            return overlap, False

    def __gt__(self, versop_other):
        """
        Determine if this instance is greater than supplied argument.

        Returns True if it is more strict in case of overlap, or if self.version > versop_other.version otherwise.
        Returns None in case of conflict.

        @param versop_other: a VersionOperator instance

        Examples:
            '> 2' > '> 1' : True, order by strictness equals order by boundaries for >, >=
            '< 8' > '< 10': True, order by strictness equals inversed order by boundaries for <, <=
            '== 4' > '> 3' : equality is more strict than inequality, but this order by boundaries
            '> 3' > '== 2' : there is no overlap, so just order the intervals according their boundaries
            '> 1' > '== 1' > '< 1' : no overlap, same boundaries, order by operator
        """
        overlap, conflict = self.test_overlap_and_conflict(versop_other)
        versop_msg = "this versop %s and versop_other %s" % (self, versop_other)

        if conflict:
            self.log.debug('gt: conflict %s, returning None' % versop_msg)
            return None

        if overlap:
            # just test one of them, because there is overlap and no conflict, no strange things can happen
            gte_ops = [self.OPERATOR_MAP['>'], self.OPERATOR_MAP['>=']]
            if self.operator in gte_ops or versop_other.operator in gte_ops:
                # test ordered boundaries
                gt_op = self.OPERATOR_MAP['>']
                msg = 'have >, >= operator; order by version'
            else:
                gt_op = self.OPERATOR_MAP['<']
                msg = 'have <, <= operator; order by inverse version'
        else:
            # no overlap, order by version
            gt_op = self.OPERATOR_MAP['>']
            msg = 'no overlap; order by version'

        is_gt = self._gt_safe(gt_op, versop_other)
        self.log.debug('gt: %s, %s => %s' % (versop_msg, msg, is_gt))

        return is_gt

    def _gt_safe(self, version_gt_op, versop_other):
        """Conflict free comparsion by version first, and if versions are equal, by operator"""
        if len(self.ORDERED_OPERATORS) != len(self.OPERATOR_MAP):
            self.log.error('Inconsistency between ORDERED_OPERATORS and OPERATORS (lists are not of same length)')

        # ensure this function is only used for non-conflicting version operators
        _, conflict = self.test_overlap_and_conflict(versop_other)
        if conflict:
            self.log.error("Conflicting version operator expressions should not be compared with _gt_safe")

        ordered_operators = [self.OPERATOR_MAP[x] for x in self.ORDERED_OPERATORS]
        if self.version == versop_other.version:
            # order by operator, lowest index wins
            op_idx = ordered_operators.index(self.operator)
            op_other_idx = ordered_operators.index(versop_other.operator)
            # strict inequality, already present operator wins
            # but this should be used with conflict-free versops
            return op_idx < op_other_idx
        else:
            return version_gt_op(self.version, versop_other.version)


class ToolchainVersionOperator(VersionOperator):
    """Class which represents a toolchain and versionoperator instance"""

    def __init__(self, tcversop_str=None):
        """
        Initialise VersionOperator instance.
        @param tcversop_str: intialise with toolchain version operator string
        """
        super(ToolchainVersionOperator, self).__init__()

        self.tc_name = None
        self.tcversop_str = None  # the full string

        if not tcversop_str is None:
            self.set(tcversop_str)

    def __str__(self):
        """Return string representation of this instance"""
        version_str = super(ToolchainVersionOperator, self).__str__()
        return ''.join(map(str, [self.tc_name, self.SEPARATOR, version_str]))

    def is_valid(self):
        """Check if this is a valid ToolchainVersionOperator"""
        _, all_tcs = search_toolchain('')
        tc_names = [x.NAME for x in all_tcs]
        known_tc_name = self.tc_name in tc_names
        return known_tc_name and super(ToolchainVersionOperator, self).is_valid()

    def versop_regex(self):
        """
        Create the regular expression for toolchain support of format ^<toolchain> <versop_expr>$ ,
        with <toolchain> the name of one of the supported toolchains and <versop_expr> in '<operator> <version>' syntax
        """
        _, all_tcs = search_toolchain('')
        tc_names = [x.NAME for x in all_tcs]
        self.log.debug("found toolchain names %s" % tc_names)

        versop_regex = super(ToolchainVersionOperator, self).versop_regex(begin_end=False)
        versop_pattern = r'(?P<versop_str>%s)' % versop_regex.pattern
        tc_names_regex = r'(?P<tc_name>(?:%s))' % '|'.join(tc_names)
        tc_regex = re.compile(r'^%s(?:%s%s)?$' % (tc_names_regex, self.SEPARATOR, versop_pattern))

        self.log.debug("toolchain versop regex pattern %s " % tc_regex.pattern)
        return tc_regex

    def parse_versop_str(self, tcversop_str):
        """
        If argument matches a toolchain versop, return dict with toolchain name and version, and optionally operator.
        Otherwise, return None.
        """
        res = self.regex.search(tcversop_str)
        if not res:
            self.parse_error("No toolchain version operator match for '%s'" % tcversop_str)
            return None

        tcversop_dict = res.groupdict()
        tcversop_dict['tcversop_str'] = tcversop_str  # the total string

        tcversop_dict = super(ToolchainVersionOperator, self).parse_versop_str(None, versop_dict=tcversop_dict)

        self.log.debug("toolchain versop expression '%s' parsed to '%s'" % (tcversop_str, tcversop_dict))
        return tcversop_dict


class OrderedVersionOperators(object):
    """
    Ordered version operators. The ordering is defined such that one can test from left to right,
    and assume that the first matching version operator is the one that is the best match.
        
    Example: '> 2', '> 3' should be ordered ['> 3', '> 2'], because for 4, both match, but 3 is considered more strict.

    Conflicting version operators are not allowed.
    """

    def __init__(self):
        """Initialise the list of version operators as an empty list."""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.versops = []
        self.datamap = {}

    def __str__(self):
        """Print the list"""
        return str(self.versops)

    def add(self, versop_new, data=None):
        """
        Try to add argument as VersionOperator instance to current list of version operators.
        Make sure there is no conflict with existing versops, and that the ordering is maintained.

        @param versop_new: VersionOperator instance (or will be converted into one if type basestring)
        @param data: additional data for supplied version operator to be stored
        """
        if isinstance(versop_new, basestring):
            versop_new = VersionOperator(versop_new)
        elif not isinstance(versop_new, VersionOperator):
            arg = (versop_new, type(versop_new))
            self.log.error(("add: argument must be a VersionOperator instance or basestring: %s; type %s") % arg)

        if versop_new in self.versops:
            # adding the same version operator twice is considered a failure
            self.log.error("Versop %s already added." % versop_new)
        else:
            # no need for equality testing, we consider it an error
            gt_test = [versop_new > versop for versop in self.versops]
            if None in gt_test:
                # conflict
                msg = 'add: conflict(s) between versop_new %s and existing versions %s'
                conflict_versops = [(idx, self.versops[idx]) for idx, gt_val in enumerate(gt_test) if gt_val is None]
                self.log.error(msg % (versop_new, conflict_versops))
            else:
                if True in gt_test:
                    # determine first element for which comparison is True
                    insert_idx = gt_test.index(True)
                    self.log.debug('add: insert versop %s in index %s' % (versop_new, insert_idx))
                    self.versops.insert(insert_idx, versop_new)
                else:
                    self.log.debug("add: versop_new %s is not > then any element, appending it" % versop_new)
                    self.versops.append(versop_new)
                self.log.debug("add: new ordered list of version operators: %s" % self.versops)

                self.log.debug("Keeping track of data for %s: %s" % (versop_new, data))
                self.datamap[versop_new] = data

class ConfigObjVersion(object):
    """
    ConfigObj version checker
    - first level sections except default
      - check toolchain
      - check version
    - second level
      - version : dependencies

    Given ConfigObj instance, make instance that can check if toolchain/version is allowed,
    return version, toolchain name, toolchain version and dependency

    Mandatory/minimal (to mimic v1.0 behaviour)
    [DEFAULT]
    versions=version_operator
    toolchains=toolchain_version_operator

    Optional
    [DEFAULT]
    [[SUPPORTED]]
    toolchains=toolchain_versop[,...]
    versions=versop[,...]
    [<operatorX> <versionX>]
    [<operatorY> <versionY>]
    [<toolchainA> <operatorA> <versionA>]
    [<toolchainB> <operatorB> <versionB>]
    
    """
    # TODO: add nested/recursive example to docstring

    DEFAULT = 'DEFAULT'
    # list of known marker types (except default)
    KNOWN_MARKER_TYPES = [ToolchainVersionOperator, VersionOperator]  # order matters, see parse_sections
    VERSION_OPERATOR_VALUE_TYPES = {
        'toolchains': ToolchainVersionOperator,
        'versions': VersionOperator,
    }

    def __init__(self, configobj=None):
        """
        Initialise ConfigObjVersion instance
        @param configobj: ConfigObj instance
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.tcname = None

        self.default = {}  # default section
        self.sections = {}  # non-default sections
        self.unfiltered_sections = {}  # unfiltered non-default sections

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
        #    versions: comma-separated list of version operators
        #    toolchains: comma-separated list of toolchain version operators
        SUPPORTED_KEYS = ('versions', 'toolchains')
        if parent is None:
            # no parent, so top sections
            parsed_sections = {}
        else:
            # parent specified, so not a top section
            parsed_sections = Section(parent=parent, depth=depth+1, main=configobj)

        # start with full configobj initially, and then process subsections recursively
        if toparse is None:
            toparse = configobj

        for key, value in toparse.items():
            if isinstance(value, Section):
                self.log.debug("Enter subsection key %s value %s" % (key, value))
                # only 3 types of sectionkeys supported: VersionOperator, ToolchainVersionOperator, and DEFAULT
                if key in [self.DEFAULT]:
                    new_key = key
                else:
                    # try parsing key as toolchain version operator first
                    # try parsing as version operator if it's not a toolchain version operator
                    for marker_type in self.KNOWN_MARKER_TYPES:
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

            else:
                new_key = key

                # don't allow any keys we don't know about (yet)
                if not new_key in SUPPORTED_KEYS:
                    self.log.error('Unsupported key %s with value %s in section' % (new_key, value))

                # parse individual key-value assignments
                if new_key in self.VERSION_OPERATOR_VALUE_TYPES:
                    value_type = self.VERSION_OPERATOR_VALUE_TYPES[new_key]
                    # list of supported toolchains/versions
                    # first one is default
                    if isinstance(value, basestring):
                        # so the split should be unnecessary
                        # (if it's not a list already, it's just one value)
                        # TODO this is annoying. check if we can force this in configobj
                        value = value.split(',')
                    # remove possible surrounding whitespace (some people add space after comma)
                    new_value = map(lambda x: value_type(x.strip()), value)
                else:
                    tup = (new_key, value, type(value))
                    self.log.error('Bug: supported but unknown key %s with non-string value: %s, type %s' % tup)

            self.log.debug('Converted key %s value %s in new key %s new value %s' % (key, value, new_key, new_value))
            parsed_sections[new_key] = new_value

        return parsed_sections

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
                        # add marker to self.tcversops (which triggers a conflict check)
                        self.tcversops.add(key, value)
                        filtered_sections[key] = value
                elif isinstance(key, VersionOperator):
                    # keep track of all version operators, and enforce conflict check
                    self.versops.add(key, value)
                    filtered_sections[key] = value
                else:
                    self.log.error("Unhandled section marker type '%s', not in %s?" % (type(key), self.KNOWN_MARKER_TYPES))

                # recursively go deeper for (relevant) sections
                self.validate_and_filter_by_toolchain(tcname, value, filtered_sections, other_sections)

            elif key in self.VERSION_OPERATOR_VALUE_TYPES:
                if key == 'toolchains':
                    # remove any other toolchain from list
                    filtered_sections[key] = [tcversop for tcversop in value if tcversop.tc_name == tcname]
                else:
                    # retain all other values
                    filtered_sections[key] = value
            else:
                filtered_sections[key] = value

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

        # check for defaults section
        default = self.sections.pop(self.DEFAULT, {})
        DEFAULT_KEYWORDS = ('toolchains', 'versions')
        # default should only have versions and toolchains
        # no nesting
        #  - add DEFAULT key,values to the root of self.sections
        for key, value in default.items():
            if not key in DEFAULT_KEYWORDS:
                self.log.error('Unsupported key %s in %s section' % (key, self.DEFAULT))
            self.sections[key] = value

        if 'versions' in default:
            # first of list is special: it is the default
            default['default_version'] = default['versions'][0]
        if 'toolchains' in default:
            # first of list is special: it is the default
            default['default_toolchain'] = default['toolchains'][0]

        self.default = default
        self.log.debug("parse: default %s, sections %s" % (self.default, self.sections))
