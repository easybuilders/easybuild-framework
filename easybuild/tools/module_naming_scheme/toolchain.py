##
# Copyright 2014-2021 Ghent University
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
##
"""
Toolchain querying support for module naming schemes.

:author: Kenneth Hoste (Ghent University)
"""
import copy

from easybuild.base import fancylogger
from easybuild.framework.easyconfig.easyconfig import EasyConfig, process_easyconfig, robot_find_easyconfig
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version


_log = fancylogger.getLogger('module_naming_scheme.toolchain', fname=False)

_toolchain_details_cache = {}


# different types of toolchain elements
TOOLCHAIN_COMPILER = 'COMPILER'
TOOLCHAIN_MPI = 'MPI'
TOOLCHAIN_BLAS = 'BLAS'
TOOLCHAIN_LAPACK = 'LAPACK'
TOOLCHAIN_FFT = 'FFT'


def det_toolchain_element_details(tc, elem, allow_missing=False):
    """
    Determine details of a particular toolchain element, for a given Toolchain instance.
    """
    # check for cached version first
    tc_dict = tc.as_dict()
    key = (tc_dict['name'], tc_dict['version'] + tc_dict['versionsuffix'], elem)
    if key in _toolchain_details_cache:
        _log.debug("Obtained details for '%s' in toolchain '%s' from cache" % (elem, tc_dict))
        return _toolchain_details_cache[key]

    # grab version from parsed easyconfig file for toolchain
    eb_file = robot_find_easyconfig(tc_dict['name'], det_full_ec_version(tc_dict))
    tc_ec = process_easyconfig(eb_file, parse_only=True)
    if len(tc_ec) > 1:
        _log.warning("More than one toolchain specification found for %s, only retaining first" % tc_dict)
        _log.debug("Full list of toolchain specifications: %s" % tc_ec)
    tc_ec = tc_ec[0]['ec']
    tc_elem_details = None
    for tc_dep in tc_ec.dependencies():
        if tc_dep['name'] == elem:
            tc_elem_details = tc_dep
            _log.debug("Found details for toolchain element %s: %s" % (elem, tc_elem_details))
            break
    if tc_elem_details is None:
        # for compiler-only toolchains, toolchain and compilers are one-and-the-same
        if tc_ec['name'] == elem:
            tc_elem_details = tc_ec
        elif allow_missing:
            tc_elem_details = None
        else:
            raise EasyBuildError("No toolchain element '%s' found for toolchain %s: %s", elem, tc.as_dict(), tc_ec)

    _toolchain_details_cache[key] = tc_elem_details
    _log.debug("Obtained details for '%s' in toolchain '%s', added to cache" % (elem, tc_dict))
    return _toolchain_details_cache[key]


def det_toolchain_compilers(ec):
    """
    Determine compilers of toolchain for given EasyConfig instance.

    :param ec: a parsed EasyConfig file (an AttributeError will occur if a simple dict is passed)
    """
    tc_elems = ec.toolchain.definition()
    if ec.toolchain.is_system_toolchain():
        # system toolchain has no (real) compiler component
        tc_comps = None
    elif TOOLCHAIN_COMPILER not in tc_elems:
        # every toolchain should have at least a compiler
        raise EasyBuildError("No compiler found in toolchain %s: %s", ec.toolchain.as_dict(), tc_elems)
    elif tc_elems[TOOLCHAIN_COMPILER]:
        tc_comps = []

        tc_comp_elems = copy.copy(tc_elems[TOOLCHAIN_COMPILER])

        # First consider a concatenation of list of compiler module names as a single toolchain element
        combined_comp_elem = ''.join(tc_comp_elems)
        elem_list = copy.copy(tc_comp_elems)
        combined_comp_elem_details = det_toolchain_element_details(ec.toolchain, combined_comp_elem, allow_missing=True)

        if not combined_comp_elem_details:
            # for toolchains including icc & ifort (like iccifortcuda), always consider iccifort
            if 'icc' in tc_comp_elems and 'ifort' in tc_comp_elems:
                combined_comp_elem_details = det_toolchain_element_details(ec.toolchain, 'iccifort', allow_missing=True)
                elem_list = ['icc', 'ifort']

        if combined_comp_elem_details:
            if isinstance(combined_comp_elem_details, EasyConfig):
                combined_comp_elem_details = combined_comp_elem_details.asdict()
            # add details for each compiler separately, using details from combo
            for comp_elem in elem_list:
                comp_elem_details = copy.copy(combined_comp_elem_details)
                comp_elem_details['name'] = comp_elem
                tc_comps.append(comp_elem_details)
                tc_comp_elems.remove(comp_elem)

        # consider any remaining individual compiler module names
        for comp_elem in tc_comp_elems:
            tc_comps.append(det_toolchain_element_details(ec.toolchain, comp_elem))
    else:
        raise EasyBuildError("Empty list of compilers for %s toolchain definition: %s",
                             ec.toolchain.as_dict(), tc_elems)
    _log.debug("Found compilers %s for toolchain %s (%s)", tc_comps, ec.toolchain.name, ec.toolchain.as_dict())

    return tc_comps


def det_toolchain_mpi(ec):
    """
    Determine MPI library of toolchain for given EasyConfig instance.

    :param ec: a parsed EasyConfig file (an AttributeError will occur if a simple dict is passed)
    """
    tc_elems = ec.toolchain.definition()
    if TOOLCHAIN_MPI in tc_elems:
        if not tc_elems[TOOLCHAIN_MPI]:
            raise EasyBuildError("Empty list of MPI libs for %s toolchain definition: %s",
                                 ec.toolchain.as_dict(), tc_elems)
        # assumption: only one MPI toolchain element
        tc_mpi = det_toolchain_element_details(ec.toolchain, tc_elems[TOOLCHAIN_MPI][0])
    else:
        # no MPI in this toolchain
        tc_mpi = None

    return tc_mpi
