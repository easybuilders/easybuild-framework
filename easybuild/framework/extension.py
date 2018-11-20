##
# Copyright 2009-2018 Ghent University
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
Generic EasyBuild support for software extensions (e.g. Python packages).
The Extension class should serve as a base class for all extensions.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
"""
import copy
import os

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, build_path
from easybuild.tools.filetools import change_dir
from easybuild.tools.run import run_cmd


class Extension(object):
    """
    Support for installing extensions.
    """
    def __init__(self, mself, ext, extra_params=None):
        """
        Constructor for Extension class

        :param mself: parent Easyblock instance
        :param ext: dictionary with extension metadata (name, version, src, patches, options, ...)
        :param extra_params: extra custom easyconfig parameters to take into account for this extension
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

        if extra_params:
            self.cfg.extend_params(extra_params, overwrite=False)

        # custom easyconfig parameters for extension are included in self.options
        # make sure they are merged into self.cfg so they can be queried;
        # unknown easyconfig parameters are ignored since self.options may include keys only there for extensions;
        # this allows to specify custom easyconfig parameters on a per-extension basis
        for key in self.options:
            if key in self.cfg:
                self.cfg[key] = self.options[key]
                self.log.debug("Customising known easyconfig parameter '%s' for extension %s/%s: %s",
                               key, self.ext['name'], self.ext['version'], self.cfg[key])
            else:
                self.log.debug("Skipping unknown custom easyconfig parameter '%s' for extension %s/%s: %s",
                               key, self.ext['name'], self.ext['version'], self.options[key])

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
        res = (True, '')

        if os.path.isdir(self.installdir):
            change_dir(self.installdir)

        # disabling templating is required here to support legacy string templates like name/version
        self.cfg.enable_templating = False
        exts_filter = self.cfg['exts_filter']
        self.cfg.enable_templating = True

        if exts_filter is not None:
            cmd, inp = exts_filter
        else:
            self.log.debug("no exts_filter setting found, skipping sanitycheck")
            cmd = None

        if 'modulename' in self.options:
            modname = self.options['modulename']
            self.log.debug("modulename found in self.options, using it: %s", modname)
        else:
            modname = self.name
            self.log.debug("self.name: %s", modname)

        # allow skipping of sanity check by setting module name to False
        if modname is False:
            self.log.info("modulename set to False for '%s' extension, so skipping sanity check", self.name)
        elif cmd:
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
            (output, ec) = run_cmd(cmd, log_ok=False, simple=False, regexp=False, inp=stdin)

            if ec:
                if stdin:
                    fail_msg = 'command "%s" (stdin: "%s") failed' % (cmd, stdin)
                else:
                    fail_msg = 'command "%s" failed' % cmd
                fail_msg += "; output:\n%s" % output.strip()
                self.log.warning("Sanity check for '%s' extension failed: %s", self.name, fail_msg)
                res = (False, fail_msg)
                # keep track of all reasons of failure
                # (only relevant when this extension is installed stand-alone via ExtensionEasyBlock)
                self.sanity_check_fail_msgs.append(fail_msg)

        return res
