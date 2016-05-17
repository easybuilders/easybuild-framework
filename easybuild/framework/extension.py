##
# Copyright 2009-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
##
"""
Generic EasyBuild support for software extensions (e.g. Python packages).
The Extension class should serve as a base class for all extensions.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
"""
import copy
import os

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, build_path
from easybuild.tools.run import run_cmd


class Extension(object):
    """
    Support for installing extensions.
    """
    def __init__(self, mself, ext):
        """
        mself has the logger
        """
        self.master = mself
        self.log = self.master.log
        self.cfg = self.master.cfg.copy()
        self.ext = copy.deepcopy(ext)
        self.dry_run = self.master.dry_run

        if not 'name' in self.ext:
            raise EasyBuildError("'name' is missing in supplied class instance 'ext'.")

        # parent sanity check paths/commands are not relevant for extension
        self.cfg['sanity_check_commands'] = []
        self.cfg['sanity_check_paths'] = []

        # list of source/patch files: we use an empty list as default value like in EasyBlock
        self.src = self.ext.get('src', [])
        self.patches = self.ext.get('patches', [])
        self.options = copy.deepcopy(self.ext.get('options', {}))

        self.sanity_check_fail_msgs = []

    @property
    def name(self):
        """
        Shortcut the get the extension name.
        """
        return self.ext.get('name', None)

    @property
    def version(self):
        """
        Shortcut the get the extension version.
        """
        return self.ext.get('version', None)

    def prerun(self):
        """
        Stuff to do before installing a extension.
        """
        pass

    def run(self):
        """
        Actual installation of a extension.
        """
        pass

    def postrun(self):
        """
        Stuff to do after installing a extension.
        """
        pass

    @property
    def toolchain(self):
        """
        Toolchain used to build this extension.
        """
        return self.master.toolchain

    def sanity_check_step(self):
        """
        Sanity check to run after installing extension
        """

        try:
            os.chdir(self.installdir)
        except OSError, err:
            raise EasyBuildError("Failed to change %s: %s", self.installdir, err)

        # disabling templating is required here to support legacy string templates like name/version
        self.cfg.enable_templating = False
        exts_filter = self.cfg['exts_filter']
        self.cfg.enable_templating = True

        if not exts_filter is None:
            cmd, inp = exts_filter
        else:
            self.log.debug("no exts_filter setting found, skipping sanitycheck")
            return True

        if 'modulename' in self.options:
            modname = self.options['modulename']
            self.log.debug("modulename found in self.options, using it: %s", modname)
        else:
            modname = self.name
            self.log.debug("self.name: %s", modname)

        if modname == False:
            # allow skipping of sanity check by setting module name to False
            return True
        else:
            template = {
                        'ext_name': modname,
                        'ext_version': self.version,
                        'src': self.src,
                        # the ones below are only there for legacy purposes
                        # TODO deprecated, remove in v2.0
                        # TODO same dict is used in easyblock.py skip_extensions, resolve this
                        'name': modname,
                        'version': self.version,
                       }
            cmd = cmd % template

            stdin = None
            if inp:
                stdin = inp % template
            # set log_ok to False so we can catch the error instead of run_cmd
            (output, ec) = run_cmd(cmd, log_ok=False, simple=False, regexp=False)

            if ec:
                msg = "%s failed to install, cmd '%s' (stdin: %s) output: %s" % (self.name, cmd, stdin, output)
                self.log.warn("Extension: %s" % msg)
                self.sanity_check_fail_msgs.append(msg)
                return False
            else:
                return True
