##
# Copyright (c) 2015 Forschungszentrum Juelich GmbH, Germany
#
# All rights reserved.
#
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
#
# * Neither the name of Forschungszentrum Juelich GmbH, nor the names of
#   its contributors may be used to endorse or promote products derived
#   from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# License: 3-clause BSD
##
"""
Implementation of a hierarchical module naming scheme using module classes.

@author: Markus Geimer (Juelich Supercomputing Centre)
"""

import os

from easybuild.tools.module_naming_scheme.hierarchical_mns import HierarchicalMNS
from easybuild.tools.config import build_option


class CategorizedHMNS(HierarchicalMNS):
    """
    Class implementing an extended hierarchical module naming scheme using the
    'moduleclass' easyconfig parameter to categorize modulefiles on each level
    of the hierarchy.
    """

    REQUIRED_KEYS = ['name', 'version', 'versionsuffix', 'toolchain', 'moduleclass']

    def det_module_subdir(self, ec):
        """
        Determine module subdirectory, relative to the top of the module path.
        This determines the separation between module names exposed to users,
        and what's part of the $MODULEPATH. This implementation appends the
        'moduleclass' easyconfig parameter to the base path of the corresponding
        hierarchy level.

        Examples:
        Core/compiler, Compiler/GCC/4.8.3/mpi, MPI/GCC/4.8.3/OpenMPI/1.6.5/bio
        """
        moduleclass = ec['moduleclass']
        basedir = super(CategorizedHMNS, self).det_module_subdir(ec)

        return os.path.join(basedir, moduleclass)

    def det_modpath_extensions(self, ec):
        """
        Determine module path extensions, if any. Appends all known (valid)
        module classes to the base path of the corresponding hierarchy level.

        Examples:
        Compiler/GCC/4.8.3/<moduleclasses> (for GCC/4.8.3 module),
        MPI/GCC/4.8.3/OpenMPI/1.6.5/<moduleclasses> (for OpenMPI/1.6.5 module)
        """
        basepaths = super(CategorizedHMNS, self).det_modpath_extensions(ec)

        return self.categorize_paths(basepaths)

    def det_user_modpath_extensions(self, ec):
        """
        Determine user module path extensions, if any. As typical users are not expected to have many local modules,
        further categorizing them using module classes is considered overkill. Thus, we are using a plain hierarchical
        scheme for user modules instead.

        Examples: Compiler/GCC/4.8.3 (for GCC/4.8.3 module), MPI/GCC/4.8.3/OpenMPI/1.6.5 (for OpenMPI/1.6.5 module)
        """
        # Use "system" module path extensions of hierarchical MNS (i.e., w/o module class)
        return super(CategorizedHMNS, self).det_modpath_extensions(ec)

    def det_init_modulepaths(self, ec):
        """
        Determine list of initial module paths (i.e., top of the hierarchy).
        Appends all known (valid) module classes to the top-level base path.

        Examples:
        Core/<moduleclasses>
        """
        basepaths = super(CategorizedHMNS, self).det_init_modulepaths(ec)

        return self.categorize_paths(basepaths)

    def categorize_paths(self, basepaths):
        """
        Returns a list of paths where all known (valid) module classes have
        been added to each of the given base paths.
        """
        valid_module_classes = build_option('valid_module_classes')

        paths = []
        for path in basepaths:
            for moduleclass in valid_module_classes:
                paths.extend([os.path.join(path, moduleclass)])

        return paths
