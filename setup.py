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
    from distutils import setup

log.info("Installing version %s (API version %s)" % (VERSION, API_VERSION))

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
    packages = ["easybuild", "easybuild.framework", "easybuild.tools", "easybuild.test"],
    package_dir = {'easybuild.test': "easybuild/test"},
    package_data = {"easybuild.test": ["easyconfigs/*eb"]},
    scripts = ["eb"],
    data_files = [
                  ('easybuild', ["easybuild/easybuild_config.py"]),
    ],
    long_description = read("README.rst"),
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
    provides = ["eb", "easybuild.framework", "easybuild.tools", "easybuild.test"],
    test_suite = "easybuild.test.suite",
)
