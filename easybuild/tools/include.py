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

from easybuild.tools.build_log import EasyBuildError
# these are imported just to we can reload them later
import easybuild.tools.module_naming_scheme
import easybuild.toolchains
import easybuild.toolchains.compiler
import easybuild.toolchains.fft
import easybuild.toolchains.linalg
import easybuild.toolchains.mpi
# importing easyblocks namespace may fail if easybuild-easyblocks is not available
# for now, we don't really care
try:
    import easybuild.easyblocks
    import easybuild.easyblocks.generic
except ImportError:
    pass


_log = fancylogger.getLogger('tools.include', fname=False)


PKG_INIT_BODY = """
from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)
"""

def create_pkg(path):
    """Write package __init__.py file at specified path."""
    init_path = os.path.join(path, '__init__.py')
    try:
        # note: can't use mkdir, since that required build options to be initialised
        if not os.path.exists(path):
            os.makedirs(path)

        # put __init__.py files in place, with required pkgutil.extend_path statement
        # note: can't use write_file, since that required build options to be initialised
        handle = open(init_path, 'w')
        handle.write(PKG_INIT_BODY)
        handle.close()
    except (IOError, OSError) as err:
        raise EasyBuildError("Failed to write %s: %s", init_path, err)


def set_up_eb_package(parent_path, eb_pkg_name, subpkgs=None):
    """Set up new easybuild subnamespace in specified path."""
    if not eb_pkg_name.startswith('easybuild'):
        raise EasyBuildError("Specified EasyBuild package name does not start with 'easybuild': %s", eb_pkg_name)

    pkgpath = os.path.join(parent_path, eb_pkg_name.replace('.', os.path.sep))

    # handle subpackages first
    if subpkgs:
        for subpkg in subpkgs:
            create_pkg(os.path.join(pkgpath, subpkg))

    # creata package dirs on each level
    while pkgpath != parent_path:
        create_pkg(pkgpath)
        pkgpath = os.path.dirname(pkgpath)


def expand_glob_paths(glob_paths):
    """Expand specified glob paths to a list of unique non-glob paths to only files."""
    paths = []
    for glob_path in glob_paths:
        paths.extend([f for f in glob.glob(glob_path) if os.path.isfile(f)])

    return nub(paths)


def safe_symlink(source_path, symlink_path):
    """Create a symlink at the specified path for the given path."""
    try:
        os.symlink(os.path.abspath(source_path), symlink_path)
        _log.info("Symlinked %s to %s", source_path, symlink_path)
    except OSError as err:
        raise EasyBuildError("Symlinking %s to %s failed: %s", source_path, symlink_path, err)


def include_easyblocks(tmpdir, paths):
    """Include generic and software-specific easyblocks found in specified locations."""
    easyblocks_path = os.path.join(tmpdir, 'included-easyblocks')

    set_up_eb_package(easyblocks_path, 'easybuild.easyblocks', subpkgs=['generic'])

    easyblocks_dir = os.path.join(easyblocks_path, 'easybuild', 'easyblocks')

    allpaths = expand_glob_paths(paths)
    for easyblock_module in allpaths:
        filename = os.path.basename(easyblock_module)

        # generic easyblocks are expected to be in a directory named 'generic'
        parent_dir = os.path.basename(os.path.dirname(easyblock_module))
        if parent_dir == 'generic':
            target_path = os.path.join(easyblocks_dir, 'generic', filename)
        else:
            target_path = os.path.join(easyblocks_dir, filename)

        safe_symlink(easyblock_module, target_path)

    included_easyblocks = [x for x in os.listdir(easyblocks_dir) if x not in ['__init__.py', 'generic']]
    included_generic_easyblocks = [x for x in os.listdir(os.path.join(easyblocks_dir, 'generic')) if x != '__init__.py']
    _log.debug("Included generic easyblocks: %s", included_easyblocks)
    _log.debug("Included software-specific easyblocks: %s", included_generic_easyblocks)

    # inject path into Python search path, and reload modules to get it 'registered' in sys.modules
    sys.path.insert(0, easyblocks_path)
    reload(easybuild)
    if 'easybuild.easyblocks' in sys.modules:
        reload(easybuild.easyblocks)
        reload(easybuild.easyblocks.generic)

    return easyblocks_path


def include_module_naming_schemes(tmpdir, paths):
    """Include module naming schemes at specified locations."""
    mns_path = os.path.join(tmpdir, 'included-module-naming-schemes')

    set_up_eb_package(mns_path, 'easybuild.tools.module_naming_scheme')

    mns_dir = os.path.join(mns_path, 'easybuild', 'tools', 'module_naming_scheme')

    allpaths = expand_glob_paths(paths)
    for mns_module in allpaths:
        filename = os.path.basename(mns_module)
        target_path = os.path.join(mns_dir, filename)
        safe_symlink(mns_module, target_path)

    included_mns = [x for x in os.listdir(mns_dir) if x not in ['__init__.py']]
    _log.debug("Included module naming schemes: %s", included_mns)

    # inject path into Python search path, and reload modules to get it 'registered' in sys.modules
    sys.path.insert(0, mns_path)
    reload(easybuild.tools.module_naming_scheme)

    return mns_path


def include_toolchains(tmpdir, paths):
    """Include toolchains and toolchain components at specified locations."""
    toolchains_path = os.path.join(tmpdir, 'included-toolchains')
    toolchain_subpkgs = ['compiler', 'fft', 'linalg', 'mpi']

    set_up_eb_package(toolchains_path, 'easybuild.toolchains', subpkgs=toolchain_subpkgs)

    toolchains_dir = os.path.join(toolchains_path, 'easybuild', 'toolchains')

    allpaths = expand_glob_paths(paths)
    for toolchain_module in allpaths:
        filename = os.path.basename(toolchain_module)

        parent_dir = os.path.basename(os.path.dirname(toolchain_module))

        # generic toolchains are expected to be in a directory named 'generic'
        if parent_dir in toolchain_subpkgs:
            target_path = os.path.join(toolchains_dir, parent_dir, filename)
        else:
            target_path = os.path.join(toolchains_dir, filename)

        safe_symlink(toolchain_module, target_path)

    included_toolchains = [x for x in os.listdir(toolchains_dir) if x not in ['__init__.py'] + toolchain_subpkgs]
    _log.debug("Included toolchains: %s", included_toolchains)
    for subpkg in toolchain_subpkgs:
        included_subpkg_modules = [x for x in os.listdir(os.path.join(toolchains_dir, subpkg)) if x != '__init__.py']
        _log.debug("Included toolchain %s components: %s", subpkg, included_subpkg_modules)

    # inject path into Python search path, and reload modules to get it 'registered' in sys.modules
    sys.path.insert(0, toolchains_path)
    reload(easybuild.toolchains)
    for subpkg in toolchain_subpkgs:
        reload(sys.modules['easybuild.toolchains.%s' % subpkg])

    return toolchains_path
