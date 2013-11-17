# #
# Copyright 2013-2013 Ghent University
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
This describes the easyconfig format version 1.X

This is the original pure python code, to be exec'ed rather then parsed

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import os
import re
import tempfile
from vsc import fancylogger

from easybuild.framework.easyconfig.format.format import get_format_version, FORMAT_DEFAULT_VERSION
from easybuild.framework.easyconfig.format.pyheaderconfigobj import EasyConfigFormatConfigObj
from easybuild.framework.easyconfig.format.version import EasyVersion
from easybuild.tools.filetools import write_file


_log = fancylogger.getLogger('easyconfig.format.format', fname=False)


class FormatOneZero(EasyConfigFormatConfigObj):
    """Support for easyconfig format 1.x"""
    VERSION = EasyVersion('1.0')
    USABLE = True  # TODO: disable it at some point, too insecure

    PYHEADER_ALLOWED_BUILTINS = None  # allow all
    PYHEADER_MANDATORY = ['version', 'name', 'toolchain', 'homepage', 'description']
    PYHEADER_BLACKLIST = []

    def validate(self):
        """Format validation"""
        # minimal checks
        self._validate_pyheader()

    def get_config_dict(self, version=None, toolchain_name=None, toolchain_version=None):
        """
        Return parsed easyconfig as a dictionary, based on specified arguments.
        This is easyconfig format 1.x, so there is only one easyconfig instance available.
        """
        cfg = self.pyheader_localvars
        if version is not None and not version == cfg['version']:
            self.log.error('Requested version %s not available, only %s' % (version, cfg['version']))

        tc_name = cfg['toolchain']['name']
        tc_version = cfg['toolchain']['version']
        if toolchain_name is not None and not toolchain_name == tc_name:
            self.log.error('Requested toolchain name %s not available, only %s' % (toolchain_name, tc_name))
        if toolchain_version is not None and not toolchain_version == tc_version:
            self.log.error('Requested toolchain version %s not available, only %s' % (toolchain_version, tc_version))

        return cfg

    def parse(self, txt):
        """
        Pre-process txt to extract header, docstring and pyheader, with non-indented section markers enforced.
        """
        super(FormatOneZero, self).parse(txt, strict_section_markers=True)


def retrieve_blocks_in_spec(spec, only_blocks, silent=False):
    """
    Easyconfigs can contain blocks (headed by a [Title]-line)
    which contain commands specific to that block. Commands in the beginning of the file
    above any block headers are common and shared between each block.
    """
    reg_block = re.compile(r"^\s*\[([\w.-]+)\]\s*$", re.M)
    reg_dep_block = re.compile(r"^\s*block\s*=(\s*.*?)\s*$", re.M)

    spec_fn = os.path.basename(spec)
    try:
        txt = open(spec).read()
    except IOError, err:
        _log.error("Failed to read file %s: %s" % (spec, err))

    # split into blocks using regex
    pieces = reg_block.split(txt)
    # the first block contains common statements
    common = pieces.pop(0)

    # determine version of easyconfig format
    ec_format_version = get_format_version(txt)
    if ec_format_version is None:
        ec_format_version = FORMAT_DEFAULT_VERSION
    _log.debug("retrieve_blocks_in_spec: derived easyconfig format version: %s" % ec_format_version)

    # blocks in easyconfigs are only supported in format versions prior to 2.0
    if pieces and ec_format_version < EasyVersion('2.0'):
        # make a map of blocks
        blocks = []
        while pieces:
            block_name = pieces.pop(0)
            block_contents = pieces.pop(0)

            if block_name in [b['name'] for b in blocks]:
                msg = "Found block %s twice in %s." % (block_name, spec)
                _log.error(msg)

            block = {'name': block_name, 'contents': block_contents}

            # dependency block
            dep_block = reg_dep_block.search(block_contents)
            if dep_block:
                dependencies = eval(dep_block.group(1))
                if type(dependencies) == list:
                    block['dependencies'] = dependencies
                else:
                    block['dependencies'] = [dependencies]

            blocks.append(block)

        # make a new easyconfig for each block
        # they will be processed in the same order as they are all described in the original file
        specs = []
        for block in blocks:
            name = block['name']
            if only_blocks and not (name in only_blocks):
                print_msg("Skipping block %s-%s" % (spec_fn, name), silent=silent)
                continue

            (fd, block_path) = tempfile.mkstemp(prefix='easybuild-', suffix='%s-%s' % (spec_fn, name))
            os.close(fd)

            txt = common

            if 'dependencies' in block:
                for dep in block['dependencies']:
                    if not dep in [b['name'] for b in blocks]:
                        log.error("Block %s depends on %s, but block was not found." % (name, dep))

                    dep = [b for b in blocks if b['name'] == dep][0]
                    txt += "\n# Dependency block %s" % (dep['name'])
                    txt += dep['contents']

            txt += "\n# Main block %s" % name
            txt += block['contents']

            write_file(block_path, txt)

            specs.append(block_path)

        _log.debug("Found %s block(s) in %s" % (len(specs), spec))
        return specs
    else:
        # no blocks, one file
        return [spec]
