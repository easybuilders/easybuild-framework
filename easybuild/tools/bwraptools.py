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

from easybuild.base import fancylogger
from easybuild.tools.build_log import print_msg
from easybuild.tools.config import install_path
from easybuild.tools.filetools import mkdir, write_file
from easybuild.tools.utilities import trace_msg

BWRAP_INFO = {
    'modules_to_install': set(),
    'installpath_software': '',
    'installpath_modules': '',
    'bwrap_installpath': '',
    'bwrap_cmd': [],
    'bwrap_eb_options': [],

}
BWRAP_INFO_JSON = 'bwrap_info.json'

_log = fancylogger.getLogger('bwrap', fname=False)


def prepare_bwrap(bwrap_installpath):
    "Prepare for running EasyBuild with bwrap"

    BWRAP_INFO['bwrap_installpath'] = bwrap_installpath
    BWRAP_INFO['installpath_software'] = install_path(typ='software')
    BWRAP_INFO['installpath_modules'] = install_path(typ='modules')
    installpath_software = BWRAP_INFO['installpath_software']
    bwrap_installpath = BWRAP_INFO['bwrap_installpath']
    bwrap_mpath = os.path.join(bwrap_installpath, 'modules')
    bwrap_cmd = ['bwrap', '--dev-bind', '/', '/']

    for mod in BWRAP_INFO['modules_to_install']:
        spath = os.path.join(os.path.realpath(installpath_software), mod)
        bwrap_spath = os.path.join(bwrap_installpath, 'software', mod)
        mkdir(spath, parents=True)
        mkdir(bwrap_spath, parents=True)
        bwrap_cmd.extend(['--bind', bwrap_spath, spath])

    BWRAP_INFO['bwrap_cmd'] = bwrap_cmd

    # disable `--bwrap` to prepare for a real installation (in bwrap namespace)
    BWRAP_INFO['bwrap_eb_options'] = ['--disable-bwrap', f'--installpath-modules={bwrap_mpath}']


def log_bwrap():
    "Log, print, write metadata for bwrap"
    _log.info(f'Info needed for bwrap: {BWRAP_INFO}')

    # write json file with bwrap install info into bwrap installpath
    bwrap_infopath = os.path.join(BWRAP_INFO['bwrap_installpath'], BWRAP_INFO_JSON)
    write_file(bwrap_infopath, json.dumps(BWRAP_INFO, default=list, indent=2, sort_keys=True), backup=True)

    print_msg('Building/installing in bwrap namespace')
    trace_msg(f'bwrap info file: {bwrap_infopath}')
    trace_msg(f'bwrap EasyBuild options: {BWRAP_INFO["bwrap_eb_options"]}')
    trace_msg(f'bwrap prefix: {" ".join(BWRAP_INFO["bwrap_cmd"])}')

    # set environment variable EB_BWRAP_CMD to make it available for the interactive debug shell
    # when rerunning with bwrap
    os.environ['EB_BWRAP_CMD'] = ' '.join(BWRAP_INFO['bwrap_cmd'])
