#!/usr/bin/env python
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
##
"""
Script to fix easyconfigs that broke due to support for deprecated functionality being dropped in EasyBuild 2.0

:author: Kenneth Hoste (Ghent University)
"""
import os
import re
import sys
from vsc.utils import fancylogger
from vsc.utils.generaloption import SimpleOption

from easybuild.framework.easyconfig.easyconfig import get_easyblock_class
from easybuild.framework.easyconfig.parser import REPLACED_PARAMETERS, fetch_parameters_from_easyconfig
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import init_build_options
from easybuild.tools.filetools import find_easyconfigs, read_file, write_file


class FixBrokenEasyconfigsOption(SimpleOption):
    """Custom option parser for this script."""
    ALLOPTSMANDATORY = False


def fix_broken_easyconfig(ectxt, easyblock_class):
    """
    Fix provided easyconfig file, that may be broken due to non-backwards-compatible changes.
    :param ectxt: raw contents of easyconfig to fix
    :param easyblock_class: easyblock class, as derived from software name/specified easyblock
    """
    log.debug("Raw contents of potentially broken easyconfig file to fix: %s" % ectxt)

    subs = {
        # replace former 'magic' variable shared_lib_ext with SHLIB_EXT constant
        'shared_lib_ext': 'SHLIB_EXT',
    }
    # include replaced easyconfig parameters
    subs.update(REPLACED_PARAMETERS)

    # check whether any substitions need to be made
    for old, new in subs.items():
        regex = re.compile(r'(\W)%s(\W)' % old)
        if regex.search(ectxt):
            tup = (regex.pattern, old, new)
            log.debug("Broken stuff detected using regex pattern '%s', replacing '%s' with '%s'" % tup)
            ectxt = regex.sub(r'\1%s\2' % new, ectxt)

    # check whether missing "easyblock = 'ConfigureMake'" needs to be inserted
    if easyblock_class is None:
        # prepend "easyblock = 'ConfigureMake'" to line containing "name =..."
        easyblock_spec = "easyblock = 'ConfigureMake'"
        log.debug("Inserting \"%s\", since no easyblock class was derived from easyconfig parameters" % easyblock_spec)
        ectxt = re.sub(r'(\s*)(name\s*=)', r"\1%s\n\n\2" % easyblock_spec, ectxt, re.M)

    return ectxt


def process_easyconfig_file(ec_file):
    """Process an easyconfig file: fix if it's broken, back it up before fixing it inline (if requested)."""
    ectxt = read_file(ec_file)
    name, easyblock = fetch_parameters_from_easyconfig(ectxt, ['name', 'easyblock'])
    derived_easyblock_class = get_easyblock_class(easyblock, name=name, error_on_missing_easyblock=False)

    fixed_ectxt = fix_broken_easyconfig(ectxt, derived_easyblock_class)

    if ectxt != fixed_ectxt:
        if go.options.backup:
            try:
                backup_ec_file = '%s.bk' % ec_file
                i = 1
                while os.path.exists(backup_ec_file):
                    backup_ec_file = '%s.bk%d' % (ec_file, i)
                    i += 1
                os.rename(ec_file, backup_ec_file)
                log.info("Backed up %s to %s" % (ec_file, backup_ec_file))
            except OSError, err:
                raise EasyBuildError("Failed to backup %s before rewriting it: %s", ec_file, err)

        write_file(ec_file, fixed_ectxt)
        log.debug("Contents of fixed easyconfig file: %s" % fixed_ectxt)

        log.info("%s: fixed" % ec_file)
    else:
        log.info("%s: nothing to fix" % ec_file)

# MAIN

try:
    init_build_options()

    options = {
        'backup': ("Backup up easyconfigs before modifying them", None, 'store_true', True, 'b'),
    }
    go = FixBrokenEasyconfigsOption(options)
    log = go.log

    fancylogger.logToScreen(enable=True, stdout=True)
    fancylogger.setLogLevel('WARNING')

    try:
        import easybuild.easyblocks.generic.configuremake
    except ImportError, err:
        raise EasyBuildError("easyblocks are not available in Python search path: %s", err)

    for path in go.args:
        if not os.path.exists(path):
            raise EasyBuildError("Non-existing path %s specified", path)

    ec_files = [ec for p in go.args for ec in find_easyconfigs(p)]
    if not ec_files:
        raise EasyBuildError("No easyconfig files specified")

    log.info("Processing %d easyconfigs" % len(ec_files))
    for ec_file in ec_files:
        try:
            process_easyconfig_file(ec_file)
        except EasyBuildError, err:
            log.warning("Ignoring issue when processing %s: %s", ec_file, err)

except EasyBuildError, err:
    sys.stderr.write("ERROR: %s\n" % err)
    sys.exit(1)
