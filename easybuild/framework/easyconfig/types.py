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
EASY_TYPES = [basestring, dict, int, list, tuple]

# specific type: dict with only name/version as keys, and with string values
# additional type requirements are specified as tuple of tuples rather than a dict, since this needs to be hashable
NAME_VERSION_DICT = (dict, (('only_keys', ('name', 'version')), ('value_types', (str,))))
# specific type: list with only string and list values
STRING_AND_LISTS = (list, (('allowed_types', (str, list)), ()))

CHECKABLE_TYPES = [NAME_VERSION_DICT, STRING_AND_LISTS]

# type checking is skipped for easyconfig parameters names not listed in TYPES
TYPES = {
    'name': basestring,
    'version': basestring,
    'toolchain': NAME_VERSION_DICT,
    'osdependencies': STRING_AND_LISTS,
}

_log = fancylogger.getLogger('easyconfig.types', fname=False)


def is_value_of_type(value, typ_spec):
    """
    Check whether specified value matches a particular very specific (non-trivial) type,
    which is specified by means of a 2-tuple: (parent type, tuple with additional type requirements).

    @param value: value to check the type of
    @param typ_spec: specific type of dict to check for
    """
    parent_type = typ_spec[0]
    print typ_spec[1]
    extra_reqs = dict(typ_spec[1])
    # first step: check parent type
    type_ok = isinstance(value, parent_type)
    if type_ok:
        _log.debug("Parent type of value %s matches %s, going in...", value, parent_type)
        # second step: check additional type requirements
        if parent_type == dict:
            extra_req_checkers = {
                # check whether all keys have allowed types
                'key_types': lambda val: all([type(el) in extra_reqs['key_types'] for el in val.keys()]),
                # check whether only allowed keys are used
                'only_keys': lambda val: set(val.keys()) == set(extra_reqs['only_keys']),
                # check whether all values have allowed types
                'value_types': lambda val: all([type(el) in extra_reqs['value_types'] for el in val.values()]),
            }
            for er_key in extra_reqs:
                if er_key in extra_req_checkers:
                    check_ok = extra_req_checkers[er_key](value)
                    msg = ('FAILED', 'passed')[check_ok]
                    type_ok &= check_ok
                    _log.debug("Check for %s requirement (%s) %s for %s", er_key, extra_reqs[er_key], msg, value)
                else:
                    raise EasyBuildError("Unknown type requirement specified: %s", er_key)

    elif parent_type == list:
            extra_req_checkers = {
                # check wether all values have allowed types
                'allowed_types': lambda val: all(type(el) in extra_reqs['allowed_types'] for el in val),
            }
            for erkey in extra_req_checkers:
                if erkey in extra_reqs:
                    if extra_req_checkers[erkey](value):
                        msg = 'passed'
                    else:
                        msg, type_ok = 'FAILed', False
                    _log.debug("Check for %s requirement (%s) %s for %s", erkey, extra_reqs[erkey], msg, value)

        else:
            raise EasyBuildError("Don't know how to check value with parent type %s", parent_type)
    else:
        _log.debug("Parent type of value %s doesn't match %s: %s", value, parent_type, type(value))

    return type_ok


def check_type_of_param_value(key, val, auto_convert=False):
    """
    Check value type of specified easyconfig parameter.

    @param key: name of easyconfig parameter
    @param val: easyconfig parameter value, of which type should be checked
    @param auto_convert: try to automatically convert to expected value type if required
    """
    type_ok, newval = False, None
    expected_type = TYPES.get(key)

    # check value type
    if expected_type is None:
        _log.debug("No type specified for easyconfig parameter '%s', so skipping type check.", key)
        type_ok = True

    elif expected_type in EASY_TYPES:
        # easy types can be checked using isinstance
        type_ok = isinstance(val, expected_type)
        msg = ('FAILED', 'passed')[type_ok]
        _log.debug("Value type checking of easyconfig parameter '%s' %s: expected '%s', got '%s'",
                   key, msg, expected_type.__name__, type(val).__name__)

    elif expected_type in CHECKABLE_TYPES:
        type_ok = is_value_of_type(val, expected_type)
        msg = ('FAILED', 'passed')[type_ok]
        _log.debug("Non-trivial value type checking of easyconfig parameter '%s': %s", key, msg)

    else:
        raise EasyBuildError("Don't know how to check whether specified value is of type %s", expected_type)

    # determine return value, attempt type conversion if needed/requested
    if type_ok:
        _log.debug("Value type check passed for %s parameter value: %s", key, val)
        newval = val
    elif auto_convert:
        _log.debug("Value type check for %s parameter value failed, going to try to automatically convert to %s",
                   key, expected_type)
        # convert_value_type will raise an error if the conversion fails
        newval = convert_value_type(val, expected_type)
        type_ok = True
    else:
        _log.debug("Value type check for %s parameter value failed, auto-conversion of type not enabled", key)

    return type_ok, newval


def convert_value_type(val, typ):
    """
    Try to convert type of provided value to specific type.

    @param val: value to convert type of
    @param typ: target type
    """
    res = None

    if typ in EASY_TYPES and isinstance(val, typ):
        _log.debug("Value %s is already of specified target type %s, no conversion needed", val, typ)
        res = val

    elif typ in CHECKABLE_TYPES and is_value_of_type(val, typ):
        _log.debug("Value %s is already of specified non-trivial target type %s, no conversion needed", val, typ)
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


def to_name_version_dict(spec):
    """
    Convert a comma-separated string or 2-element list of strings to a dictionary with name/version keys.
    If the specified value is a dict already, the keys are checked to be only name/version.

    For example: "intel, 2015a" => {'name': 'intel', 'version': '2015a'}

    @param spec: a comma-separated string with two values, or a 2-element list of strings, or a dict
    """
    # check if spec is a string or a list of two values; else, it can not be converted
    if isinstance(spec, basestring):
        spec = spec.split(',')

    if isinstance(spec, list):
        # 2-element list
        if len(spec) == 2:
            res = {'name': spec[0].strip(), 'version': spec[1].strip()}
        else:
            raise EasyBuildError("Can not convert list %s to name and version dict. Expected 2 elements", spec)

    elif isinstance(spec, dict):
        # already a dict, check keys
        if sorted(spec.keys()) == ['name', 'version']:
            res = spec
        else:
            raise EasyBuildError("Incorrect set of keys in provided dictionary, should be only name/version: %s", spec)

    else:
        raise EasyBuildError("Conversion of %s (type %s) to name and version dict is not supported", spec, type(spec))

    return res


def to_list_of_strings_and_tuples(os_dep_specs):
    os_dep_list = []
    for os_dep in os_dep_specs:
        if isinstance(os_dep, basestring):
            os_dep_list.append(os_dep)
        elif isinstance(os_dep, list):
            os_dep_list.append(tuple(os_dep))
        else:
            raise EasyBuildError("Expected osdependency to be of type string or list, got %s (%s)", os_dep, type(os_dep))

    return os_dep_list

# this uses to_toolchain, so it needs to be at the bottom of the module
def to_dependency(dep):
    """
    Convert a dependency dict obtained from parsing a .yeb easyconfig
    to a dependency dict with name/version/versionsuffix/toolchain keys

    Example:
        {'foo': '1.2.3', 'toolchain': 'GCC, 4.8.2'}
        to
        {'name': 'foo', 'version': '1.2.3', 'toolchain': {'name': 'GCC', 'version': '4.8.2'}}
    """
    depspec = {}
    if isinstance(dep, dict):
        found_name_version = False
        for key, value in dep.items():
            if key in ['name', 'version', 'versionsuffix']:
                depspec[key] = value
            elif key == 'toolchain':
                depspec['toolchain'] = to_name_version_dict(value)
            elif not found_name_version:
                depspec.update({'name': key, 'version': value})
            else:
                raise EasyBuildError("Found unexpected (key, value) pair: %s, %s", key, value)

            if 'name' in depspec and 'version' in depspec:
                found_name_version = True

        if not found_name_version:
            raise EasyBuildError("Can not parse dependency without name and version: %s", dep)

    else:
        raise EasyBuildError("Can not convert %s (type %s) to dependency dict", dep, type(dep))

    return depspec


# this uses functions defined in this module, so it needs to be at the bottom of the module
TYPE_CONVERSION_FUNCTIONS = {
    basestring: str,
    float: float,
    int: int,
    str: str,
    NAME_VERSION_DICT: to_name_version_dict,
    STRING_AND_LISTS: to_list_of_strings_and_tuples,
}
