#
# Copyright 2011-2026 Ghent University
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
#
"""This module contains utility functions to deprecate EasyBuild features."""

import inspect
import functools

from easybuild.base import fancylogger
from easybuild.tools.version import VERSION

_log = fancylogger.getLogger('_deprecated', fname=False)

def deprecate_argument(old_arg, version, new_arg=None, msg=None):
    """Deprecate an argument of a function. The decorator should be applied to the function with the old signature
    and will log a deprecation warning if the old argument is used.

    Args:
        old_arg (str): Name of the deprecated argument.
        version (str): Version in which the old argument will be removed.
        new_arg (str): Name of the new argument. Defaults to None, which means the old argument will be removed without
          replacement.
        msg (str, optional): Custom message to display in the deprecation warning.
    """
    def decorator(func):
        signature = inspect.signature(func)
        params = list(signature.parameters)

        try:
            old_arg_index = params.index(old_arg)
        except ValueError:
            raise ValueError(f"Argument '{old_arg}' not found in function '{func.__name__}'")

        # if new_arg is not None:
        #     try:
        #         new_arg_index = params.index(new_arg)
        #     except ValueError:
        #         raise ValueError(f"Argument '{new_arg}' not found in function '{func.__name__}'")
        # TODO: this might only work if we have positional-only arguments
        #     if old_arg_index != new_arg_index:
        #         raise ValueError(
        #             f"The new argument '{new_arg}' index should be the same as the old argument '{old_arg}' index "
        #             f"when replacing it as a positional argument in function '{func.__name__}'"
        #         )

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from easybuild.framework.easyblock import EasyBlock

            if isinstance(args[0], EasyBlock):
                log_func = functools.partial(args[0].log.deprecated, ver=version)
            else:
                log_func = functools.partial(_log.deprecated, cur_ver=VERSION, max_ver=version)

            used = False
            # If the argument would be passed as a positional argument and will be removed in the future
            # attempt to insert a None value at the position of the old argument to check if the function is being
            # called with the intended new signature or the old one (would cause TypeError if too many arguments
            # are passed)
            # TODO: this might not be fool-proof, eg if the function accepts other keyword arguments, it is possible
            #   the signature.bind() call will succeed even if we are calling the function with the old signature
            #   EG: def func(a, b, c=None): pass
            #   func(1, 2) with a deprecated argument 'b' would succeed even if we insert None at the position of 'b'
            #   not sure there is a way to better generalize this unless we start specifing keyword arguments as kw-only
            if len(args) > old_arg_index and new_arg is None:
                new_args = list(args)
                try:
                    new_args.insert(old_arg_index, None)
                    signature.bind(*new_args, **kwargs)
                except TypeError as e:
                    used = True
                    new_args = list(args)

            if old_arg in kwargs:
                used = True
                value = kwargs.pop(old_arg)
                if new_arg is not None:
                    kwargs[new_arg] = value

            if used:
                if msg is None:
                    _msg = f"Argument '{old_arg}' is deprecated in function '{func.__name__}' "
                    if new_arg is not None:
                        _msg += f", use '{new_arg}' instead"
                    else:
                        _msg += " and will be removed in future versions"
                else:
                    _msg = msg
                log_func(_msg)

            # print(f'Calling {func.__name__} with args: {new_args}, kwargs: {kwargs}')
            return func(*new_args, **kwargs)
        return wrapper
    return decorator
