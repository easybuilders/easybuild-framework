# #
# Copyright 2012-2018 Ghent University
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
Unit tests for docs.py.
"""
import inspect
import os
import re
import sys
from unittest import TextTestRunner

from easybuild.tools.config import module_classes
from easybuild.tools.docs import avail_easyconfig_licenses, gen_easyblocks_overview_rst, list_software
from easybuild.tools.utilities import import_available_modules
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config


class DocsTest(EnhancedTestCase):

    def test_gen_easyblocks(self):
        """ Test gen_easyblocks_overview_rst function """
        gen_easyblocks_pkg = 'easybuild.easyblocks.generic'
        modules = import_available_modules(gen_easyblocks_pkg)
        common_params = {
            'ConfigureMake' : ['configopts', 'buildopts', 'installopts'],
        }
        doc_functions = ['build_step', 'configure_step', 'test_step']

        eb_overview = gen_easyblocks_overview_rst(gen_easyblocks_pkg, 'easyconfigs', common_params, doc_functions)
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
            "Extra easyconfig parameters specific to ``ConfigureMake`` easyblock",
            "-------------------------------------------------------------------",
            '',
            "====================    ============    =============",
            "easyconfig parameter    description     default value",
            "====================    ============    =============",
            '``test_123``            Test 1, 2, 3    ``""``       ',
            "``test_bool``           Just a test     ``False``    ",
            "``test_none``           Another test    ``None``     ",
            "====================    ============    =============",
            '',
            "Commonly used easyconfig parameters with ``ConfigureMake`` easyblock",
            "--------------------------------------------------------------------",
            '',
            "====================    ================================================================",
            "easyconfig parameter    description                                                     ",
            "====================    ================================================================",
            "configopts              Extra options passed to configure (default already has --prefix)",
            "buildopts               Extra options passed to make step (default already has -j X)    ",
            "installopts             Extra options for installation                                  ",
            "====================    ================================================================",
        ])

        self.assertTrue(check_configuremake in ebdoc, "Found '%s' in: %s" % (check_configuremake, ebdoc))
        names = []

        for mod in modules:
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                eb_class = getattr(mod, name)
                # skip imported classes that are not easyblocks
                if eb_class.__module__.startswith(gen_easyblocks_pkg):
                    self.assertTrue(name in ebdoc)
                    names.append(name)

        toc = [":ref:`" + n + "`" for n in sorted(set(names))]
        pattern = " - ".join(toc)

        regex = re.compile(pattern)
        self.assertTrue(re.search(regex, ebdoc), "Pattern %s found in %s" % (regex.pattern, ebdoc))

    def test_license_docs(self):
        """Test license_documentation function."""
        lic_docs = avail_easyconfig_licenses(output_format='txt')
        gplv3 = "GPLv3: The GNU General Public License"
        self.assertTrue(gplv3 in lic_docs, "%s found in: %s" % (gplv3, lic_docs))

        lic_docs = avail_easyconfig_licenses(output_format='rst')
        regex = re.compile("^``GPLv3``\s*The GNU General Public License", re.M)
        self.assertTrue(regex.search(lic_docs), "%s found in: %s" % (regex.pattern, lic_docs))

    def test_list_software(self):
        """Test list_software* functions."""
        build_options = {
            'robot_path': [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'v1.0')],
            'silent': True,
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)

        expected = '\n'.join([
            '',
            '* GCC',
            '* gzip',
        ])
        self.assertEqual(list_software(output_format='txt'), expected)

        expected = re.compile('\n'.join([
            r'',
            r'\* GCC',
            r'',
            r"The GNU Compiler Collection .*",
            r'',
            r'homepage: http://gcc.gnu.org/',
            r'',
            r'  \* GCC v4.6.3: dummy',
            r'',
            r'\* gzip',
            r'',
            r"gzip \(GNU zip\) is .*",
            r'',
            r'homepage: http://www.gzip.org/',
            r'',
            r"  \* gzip v1.4: GCC/4.6.3, dummy",
            r"  \* gzip v1.5: goolf/1.4.10, ictce/4.1.13",
            '',
        ]))
        txt = list_software(output_format='txt', detailed=True)
        self.assertTrue(expected.match(txt), "Pattern '%s' found in: %s" % (expected.pattern, txt))

        expected = '\n'.join([
            "List of supported software",
            "==========================",
            '',
            "EasyBuild |version| supports 2 different software packages (incl. toolchains, bundles):",
            '',
            ':ref:`list_software_letter_g`',
            '',
            '',
            '.. _list_software_letter_g:',
            '',
            '*G*',
            '---',
            '',
            '* GCC',
            '* gzip',
        ])
        self.assertEqual(list_software(output_format='rst'), expected)

        expected = re.compile('\n'.join([
            r"List of supported software",
            r"==========================",
            r'',
            r"EasyBuild \|version\| supports 2 different software packages \(incl. toolchains, bundles\):",
            r'',
            r':ref:`list_software_letter_g`',
            r'',
            r'',
            r'.. _list_software_letter_g:',
            r'',
            r'\*G\*',
            r'---',
            r'',
            r'',
            r':ref:`list_software_GCC_205` - :ref:`list_software_gzip_442`',
            r'',
            r'',
            r'\.\. _list_software_GCC_205:',
            r'',
            r'\*GCC\*',
            r'\+\+\+\+\+',
            r'',
            r'The GNU Compiler Collection .*',
            r'',
            r'\*homepage\*: http://gcc.gnu.org/',
            r'',
            r'=========    =========',
            r'version      toolchain',
            r'=========    =========',
            r'``4.6.3``    ``dummy``',
            r'=========    =========',
            r'',
            r'',
            r'\.\. _list_software_gzip_442:',
            r'',
            r'\*gzip\*',
            r'\+\+\+\+\+\+',
            r'',
            r'gzip \(GNU zip\) is a popular .*',
            r'',
            r'\*homepage\*: http://www.gzip.org/',
            r'',
            r'=======    ==================================',
            r'version    toolchain                         ',
            r'=======    ==================================',
            r'``1.4``    ``GCC/4.6.3``, ``dummy``          ',
            r'``1.5``    ``goolf/1.4.10``, ``ictce/4.1.13``',
            r'=======    ==================================',
        ]))
        txt = list_software(output_format='rst', detailed=True)
        self.assertTrue(expected.match(txt), "Pattern '%s' found in: %s" % (expected.pattern, txt))

        # GCC/4.6.3 is installed, no gzip module installed
        txt = list_software(output_format='txt', detailed=True, only_installed=True)
        self.assertTrue(re.search('^\* GCC', txt, re.M))
        self.assertTrue(re.search('^\s*\* GCC v4.6.3: dummy', txt, re.M))
        self.assertFalse(re.search('^\* gzip', txt, re.M))
        self.assertFalse(re.search('gzip v1\.', txt, re.M))

        txt = list_software(output_format='rst', detailed=True, only_installed=True)
        self.assertTrue(re.search('^\*GCC\*', txt, re.M))
        self.assertTrue(re.search('4\.6\.3.*dummy', txt, re.M))
        self.assertFalse(re.search('^\*gzip\*', txt, re.M))
        self.assertFalse(re.search('1\.4', txt, re.M))
        self.assertFalse(re.search('1\.5', txt, re.M))

        # check for specific patterns in output for larger set of test easyconfigs
        build_options = {
            'robot_path': [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')],
            'silent': True,
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)

        expected = [
            '* toy',
            '',
            'Toy C program, 100% toy.',
            '',
            'homepage: https://easybuilders.github.io/easybuild',
            '',
            "  * toy v0.0: dummy",
            "  * toy v0.0 (versionsuffix: '-deps'): dummy",
            "  * toy v0.0 (versionsuffix: '-iter'): dummy",
            "  * toy v0.0 (versionsuffix: '-multiple'): dummy",
            "  * toy v0.0 (versionsuffix: '-test'): gompi/1.3.12",
        ]
        txt = list_software(output_format='txt', detailed=True)
        lines = txt.split('\n')
        expected_found = any([lines[i:i+len(expected)] == expected for i in range(len(lines))])
        self.assertTrue(expected_found, "%s found in: %s" % (expected, lines))

        expected = [
            '*toy*',
            '+++++',
            '',
            'Toy C program, 100% toy.',
            '',
            '*homepage*: https://easybuilders.github.io/easybuild',
            '',
            '=======    =============    ================',
            'version    versionsuffix    toolchain       ',
            '=======    =============    ================',
            '``0.0``                     ``dummy``       ',
            '``0.0``    ``-deps``        ``dummy``       ',
            '``0.0``    ``-iter``        ``dummy``       ',
            '``0.0``    ``-multiple``    ``dummy``       ',
            '``0.0``    ``-test``        ``gompi/1.3.12``',
            '=======    =============    ================',
        ]
        txt = list_software(output_format='rst', detailed=True)
        lines = txt.split('\n')
        expected_found = any([lines[i:i+len(expected)] == expected for i in range(len(lines))])
        self.assertTrue(expected_found, "%s found in: %s" % (expected, lines))


def suite():
    """ returns all test cases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(DocsTest, sys.argv[1:])

if __name__ == '__main__':
    # also check the setUp for debug
    # logToScreen(enable=True)
    # setLogLevelDebug()
    TextTestRunner(verbosity=1).run(suite())
