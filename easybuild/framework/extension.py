##
# Copyright 2009-2012 Ghent University
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
# Copyright 2012 Toon Willems
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
##
"""
Generic EasyBuild support for software extensions (e.g. Python packages).
The Extension class should serve as a base class for all extensions.
"""
import copy

from easybuild.tools.filetools import run_cmd


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

        if not 'name' in self.ext:
            self.log.error("'name' is missing in supplied class instance 'ext'.")

        self.src = self.ext.get('src', None)
        self.patches = self.ext.get('patches', None)
        self.options = copy.deepcopy(self.ext.get('options', {}))

        self.toolchain.prepare(self.cfg['onlytcmod'])

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
        sanity check to run after installing
        """
        if not self.cfg['exts_filter'] is None:
            cmd, inp = self.cfg['exts_filter']
        else:
            self.log.debug("no exts_filter setting found, skipping sanitycheck")
            return

        if 'modulename' in self.options:
            modname = self.options['modulename']
        else:
            modname = self.name

        template = {
                    'name': modname,
                    'version': self.version,
                    'src': self.src
                   }
        cmd = cmd % template

        if inp:
            stdin = inp % template
            # set log_ok to False so we can catch the error instead of run_cmd
            (output, ec) = run_cmd(cmd, log_ok=False, simple=False, inp=stdin, regexp=False)
        else:
            (output, ec) = run_cmd(cmd, log_ok=False, simple=False, regexp=False)
        if ec:
            self.log.warn("Extension: %s failed to install! (output: %s)" % (self.name, output))
            return False
        else:
            return True
