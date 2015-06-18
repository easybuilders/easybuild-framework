#!/usr/bin/env python
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
Support for including additional Python modules, for easyblocks, module naming schemes and toolchains.

@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import sys
from vsc.utils.missing import nub
from vsc.utils import fancylogger

import easybuild.easyblocks  # just so we can reload it later
from easybuild.tools.build_log import EasyBuildError


_log = fancylogger.getLogger('tools.include', fname=False)


PKG_INIT_BODY = """
from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)
"""


def set_up_eb_package(parent_path, eb_pkg_name):
    """Set up new easybuild subnamespace in specified path."""
    if not eb_pkg_name.startswith('easybuild'):
        raise EasyBuildError("Specified EasyBuild package name does not start with 'easybuild': %s", eb_pkg_name)

    pkgpath = os.path.join(parent_path, eb_pkg_name.replace('.', os.path.sep))
    # note: can't use mkdir, since that required build options to be initialised
    os.makedirs(pkgpath)

    # put __init__.py files in place, with required pkgutil.extend_path statement
    while pkgpath != parent_path:
        # note: can't use write_file, since that required build options to be initialised
        handle = open(os.path.join(pkgpath, '__init__.py'), 'w')
        handle.write(PKG_INIT_BODY)
        handle.close()

        pkgpath = os.path.dirname(pkgpath)


def include_easyblocks(tmpdir, paths):
    """Include generic and software-specific easyblocks found in specified locations."""
    easyblocks_path = os.path.join(tmpdir, 'included-easyblocks')

    # covers both easybuild.easyblocks and easybuild.easyblocks.generic namespaces
    set_up_eb_package(easyblocks_path, 'easybuild.easyblocks.generic')

    easyblocks_dir = os.path.join(easyblocks_path, 'easybuild', 'easyblocks')

    allpaths = nub([y for x in paths for y in glob.glob(x)])
    for easyblock_module in allpaths:
        filename = os.path.basename(easyblock_module)

        # generic easyblocks are expected to be in a directory named 'generic'
        if os.path.basename(os.path.dirname(easyblock_module)) == 'generic':
            target_path = os.path.join(easyblocks_dir, 'generic', filename)
        else:
            target_path = os.path.join(easyblocks_dir, filename)

        try:
            os.symlink(easyblock_module, target_path)
            _log.info("Symlinking %s to %s", easyblock_module, target_path)
        except OSError as err:
            raise EasyBuildError("Symlinking %s to %s failed: %s", easyblock_module, target_path, err)

    included_easyblocks = [x for x in os.listdir(easyblocks_dir) if x not in ['__init__.py', 'generic']]
    included_generic_easyblocks = [x for x in os.listdir(os.path.join(easyblocks_dir, 'generic')) if x != '__init__.py']
    _log.debug("Included generic easyblocks: %s", included_easyblocks)
    _log.debug("Included software-specific easyblocks: %s", included_generic_easyblocks)

    # inject path into Python search path, and reload easybuild.easyblocks to get it 'registered' in sys.modules
    sys.path.insert(0, easyblocks_path)
    reload(easybuild.easyblocks)


def include_module_naming_schemes(tmpdir, paths):
    """Include module naming schemes at specified locations."""
    # FIXME todo
    raise NotImplementedError


def include_toolchains(tmpdir, paths):
    """Include toolchains and toolchain components at specified locations."""
    # FIXME todo
    raise NotImplementedError
