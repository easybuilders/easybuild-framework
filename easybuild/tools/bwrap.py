#!/usr/bin/env python
# #
# Copyright 2009-2026 Ghent University
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
Module for handling installations with bwrap (bubblewrap)

Authors:

* Samuel Moors (Vrije Universiteit Brussel)
"""
import json
import os
from typing import Any

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import install_path, ConfigurationVariables
from easybuild.tools.filetools import mkdir, write_file
from easybuild.tools.utilities import trace_msg


BWRAP_INFO_JSON = 'bwrap_info.json'

# global state to exchange info required when using bwrap between EasyBuild sessions
_bwrap_info = {
    'bwrap_cmd': [],
    'bwrap_eb_options': [],
    'bwrap_installpath': '',
    'bwrap_installpath_software': '',
    'bwrap_installpath_modules': '',
    'installpath_modules': '',
    'installpath_software': '',
    'modules_to_install': set(),

}

_log = fancylogger.getLogger('bwrap', fname=False)


def get_bwrap_info(key):
    """
    Get specified info w.r.t. use of bwrap
    """
    if key in _bwrap_info:
        return _bwrap_info[key]
    else:
        raise EasyBuildError(f"Unknown key specified to get bwrap info: {key}")


def set_bwrap_info(key: str, value: Any) -> None:
    """
    Set specified info w.r.t. use of bwrap
    """
    if key in _bwrap_info:
        _bwrap_info[key] = value
    else:
        raise EasyBuildError(f"Unknown key specified to set bwrap info: {key}")


def update_bwrap_info(key: str, value: Any) -> None:
    """
    Update specified info w.r.t. use of bwrap (only supports 'set' values currently)
    """
    if key in _bwrap_info:
        current_value = _bwrap_info[key]
        if isinstance(current_value, set) and isinstance(value, set):
            current_value.update(value)
        else:
            raise EasyBuildError("Unknown type of value encountered when updating bwrap info!")
    else:
        raise EasyBuildError(f"Unknown key specified to update bwrap info: {key}")


def prepare_bwrap(bwrap_installpath: str) -> None:
    """
    Prepare for running EasyBuild with bwrap:
    - update _bwrap_info
    - write json metadata file with contents of _bwrap_info
    - set environment variable $EB_BWRAP_CMD

    :param bwrap_installpath: bwrap install path
    """

    set_bwrap_info('bwrap_installpath', bwrap_installpath)

    installpath_software = install_path(typ='software')
    set_bwrap_info('installpath_software', installpath_software)

    set_bwrap_info('installpath_modules', install_path(typ='modules'))

    variables = ConfigurationVariables()
    bwrap_installpath_software = os.path.join(bwrap_installpath, variables['subdir_software'])
    bwrap_installpath_modules = os.path.join(bwrap_installpath, variables['subdir_modules'])
    set_bwrap_info('bwrap_installpath_software', bwrap_installpath_software)
    set_bwrap_info('bwrap_installpath_modules', bwrap_installpath_modules)

    bwrap_cmd = ['bwrap', '--dev-bind', '/', '/']

    # bind mount all software directories
    for mod in sorted(get_bwrap_info('modules_to_install')):
        installdir = os.path.join(os.path.realpath(installpath_software), mod)
        bwrap_installdir = os.path.join(bwrap_installpath_software, mod)
        use_overlayfs = False
        try:
            mkdir(installdir, parents=True)
        except EasyBuildError:
            # if we can't create the external installation directory, try to use overlayfs
            use_overlayfs = True
        mkdir(bwrap_installdir, parents=True)
        if use_overlayfs:
            bwrap_workdir = os.path.join(bwrap_installpath, 'workdir', mod)
            mkdir(bwrap_workdir, parents=True)
            # go up the tree until we find a directory that exists
            while not os.path.exists(installdir):
                installdir = os.path.dirname(installdir)
                bwrap_installdir = os.path.dirname(bwrap_installdir)
            opts = ['--overlay-src', installdir, '--overlay', bwrap_installdir, bwrap_workdir, installdir]
        else:
            opts = ['--bind', bwrap_installdir, installdir]
        bwrap_cmd.extend(opts)

    set_bwrap_info('bwrap_cmd', bwrap_cmd)
    bwrap_cmd_str = ' '.join(bwrap_cmd)

    # disable `--bwrap` to prepare for a real installation (in bwrap namespace)
    bwrap_eb_options = ['--disable-bwrap', f'--installpath-modules={bwrap_installpath_modules}']
    set_bwrap_info('bwrap_eb_options', bwrap_eb_options)

    _log.info(f'Info needed for bwrap: {_bwrap_info}')

    # write json file with bwrap install info into bwrap installpath
    bwrap_infopath = os.path.join(bwrap_installpath, BWRAP_INFO_JSON)
    write_file(bwrap_infopath, json.dumps(_bwrap_info, default=list, indent=2, sort_keys=True), backup=True)

    print_msg('Building/installing in bwrap namespace')
    trace_msg(f'bwrap command (to prefix eb command): {bwrap_cmd_str}')
    trace_msg(f'bwrap info file: {bwrap_infopath}')
    trace_msg(f'bwrap EasyBuild options: {bwrap_eb_options}')

    # set environment variable $EB_BWRAP_CMD to make it available for the interactive debug shell
    # when rerunning with bwrap
    os.environ['EB_BWRAP_CMD'] = bwrap_cmd_str
