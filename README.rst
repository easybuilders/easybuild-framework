.. image:: http://hpcugent.github.io/easybuild/images/easybuild_logo_small.png
   :align: center

`EasyBuild <https://hpcugent.github.io/easybuild>`_ is a software build
and installation framework that allows you to manage (scientific) software
on High Performance Computing (HPC) systems in an efficient way.

The **easybuild-framework** package is the core of EasyBuild. It
supports the implementation and use of so-called easyblocks which
implement the software install procedure for a particular (group of) software
package(s).

The EasyBuild documentation is available at http://easybuild.readthedocs.org/.

The EasyBuild framework source code is hosted on GitHub, along
with an issue tracker for bug reports and feature requests, see
http://github.com/hpcugent/easybuild-framework.

Related Python packages:

* **easybuild-easyblocks**

  * a collection of easyblocks that implement support for building and installing (groups of) software packages
  * GitHub repository: http://github.com/hpcugent/easybuild-easyblocks
  * package on PyPi: https://pypi.python.org/pypi/easybuild-easyblocks

* **easybuild-easyconfigs**

  * a collection of example easyconfig files that specify which software to build,
    and using which build options; these easyconfigs will be well tested
    with the latest compatible versions of the easybuild-framework and easybuild-easyblocks packages
  * GitHub repository: http://github.com/hpcugent/easybuild-easyconfigs
  * PyPi: https://pypi.python.org/pypi/easybuild-easyconfigs

The code in the ``vsc`` directory originally comes from the *vsc-base* package
(https://github.com/hpcugent/vsc-base).


*Build status overview:*

* **master** branch:

  .. image:: https://travis-ci.org/hpcugent/easybuild-framework.svg?branch=master
      :target: https://travis-ci.org/hpcugent/easybuild-framework/branches

* **develop** branch:

  .. image:: https://travis-ci.org/hpcugent/easybuild-framework.svg?branch=develop
      :target: https://travis-ci.org/hpcugent/easybuild-framework/branches
