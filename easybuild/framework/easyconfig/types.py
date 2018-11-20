# #
# Copyright 2015-2018 Ghent University
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
Support for checking types of easyconfig parameter values.

:author: Caroline De Brouwer (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
from vsc.utils import fancylogger
from distutils.util import strtobool

from easybuild.tools.build_log import EasyBuildError
from easybuild.framework.easyconfig.format.format import DEPENDENCY_PARAMETERS

_log = fancylogger.getLogger('easyconfig.types', fname=False)


def as_hashable(dict_value):
    """Helper function, convert dict value to hashable equivalent via tuples."""
    res = []
    for key, val in sorted(dict_value.items()):
        if isinstance(val, list):
            val = tuple(val)
        elif isinstance(val, dict):
            val = as_hashable(val)
        res.append((key, val))
    return tuple(res)


def check_element_types(elems, allowed_types):
    """
    Check whether types of elements of specified (iterable) value are as expected.

    :param elems: iterable value (list or dict) of elements
    :param allowed_types: allowed types per element; either a simple list, or a dict of allowed_types by element name
    """
    # combine elements with their list of allowed types
    elems_and_allowed_types = None
    if isinstance(elems, (list, tuple)):
        if isinstance(allowed_types, (list, tuple)):
            elems_and_allowed_types = [(elem, allowed_types) for elem in elems]
        else:
            raise EasyBuildError("Don't know how to combine value of type %s with allowed types of type %s",
                                 type(elems), type(allowed_types))
    elif isinstance(elems, dict):
        # allowed_types can be a tuple representation of a dict, or a flat list of types

        # try to convert to a dict, but ignore if it fails
        try:
            allowed_types = dict(allowed_types)
        except (ValueError, TypeError):
            pass

        if isinstance(allowed_types, (list, tuple)):
            elems_and_allowed_types = [(elem, allowed_types) for elem in elems.values()]
        elif isinstance(allowed_types, dict):
            elems_and_allowed_types = []
            for key, val in elems.items():
                if key in allowed_types:
                    elems_and_allowed_types.append((val, allowed_types[key]))
                else:
                    # if key has no known allowed types, use empty list of allowed types to yield False check result
                    elems_and_allowed_types.append((val, []))
        else:
            raise EasyBuildError("Unknown type of allowed types specification: %s", type(allowed_types))
    else:
        raise EasyBuildError("Don't know how to check element types for value of type %s: %s", type(elems), elems)

    # check whether all element types are allowed types
    res = True
    for elem, allowed_types_elem in elems_and_allowed_types:
        res &= any(is_value_of_type(elem, t) for t in allowed_types_elem)

    return res


def check_key_types(val, allowed_types):
    """Check whether type of keys for specific dict value are as expected."""
    if isinstance(val, dict):
        res = True
        for key in val.keys():
            res &= any(is_value_of_type(key, t) for t in allowed_types)
    else:
        _log.debug("Specified value %s (type: %s) is not a dict, so key types check failed", val, type(val))
        res = False

    return res


def check_known_keys(val, allowed_keys):
    """Check whether all keys for specified dict value are known keys."""
    if isinstance(val, dict):
        res = all(key in allowed_keys for key in val.keys())
    else:
        _log.debug("Specified value %s (type: %s) is not a dict, so known keys check failed", val, type(val))
        res = False
    return res


def check_required_keys(val, required_keys):
    """Check whether all required keys are present in the specified dict value."""
    if isinstance(val, dict):
        keys = val.keys()
        res = all(key in keys for key in required_keys)
    else:
        _log.debug("Specified value %s (type: %s) is not a dict, so known keys check failed", val, type(val))
        res = False
    return res


def is_value_of_type(value, expected_type):
    """
    Check whether specified value matches a particular very specific (non-trivial) type,
    which is specified by means of a 2-tuple: (parent type, tuple with additional type requirements).

    :param value: value to check the type of
    :param expected_type: type of value to check against
    """
    type_ok = False

    if expected_type in EASY_TYPES:
        # easy types can be checked using isinstance
        type_ok = isinstance(value, expected_type)

    elif expected_type in CHECKABLE_TYPES:
        # more complex types need to be checked differently, through helper functions for extra type requirements
        parent_type = expected_type[0]
        extra_reqs = dict(expected_type[1])

        # first step: check parent type
        type_ok = isinstance(value, parent_type)
        if type_ok:
            _log.debug("Parent type of value %s matches %s, going in...", value, parent_type)
            # second step: check additional type requirements
            extra_req_checkers = {
                'elem_types': lambda val: check_element_types(val, extra_reqs['elem_types']),
            }
            if parent_type == dict:
                extra_req_checkers.update({
                    'key_types': lambda val: check_key_types(val, extra_reqs['key_types']),
                    'opt_keys': lambda val: check_known_keys(val, extra_reqs['opt_keys'] + extra_reqs['req_keys']),
                    'req_keys': lambda val: check_required_keys(val, extra_reqs['req_keys']),
                })

            for er_key in extra_reqs:
                if er_key in extra_req_checkers:
                    check_ok = extra_req_checkers[er_key](value)
                    msg = ('FAILED', 'passed')[check_ok]
                    type_ok &= check_ok
                    _log.debug("Check for %s requirement (%s) %s for %s", er_key, extra_reqs[er_key], msg, value)
                else:
                    raise EasyBuildError("Unknown type requirement specified: %s", er_key)

            msg = ('FAILED', 'passed')[type_ok]
            _log.debug("Non-trivial value type checking of easyconfig value '%s': %s", value, msg)

        else:
            _log.debug("Parent type of value %s doesn't match %s: %s", value, parent_type, type(value))

    else:
        raise EasyBuildError("Don't know how to check whether specified value is of type %s", expected_type)

    return type_ok


def check_type_of_param_value(key, val, auto_convert=False):
    """
    Check value type of specified easyconfig parameter.

    :param key: name of easyconfig parameter
    :param val: easyconfig parameter value, of which type should be checked
    :param auto_convert: try to automatically convert to expected value type if required
    """
    type_ok, newval = False, None
    expected_type = PARAMETER_TYPES.get(key)

    # check value type
    if expected_type is None:
        _log.debug("No type specified for easyconfig parameter '%s', so skipping type check.", key)
        type_ok = True

    else:
        type_ok = is_value_of_type(val, expected_type)

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

    :param val: value to convert type of
    :param typ: target type
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


def to_toolchain_dict(spec):
    """
    Convert a comma-separated string or 2/3-element list of strings to a dictionary with name/version keys, and
    optionally a hidden key. If the specified value is a dict already, the keys are checked to be only
    name/version/hidden.

    For example: "intel, 2015a" => {'name': 'intel', 'version': '2015a'}
                 "foss, 2016a, True" => {'name': 'foss', 'version': '2016a', 'hidden': True}

    :param spec: a comma-separated string with two or three values, or a 2/3-element list of strings, or a dict
    """
    # check if spec is a string or a list of two values; else, it can not be converted
    if isinstance(spec, basestring):
        spec = spec.split(',')

    if isinstance(spec, (list, tuple)):
        # 2-element list
        if len(spec) == 2:
            res = {'name': spec[0].strip(), 'version': spec[1].strip()}
        # 3-element list
        elif len(spec) == 3:
            res = {'name': spec[0].strip(), 'version': spec[1].strip(), 'hidden': strtobool(spec[2].strip())}
        else:
            raise EasyBuildError("Can not convert list %s to toolchain dict. Expected 2 or 3 elements", spec)

    elif isinstance(spec, dict):
        # already a dict, check keys
        sorted_keys = sorted(spec.keys())
        if sorted_keys == ['name', 'version'] or sorted_keys == ['hidden', 'name', 'version']:
            res = spec
        else:
            raise EasyBuildError("Incorrect set of keys in provided dictionary, should be only name/version/hidden: %s",
                                 spec)

    else:
        raise EasyBuildError("Conversion of %s (type %s) to toolchain dict is not supported", spec, type(spec))

    return res


def to_name_version_dict(spec):
    """No longer supported, replaced by to_toolchain_dict."""
    _log.nosupport("to_name_version_dict; use to_toolchain_dict instead.", '3.0')


def to_list_of_strings_and_tuples(spec):
    """
    Convert a 'list of lists and strings' to a 'list of tuples and strings'

    Example:
        ['foo', ['bar', 'baz']]
        to
        ['foo', ('bar', 'baz')]
    """
    str_tup_list = []

    if not isinstance(spec, (list, tuple)):
        raise EasyBuildError("Expected value to be a list, found %s (%s)", spec, type(spec))

    for elem in spec:
        if isinstance(elem, (basestring, tuple)):
            str_tup_list.append(elem)
        elif isinstance(elem, list):
            str_tup_list.append(tuple(elem))
        else:
            raise EasyBuildError("Expected elements to be of type string, tuple or list, got %s (%s)", elem, type(elem))

    return str_tup_list


def to_sanity_check_paths_dict(spec):
    """
    Convert a sanity_check_paths dict as received by yaml (a dict with list values that contain either lists or strings)

    Example:
        {'files': ['file1', ['file2a', 'file2b]], 'dirs': ['foo/bar']}
        to
        {'files': ['file1', ('file2a', 'file2b')], 'dirs': ['foo/bar']}
    """
    if not isinstance(spec, dict):
        raise EasyBuildError("Expected value to be a dict, found %s (%s)", spec, type(spec))

    sanity_check_dict = {}
    for key in spec:
        sanity_check_dict[key] = to_list_of_strings_and_tuples(spec[key])
    return sanity_check_dict


# this uses to_toolchain, so it needs to be at the bottom of the module
def to_dependency(dep):
    """
    Convert a dependency specification to a dependency dict with name/version/versionsuffix/toolchain keys.

    Example:
        {'foo': '1.2.3', 'toolchain': 'GCC, 4.8.2'}
        to
        {'name': 'foo', 'version': '1.2.3', 'toolchain': {'name': 'GCC', 'version': '4.8.2'}}

    or
        {'name': 'fftw/3.3.4.1', 'external_module': True}
        to
        {'name': 'fftw/3.3.4.1', 'external_module': True, 'version': None}
    """
    # deal with dependencies coming for .eb easyconfig, typically in tuple format:
    #   (name, version[, versionsuffix[, toolchain]])
    if isinstance(dep, dict):
        depspec = {}

        if dep.get('external_module', False):
            expected_keys = ['external_module', 'name']
            if sorted(dep.keys()) == expected_keys:
                depspec.update({
                    'external_module': True,
                    'full_mod_name': dep['name'],
                    'name': None,
                    'short_mod_name': dep['name'],
                    'version': None,
                })
            else:
                raise EasyBuildError("Unexpected format for dependency marked as external module: %s", dep)

        else:
            found_name_version = False
            for key, value in dep.items():
                if key in ['name', 'version', 'versionsuffix']:
                    depspec[key] = str(value)
                elif key == 'toolchain':
                    depspec['toolchain'] = to_toolchain_dict(value)
                elif not found_name_version:
                    depspec.update({'name': key, 'version': str(value)})
                else:
                    raise EasyBuildError("Found unexpected (key, value) pair: %s, %s", key, value)

                if 'name' in depspec and 'version' in depspec:
                    found_name_version = True

            if not found_name_version:
                raise EasyBuildError("Can not parse dependency without name and version: %s", dep)

    else:
        # pass down value untouched, let EasyConfig._parse_dependency handle it
        depspec = dep
        if isinstance(dep, (tuple, list)):
            _log.debug("Passing down dependency value of type %s without touching it: %s", type(dep), dep)
        else:
            _log.warning("Unknown type of value in to_dependency %s; passing value down as is: %s", type(dep), dep)

    return depspec


def to_dependencies(dep_list):
    """
    Convert a list of dependencies obtained from parsing a .yeb easyconfig
    to a list of dependencies in the correct format
    """
    return [to_dependency(dep) for dep in dep_list]


def to_checksums(checksums):
    """Ensure correct element types for list of checksums: convert list elements to tuples."""
    res = []
    for checksum in checksums:
        # each list entry can be:
        # * a string (MD5 checksum)
        # * a tuple with 2 elements: checksum type + checksum value
        # * a list of checksums (i.e. multiple checksums for a single file)
        if isinstance(checksum, basestring):
            res.append(checksum)
        elif isinstance(checksum, (list, tuple)):
            # 2 elements + only string/int values => a checksum tuple
            if len(checksum) == 2 and all(isinstance(x, (basestring, int)) for x in checksum):
                res.append(tuple(checksum))
            else:
                res.append(to_checksums(checksum))

    return res

def ensure_iterable_license_specs(specs):
    """
    Ensures that the provided license file/server specifications are of correct type and converts
    them to a list.  The input can either be None, a string, or a list/tuple of strings.

    :param specs: License file/server specifications as provided via `license_file` easyconfig parameter
    """
    if specs is None:
        license_specs = [None]
    elif isinstance(specs, basestring):
        license_specs = [specs]
    elif isinstance(specs, (list, tuple)) and all(isinstance(x, basestring) for x in specs):
        license_specs = list(specs)
    else:
        msg = "Unsupported type %s for easyconfig parameter 'license_file'! " % type(specs)
        msg += "Can either be None, a string, or a tuple/list of strings."
        raise EasyBuildError(msg)

    return license_specs

# these constants use functions defined in this module, so they needs to be at the bottom of the module
# specific type: dict with only name/version as keys with string values, and optionally a hidden key with bool value
# additional type requirements are specified as tuple of tuples rather than a dict, since this needs to be hashable
TOOLCHAIN_DICT = (dict, as_hashable({
    'elem_types': {
        'hidden': [bool],
        'name': [str],
        'version': [str],
    },
    'opt_keys': ['hidden'],
    'req_keys': ['name', 'version'],
}))
DEPENDENCY_DICT = (dict, as_hashable({
    'elem_types': {
        'full_mod_name': [str],
        'name': [str],
        'short_mod_name': [str],
        'toolchain': [TOOLCHAIN_DICT],
        'version': [str],
        'versionsuffix': [str],
    },
    'opt_keys': ['full_mod_name', 'short_mod_name', 'toolchain', 'versionsuffix'],
    'req_keys': ['name', 'version'],
}))
DEPENDENCIES = (list, as_hashable({'elem_types': [DEPENDENCY_DICT]}))

TUPLE_OF_STRINGS = (tuple, as_hashable({'elem_types': [str]}))
STRING_OR_TUPLE_LIST = (list, as_hashable({'elem_types': [str, TUPLE_OF_STRINGS]}))
SANITY_CHECK_PATHS_DICT = (dict, as_hashable({
    'elem_types': {
        'files': [STRING_OR_TUPLE_LIST],
        'dirs': [STRING_OR_TUPLE_LIST],
    },
    'opt_keys': [],
    'req_keys': ['files', 'dirs'],
}))
CHECKSUMS = (list, as_hashable({'elem_types': [STRING_OR_TUPLE_LIST]}))

CHECKABLE_TYPES = [CHECKSUMS, DEPENDENCIES, DEPENDENCY_DICT, TOOLCHAIN_DICT, SANITY_CHECK_PATHS_DICT,
                  STRING_OR_TUPLE_LIST, TUPLE_OF_STRINGS]

# easy types, that can be verified with isinstance
EASY_TYPES = [basestring, bool, dict, int, list, str, tuple]

# type checking is skipped for easyconfig parameters names not listed in PARAMETER_TYPES
PARAMETER_TYPES = {
    'checksums': CHECKSUMS,
    'name': basestring,
    'osdependencies': STRING_OR_TUPLE_LIST,
    'patches': STRING_OR_TUPLE_LIST,
    'sanity_check_paths': SANITY_CHECK_PATHS_DICT,
    'toolchain': TOOLCHAIN_DICT,
    'version': basestring,
}
# add all dependency types as dependencies
for dep in DEPENDENCY_PARAMETERS:
    PARAMETER_TYPES[dep] = DEPENDENCIES

TYPE_CONVERSION_FUNCTIONS = {
    basestring: str,
    float: float,
    int: int,
    str: str,
    CHECKSUMS: to_checksums,
    DEPENDENCIES: to_dependencies,
    TOOLCHAIN_DICT: to_toolchain_dict,
    SANITY_CHECK_PATHS_DICT: to_sanity_check_paths_dict,
    STRING_OR_TUPLE_LIST: to_list_of_strings_and_tuples,
}
