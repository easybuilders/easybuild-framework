##
# Copyright 2012-2021 Ghent University
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
EasyBuild support for Fujitsu Compiler toolchain.

:author: Miguel Dias Costa (National University of Singapore)
"""
from easybuild.toolchains.compiler.fujitsu import FujitsuCompiler
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME


class FCC(FujitsuCompiler):
    """Compiler toolchain with Fujitsu Compiler."""
    NAME = 'FCC'
    SUBTOOLCHAIN = SYSTEM_TOOLCHAIN_NAME
    OPTIONAL = False

    # override in order to add an exception for the Fujitsu lang/tcsds module
    def _add_dependency_variables(self, names=None, cpp=None, ld=None):
        """ Add LDFLAGS and CPPFLAGS to the self.variables based on the dependencies
            names should be a list of strings containing the name of the dependency
        """
        cpp_paths = ['include']
        ld_paths = ['lib']
        if not self.options.get('32bit', None):
            ld_paths.insert(0, 'lib64')

        if cpp is not None:
            for p in cpp:
                if p not in cpp_paths:
                    cpp_paths.append(p)
        if ld is not None:
            for p in ld:
                if p not in ld_paths:
                    ld_paths.append(p)

        if not names:
            deps = self.dependencies
        else:
            deps = [{'name': name} for name in names if name is not None]

        # collect software install prefixes for dependencies
        roots = []
        for dep in deps:
            if dep.get('external_module', False):
                # for software names provided via external modules, install prefix may be unknown
                names = dep['external_module_metadata'].get('name', [])
                roots.extend([root for root in self.get_software_root(names) if root is not None])
            else:
                roots.extend(self.get_software_root(dep['name']))

        for root in roots:
            # skip Fujitsu's 'lang/tcsds' module, including the top level include breaks vectorization in clang mode
            if 'tcsds' not in root:
                self.variables.append_subdirs("CPPFLAGS", root, subdirs=cpp_paths)
            self.variables.append_subdirs("LDFLAGS", root, subdirs=ld_paths)
