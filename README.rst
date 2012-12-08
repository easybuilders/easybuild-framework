EasyBuild: building software with ease
--------------------------------------

The easybuild-framework package is the basis for EasyBuild
(http://hpcugent.github.com/easybuild), a software build and
installation framework written in Python that allows you to install
software in a structured, repeatable and robust way.

This package contains the EasyBuild framework that supports the
implementation and use of so-called easyblocks, that implement the
software install procedure for a particular (group of) software
package(s).

The code of the easybuild-framework package is hosted on GitHub, along
with an issue tracker for bug reports and feature requests, see
http://github.com/hpcugent/easybuild-framework.

The EasyBuild documentation is available on the GitHub wiki of the
easybuild meta-package, see
http://github.com/hpcugent/easybuild/wiki/Home.

Related packages: 
- easybuild-easyblocks
(http://pypi.python.org/pypi/easybuild-easyblocks): a collection of
easyblocks that implement support for building and installing (groups
of) software packages.
 
- easybuild-easyconfigs
(http://pypi.python.org/pypi/easybuild-easyconfigs): a collection of
example easyconfig files that specify which software to build, and using
which build options; these easyconfigs will be well tested with the
latest compatible versions of the easybuild-framework and
easybuild-easyblocks packages.

The code in the vsc directory originally comes from VSC-tools
(https://github.com/hpcugent/VSC-tools).
