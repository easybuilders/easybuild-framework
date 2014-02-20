# #
# Copyright 2012-2014 Ghent University
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
Toolchain utility module

Easy access to actual Toolchain classes
    search_toolchain

Based on VSC-tools vsc.mympirun.mpi.mpi and vsc.mympirun.rm.sched

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import re
import sys
from vsc import fancylogger
from vsc.utils.missing import get_subclasses, nub

import easybuild.tools.toolchain
from easybuild.tools.toolchain.toolchain import Toolchain
from easybuild.tools.utilities import import_available_modules


TC_CONST_PREFIX = 'TC_CONSTANT_'


def search_toolchain(name):
    """
    Find a toolchain with matching name
    returns toolchain (or None), found_toolchains
    """

    log = fancylogger.getLogger("search_toolchain")

    package = easybuild.tools.toolchain
    check_attr_name = '%s_PROCESSED' % TC_CONST_PREFIX

    if not hasattr(package, check_attr_name) or not getattr(package, check_attr_name):
        # import all available toolchains, so we know about them
        tc_modules = import_available_modules('easybuild.toolchains')

        # make sure all defined toolchain constants are available in toolchain module
        tc_const_re = re.compile('^%s(.*)$' % TC_CONST_PREFIX)
        for tc_mod in tc_modules:
            # determine classes imported in this module
            mod_classes = []
            for elem in [getattr(tc_mod, x) for x in dir(tc_mod)]:
                if hasattr(elem, '__module__'):
                    # exclude the toolchain class defined in that module
                    if not tc_mod.__file__ == sys.modules[elem.__module__].__file__:
                        log.debug("Adding %s to list of imported classes used for looking for constants" % elem.__name__)
                        mod_classes.append(elem)

            # look for constants in modules of imported classes, and make them available
            for mod_class_mod in [sys.modules[mod_class.__module__] for mod_class in mod_classes]:
                for elem in dir(mod_class_mod):
                    res = tc_const_re.match(elem)
                    if res:
                        tc_const_name = res.group(1)
                        tc_const_value = getattr(mod_class_mod, elem)
                        log.debug("Found constant %s ('%s') in module %s, adding it to %s" % (tc_const_name,
                                                                                              tc_const_value,
                                                                                              mod_class_mod.__name__,
                                                                                              package.__name__))
                        if hasattr(package, tc_const_name):
                            cur_value = getattr(package, tc_const_name)
                            if not tc_const_value == cur_value:
                                log.error("Constant %s.%s defined as '%s', can't set it to '%s'." % (package.__name__,
                                                                                                     tc_const_name,
                                                                                                     cur_value,
                                                                                                     tc_const_value
                                                                                                    ))
                        else:
                            setattr(package, tc_const_name, tc_const_value)

        # indicate that processing of toolchain constants is done, so it's not done again
        setattr(package, check_attr_name, True)
    else:
        log.debug("Skipping importing of toolchain modules, processing of toolchain constants is already done.")

    # obtain all subclasses of toolchain
    found_tcs = nub(get_subclasses(Toolchain))

    # filter found toolchain subclasses based on whether they can be used a toolchains
    found_tcs = [tc for tc in found_tcs if tc._is_toolchain_for(None)]

    for tc in found_tcs:
        if tc._is_toolchain_for(name):
            return tc, found_tcs

    return None, found_tcs
