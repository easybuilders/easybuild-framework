# #
# Copyright 2013-2018 Ghent University
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
# #

"""
This describes the easyconfig version class. To be used in EasyBuild for anything related to version checking

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
import operator as op
import re
from distutils.version import LooseVersion
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.utilities import search_toolchain


# a cache for toolchain names lookups (defined at runtime).
TOOLCHAIN_NAMES = {}


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

    # default version and operator when version is undefined
    DEFAULT_UNDEFINED_VERSION = EasyVersion('0.0.0')
    DEFAULT_UNDEFINED_VERSION_OPERATOR = OPERATOR_MAP['>']
    # default operator when operator is undefined (but version is)
    DEFAULT_UNDEFINED_OPERATOR = OPERATOR_MAP['==']

    DICT_SEPARATOR = ':'

    def __init__(self, versop_str=None, error_on_parse_failure=False):
        """
        Initialise VersionOperator instance.
        :param versop_str: intialise with version operator string
        :param error_on_parse_failure: raise EasyBuildError in case of parse error
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.versop_str = None
        self.operator_str = None
        self.version_str = None
        self.version = None
        self.operator = None
        self.suffix = None
        self.regex = self.versop_regex()

        self.error_on_parse_failure = error_on_parse_failure
        if not versop_str is None:
            self.set(versop_str)

    def parse_error(self, msg):
        """Special function to deal with parse errors"""
        # TODO major issue what to do in case of misparse. error or not?
        if self.error_on_parse_failure:
            raise EasyBuildError(msg)
        else:
            self.log.debug(msg)

    def __bool__(self):
        """Interpretation of a VersionOperator instance as a boolean expression: is it valid?"""
        return self.is_valid()

    # Python 2.x compatibility
    __nonzero__ = __bool__

    def is_valid(self):
        """Check if this is a valid VersionOperator. Suffix can be anything."""
        return not(self.version is None or self.operator is None)

    def set(self, versop_str):
        """
        Parse argument as a version operator, and set attributes.
        Returns True in case of success, throws an error in case of parsing failure.
        """
        versop_dict = self.parse_versop_str(versop_str)
        if versop_dict is None:
            raise EasyBuildError("Failed to parse '%s' as a version operator string", versop_str)
        else:
            for k, v in versop_dict.items():
                setattr(self, k, v)
            return True

    def test(self, test_version):
        """
        Convert argument to an EasyVersion instance if needed, and return self.operator(<argument>, self.version)
            Versions only, no suffix.
        :param test_version: a version string or EasyVersion instance
        """
        # checks whether this VersionOperator instance is valid using __bool__ function
        if not self:
            raise EasyBuildError('Not a valid %s. Not initialised yet?', self.__class__.__name__)

        if isinstance(test_version, basestring):
            test_version = self._convert(test_version)
        elif not isinstance(test_version, EasyVersion):
            raise EasyBuildError("test: argument should be a basestring or EasyVersion (type %s)", type(test_version))

        res = self.operator(test_version, self.version)
        self.log.debug("result of testing expression '%s %s %s': %s",
                       test_version, self.REVERSE_OPERATOR_MAP[self.operator], self.version, res)

        return res

    def __str__(self):
        """Return string representation of this VersionOperator instance"""
        if self.operator is None:
            if self.version is None:
                operator = self.DEFAULT_UNDEFINED_VERSION_OPERATOR
            else:
                operator = self.DEFAULT_UNDEFINED_OPERATOR
        else:
            operator = self.operator
        operator_str = self.REVERSE_OPERATOR_MAP[operator]

        tmp = [operator_str, self.SEPARATOR, self.version]
        if self.suffix is not None:
            tmp.extend([self.SEPARATOR, self.suffix])
        return ''.join(map(str, tmp))

    def get_version_str(self):
        """Return string representation of version (ignores operator)."""
        return str(self.version)

    def __repr__(self):
        """Return instance as string (ignores begin_end)"""
        return "%s('%s')" % (self.__class__.__name__, self)

    def __eq__(self, versop):
        """Compare this instance to supplied argument."""
        if versop is None:
            return False
        elif not isinstance(versop, self.__class__):
            raise EasyBuildError("Types don't match in comparison: %s, expected %s", type(versop), self.__class__)
        return self.version == versop.version and self.operator == versop.operator and self.suffix == versop.suffix

    def __ne__(self, versop):
        """Is self not equal to versop"""
        return not self.__eq__(versop)

    def versop_regex(self, begin_end=True):
        """
        Create the version regular expression with operator support.
        This supports version expressions like '> 5' (anything strict larger than 5),
        or '<= 1.2' (anything smaller than or equal to 1.2)
        :param begin_end: boolean, create a regex with begin/end match
        """
        # construct escaped operator symbols, e.g. '\<\='
        operators = []
        for operator in self.OPERATOR_MAP.keys():
            operators.append(re.sub(r'(.)', r'\\\1', operator))

        # regex to parse version expression
        # - operator_str part is optional
        # - version_str should start/end with any word character except separator
        # - minimal version_str length is 1
        # - optional extensions:
        #    - suffix: the version suffix
        reg_text_operator = r"(?:(?P<operator_str>%(ops)s)%(sep)s)?" % {
            'sep': self.SEPARATOR,
            'ops': '|'.join(operators),
        }
        reg_text_version = r"(?P<version_str>[^%(sep)s\W](?:\S*[^%(sep)s\W])?)" % { 'sep': self.SEPARATOR }
        reg_text_ext = r"(?:%(sep)s(?:suffix%(extsep)s(?P<suffix>[^%(sep)s]+)))?" % {
            'sep': self.SEPARATOR,
            'extsep': self.DICT_SEPARATOR,
        }

        reg_text = r"%s%s%s" % (reg_text_operator, reg_text_version, reg_text_ext)
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

    def _convert_operator(self, operator_str, version=None):
        """Return the operator"""
        operator = None
        if operator_str is None:
            if version == self.DEFAULT_UNDEFINED_VERSION or version is None:
                operator = self.DEFAULT_UNDEFINED_VERSION_OPERATOR
            else:
                operator = self.DEFAULT_UNDEFINED_OPERATOR
            self.log.warning('_convert: operator_str None, set it to default operator (with version: %s) %s' % (operator, version))
        elif operator_str in self.OPERATOR_MAP:
            operator = self.OPERATOR_MAP[operator_str]
        else:
            self.parse_error('Failed to match specified operator %s to operator function' % operator_str)
        return operator

    def parse_versop_str(self, versop_str, versop_dict=None):
        """
        If argument contains a version operator, returns a dict with version and operator; returns None otherwise
        :param versop_str: the string to parse
        :param versop_dict: advanced usage: pass intialised versop_dict (eg for ToolchainVersionOperator)
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
            raise EasyBuildError('Missing versop_str in versop_dict %s', versop_dict)

        version = self._convert(versop_dict['version_str'])
        operator = self._convert_operator(versop_dict['operator_str'], version=version)

        versop_dict['version'] = version
        versop_dict['operator'] = operator
        self.log.debug('versop expression %s parsed into versop_dict %s' % (versop_dict['versop_str'], versop_dict))

        return versop_dict

    def _boundary_check(self, other):
        """Return the boundary checks via testing: is self in other, and is other in self
        :param other: a VersionOperator instance
        """
        boundary_self_in_other = other.test(self.version)
        boundary_other_in_self = self.test(other.version)
        return boundary_self_in_other, boundary_other_in_self

    def test_overlap_and_conflict(self, versop_other):
        """
        Test if there is any overlap between this instance and versop_other, and if so, if there is a conflict or not.
        
        Returns 2 booleans: has_overlap, is_conflict
        
        :param versop_other: a VersionOperator instance
        
        Examples:
            '> 3' and '> 3' : equal, and thus overlap (no conflict)
            '> 3' and '< 2' : no overlap
            '< 3' and '> 2' : overlap, and conflict (region between 2 and 3 is ambiguous)
            '> 3' and '== 3' : no overlap
            '>= 3' and '== 3' : overlap, and conflict (boundary 3 is ambigous)
            '> 3' and '>= 3' : overlap, no conflict ('> 3' is more strict then '>= 3')
            
            # suffix
            '> 2 suffix:-x1' > '> 1 suffix:-x2': suffix not equal, conflict
        """
        versop_msg = "this versop %s and versop_other %s" % (self, versop_other)

        if not isinstance(versop_other, self.__class__):
            raise EasyBuildError("overlap/conflict check needs instance of self %s (got type %s)",
                                 self.__class__.__name__, type(versop_other))

        if self == versop_other:
            self.log.debug("%s are equal. Return overlap True, conflict False." % versop_msg)
            return True, False

        # from here on, this versop and versop_other are not equal
        same_boundary = self.version == versop_other.version
        boundary_self_in_other, boundary_other_in_self = self._boundary_check(versop_other)

        suffix_allowed = self.suffix == versop_other.suffix

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
                    overlap_conflict = (True, False)
                else:
                    # conflict
                    self.log.debug("%s, and both include the boundary => overlap and conflict" % msg)
                    overlap_conflict = (True, True)
            else:
                # conflict
                self.log.debug("%s, and different boundaries => overlap and conflict" % msg)
                overlap_conflict = (True, True)
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
            overlap_conflict = (overlap, False)

        if not suffix_allowed:
            # always conflict
            self.log.debug("Suffix for %s are not equal. Force conflict True." % versop_msg)
            overlap_conflict = (overlap_conflict[0], True)

        return overlap_conflict

    def __gt__(self, versop_other):
        """
        Determine if this instance is greater than supplied argument.

        Returns True if it is more strict in case of overlap, or if self.version > versop_other.version otherwise.
        Returns None in case of conflict.

        :param versop_other: a VersionOperator instance

        Examples:
            '> 2' > '> 1' : True, order by strictness equals order by boundaries for >, >=
            '< 8' > '< 10': True, order by strictness equals inversed order by boundaries for <, <=
            '== 4' > '> 3' : equality is more strict than inequality, but this order by boundaries
            '> 3' > '== 2' : there is no overlap, so just order the intervals according their boundaries
            '> 1' > '== 1' > '< 1' : no overlap, same boundaries, order by operator
            suffix:
                '> 2' > '> 1': both equal (both None), ordering like above
                '> 2 suffix:-x1' > '> 1 suffix:-x1': both equal (both -x1), ordering like above
                '> 2 suffix:-x1' > '> 1 suffix:-x2': not equal, conflict
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
        """Conflict free comparsion by version first, and if versions are equal, by operator. 
            Suffix are not considered.
        """
        if len(self.ORDERED_OPERATORS) != len(self.OPERATOR_MAP):
            raise EasyBuildError("Inconsistency between ORDERED_OPERATORS and OPERATORS (lists are not of same length)")

        # ensure this function is only used for non-conflicting version operators
        _, conflict = self.test_overlap_and_conflict(versop_other)
        if conflict:
            raise EasyBuildError("Conflicting version operator expressions should not be compared with _gt_safe")

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
        :param tcversop_str: intialise with toolchain version operator string
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

    def _get_all_toolchain_names(self, search_string=''):
        """
        Initialise each search_toolchain request, save in module constant TOOLCHAIN_NAMES.
        :param search_string: passed to search_toolchain function.
        """
        global TOOLCHAIN_NAMES
        if not search_string in TOOLCHAIN_NAMES:
            _, all_tcs = search_toolchain(search_string)
            self.log.debug('Found all toolchains for "%s" to %s' % (search_string, all_tcs))
            TOOLCHAIN_NAMES[search_string] = [x.NAME for x in all_tcs]
            self.log.debug('Set TOOLCHAIN_NAMES for "%s" to %s' % (search_string, TOOLCHAIN_NAMES[search_string]))

        return TOOLCHAIN_NAMES[search_string]

    def is_valid(self):
        """Check if this is a valid ToolchainVersionOperator"""
        tc_names = self._get_all_toolchain_names()
        known_tc_name = self.tc_name in tc_names
        return known_tc_name and super(ToolchainVersionOperator, self).is_valid()

    def set(self, tcversop_str):
        """
        Parse argument as toolchain version string, and set attributes.
        Returns None in case of failure (e.g. if supplied string doesn't parse), True in case of success.
        """
        versop_dict = self.parse_versop_str(tcversop_str)
        if versop_dict is None:
            self.log.warning("Failed to parse '%s' as a toolchain version operator string" % tcversop_str)
            return None
        else:
            for k, v in versop_dict.items():
                setattr(self, k, v)
            return True

    def versop_regex(self):
        """
        Create the regular expression for toolchain support of format ^<toolchain> <versop_expr>$ ,
        with <toolchain> the name of one of the supported toolchains and <versop_expr> in '<operator> <version>' syntax
        """
        tc_names = self._get_all_toolchain_names()
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

        if tcversop_dict.get('version_str', None) is not None and tcversop_dict.get('operator_str', None) is None:
            raise EasyBuildError("Toolchain version found, but no operator (use ' == '?).")

        self.log.debug("toolchain versop expression '%s' parsed to '%s'" % (tcversop_str, tcversop_dict))
        return tcversop_dict

    def _boundary_check(self, other):
        """Return the boundary checks via testing: is self in other, and is other in self
        :param other: a ToolchainVersionOperator instance
        """
        boundary_self_in_other = other.test(self.tc_name, self.version)
        boundary_other_in_self = self.test(other.tc_name, other.version)
        return boundary_self_in_other, boundary_other_in_self

    def test(self, name, version):
        """
        Check if a toolchain with name name and version version would fit 
            in this ToolchainVersionOperator 
        :param name: toolchain name
        :param version: a version string or EasyVersion instance
        """
        # checks whether this ToolchainVersionOperator instance is valid using __bool__ function
        if not self:
            raise EasyBuildError('Not a valid %s. Not initialised yet?', self.__class__.__name__)

        tc_name_res = name == self.tc_name
        if not tc_name_res:
            self.log.debug('Toolchain name %s different from test toolchain name %s' % (self.tc_name, name))
        version_res = super(ToolchainVersionOperator, self).test(version)
        res = tc_name_res and version_res
        self.log.debug("result of testing expression tc_name_res %s version_res %s: %s", tc_name_res, version_res, res)

        return res

    def as_dict(self):
        """
        Return toolchain version operator as a dictionary with name/version keys.
        Returns None if translation to a dictionary is not possible (e.g. non-equals operator, missing version, ...).
        """
        version = self.get_version_str()
        # TODO allow all self.INCLUDE_OPERATORS?
        allowed = [self.OPERATOR_MAP[x] for x in ['==']]
        if self.operator in allowed:
            tc_dict = {
                'name': self.tc_name,
                'version': version,
            }
            if self.suffix is not None:
                tc_dict.update({'versionsuffix': self.suffix})
            self.log.debug('returning %s as dict (allowed operator %s)' % (tc_dict, self.operator))
            return tc_dict
        else:
            self.log.debug('returning None as dict; operator %s not in allowed list (%s)' % (self.operator, allowed))
            return None


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
        """Print the list and map"""
        return "ordered version operators: %s; data map: %s" % (self.versops, self.datamap)

    def add(self, versop_new, data=None, update=None):
        """
        Try to add argument as VersionOperator instance to current list of version operators.
        Make sure there is no conflict with existing versops, and that the ordering is maintained.
        After add, versop_new is in the OrderedVersionOperators. If the same versop_new was already in it,
        it will update the data (if not None) (and not raise an error)

        :param versop_new: VersionOperator instance (or will be converted into one if type basestring)
        :param data: additional data for supplied version operator to be stored
        :param update: if versop_new already exist and has data set, try to update the existing data with the new data; 
                       instead of overriding the existing data with the new data (method used for updating is .update)    
        """
        if isinstance(versop_new, basestring):
            versop_new = VersionOperator(versop_new)
        elif not isinstance(versop_new, VersionOperator):
            raise EasyBuildError("add: argument must be a VersionOperator instance or basestring: %s; type %s",
                                 versop_new, type(versop_new))

        if versop_new in self.versops:
            self.log.debug("Versop %s already added." % versop_new)
        else:
            # no need for equality testing, we consider it an error
            gt_test = [versop_new > versop for versop in self.versops]
            if None in gt_test:
                # conflict
                conflict_versops = [(idx, self.versops[idx]) for idx, gt_val in enumerate(gt_test) if gt_val is None]
                raise EasyBuildError("add: conflict(s) between versop_new %s and existing versions %s",
                                     versop_new, conflict_versops)
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

        self._add_data(versop_new, data, update)

    def _add_data(self, versop_new, data, update):
        """Add the data to the datamap, use the string representation of the operator as key"""
        versop_new_str = str(versop_new)

        if update and versop_new_str in self.datamap:
            self.log.debug("Keeping track of data for %s UPDATE: %s" % (versop_new_str, data))
            if not hasattr(self.datamap[versop_new_str], 'update'):
                raise EasyBuildError("Can't update on datamap key %s type %s",
                                     versop_new_str, type(self.datamap[versop_new_str]))
            self.datamap[versop_new_str].update(data)
        else:
            self.log.debug("Keeping track of data for %s SET: %s" % (versop_new_str, data))
            self.datamap[versop_new_str] = data

    def get_data(self, versop):
        """Return the data for versop from datamap"""
        if not isinstance(versop, VersionOperator):
            raise EasyBuildError("get_data: argument must be a VersionOperator instance: %s; type %s",
                                  versop, type(versop))

        versop_str = str(versop)
        if versop_str in self.datamap:
            return self.datamap[versop_str]
        else:
            raise EasyBuildError("No data in datamap for versop %s", versop)
