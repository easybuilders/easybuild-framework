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
This describes the easyconfig version class. To be used in easybuild for anything related to version checking

@author: Stijn De Weirdt (Ghent University)
"""

import operator as op
import re
from distutils.version import LooseVersion
from vsc import fancylogger

from easybuild.tools.toolchain.utilities import search_toolchain


class EasyVersion(LooseVersion):
    """Exact LooseVersion. No modifications needed (yet)"""
    # TODO: replace all LooseVersion with EasyVersion in eb, after moving EasyVersion to easybuild/tools?

    def __len__(self):
        """Determine length of this EasyVersion instance."""
        return len(self.version)

class VersionOperator(object):
    """
    VersionOperator class represents a version expression that includes an operator.
    """

    SEPARATOR = ' '  # single space as (mandatory) separator in section markers, excellent readability
    OPERATOR = {
        '==': op.eq,  # no !=, exceptions to the default should be handled with a dedicated section using ==
        '>': op.gt,
        '>=': op.ge,
        '<': op.lt,
        '<=': op.le,
    }
    INCLUDE_OPERATORS = ('==', '>=', '<=')  # these version operators include the version-boundary
    ORDERED_OPERATORS = ('>', '>=', '==', '<=', '<')  # arbitrary ordering for consistency
    OPERATOR_FAMILIES = (('>', '>='), ('<', '<='))  # similar operators
    DEFAULT_UNDEFINED_VERSION = EasyVersion('0.0.0')
    DEFAULT_UNDEFINED_OPERATOR = op.eq

    def __init__(self, versop_str=None):
        """Initialise.
            @param versop: intialise with version operator string
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.regex = self.versop_regex()

        self.versop_str = None
        self.operator_str = None
        self.version_str = None
        self.version = None
        self.operator = None
        self._test_fn = None

        if not versop_str is None:
            self.set(versop_str)

    def set(self, versop_str):
        """Convert versop_str and set the attributes.
            Return None in case of failure (eg versop_str doesn't parse), True in case of success
        """
        versop_dict = self.parse_versop_str(versop_str)
        if versop_dict is None:
            self.log.debug("Failed to set versop_str %s" % versop_str)
            return None
        else:
            for k, v in versop_dict.items():
                setattr(self, k, v)
            return True

    def test(self, test_version):
        """Convert test_version in EasyVersion if needed, and return self.operator(test_version,self.version)
            Wrapper around self._test_fn. 
            @param test_version: a version string or EasyVersion instance
        """
        if self.operator is None:
            self.log.error('self.operator None. Not initialised yet? returning None')
            return None
        if self.version is None:
            self.log.error('self.version None. Not initialised yet? returning None')
            return None

        if isinstance(test_version, basestring):
            test_version = self._convert(test_version)
        elif not isinstance(test_version, EasyVersion):
            self.log.error('test_verstion_str %s should be basestring or EasyVersion (type %s)' % type(test_version))

        res = self.operator(test_version, self.version)
        self.log.debug('Testversion %s version %s operator %s: %s' % (test_version, self.version, self.operator, res))

        return res

    def __str__(self):
        """Return string"""
        if self.operator is None:
            operator = self.DEFAULT_UNDEFINED_OPERATOR
        else:
            operator = self.operator
        operator_str = dict([(v, k) for k, v in self.OPERATOR.items()]).get(operator)
        return "%s%s%s" % (operator_str, self.SEPARATOR, self.version)

    def __repr__(self):
        """Return the vers_str (ignores begin_end)"""
        return "%s('%s')" % (self.__class__.__name__, self)

    def __eq__(self, versop):
        """Is self equal to versop"""
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
        for operator in self.OPERATOR.keys():
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

        self.log.debug("versop pattern '%s' (begin_end: %s)" % (reg.pattern, begin_end))
        return reg

    def _convert(self, version_str):
        """Convert string to EasyVersion instance that can be compared"""
        if version_str is None:
            version = self.DEFAULT_UNDEFINED_VERSION
            self.log.warning('_convert: version_str None, set it to DEFAULT_UNDEFINED_VERSION %s' % version)
        else:
            try:
                version = EasyVersion(version_str)
            except (AttributeError, ValueError), err:
                self.log.error('Failed to convert %s to an EasyVersion instance: %s' % (version_str, err))

        self.log.debug('converted string %s to version %s' % (version_str, version))
        return version

    def _convert_operator(self, operator_str):
        """Return the operator"""
        if operator_str is None:
            operator = self.DEFAULT_UNDEFINED_OPERATOR
            self.log.warning('_convert: operator_str None, set it to DEFAULT_UNDEFINED_OPERATOR %s' % operator)
        elif operator_str in self.OPERATOR:
            operator = self.OPERATOR[operator_str]
        else:
            self.log.error('Failed to match specified operator %s to operator function' % operator_str)
        return operator

    def parse_versop_str(self, versop_str, versop_dict=None):
        """
        If argument contains a version operator, returns a dict with 
            version and test_fn; 
            returns None otherwise
            @param versop_str: the string to parse 
            @param versop_dict: advanced usage: pass intialised versop_dict (eg for ToolchainVersionOperator)
        """
        if versop_dict is None:
            versop_dict = {}

        if versop_str is not None:
            res = self.regex.search(versop_str)
            if not res:
                self.log.error('No regex match for versop expression %s' % versop_str)
                return None

            versop_dict.update(res.groupdict())
            versop_dict['versop_str'] = versop_str

        if not 'versop_str' in versop_dict:
            self.log.error('Missing versop_strin versop_dict %s' % versop_dict)

        versop_dict['version'] = self._convert(versop_dict['version_str'])
        versop_dict['operator'] = self._convert_operator(versop_dict['operator_str'])
        self.log.debug('versop expression %s parsed into versop_dict %s' % (versop_dict['versop_str'], versop_dict))

        return versop_dict

    def test_overlap_and_conflict(self, versop_other):
        """
        Test if there is any overlap between this versop and versop_other, and if so, 
        if it is a conflict or not.
        
        Returns 2 booleans: has_overlap, is_conflict
        
        @param versop_other: VersionOperator instances
        
        Examples:
            '> 3' and '> 3' : equal, and thus overlap
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
        boundary_self_in_other = versop_other.test(self.version)
        boundary_other_in_self = self.test(versop_other.version)

        same_boundary = self.version == versop_other.version
        same_family = False
        for fam in self.OPERATOR_FAMILIES:
            fam_op = [self.OPERATOR[x] for x in fam]
            if self.operator in fam_op and versop_other.operator in fam_op:
                same_family = True

        include_ops = [self.OPERATOR[x] for x in self.INCLUDE_OPERATORS]
        self_includes_boundary = self.operator in include_ops
        other_includes_boundary = versop_other.operator in include_ops

        if boundary_self_in_other and boundary_other_in_self:
            msg = "Both %s are in each others range" % versop_msg
            if same_boundary:
                if op.xor(self_includes_boundary, other_includes_boundary):
                    self.log.debug("%s, one of them includes the boundary and one of them is strict; return True,False" % msg)
                    return True, False
                else:
                    # conflict.
                    self.log.debug("%s, and both include the boundary; Conflict, returning True,True" % msg)
                    return True, True
            else:
                # conflict.
                self.log.debug("%s, and different boundaries; Conflict, returning True,True" % msg)
                return True, True
        else:
            msg = 'same boundary %s, same_family %s;' % (same_boundary, same_family)
            if same_boundary:
                if same_family:
                    # overlap if one includes the boundary
                    ans = self_includes_boundary or other_includes_boundary
                else:
                    # overlap if they both include the boundary
                    ans = self_includes_boundary and other_includes_boundary
            else:
                ans = boundary_self_in_other or boundary_other_in_self
            self.log.debug("No conflict between %s;%s overlap %s " % (versop_msg, msg, ans))
            return ans, False

    def __gt__(self, versop_other):
        """self is greater then versop_other if it is more strict in case of overlap or
            in case self.version > versop_other.version otherwise.
            Return None in case of conflict.

            e.g. '> 2' > '> 1' : True, order by strictness equals order by boundaries for gt/ge
                 '< 8' > '< 10': True, order by strictness equals inversed order by boundaries for lt/le
                 '== 4' > '> 3' : equality is more strict then inequality, but this order by boundaries
                 '> 3' > '== 2' : there is no overlap, so just order the intervals according their boundaries
                 '> 1' > '== 1' > '< 1' : no overlap, same boundaries, order by operator
        """
        overlap, conflict = self.test_overlap_and_conflict(versop_other)
        versop_msg = "this versop %s and versop_other %s" % (self, versop_other)

        if conflict:
            self.log.debug('gt: conflict %s. returning None' % versop_msg)
            ans = None
        else:
            if overlap:
                # just test one of them, because there is overlap and no conflict, no strange things can happen
                if self.operator in (op.gt, op.ge) or versop_other.operator in (op.gt, op.ge):
                    # test ordered boundaries/
                    gt_op = op.gt
                    msg = 'have gt/ge operator; order by version'
                else:
                    gt_op = op.lt
                    msg = 'have lt/le operator; order by inverse version'
            else:
                # no overlap, order by version
                gt_op = op.gt
                msg = 'no overlap; order by version'

            ans = self._gt_safe(gt_op, versop_other)
            self.log.debug('gt: %s, %s, ans %s' % (versop_msg, msg, ans))

        return ans

    def _gt_safe(self, version_gt_op, versop_other):
        """Conflict free comparsion by version first, and if versions are equal, by operator"""
        if len(self.ORDERED_OPERATORS) != len(self.OPERATOR):
            self.log.error('Inconsistency between ORDERED_OPERATORS and OPERATORS')

        ordered_operators = [self.OPERATOR[x] for x in self.ORDERED_OPERATORS]
        if self.version == versop_other.version:
            # order by operator, lowest index wins
            idx = ordered_operators.index(self.operator)
            idx_other = ordered_operators.index(versop_other.operator)
            # strict inequality, already present operator wins
            # but this should be used with conflict-free versops
            return idx < idx_other
        else:
            return version_gt_op(self.version, versop_other.version)


class ToolchainVersionOperator(VersionOperator):
    """Class which represents a toolchain and versionoperator instance"""

    def __init__(self, tcversop_str=None):
        """Initialise"""
        super(ToolchainVersionOperator, self).__init__()

        self.tc_name = None
        self.tcversop_str = None  # the full string

        if not tcversop_str is None:
            self.set(tcversop_str)

    def versop_regex(self):
        """
        Create the regular expression for toolchain support of format
            ^<toolchain> <versop_expr>$
                with <toolchain> the name of one of the supported toolchains and 
                <versop_expr> in '<operator> <version>' syntax
        """
        _, all_tcs = search_toolchain('')
        tc_names = [x.NAME for x in all_tcs]
        self.log.debug("found toolchain names %s" % tc_names)

        versop_regex = super(ToolchainVersionOperator, self).versop_regex(begin_end=False)
        versop_pattern = r'(?P<versop_str>%s)' % versop_regex.pattern
        tc_names_regex = r'(?P<tc_name>(?:%s))' % '|'.join(tc_names)
        tc_regex = re.compile(r'^%s(?:%s%s)?$' % (tc_names_regex, self.SEPARATOR, versop_pattern))

        self.log.debug("Toolchain_versop pattern %s " % tc_regex.pattern)
        return tc_regex

    def parse_versop_str(self, tcversop_str):
        """
        If argument matches a toolchain versop, return dict with 
            toolchain name and version, and optionally operator and test_function.
        Otherwise, return None
        """
        res = self.regex.search(tcversop_str)
        if not res:
            self.log.error('No toolchain versionoperator match for %s' % tcversop_str)
            return None

        tcversop_dict = res.groupdict()
        tcversop_dict['tcversop_str'] = tcversop_str  # the total string

        tcversop_dict = super(ToolchainVersionOperator, self).parse_versop_str(None, versop_dict=tcversop_dict)

        self.log.debug('toolchain versop expression %s parsed to %s' % (tcversop_str, tcversop_dict))
        return tcversop_dict


class OrderedVersionOperators(object):
    """
    Ordered version operators. The ordering is defined such that 
        one can test from left to right and that assume that the first 
        matching version operator is the one that is the best match.
        
    E.g. '> 3' and '> 2' should be ordered ['> 3', '> 2'], because for 
        4, both with match, but 3 is considered more strict.

    Conflicting versops are not allowed.   
    """

    def __init__(self):
        """Initialise the list"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.versops = []

    def __str__(self):
        """Print the list"""
        return str(self.versops)

    def add(self, versop_new):
        """
        Try to add version_str as VersionOperator instance to self.versions.
        Make sure there is no conflict with existing versions, and that the 
            ordering is kept. 

        @param versop_new: VersionOperator instance (or will be converted into one if type basestring)
        """
        if isinstance(versop_new, basestring):
            versop_new = VersionOperator(versop_new)

        if versop_new in self.versops:
            # consider it an error.
            self.log.error("Versop %s already added." % versop_new)
            return None
        else:
            # no need for equality testing, we consider it an error
            gt_test = [versop_new > versop for versop in self.versops]
            if None in gt_test:
                # conflict
                msg = 'add: conflict between versop_new %s and existing versions %s'
                conflict_versops = [(idx, self.versops[idx]) for idx, gt_val in gt_test if gt_val is None]
                self.log.error(msg % (versop_new, conflict_versops))
            else:
                if True in gt_test:
                    # first element for which
                    insert_idx = gt_test.index(True)
                    self.log.debug('add: insert versop %s in index %s' % (versop_new, insert_idx))
                    self.versops.insert(insert_idx, versop_new)
                else:
                    self.log.debug("add: versop_new %s is not > then any element, appending it" % versop_new)
                    self.versops.append(versop_new)


class OrderedToolchainVersionOperators(object):
    """Ordered toolchain version operators"""
    # sort of dict of OrderedVersionOperators?
    # TODO : implement it

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
    version=version_operator
    toolchain=toolchain_version_operator

    Optional
    [DEFAULT]
    [[SUPPORTED]]
    toolchains=toolchain_versop[,...]
    versions=versop[,...]
    [versionX_operatorZ]
    [versionY_operatorZZ]
    [toolchainX_operatorZ]
    [toolchainY_operatorZZ]
    
    TODO: Add nested/recursive example
    """

    def __init__(self, configobj=None):
        """
        Initialise.
            @param configobj: ConfigObj instance
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        # TODO rename, this is for prototyping
        self.ovos = OrderedVersionOperators()
        self.otcvos = OrderedToolchainVersionOperators()

        if configobj is not None:
            self.set(configobj)

    def set(self, configobj):
        """
        Parse the configobj instance
        @param configobj: ConfigObj instance
        """
        # FIXME: clarify docstring, what's going on here?
        # FIXME: add_version, add_toolchain functions totally missing?
        for name, section in configobj.items():
            if name == 'DEFAULT':
                if 'version' in section:
                    self.add_version(section['version'], section=name)
                if 'toolchain' in section:
                    toolchain = self.toolchain_parse_version_str(section['toolchain'])
                    if toolchain is None:
                        self.log.error('Section %s toolchain %s does not toolchain_match' %
                                       (name, section['toolchain']))
            else:
                toolchain = self.add_toolchain(name, section=name, error=False)
                if toolchain is None:
                    version = self.add_version(name, section=name, error=False)
                    if version is None:
                        self.log.debug('Name %s section %s no version nor toolchain' % (name, section))
