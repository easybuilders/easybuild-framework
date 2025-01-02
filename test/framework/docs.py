# #
# Copyright 2012-2025 Ghent University
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
from easybuild.tools.docs import avail_cfgfile_constants, avail_easyconfig_constants, avail_easyconfig_licenses
from easybuild.tools.docs import avail_easyconfig_templates, avail_toolchain_opts
from easybuild.tools.docs import get_easyblock_classes, gen_easyblocks_overview_md, gen_easyblocks_overview_rst
from easybuild.tools.docs import list_easyblocks, list_software, list_toolchains
from easybuild.tools.docs import md_title_and_table, rst_title_and_table
from easybuild.tools.options import EasyBuildOptions
from easybuild.tools.utilities import import_available_modules, mk_md_table, mk_rst_table
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config


LIST_EASYBLOCKS_SIMPLE_TXT = """EasyBlock
|-- bar
|-- ConfigureMake
|   |-- MakeCp
|-- EB_EasyBuildMeta
|-- EB_FFTW
|-- EB_foo
|   |-- EB_foofoo
|-- EB_GCC
|-- EB_HPL
|-- EB_libtoy
|-- EB_OpenBLAS
|-- EB_OpenMPI
|-- EB_ScaLAPACK
|-- EB_toy_buggy
|-- ExtensionEasyBlock
|   |-- DummyExtension
|   |-- EB_toy
|   |   |-- EB_toy_eula
|   |   |-- EB_toytoy
|   |-- Toy_Extension
|-- ModuleRC
|-- PythonBundle
|-- Toolchain
Extension
|-- ExtensionEasyBlock
|   |-- DummyExtension
|   |-- EB_toy
|   |   |-- EB_toy_eula
|   |   |-- EB_toytoy
|   |-- Toy_Extension"""

LIST_EASYBLOCKS_DETAILED_TXT = """EasyBlock (easybuild.framework.easyblock)
|-- bar (easybuild.easyblocks.generic.bar @ %(topdir)s/generic/bar.py)
|-- ConfigureMake (easybuild.easyblocks.generic.configuremake @ %(topdir)s/generic/configuremake.py)
|   |-- MakeCp (easybuild.easyblocks.generic.makecp @ %(topdir)s/generic/makecp.py)
|-- EB_EasyBuildMeta (easybuild.easyblocks.easybuildmeta @ %(topdir)s/e/easybuildmeta.py)
|-- EB_FFTW (easybuild.easyblocks.fftw @ %(topdir)s/f/fftw.py)
|-- EB_foo (easybuild.easyblocks.foo @ %(topdir)s/f/foo.py)
|   |-- EB_foofoo (easybuild.easyblocks.foofoo @ %(topdir)s/f/foofoo.py)
|-- EB_GCC (easybuild.easyblocks.gcc @ %(topdir)s/g/gcc.py)
|-- EB_HPL (easybuild.easyblocks.hpl @ %(topdir)s/h/hpl.py)
|-- EB_libtoy (easybuild.easyblocks.libtoy @ %(topdir)s/l/libtoy.py)
|-- EB_OpenBLAS (easybuild.easyblocks.openblas @ %(topdir)s/o/openblas.py)
|-- EB_OpenMPI (easybuild.easyblocks.openmpi @ %(topdir)s/o/openmpi.py)
|-- EB_ScaLAPACK (easybuild.easyblocks.scalapack @ %(topdir)s/s/scalapack.py)
|-- EB_toy_buggy (easybuild.easyblocks.toy_buggy @ %(topdir)s/t/toy_buggy.py)
|-- ExtensionEasyBlock (easybuild.framework.extensioneasyblock )
|   |-- DummyExtension (easybuild.easyblocks.generic.dummyextension @ %(topdir)s/generic/dummyextension.py)
|   |-- EB_toy (easybuild.easyblocks.toy @ %(topdir)s/t/toy.py)
|   |   |-- EB_toy_eula (easybuild.easyblocks.toy_eula @ %(topdir)s/t/toy_eula.py)
|   |   |-- EB_toytoy (easybuild.easyblocks.toytoy @ %(topdir)s/t/toytoy.py)
|   |-- Toy_Extension (easybuild.easyblocks.generic.toy_extension @ %(topdir)s/generic/toy_extension.py)
|-- ModuleRC (easybuild.easyblocks.generic.modulerc @ %(topdir)s/generic/modulerc.py)
|-- PythonBundle (easybuild.easyblocks.generic.pythonbundle @ %(topdir)s/generic/pythonbundle.py)
|-- Toolchain (easybuild.easyblocks.generic.toolchain @ %(topdir)s/generic/toolchain.py)
Extension (easybuild.framework.extension)
|-- ExtensionEasyBlock (easybuild.framework.extensioneasyblock )
|   |-- DummyExtension (easybuild.easyblocks.generic.dummyextension @ %(topdir)s/generic/dummyextension.py)
|   |-- EB_toy (easybuild.easyblocks.toy @ %(topdir)s/t/toy.py)
|   |   |-- EB_toy_eula (easybuild.easyblocks.toy_eula @ %(topdir)s/t/toy_eula.py)
|   |   |-- EB_toytoy (easybuild.easyblocks.toytoy @ %(topdir)s/t/toytoy.py)
|   |-- Toy_Extension (easybuild.easyblocks.generic.toy_extension @ %(topdir)s/generic/toy_extension.py)"""

LIST_EASYBLOCKS_SIMPLE_RST = """* **EasyBlock**

  * bar
  * ConfigureMake

    * MakeCp

  * EB_EasyBuildMeta
  * EB_FFTW
  * EB_foo

    * EB_foofoo

  * EB_GCC
  * EB_HPL
  * EB_libtoy
  * EB_OpenBLAS
  * EB_OpenMPI
  * EB_ScaLAPACK
  * EB_toy_buggy
  * ExtensionEasyBlock

    * DummyExtension
    * EB_toy

      * EB_toy_eula
      * EB_toytoy

    * Toy_Extension

  * ModuleRC
  * PythonBundle
  * Toolchain

* **Extension**

  * ExtensionEasyBlock

    * DummyExtension
    * EB_toy

      * EB_toy_eula
      * EB_toytoy

    * Toy_Extension

"""

LIST_EASYBLOCKS_DETAILED_RST = """* **EasyBlock** (easybuild.framework.easyblock)

  * bar (easybuild.easyblocks.generic.bar @ %(topdir)s/generic/bar.py)
  * ConfigureMake (easybuild.easyblocks.generic.configuremake @ %(topdir)s/generic/configuremake.py)

    * MakeCp (easybuild.easyblocks.generic.makecp @ %(topdir)s/generic/makecp.py)

  * EB_EasyBuildMeta (easybuild.easyblocks.easybuildmeta @ %(topdir)s/e/easybuildmeta.py)
  * EB_FFTW (easybuild.easyblocks.fftw @ %(topdir)s/f/fftw.py)
  * EB_foo (easybuild.easyblocks.foo @ %(topdir)s/f/foo.py)

    * EB_foofoo (easybuild.easyblocks.foofoo @ %(topdir)s/f/foofoo.py)

  * EB_GCC (easybuild.easyblocks.gcc @ %(topdir)s/g/gcc.py)
  * EB_HPL (easybuild.easyblocks.hpl @ %(topdir)s/h/hpl.py)
  * EB_libtoy (easybuild.easyblocks.libtoy @ %(topdir)s/l/libtoy.py)
  * EB_OpenBLAS (easybuild.easyblocks.openblas @ %(topdir)s/o/openblas.py)
  * EB_OpenMPI (easybuild.easyblocks.openmpi @ %(topdir)s/o/openmpi.py)
  * EB_ScaLAPACK (easybuild.easyblocks.scalapack @ %(topdir)s/s/scalapack.py)
  * EB_toy_buggy (easybuild.easyblocks.toy_buggy @ %(topdir)s/t/toy_buggy.py)
  * ExtensionEasyBlock (easybuild.framework.extensioneasyblock )

    * DummyExtension (easybuild.easyblocks.generic.dummyextension @ %(topdir)s/generic/dummyextension.py)
    * EB_toy (easybuild.easyblocks.toy @ %(topdir)s/t/toy.py)

      * EB_toy_eula (easybuild.easyblocks.toy_eula @ %(topdir)s/t/toy_eula.py)
      * EB_toytoy (easybuild.easyblocks.toytoy @ %(topdir)s/t/toytoy.py)

    * Toy_Extension (easybuild.easyblocks.generic.toy_extension @ %(topdir)s/generic/toy_extension.py)

  * ModuleRC (easybuild.easyblocks.generic.modulerc @ %(topdir)s/generic/modulerc.py)
  * PythonBundle (easybuild.easyblocks.generic.pythonbundle @ %(topdir)s/generic/pythonbundle.py)
  * Toolchain (easybuild.easyblocks.generic.toolchain @ %(topdir)s/generic/toolchain.py)

* **Extension** (easybuild.framework.extension)

  * ExtensionEasyBlock (easybuild.framework.extensioneasyblock )

    * DummyExtension (easybuild.easyblocks.generic.dummyextension @ %(topdir)s/generic/dummyextension.py)
    * EB_toy (easybuild.easyblocks.toy @ %(topdir)s/t/toy.py)

      * EB_toy_eula (easybuild.easyblocks.toy_eula @ %(topdir)s/t/toy_eula.py)
      * EB_toytoy (easybuild.easyblocks.toytoy @ %(topdir)s/t/toytoy.py)

    * Toy_Extension (easybuild.easyblocks.generic.toy_extension @ %(topdir)s/generic/toy_extension.py)

"""

LIST_EASYBLOCKS_SIMPLE_MD = """- **EasyBlock**
  - bar
  - ConfigureMake
    - MakeCp
  - EB_EasyBuildMeta
  - EB_FFTW
  - EB_foo
    - EB_foofoo
  - EB_GCC
  - EB_HPL
  - EB_libtoy
  - EB_OpenBLAS
  - EB_OpenMPI
  - EB_ScaLAPACK
  - EB_toy_buggy
  - ExtensionEasyBlock
    - DummyExtension
    - EB_toy
      - EB_toy_eula
      - EB_toytoy
    - Toy_Extension
  - ModuleRC
  - PythonBundle
  - Toolchain
- **Extension**
  - ExtensionEasyBlock
    - DummyExtension
    - EB_toy
      - EB_toy_eula
      - EB_toytoy
    - Toy_Extension"""

LIST_EASYBLOCKS_DETAILED_MD = """- **EasyBlock** (easybuild.framework.easyblock)
  - bar (easybuild.easyblocks.generic.bar @ %(topdir)s/generic/bar.py)
  - ConfigureMake (easybuild.easyblocks.generic.configuremake @ %(topdir)s/generic/configuremake.py)
    - MakeCp (easybuild.easyblocks.generic.makecp @ %(topdir)s/generic/makecp.py)
  - EB_EasyBuildMeta (easybuild.easyblocks.easybuildmeta @ %(topdir)s/e/easybuildmeta.py)
  - EB_FFTW (easybuild.easyblocks.fftw @ %(topdir)s/f/fftw.py)
  - EB_foo (easybuild.easyblocks.foo @ %(topdir)s/f/foo.py)
    - EB_foofoo (easybuild.easyblocks.foofoo @ %(topdir)s/f/foofoo.py)
  - EB_GCC (easybuild.easyblocks.gcc @ %(topdir)s/g/gcc.py)
  - EB_HPL (easybuild.easyblocks.hpl @ %(topdir)s/h/hpl.py)
  - EB_libtoy (easybuild.easyblocks.libtoy @ %(topdir)s/l/libtoy.py)
  - EB_OpenBLAS (easybuild.easyblocks.openblas @ %(topdir)s/o/openblas.py)
  - EB_OpenMPI (easybuild.easyblocks.openmpi @ %(topdir)s/o/openmpi.py)
  - EB_ScaLAPACK (easybuild.easyblocks.scalapack @ %(topdir)s/s/scalapack.py)
  - EB_toy_buggy (easybuild.easyblocks.toy_buggy @ %(topdir)s/t/toy_buggy.py)
  - ExtensionEasyBlock (easybuild.framework.extensioneasyblock )
    - DummyExtension (easybuild.easyblocks.generic.dummyextension @ %(topdir)s/generic/dummyextension.py)
    - EB_toy (easybuild.easyblocks.toy @ %(topdir)s/t/toy.py)
      - EB_toy_eula (easybuild.easyblocks.toy_eula @ %(topdir)s/t/toy_eula.py)
      - EB_toytoy (easybuild.easyblocks.toytoy @ %(topdir)s/t/toytoy.py)
    - Toy_Extension (easybuild.easyblocks.generic.toy_extension @ %(topdir)s/generic/toy_extension.py)
  - ModuleRC (easybuild.easyblocks.generic.modulerc @ %(topdir)s/generic/modulerc.py)
  - PythonBundle (easybuild.easyblocks.generic.pythonbundle @ %(topdir)s/generic/pythonbundle.py)
  - Toolchain (easybuild.easyblocks.generic.toolchain @ %(topdir)s/generic/toolchain.py)
- **Extension** (easybuild.framework.extension)
  - ExtensionEasyBlock (easybuild.framework.extensioneasyblock )
    - DummyExtension (easybuild.easyblocks.generic.dummyextension @ %(topdir)s/generic/dummyextension.py)
    - EB_toy (easybuild.easyblocks.toy @ %(topdir)s/t/toy.py)
      - EB_toy_eula (easybuild.easyblocks.toy_eula @ %(topdir)s/t/toy_eula.py)
      - EB_toytoy (easybuild.easyblocks.toytoy @ %(topdir)s/t/toytoy.py)
    - Toy_Extension (easybuild.easyblocks.generic.toy_extension @ %(topdir)s/generic/toy_extension.py)"""

LIST_SOFTWARE_SIMPLE_TXT = """
* GCC
* gzip"""

GCC_DESCR = "The GNU Compiler Collection includes front ends for C, C++, Objective-C, Fortran, Java, and Ada, "
GCC_DESCR += "as well as libraries for these languages (libstdc++, libgcj,...)."
GZIP_DESCR = "gzip (GNU zip) is a popular data compression program as a replacement for compress"

LIST_SOFTWARE_DETAILED_TXT = """
* GCC

%(gcc_descr)s

homepage: http://gcc.gnu.org/

  * GCC v4.6.3: system

* gzip

%(gzip_descr)s

homepage: http://www.gzip.org/

  * gzip v1.4: GCC/4.6.3, system
  * gzip v1.5: foss/2018a, intel/2018a
""" % {'gcc_descr': GCC_DESCR, 'gzip_descr': GZIP_DESCR}

LIST_SOFTWARE_SIMPLE_RST = """List of supported software
==========================

EasyBuild |version| supports 2 different software packages (incl. toolchains, bundles):

:ref:`list_software_letter_g`


.. _list_software_letter_g:

*G*
---

* GCC
* gzip"""

LIST_SOFTWARE_DETAILED_RST = """List of supported software
==========================

EasyBuild |version| supports 2 different software packages (incl. toolchains, bundles):

:ref:`list_software_letter_g`


.. _list_software_letter_g:

*G*
---


:ref:`list_software_GCC_205` - :ref:`list_software_gzip_442`


.. _list_software_GCC_205:

*GCC*
+++++

%(gcc_descr)s

*homepage*: http://gcc.gnu.org/

=========    ==========
version      toolchain
=========    ==========
``4.6.3``    ``system``
=========    ==========


.. _list_software_gzip_442:

*gzip*
++++++

%(gzip_descr)s

*homepage*: http://www.gzip.org/

=======    ===============================
version    toolchain
=======    ===============================
``1.4``    ``GCC/4.6.3``, ``system``
``1.5``    ``foss/2018a``, ``intel/2018a``
=======    ===============================
""" % {'gcc_descr': GCC_DESCR, 'gzip_descr': GZIP_DESCR}

LIST_SOFTWARE_SIMPLE_MD = """# List of supported software

EasyBuild supports 2 different software packages (incl. toolchains, bundles):

[g](#g)


## G

* GCC
* gzip"""

LIST_SOFTWARE_DETAILED_MD = """# List of supported software

EasyBuild supports 2 different software packages (incl. toolchains, bundles):

[g](#g)


## G


[GCC](#gcc) - [gzip](#gzip)


### GCC

%(gcc_descr)s

*homepage*: <http://gcc.gnu.org/>

version  |toolchain
---------|----------
``4.6.3``|``system``

### gzip

%(gzip_descr)s

*homepage*: <http://www.gzip.org/>

version|toolchain
-------|-------------------------------
``1.4``|``GCC/4.6.3``, ``system``
``1.5``|``foss/2018a``, ``intel/2018a``""" % {'gcc_descr': GCC_DESCR, 'gzip_descr': GZIP_DESCR}

LIST_SOFTWARE_SIMPLE_MD = """# List of supported software

EasyBuild supports 2 different software packages (incl. toolchains, bundles):

[g](#g)


## G

* GCC
* gzip"""

LIST_SOFTWARE_DETAILED_MD = """# List of supported software

EasyBuild supports 2 different software packages (incl. toolchains, bundles):

[g](#g)


## G


[GCC](#gcc) - [gzip](#gzip)


### GCC

%(gcc_descr)s

*homepage*: <http://gcc.gnu.org/>

version  |toolchain
---------|----------
``4.6.3``|``system``

### gzip

%(gzip_descr)s

*homepage*: <http://www.gzip.org/>

version|toolchain
-------|-------------------------------
``1.4``|``GCC/4.6.3``, ``system``
``1.5``|``foss/2018a``, ``intel/2018a``""" % {'gcc_descr': GCC_DESCR, 'gzip_descr': GZIP_DESCR}

LIST_SOFTWARE_SIMPLE_JSON = """[
{
    "name": "GCC"
},
{
    "name": "gzip"
}
]"""

LIST_SOFTWARE_DETAILED_JSON = """[
{
    "description": "%(gcc_descr)s",
    "homepage": "http://gcc.gnu.org/",
    "name": "GCC",
    "toolchain": "system",
    "version": "4.6.3",
    "versionsuffix": ""
},
{
    "description": "%(gzip_descr)s",
    "homepage": "http://www.gzip.org/",
    "name": "gzip",
    "toolchain": "GCC/4.6.3",
    "version": "1.4",
    "versionsuffix": ""
},
{
    "description": "%(gzip_descr)s",
    "homepage": "http://www.gzip.org/",
    "name": "gzip",
    "toolchain": "system",
    "version": "1.4",
    "versionsuffix": ""
},
{
    "description": "%(gzip_descr)s",
    "homepage": "http://www.gzip.org/",
    "name": "gzip",
    "toolchain": "foss/2018a",
    "version": "1.5",
    "versionsuffix": ""
},
{
    "description": "%(gzip_descr)s",
    "homepage": "http://www.gzip.org/",
    "name": "gzip",
    "toolchain": "intel/2018a",
    "version": "1.5",
    "versionsuffix": ""
}
]""" % {'gcc_descr': GCC_DESCR, 'gzip_descr': GZIP_DESCR}


class DocsTest(EnhancedTestCase):

    def test_get_easyblock_classes(self):
        """
        Test for get_easyblock_classes function.
        """
        # result should correspond with test easyblocks in test/framework/sandbox/easybuild/easyblocks/generic
        eb_classes = get_easyblock_classes('easybuild.easyblocks.generic')
        eb_names = [x.__name__ for x in eb_classes]
        expected = ['ConfigureMake', 'DummyExtension', 'MakeCp', 'ModuleRC',
                    'PythonBundle', 'Toolchain', 'Toy_Extension', 'bar']
        self.assertEqual(sorted(eb_names), expected)

    def test_gen_easyblocks_overview(self):
        """ Test gen_easyblocks_overview_* functions """
        gen_easyblocks_pkg = 'easybuild.easyblocks.generic'
        modules = import_available_modules(gen_easyblocks_pkg)
        common_params = {
            'ConfigureMake': ['configopts', 'buildopts', 'installopts'],
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
            '``test_123``            Test 1, 2, 3    ``""``',
            "``test_bool``           Just a test     ``False``",
            "``test_none``           Another test    ``None``",
            "====================    ============    =============",
            '',
            "Commonly used easyconfig parameters with ``ConfigureMake`` easyblock",
            "--------------------------------------------------------------------",
            '',
            "====================    ================================================================",
            "easyconfig parameter    description",
            "====================    ================================================================",
            "configopts              Extra options passed to configure (default already has --prefix)",
            "buildopts               Extra options passed to make step (default already has -j X)",
            "installopts             Extra options for installation",
            "====================    ================================================================",
        ])

        self.assertIn(check_configuremake, ebdoc)
        names = []

        for mod in modules:
            for name, _ in inspect.getmembers(mod, inspect.isclass):
                eb_class = getattr(mod, name)
                # skip imported classes that are not easyblocks
                if eb_class.__module__.startswith(gen_easyblocks_pkg):
                    self.assertIn(name, ebdoc)
                    names.append(name)

        toc = [":ref:`" + n + "`" for n in sorted(set(names))]
        pattern = " - ".join(toc)

        regex = re.compile(pattern)
        self.assertTrue(re.search(regex, ebdoc), "Pattern %s found in %s" % (regex.pattern, ebdoc))

        # MarkDown format
        eb_overview = gen_easyblocks_overview_md(gen_easyblocks_pkg, 'easyconfigs', common_params, doc_functions)
        ebdoc = '\n'.join(eb_overview)

        # extensive check for ConfigureMake easyblock
        check_configuremake = '\n'.join([
            "## ``ConfigureMake``",
            '',
            "(derives from ``EasyBlock``)",
            '',
            "Dummy support for building and installing applications with configure/make/make install.",
            '',
            "### Extra easyconfig parameters specific to ``ConfigureMake`` easyblock",
            '',
            "easyconfig parameter|description |default value",
            "--------------------|------------|-------------",
            '``test_123``        |Test 1, 2, 3|``""``',
            "``test_bool``       |Just a test |``False``",
            "``test_none``       |Another test|``None``",
            '',
            "### Commonly used easyconfig parameters with ``ConfigureMake`` easyblock",
            '',
            "easyconfig parameter|description",
            "--------------------|----------------------------------------------------------------",
            "configopts          |Extra options passed to configure (default already has --prefix)",
            "buildopts           |Extra options passed to make step (default already has -j X)",
            "installopts         |Extra options for installation",
        ])

        self.assertIn(check_configuremake, ebdoc)
        names = []

        for mod in modules:
            for name, _ in inspect.getmembers(mod, inspect.isclass):
                eb_class = getattr(mod, name)
                # skip imported classes that are not easyblocks
                if eb_class.__module__.startswith(gen_easyblocks_pkg):
                    self.assertIn(name, ebdoc)
                    names.append(name)

        toc = ["\\[" + n + "\\]\\(#" + n.lower() + "\\)" for n in sorted(set(names))]
        pattern = " - ".join(toc)
        regex = re.compile(pattern)
        self.assertTrue(re.search(regex, ebdoc), "Pattern %s found in %s" % (regex.pattern, ebdoc))

    def test_license_docs(self):
        """Test license_documentation function."""
        lic_docs = avail_easyconfig_licenses(output_format='txt')
        gplv3 = "GPLv3: The GNU General Public License"
        self.assertIn(gplv3, lic_docs)

        lic_docs = avail_easyconfig_licenses(output_format='rst')
        regex = re.compile(r"^``GPLv3``\s*The GNU General Public License", re.M)
        self.assertTrue(regex.search(lic_docs), "%s found in: %s" % (regex.pattern, lic_docs))

        lic_docs = avail_easyconfig_licenses(output_format='md')
        regex = re.compile(r"^``GPLv3``\s*|The GNU General Public License", re.M)
        self.assertTrue(regex.search(lic_docs), "%s found in: %s" % (regex.pattern, lic_docs))

        # expect NotImplementedError for JSON output
        self.assertRaises(NotImplementedError, avail_easyconfig_licenses, output_format='json')

    def test_list_easyblocks(self):
        """
        Tests for list_easyblocks function
        """
        topdir = os.path.dirname(os.path.abspath(__file__))
        topdir_easyblocks = os.path.join(topdir, 'sandbox', 'easybuild', 'easyblocks')

        txt = list_easyblocks()
        self.assertEqual(txt, LIST_EASYBLOCKS_SIMPLE_TXT)

        txt = list_easyblocks(list_easyblocks='simple', output_format='txt')
        self.assertEqual(txt, LIST_EASYBLOCKS_SIMPLE_TXT)

        txt = list_easyblocks(list_easyblocks='detailed', output_format='txt')
        self.assertEqual(txt, LIST_EASYBLOCKS_DETAILED_TXT % {'topdir': topdir_easyblocks})

        txt = list_easyblocks(list_easyblocks='simple', output_format='rst')
        self.assertEqual(txt, LIST_EASYBLOCKS_SIMPLE_RST)

        txt = list_easyblocks(list_easyblocks='detailed', output_format='rst')
        self.assertEqual(txt, LIST_EASYBLOCKS_DETAILED_RST % {'topdir': topdir_easyblocks})

        txt = list_easyblocks(list_easyblocks='simple', output_format='md')
        self.assertEqual(txt, LIST_EASYBLOCKS_SIMPLE_MD)

        txt = list_easyblocks(list_easyblocks='detailed', output_format='md')
        self.assertEqual(txt, LIST_EASYBLOCKS_DETAILED_MD % {'topdir': topdir_easyblocks})

        # expect NotImplementedError for JSON output
        self.assertRaises(NotImplementedError, list_easyblocks, output_format='json')

    def test_list_software(self):
        """Test list_software* functions."""
        build_options = {
            'robot_path': [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'v1.0')],
            'silent': True,
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)

        self.assertEqual(list_software(output_format='txt'), LIST_SOFTWARE_SIMPLE_TXT)
        self.assertEqual(list_software(output_format='txt', detailed=True), LIST_SOFTWARE_DETAILED_TXT)

        self.assertEqual(list_software(output_format='rst'), LIST_SOFTWARE_SIMPLE_RST)
        self.assertEqual(list_software(output_format='rst', detailed=True), LIST_SOFTWARE_DETAILED_RST)

        self.assertEqual(list_software(output_format='md'), LIST_SOFTWARE_SIMPLE_MD)
        self.assertEqual(list_software(output_format='md', detailed=True), LIST_SOFTWARE_DETAILED_MD)

        self.assertEqual(list_software(output_format='json'), LIST_SOFTWARE_SIMPLE_JSON)
        self.assertEqual(list_software(output_format='json', detailed=True), LIST_SOFTWARE_DETAILED_JSON)

        # GCC/4.6.3 is installed, no gzip module installed
        txt = list_software(output_format='txt', detailed=True, only_installed=True)
        self.assertTrue(re.search(r'^\* GCC', txt, re.M))
        self.assertTrue(re.search(r'^\s*\* GCC v4.6.3: system', txt, re.M))
        self.assertFalse(re.search(r'^\* gzip', txt, re.M))
        self.assertFalse(re.search(r'gzip v1\.', txt, re.M))

        txt = list_software(output_format='rst', detailed=True, only_installed=True)
        self.assertTrue(re.search(r'^\*GCC\*', txt, re.M))
        self.assertTrue(re.search(r'4\.6\.3.*system', txt, re.M))
        self.assertFalse(re.search(r'^\*gzip\*', txt, re.M))
        self.assertFalse(re.search(r'1\.4', txt, re.M))
        self.assertFalse(re.search(r'1\.5', txt, re.M))

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
            "  * toy v0.0: gompi/2018a, system",
            "  * toy v0.0 (versionsuffix: '-deps'): system",
            "  * toy v0.0 (versionsuffix: '-iter'): system",
            "  * toy v0.0 (versionsuffix: '-multiple'): system",
            "  * toy v0.0 (versionsuffix: '-test'): gompi/2018a, system",
        ]
        txt = list_software(output_format='txt', detailed=True)
        lines = txt.split('\n')
        expected_found = any(lines[i:i + len(expected)] == expected for i in range(len(lines)))
        self.assertTrue(expected_found, "%s found in: %s" % (expected, lines))

        expected = [
            '*toy*',
            '+++++',
            '',
            'Toy C program, 100% toy.',
            '',
            '*homepage*: https://easybuilders.github.io/easybuild',
            '',
            '=======    =============    ===========================',
            'version    versionsuffix    toolchain',
            '=======    =============    ===========================',
            '``0.0``                     ``gompi/2018a``, ``system``',
            '``0.0``    ``-deps``        ``system``',
            '``0.0``    ``-iter``        ``system``',
            '``0.0``    ``-multiple``    ``system``',
            '``0.0``    ``-test``        ``gompi/2018a``, ``system``',
            '=======    =============    ===========================',
        ]
        txt = list_software(output_format='rst', detailed=True)
        lines = txt.split('\n')
        expected_found = any(lines[i:i + len(expected)] == expected for i in range(len(lines)))
        self.assertTrue(expected_found, "%s found in: %s" % (expected, lines))

    def test_list_toolchains(self):
        """Test list_toolchains* functions."""

        txt_patterns = [
            r"^List of known toolchains \(toolchain name: module\[, module, ...\]\):",
            r"^\s+GCC: GCC",
            r"^\s+foss: BLACS, FFTW, GCC, OpenBLAS, OpenMPI, ScaLAPACK",
            r"^\s+intel: icc, ifort, imkl, impi",
            r"^\s+system:\s*$",
        ]

        for txt in (list_toolchains(), list_toolchains(output_format='txt')):
            for pattern in txt_patterns:
                regex = re.compile(pattern, re.M)
                self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        md_patterns = [
            r"^# List of known toolchains",
            r"^\*\*GCC\*\*\s+\|GCC\s+\|\*\(none\)\*\s+\|\*\(none\)\*\s+\|\*\(none\)\*$",
            r"^\*\*foss\*\*\s+\|GCC\s+\|OpenMPI\s+\|OpenBLAS, ScaLAPACK\s+\|FFTW$",
            r"^\*\*intel\*\*\s+\|icc, ifort\s+\|impi\s+\|imkl\s+\|imkl",
            r"^\*\*system\*\*\s+\|\*\(none\)\*\s+\|\*\(none\)\*\s+\|\*\(none\)\*\s+\|\*\(none\)\*$",
        ]
        txt_md = list_toolchains(output_format='md')
        for pattern in md_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_md), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_md))

        rst_patterns = [
            r"^List of known toolchains\n\-{24}",
            r"^\*\*GCC\*\*\s+GCC\s+\*\(none\)\*\s+\*\(none\)\*\s+\*\(none\)\*$",
            r"^\*\*foss\*\*\s+GCC\s+OpenMPI\s+OpenBLAS, ScaLAPACK\s+FFTW$",
            r"^\*\*intel\*\*\s+icc, ifort\s+impi\s+imkl\s+imkl",
            r"^\*\*system\*\*\s+\*\(none\)\*\s+\*\(none\)\*\s+\*\(none\)\*\s+\*\(none\)\*$",
        ]
        txt_rst = list_toolchains(output_format='rst')
        for pattern in rst_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_rst), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_rst))

        # expect NotImplementedError for json output format
        with self.assertRaises(NotImplementedError):
            list_toolchains(output_format='json')

    def test_avail_cfgfile_constants(self):
        """
        Test avail_cfgfile_constants to generate overview of constants that can be used in a configuration file.
        """
        option_parser = EasyBuildOptions()
        txt_patterns = [
            r"^Constants available \(only\) in configuration files:",
            r"^syntax: %\(CONSTANT_NAME\)s",
            r"^only in 'DEFAULT' section:",
            r"^\* HOME: Current user's home directory, expanded '~' \[value: %s\]" % os.getenv('HOME'),
            r"^\* USER: Current username, translated uid from password file \[value: %s\]" % os.getenv('USER'),
        ]
        txt = avail_cfgfile_constants(option_parser.go_cfg_constants)
        for pattern in txt_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        txt = avail_cfgfile_constants(option_parser.go_cfg_constants, output_format='txt')
        for pattern in txt_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        md_patterns = [
            r"^# Constants available \(only\) in configuration files",
            r"^## Only in 'DEFAULT' section:",
            r"^``HOME``\s*\|Current user's home directory, expanded '~'\s*\|``%s``$" % os.getenv('HOME'),
            r"^``USER``\s*\|Current username, translated uid from password file\s*\|``%s``" % os.getenv('USER'),
        ]
        txt_md = avail_cfgfile_constants(option_parser.go_cfg_constants, output_format='md')
        for pattern in md_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_md), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_md))

        rst_patterns = [
            r"^Constants available \(only\) in configuration files\n-{49}\n",
            r"^Only in 'DEFAULT' section:\n-{26}",
            r"^``HOME``\s*Current user's home directory, expanded '~'\s*``%s``$" % os.getenv('HOME'),
            r"^``USER``\s*Current username, translated uid from password file\s*``%s``" % os.getenv('USER'),
        ]
        txt_rst = avail_cfgfile_constants(option_parser.go_cfg_constants, output_format='rst')
        for pattern in rst_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_rst), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_rst))

        # expect NotImplementedError for json output format
        with self.assertRaises(NotImplementedError):
            avail_cfgfile_constants(option_parser.go_cfg_constants, output_format='json')

    def test_avail_easyconfig_constants(self):
        """
        Test avail_easyconfig_constants to generate overview of constants that can be used in easyconfig files.
        """
        txt_patterns = [
            r"^Constants that can be used in easyconfigs",
            r"^\s*ARCH: .* \(CPU architecture of current system \(aarch64, x86_64, ppc64le, ...\)\)",
            r"^\s*OS_PKG_OPENSSL_DEV: \('openssl-devel', 'libssl-dev', 'libopenssl-devel'\) "
            r"\(OS packages providing openSSL development support\)",
        ]

        txt = avail_easyconfig_constants()
        for pattern in txt_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        txt = avail_easyconfig_constants(output_format='txt')
        for pattern in txt_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        md_patterns = [
            r"^# Constants that can be used in easyconfigs",
            r"^``ARCH``\s*\|``.*``\s*\|CPU architecture of current system \(aarch64, x86_64, ppc64le, ...\)$",
            r"^``OS_PKG_OPENSSL_DEV``\s*\|``\('openssl-devel', 'libssl-dev', 'libopenssl-devel'\)``\s*\|"
            r"OS packages providing openSSL development support$",
        ]
        txt_md = avail_easyconfig_constants(output_format='md')
        for pattern in md_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_md), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_md))

        rst_patterns = [
            r"^Constants that can be used in easyconfigs\n-{41}",
            r"^``ARCH``\s*``.*``\s*CPU architecture of current system \(aarch64, x86_64, ppc64le, ...\)$",
            r"^``OS_PKG_OPENSSL_DEV``\s*``\('openssl-devel', 'libssl-dev', 'libopenssl-devel'\)``\s*"
            r"OS packages providing openSSL development support$",
        ]
        txt_rst = avail_easyconfig_constants(output_format='rst')
        for pattern in rst_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_rst), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_rst))

        # expect NotImplementedError for json output format
        with self.assertRaises(NotImplementedError):
            avail_easyconfig_constants(output_format='json')

    def test_avail_easyconfig_templates(self):
        """
        Test avail_easyconfig_templates to generate overview of templates that can be used in easyconfig files.
        """
        txt_patterns = [
            r"^Template names/values derived from easyconfig instance",
            r"^\s+%\(version_major\)s: Major version",
            r"^Template names/values for \(short\) software versions",
            r"^\s+%\(pymajver\)s: major version for Python",
            r"^\s+%\(pyshortver\)s: short version for Python \(<major>\.<minor>\)",
            r"^Template constants that can be used in easyconfigs",
            r"^\s+SOURCE_TAR_GZ: Source \.tar\.gz bundle \(%\(name\)s-%\(version\)s.tar.gz\)",
        ]

        txt = avail_easyconfig_templates()
        for pattern in txt_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        txt = avail_easyconfig_templates(output_format='txt')
        for pattern in txt_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        md_patterns = [
            r"^## Template names/values derived from easyconfig instance",
            r"^``%\(version_major\)s``\s+|Major version",
            r"^## Template names/values for \(short\) software versions",
            r"^``%\(pyshortver\)s``\s+|short version for Python \(``<major>\.<minor>``\)",
            r"^## Template constants that can be used in easyconfigs",
            r"^``SOURCE_TAR_GZ``\s+|Source \.tar\.gz bundle \(%\(name\)s-%\(version\)s.tar.gz\)",
        ]
        txt_md = avail_easyconfig_templates(output_format='md')
        for pattern in md_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_md), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_md))

        rst_patterns = [
            r"^Template names/values derived from easyconfig instance\n\-+",
            r"^``%\(version_major\)s``\s+|Major version",
            r"^Template names/values for \(short\) software versions\n-+",
            r"^``%\(pyshortver\)s``\s+|short version for Python \(<major>\.<minor>\)",
            r"^Template constants that can be used in easyconfigs\n\-+",
            r"^``SOURCE_TAR_GZ``\s+|Source \.tar\.gz bundle \(%\(name\)s-%\(version\)s.tar.gz\)",
        ]
        txt_rst = avail_easyconfig_templates(output_format='rst')
        for pattern in rst_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_rst), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_rst))

        # expect NotImplementedError for json output format
        with self.assertRaises(NotImplementedError):
            avail_easyconfig_templates(output_format='json')

    def test_avail_toolchain_opts(self):
        """
        Test avail_toolchain_opts to generate overview of supported toolchain options.
        """
        txt_patterns_foss = [
            r"^Available options for foss toolchain:",
            r"^\s+extra_cxxflags: Specify extra CXXFLAGS options. \(default: None\)",
            r"^\s+optarch: Enable architecture optimizations \(default: True\)",
            r"^\s+precise: High precision \(default: False\)",
        ]
        oneapi_txt = r"^\s+oneapi: Use oneAPI compilers icx/icpx/ifx instead of classic compilers \(default: None\)"

        for txt in (avail_toolchain_opts('foss'), avail_toolchain_opts('foss', output_format='txt')):
            for pattern in txt_patterns_foss:
                regex = re.compile(pattern, re.M)
                self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

            regex = re.compile(oneapi_txt, re.M)
            self.assertFalse(regex.search(txt), "Pattern '%s' should not be found in: %s" % (regex.pattern, txt))

        txt_patterns_intel = [
            r"^Available options for intel toolchain:",
            oneapi_txt,
        ] + txt_patterns_foss[1:]

        for txt in (avail_toolchain_opts('intel'), avail_toolchain_opts('intel', output_format='txt')):
            for pattern in txt_patterns_intel:
                regex = re.compile(pattern, re.M)
                self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        # MarkDown output format
        md_patterns_foss = [
            r"^## Available options for foss toolchain",
            r"^``extra_cxxflags``\s+\|Specify extra CXXFLAGS options.\s+\|``None``",
            r"^``optarch``\s+\|Enable architecture optimizations\s+\|``True``",
            r"^``precise``\s+\|High precision\s+\|``False``",
        ]

        txt_md = avail_toolchain_opts('foss', output_format='md')
        for pattern in md_patterns_foss:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_md), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_md))

        oneapi_md = r"^``oneapi``\s+\|Use oneAPI compilers icx/icpx/ifx instead of classic compilers\s+\|``None``"
        regex = re.compile(oneapi_md, re.M)
        self.assertFalse(regex.search(txt_md), "Pattern '%s' should not be found in: %s" % (regex.pattern, txt_md))

        md_patterns_intel = [
            r"^## Available options for intel toolchain",
            oneapi_md,
        ] + md_patterns_foss[1:]

        txt_md = avail_toolchain_opts('intel', output_format='md')
        for pattern in md_patterns_intel:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_md), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_md))

        # rst output format
        rst_patterns_foss = [
            r"^Available options for foss toolchain\n-{36}",
            r"^``extra_cxxflags``\s+Specify extra CXXFLAGS options.\s+``None``",
            r"^``optarch``\s+Enable architecture optimizations\s+``True``",
            r"^``precise``\s+High precision\s+``False``",
        ]

        txt_rst = avail_toolchain_opts('foss', output_format='rst')
        for pattern in rst_patterns_foss:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_rst), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_rst))

        oneapi_rst = r"^``oneapi``\s+Use oneAPI compilers icx/icpx/ifx instead of classic compilers\s+``None``"
        regex = re.compile(oneapi_rst, re.M)
        self.assertFalse(regex.search(txt_rst), "Pattern '%s' should not be found in: %s" % (regex.pattern, txt_rst))

        rst_patterns_intel = [
            r"^Available options for intel toolchain\n-{37}",
            oneapi_rst,
        ] + rst_patterns_foss[1:]

        txt_rst = avail_toolchain_opts('intel', output_format='rst')
        for pattern in rst_patterns_intel:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_rst), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_rst))

        # expect NotImplementedError for json output format
        with self.assertRaises(NotImplementedError):
            avail_toolchain_opts('foss', output_format='json')
        with self.assertRaises(NotImplementedError):
            avail_toolchain_opts('intel', output_format='json')

    def test_mk_table(self):
        """
        Tests for mk_*_table functions.
        """
        titles = ('one', 'two', 'three')
        table = [
            ('1', '11111'),
            ('2222222', '2'),
            ('3', '3'),
        ]
        expected_md = [
            'one  |two    |three',
            '-----|-------|-----',
            '1    |2222222|3',
            '11111|2      |3',
        ]
        expected_rst = [
            '=====    =======    =====',
            'one      two        three',
            '=====    =======    =====',
            '1        2222222    3',
            '11111    2          3',
            '=====    =======    =====',
            '',
        ]

        res = mk_md_table(titles, table)
        self.assertEqual(res, expected_md)

        res = mk_rst_table(titles, table)
        self.assertEqual(res, expected_rst)

        self.assertErrorRegex(ValueError, "Number of titles/columns should be equal", mk_md_table, titles, [])
        self.assertErrorRegex(ValueError, "Number of titles/columns should be equal", mk_rst_table, titles, [])

    def test_title_and_table(self):
        """
        Tests for *_title_and_table functions.
        """
        titles = ('one', 'two', '3 is a wide column')
        table = [
            titles,
            ('val 11', 'val 21'),
            ('val 12', 'val 22'),
            ('val 13', 'val 23'),
        ]
        expected_md = [
            '## test title',
            '',
            'one   |two   |3 is a wide column',
            '------|------|------------------',
            'val 11|val 12|val 13',
            'val 21|val 22|val 23',
        ]
        expected_rst = [
            'test title',
            '----------',
            '',
            '======    ======    ==================',
            'one       two       3 is a wide column',
            '======    ======    ==================',
            'val 11    val 12    val 13',
            'val 21    val 22    val 23',
            '======    ======    ==================',
            '',
        ]
        res = md_title_and_table('test title', table[0], table[1:], title_level=2)
        self.assertEqual(res, expected_md)

        res = rst_title_and_table('test title', table[0], table[1:])
        self.assertEqual(res, expected_rst)

        error_pattern = "Number of titles/columns should be equal"
        self.assertErrorRegex(ValueError, error_pattern, md_title_and_table, '', titles, [])
        self.assertErrorRegex(ValueError, error_pattern, rst_title_and_table, '', titles, [('val 11', 'val 12')])

    def test_help(self):
        """
        Test output produced by --help, with various output formats
        """
        def get_eb_help_output(arg=''):
            self.mock_stderr(True)
            self.mock_stdout(True)
            self.eb_main(['--help', arg])
            stderr = self.get_stderr()
            stdout = self.get_stdout()
            self.mock_stderr(False)
            self.mock_stdout(False)

            self.assertFalse(stderr)
            return stdout

        txt_patterns = [
            r"^Usage: eb \[options\] easyconfig \[...\]",
            r"^Options:\n\s+--version",
            r"^\s+Basic options:\n\s+Basic runtime options for EasyBuild",
            r"^\s+-f, --force\s+Force to rebuild software",
            r"^\s+--module-only\s+Only generate module file\(s\)",
            r"^\s+Software search and build options:",
            r"^\s+--try-toolchain=NAME,VERSION",
            r"^Boolean options support disable prefix",
            r"^All long option names can be passed as environment variables",
        ]
        txt = get_eb_help_output()
        for pattern in txt_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        short_patterns = [
            r"^Usage: eb \[options\] easyconfig \[...\]",
            r"^Options:\n\s+-h",
            r"^\s+Basic options:\n\s+Basic runtime options for EasyBuild",
            r"^\s+-f\s+Force to rebuild software",
            r"^\s+Override options:\n\s+Override default EasyBuild behavior",
            r"^\s+-e CLASS\s+easyblock to use",
            r"^Boolean options support disable prefix",
            r"^All long option names can be passed as environment variables",
        ]
        txt_short = get_eb_help_output('short')
        for pattern in short_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_short), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_short))

        config_patterns = [
            r"^\[MAIN\]\n# Enable debug log mode \(default: False\)\n#debug=",
            r"^\[override\](\n.*)+#filter-deps=",
        ]
        txt_cfg = get_eb_help_output('config')
        for pattern in config_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_cfg), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_cfg))

        md_patterns = [
            r"^## Usage\n\n``eb \[options\] easyconfig \[...\]``",
            r"^## Basic options",
            r"^``-f, --force``\s+\|Force to rebuild software",
            r"^## Override options",
            r"^``-e CLASS, --easyblock=CLASS``\s+\|easyblock to use",
        ]
        txt_md = get_eb_help_output('md')
        for pattern in md_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_md), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_md))

        rst_patterns = [
            r"^Usage\n-{5}\n\n``eb \[options\] easyconfig \[...\]``",
            r"^Basic options\n-{13}",
            r"^``-f, --force``\s+Force to rebuild software",
            r"^Override options\n-{16}",
            r"^``-e CLASS, --easyblock=CLASS``\s+easyblock to use",
        ]
        txt_rst = get_eb_help_output('rst')
        for pattern in rst_patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(txt_rst), "Pattern '%s' should be found in: %s" % (regex.pattern, txt_rst))


def suite():
    """ returns all test cases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(DocsTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
