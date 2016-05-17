# #
# Copyright 2012-2016 Ghent University
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
Unit tests for docs.py.
"""
import inspect
import os
import re
import sys
from unittest import TestLoader, main

from easybuild.framework.easyconfig.licenses import license_documentation
from easybuild.tools.docs import gen_easyblocks_overview_rst
from easybuild.tools.utilities import import_available_modules
from test.framework.utilities import EnhancedTestCase, init_config

class DocsTest(EnhancedTestCase):

    def test_gen_easyblocks(self):
        """ Test gen_easyblocks_overview_rst function """
        module = 'easybuild.easyblocks.generic'
        modules = import_available_modules(module)
        common_params = {
            'ConfigureMake' : ['configopts', 'buildopts', 'installopts'],
        }
        doc_functions = ['build_step', 'configure_step', 'test_step']

        eb_overview = gen_easyblocks_overview_rst(module, 'easyconfigs', common_params, doc_functions)
        ebdoc = '\n'.join(eb_overview)

        # extensive check for ConfigureMake easyblock
        check_configuremake = '\n'.join([
            ".. _ConfigureMake:",
            '',
            "``ConfigureMake``",
            "=================",
            '',
            "(derives from EasyBlock)",
            '',
            "Dummy support for building and installing applications with configure/make/make install.",
            '',
            "Commonly used easyconfig parameters with ``ConfigureMake`` easyblock",
            "--------------------------------------------------------------------",
            "====================    ================================================================",
            "easyconfig parameter    description                                                     ",
            "====================    ================================================================",
            "configopts              Extra options passed to configure (default already has --prefix)",
            "buildopts               Extra options passed to make step (default already has -j X)    ",
            "installopts             Extra options for installation                                  ",
            "====================    ================================================================",
        ])

        self.assertTrue(check_configuremake in ebdoc)
        names = []

        for mod in modules:
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                eb_class = getattr(mod, name)
                # skip imported classes that are not easyblocks
                if eb_class.__module__.startswith(module):
                    self.assertTrue(name in ebdoc)
                    names.append(name)

        toc = [":ref:`" + n + "`" for n in sorted(names)]
        pattern = " - ".join(toc)

        regex = re.compile(pattern)
        self.assertTrue(re.search(regex, ebdoc), "Pattern %s found in %s" % (regex.pattern, ebdoc))

    def test_license_docs(self):
        """Test license_documentation function."""
        lic_docs = license_documentation()
        gplv3 = "GPLv3: The GNU General Public License"
        self.assertTrue(gplv3 in lic_docs, "%s found in: %s" % (gplv3, lic_docs))


def suite():
    """ returns all test cases in this module """
    return TestLoader().loadTestsFromTestCase(DocsTest)

if __name__ == '__main__':
    # also check the setUp for debug
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
