# #
# Copyright 2015-2015 Ghent University
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
Support for checking types of easyconfig parameter values.

@author: Kenneth Hoste (Ghent University)
"""
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError


# easy types, that can be verified with isinstance
EASY_TYPES = [basestring, int]
# type checking is skipped for easyconfig parameters names not listed in TYPES
TYPES = {
    'name': basestring,
    'version': basestring,
}
TYPE_CONVERSION_FUNCTIONS = {
    basestring: str,
    float: float,
    int: int,
    str: str,
}


_log = fancylogger.getLogger('easyconfig.types', fname=False)


def check_type_of_param_value(key, val, auto_convert=False):
    """
    Check value type of specified easyconfig parameter.

    @param key: name of easyconfig parameter
    @param val: easyconfig parameter value, of which type should be checked
    @param auto_convert: try to automatically convert to expected value type if required
    """
    type_ok, newval = False, None
    expected_type = TYPES.get(key)

    if expected_type is None:
        _log.debug("No type specified for easyconfig parameter '%s', so skipping type check.", key)
        type_ok, newval = True, val

    elif expected_type in EASY_TYPES:
        # easy types can be checked using isinstance
        if isinstance(val, expected_type):
            type_ok, newval = True, val
            _log.debug("Value type checking of easyconfig parameter '%s' passed: expected '%s', got '%s'",
                       key, expected_type.__name__, type(val).__name__)

        else:
            _log.warning("Value type checking of easyconfig parameter '%s' FAILED: expected '%s', got '%s'",
                         key, expected_type.__name__, type(val).__name__)
    else:
        raise EasyBuildError("Don't know how to check whether specified value is of type %s", expected_type)

    if not type_ok and auto_convert:
        _log.debug("Value type check failed, going to try to automatically convert to %s", expected_type)
        newval = convert_value_type(val, expected_type)
        type_ok = True

    return type_ok, newval


def convert_value_type(val, typ):
    """
    Try to convert type of provided value to specific type.

    @param val: value to convert type of
    @param typ: target type
    """
    res = None

    if isinstance(val, typ):
        _log.debug("Value %s is already of specified target type %s, no conversion needed", val, typ)
        res = val

    elif typ in TYPE_CONVERSION_FUNCTIONS:
        func = TYPE_CONVERSION_FUNCTIONS[typ]
        _log.debug("Trying to convert value %s (type: %s) to %s using %s", val, type(val), typ, func)
        try:
            res = func(val)
            _log.debug("Type conversion seems to have worked, new type: %s", type(res))
        except Exception as err:
            raise EasyBuildError("Converting type of %s (%s) to %s using %s failed: %s", val, type(val), typ, func, err)

        if not isinstance(res, typ):
            raise EasyBuildError("Converting value %s to type %s didn't work as expected: got %s", val, typ, type(res))

    else:
        raise EasyBuildError("No conversion function available (yet) for target type %s", typ)

    return res
