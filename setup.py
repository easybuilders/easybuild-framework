# #
# Copyright 2012-2013 Ghent University
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
This script can be used to install easybuild-framework, e.g. using:
  easy_install --user .
or
  python setup.py --prefix=$HOME/easybuild

@author: Kenneth Hoste (Ghent University)
"""

import os
from distutils import log

from easybuild.tools.version import VERSION

API_VERSION = str(VERSION).split('.')[0]

# Utility function to read README file
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

# log levels: 0 = WARN (default), 1 = INFO, 2 = DEBUG
log.set_verbosity(1)

try:
    from setuptools import setup
    log.info("Installing with setuptools.setup...")
except ImportError, err:
    log.info("Failed to import setuptools.setup, so falling back to distutils.setup")
    from distutils.core import setup

log.info("Installing version %s (API version %s)" % (VERSION, API_VERSION))

def find_rel_test():
    """Return list of files recursively from basedir (aka find -type f)"""
    basedir = os.path.join(os.path.dirname(__file__), "test", "framework")
    current = os.getcwd()
    os.chdir(basedir)
    res = []
    for subdir in ["sandbox", "easyconfigs", "modules"]:
        res.extend([os.path.join(root, filename)
                    for root, dirnames, filenames in os.walk(subdir)
                    for filename in filenames if os.path.isfile(os.path.join(root, filename))])
    os.chdir(current)
    return res

easybuild_packages = [
    "easybuild", "easybuild.framework", "easybuild.framework.easyconfig", "easybuild.framework.easyconfig.format",
    "easybuild.toolchains", "easybuild.toolchains.compiler", "easybuild.toolchains.mpi",
    "easybuild.toolchains.fft", "easybuild.toolchains.linalg", "easybuild.tools",
    "easybuild.tools.toolchain", "easybuild.tools.module_naming_scheme",
    "test.framework", "test",
    "vsc", "vsc.utils",
]

setup(
    name = "easybuild-framework",
    version = str(VERSION),
    author = "EasyBuild community",
    author_email = "easybuild@lists.ugent.be",
    description = """EasyBuild is a software installation framework in Python that allows you to \
install software in a structured and robust way.
This package contains the EasyBuild framework, which supports the creation of custom easyblocks that \
implement support for installing particular (groups of) software packages.""",
    license = "GPLv2",
    keywords = "software build building installation installing compilation HPC scientific",
    url = "http://hpcugent.github.com/easybuild",
    packages = easybuild_packages,
    package_dir = {'test.framework': "test/framework"},
    package_data = {"test.framework": find_rel_test()},
    scripts = ["eb"],
    data_files = [
        ('easybuild', ["easybuild/easybuild_config.py"]),
    ],
    long_description = """This package contains the EasyBuild
framework, which supports the creation of custom easyblocks that
implement support for installing particular (groups of) software
packages.

""" + read("README.rst"),
    classifiers = [
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 2.4",
        "Topic :: Software Development :: Build Tools",
    ],
    platforms = "Linux",
    provides = ["eb"] + easybuild_packages,
    test_suite = "test.framework.suite",
    zip_safe = False,
)
