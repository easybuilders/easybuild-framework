##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
# Copyright 2012 Toon Willems
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
EasyBuild support for building and installing GCC, implemented as an easyblock
"""

import re
import os
import shutil
from copy import copy
from distutils.version import LooseVersion

import easybuild.tools.environment as env
from easybuild.framework.application import Application
from easybuild.framework.easyconfig import CUSTOM
from easybuild.tools.filetools import run_cmd
from easybuild.tools.modules import get_software_root
from easybuild.tools.systemtools import get_kernel_name, get_shared_lib_ext, get_platform_name


class EB_GCC(Application):
    """
    Self-contained build of GCC.
    Uses system compiler for initial build, then bootstraps.
    """

    def __init__(self, *args, **kwargs):
        Application.__init__(self, *args, **kwargs)

        self.stagedbuild = False

    @staticmethod
    def extra_options():
        extra_vars = [
                      ('languages', [[], "List of languages to build GCC for (--enable-languages) (default: [])", CUSTOM]),
                      ('withlto', [True, "Enable LTO support (default: True)", CUSTOM]),
                      ('withcloog', [False, "Build GCC with CLooG support (default: False).", CUSTOM]),
                      ('withppl', [False, "Build GCC with PPL support (default: False).", CUSTOM]),
                      ('pplwatchdog', [False, "Enable PPL watchdog (default: False)", CUSTOM]),
                      ('clooguseisl', [False, "Use ISL with CLooG or not (use PPL otherwise) (default: False)", CUSTOM])
                     ]
        return Application.extra_options(extra_vars)

    def create_dir(self, dirname):
        """
        Create a dir to build in.
        """
        dirpath = os.path.join(self.getcfg('startfrom'), dirname)
        try:
            os.mkdir(dirpath)
            os.chdir(dirpath)
            self.log.debug("Created dir at %s" % dirpath)
            return dirpath
        except OSError, err:
            self.log.error("Can't use dir %s to build in: %s" % (dirpath, err))

    def prep_extra_src_dirs(self, stage, target_prefix=None):
        """
        Prepare extra (optional) source directories, so GCC will build these as well.
        """

        known_stages = ["stage1", "stage2", "stage3"]
        if not stage in known_stages:
            self.log.error("Incorrect argument for prep_extra_src_dirs, should be one of: %s" % known_stages)

        configopts = ''
        if stage == "stage2":
            # no MPFR/MPC needed in stage 2
            extra_src_dirs = ["gmp"]
        else:
            extra_src_dirs = ["gmp", "mpfr", "mpc"]

        # add optional ones that were selected (e.g. CLooG, PPL, ...)
        for x in ["cloog", "ppl"]:
            if self.getcfg('with%s' % x):
                extra_src_dirs.append(x)

        # see if modules are loaded
        # if module is available, just use the --with-X GCC configure option
        for extra in copy(extra_src_dirs):
            envvar = get_software_root(extra)
            if envvar:
                configopts += " --with-%s=%s" % (extra, envvar)
                extra_src_dirs.remove(extra)
            elif extra in ["cloog", "ppl"] and stage in ["stage1", "stage3"]:
                # building CLooG or PPL requires a recent compiler
                # our best bet is to do a 3-staged build of GCC, and
                # build CLooG/PPL with the GCC we're building in stage 2
                # then (bootstrap) build GCC in stage 3
                # also, no need to stage cloog/ppl in stage3 (may even cause troubles)
                self.stagedbuild = True
                extra_src_dirs.remove(extra)

        # try and find source directories with given prefixes
        # these sources should be included in list of sources in .eb spec file,
        # so EasyBuild can unpack them in the build dir
        found_src_dirs = []
        versions = {}
        names = {}
        all_dirs = os.listdir(self.builddir)
        for d in all_dirs:
            for sd in extra_src_dirs:
                if d.startswith(sd):
                    found_src_dirs.append({
                                           'source_dir': d,
                                           'target_dir': sd
                                          })
                    # expected format: name[-subname]-version
                    ds = os.path.basename(d).split('-')
                    name = '-'.join(ds[0:-1])
                    names.update({sd: name})
                    ver = ds[-1]
                    versions.update({sd: ver})

        # we need to find all dirs specified, or else...
        if not len(found_src_dirs) == len(extra_src_dirs):
            self.log.error("Couldn't find all source dirs %s: found %s from %s" % (extra_src_dirs, found_src_dirs, all_dirs))

        # copy to a dir with name as expected by GCC build framework
        for d in found_src_dirs:
            src = os.path.join(self.builddir, d['source_dir'])
            if target_prefix:
                dst = os.path.join(target_prefix, d['target_dir'])
            else:
                dst = os.path.join(self.getcfg('startfrom'), d['target_dir'])
            if not os.path.exists(dst):
                try:
                    shutil.copytree(src, dst)
                except OSError, err:
                    self.log.error("Failed to copy src %s to dst %s: %s" % (src, dst, err))
                self.log.debug("Copied %s to %s, so GCC can build %s" % (src, dst, d['target_dir']))
            else:
                self.log.debug("No need to copy %s to %s, it's already there." % (src, dst))

        self.log.debug("Prepared extra src dirs for %s: %s (configopts: %s)" % (stage, found_src_dirs, configopts))

        return {
                'configopts': configopts,
                'names': names,
                'versions': versions
               }

    def run_configure_cmd(self, cmd):
        """
        Run a configure command, with some extra checking (e.g. for unrecognized options).
        """
        (out, ec) = run_cmd(cmd, log_all=True, simple=False)

        if ec != 0:
            self.log.error("Command '%s' exited with exit code != 0 (%s)" % (cmd, ec))

        # configure scripts tend to simply ignore unrecognized options
        # we should be more strict here, because GCC is very much a moving target
        unknown_re = re.compile("WARNING: unrecognized options")

        unknown_options = unknown_re.findall(out)
        if unknown_options:
            self.log.error("Unrecognized options found during configure: %s" % unknown_options)

    def configure(self):
        """
        Configure for GCC build:
        - prepare extra source dirs (GMP, MPFR, MPC, ...)
        - create obj dir to build in (GCC doesn't like to be built in source dir)
        - add configure and make options, according to .eb spec file
        - decide whether or not to do a staged build (which is required to enable PPL/CLooG support)
        - set platform_lib based on config.guess output
        """

        # self.configopts will be reused in a 3-staged build,
        # configopts is only used in first configure
        self.configopts = self.getcfg('configopts')

        # I) prepare extra source dirs, e.g. for GMP, MPFR, MPC (if required), so GCC can build them
        stage1_info = self.prep_extra_src_dirs("stage1")
        configopts = stage1_info['configopts']

        # II) update config options

        # enable specified language support
        if self.getcfg('languages'):
            self.configopts += " --enable-languages=%s" % ','.join(self.getcfg('languages'))

        # enable link-time-optimization (LTO) support, if desired
        if self.getcfg('withlto'):
            self.configopts += " --enable-lto"

        # configure for a release build
        self.configopts += " --enable-checking=release "
        # enable C++ support (required for GMP build), disable multilib (???)
        self.configopts += " --enable-cxx --disable-multilib"
        # build both static and dynamic libraries (???)
        self.configopts += " --enable-shared=yes --enable-static=yes "
        # use POSIX threads
        self.configopts += " --enable-threads=posix "
        # use GOLD as default linker, enable plugin support
        self.configopts += " --enable-gold=default --enable-plugins "
        self.configopts += " --enable-ld --with-plugin-ld=ld.gold"

        # enable bootstrap build for self-containment (unless for staged build)
        if not self.stagedbuild:
            configopts += " --enable-bootstrap"
        else:
            configopts += " --disable-bootstrap"

        if self.stagedbuild:
            #
            # STAGE 1: configure GCC build that will be used to build PPL/CLooG
            #
            self.log.info("Starting with stage 1 of 3-staged build to enable CLooG and/or PPL support...")
            self.stage1installdir = os.path.join(self.builddir, 'GCC_stage1_eb')
            configopts += " --prefix=%(p)s --with-local-prefix=%(p)s" % {'p' : self.stage1installdir}

        else:
            # unstaged build, so just run standard configure/make/make install
            # set prefixes
            self.log.info("Performing regular GCC build...")
            configopts += " --prefix=%(p)s --with-local-prefix=%(p)s" % {'p' : self.installdir}

        # III) create obj dir to build in, and change to it
        #     GCC doesn't like to be built in the source dir
        if self.stagedbuild:
            self.stage1prefix = self.create_dir("stage1_obj")
        else:
            self.create_dir("obj")

        # IV) actual configure, but not on default path
        cmd = "%s ../configure  %s %s" % (
                                          self.getcfg('preconfigopts'),
                                          self.configopts,
                                          configopts
                                         )

        # instead of relying on uname, we run the same command GCC uses to
        # determine the platform
        out, ec = run_cmd("../config.guess", simple=False)
        if ec == 0:
            self.platform_lib = out.rstrip()
        else:
            self.platform_lib = get_platform_name(withversion=True)

        self.run_configure_cmd(cmd)

    def make(self):

        if self.stagedbuild:

            # make and install stage 1 build of GCC
            paracmd = ''
            if self.getcfg('parallel'):
                paracmd = "-j %s" % self.getcfg('parallel')

            cmd = "%s make %s %s" % (self.getcfg('premakeopts'), paracmd, self.getcfg('makeopts'))
            run_cmd(cmd, log_all=True, simple=True)

            cmd = "make install %s" % (self.getcfg('installopts'))
            run_cmd(cmd, log_all=True, simple=True)

            # register built GCC as compiler to use for stage 2/3
            path = "%s/bin:%s" % (self.stage1installdir, os.getenv('PATH'))
            env.set('PATH', path)

            ld_lib_path = "%(dir)s/lib64:%(dir)s/lib:%(val)s" % {
                                                                 'dir': self.stage1installdir,
                                                                 'val': os.getenv('LD_LIBRARY_PATH')
                                                                }
            env.set('LD_LIBRARY_PATH', ld_lib_path)

            #
            # STAGE 2: build GMP/PPL/CLooG for stage 3
            #

            # create dir to build GMP/PPL/CLooG in
            stage2dir = "stage2_stuff"
            stage2prefix = self.create_dir(stage2dir)

            # prepare directories to build GMP/PPL/CLooG
            stage2_info = self.prep_extra_src_dirs("stage2", target_prefix=stage2prefix)
            configopts = stage2_info['configopts']

            # build PPL and CLooG (GMP as dependency)

            for lib in ["gmp", "ppl", "cloog"]:

                self.log.debug("Building %s in stage 2" % lib)

                if lib == "gmp" or self.getcfg('with%s' % lib):

                    libdir = os.path.join(stage2prefix, lib)
                    try:
                        os.chdir(libdir)
                    except OSError, err:
                        self.log.error("Failed to change to %s: %s" % (libdir, err))

                    if lib == "gmp":

                        cmd = "./configure --prefix=%s " % stage2prefix
                        cmd += "--with-pic --disable-shared --enable-cxx"

                    elif lib == "ppl":

                        self.pplver = LooseVersion(stage2_info['versions']['ppl'])

                        cmd = "./configure --prefix=%s --with-pic -disable-shared " % stage2prefix

                        # only enable C/C++ interfaces (Java interface is sometimes troublesome)
                        cmd += "--enable-interfaces='c c++' "

                        # enable watchdog (or not)
                        if self.pplver <= LooseVersion("0.11"):
                            if self.getcfg('pplwatchdog'):
                                cmd += "--enable-watchdog "
                            else:
                                cmd += "--disable-watchdog "
                        elif self.getcfg('pplwatchdog'):
                            self.log.error("Enabling PPL watchdog only supported in PPL <= v0.11 .")

                        # make sure GMP we just built is found
                        cmd += "--with-gmp=%s " % stage2prefix

                    elif lib == "cloog":

                        self.cloogname = stage2_info['names']['cloog']
                        self.cloogver = LooseVersion(stage2_info['versions']['cloog'])
                        v0_15 = LooseVersion("0.15")
                        v0_16 = LooseVersion("0.16")

                        cmd = "./configure --prefix=%s --with-pic --disable-shared " % stage2prefix
                        # use isl or PPL
                        if self.getcfg('clooguseisl'):
                            if self.cloogver >= v0_16:
                                cmd += "--with-isl=bundled "
                            else:
                                self.log.error("Using ISL is only supported in CLooG >= v0.16 (detected v%s)." % self.cloogver)
                        else:
                            if self.cloogname == "cloog-ppl" and self.cloogver >= v0_15 and self.cloogver < v0_16:
                                cmd += "--with-ppl=%s " % stage2prefix
                            else:
                                errormsg = "PPL only supported with CLooG-PPL v0.15.x (detected v%s)" % self.cloogver
                                errormsg += "\nNeither using PPL or ISL-based ClooG, I'm out of options..."
                                self.log.error(errormsg)

                        # make sure GMP is found
                        if self.cloogver >= v0_15 and self.cloogver < v0_16:
                            cmd += "--with-gmp=%s " % stage2prefix
                        elif self.cloogver >= v0_16:
                            cmd += "--with-gmp=system --with-gmp-prefix=%s " % stage2prefix
                        else:
                            self.log.error("Don't know how to specify location of GMP to configure of CLooG v%s." % self.cloogver)

                    else:
                        self.log.error("Don't know how to configure for %s" % lib)

                    # configure
                    self.run_configure_cmd(cmd)

                    # build and 'install'
                    cmd = "make %s install" % paracmd
                    run_cmd(cmd, log_all=True, simple=True)

                    if lib == "gmp":
                        # make sure correct GMP is found
                        libpath = os.path.join(stage2prefix, 'lib')
                        incpath = os.path.join(stage2prefix, 'include')

                        cppflags = os.getenv('CPPFLAGS', '')
                        env.set('CPPFLAGS', "%s -L%s -I%s " % (cppflags, libpath, incpath))

            #
            # STAGE 3: bootstrap build of final GCC (with PPL/CLooG support)
            #

            # create new obj dir and change into it
            self.create_dir("stage3_obj")

            # reconfigure for stage 3 build
            self.log.info("Stage 2 of 3-staged build completed, continuing with stage 2 (with CLooG and/or PPL support enabled)...")

            stage3_info = self.prep_extra_src_dirs("stage3")
            configopts = stage3_info['configopts']
            configopts += " --prefix=%(p)s --with-local-prefix=%(p)s" % {'p' : self.installdir }

            # enable bootstrapping for self-containment
            configopts += " --enable-bootstrap "

            # PPL config options
            if self.getcfg('withppl'):
                # for PPL build and CLooG-PPL linking
                libstdcxxpath = "%s/lib64/libstdc++.a" % self.stage1installdir
                configopts += "--with-host-libstdcxx='-static-libgcc %s -lm' " % libstdcxxpath

                configopts += "--with-ppl=%s " % stage2prefix

                if self.pplver <= LooseVersion("0.11"):
                    if self.getcfg('pplwatchdog'):
                        configopts += "--enable-watchdog "
                    else:
                        configopts += "--disable-watchdog "

            # CLooG config options
            if self.getcfg('withcloog'):
                configopts += "--with-cloog=%s " % stage2prefix

                if self.getcfg('clooguseisl') and self.cloogver >= LooseVersion("0.16"):
                    configopts += "--enable-cloog-backend=isl "

            # configure
            cmd = "%s ../configure %s %s" % (
                                             self.getcfg('preconfigopts'),
                                             self.configopts,
                                             configopts
                                            )
            self.run_configure_cmd(cmd)

        # build with bootstrapping for self-containment
        self.updatecfg('makeopts', 'bootstrap')

        # call standard make
        Application.make(self)

    # make install is just standard makeInstall, nothing special there

    def sanitycheck(self):
        """
        Custom sanity check for GCC
        """

        if not self.getcfg('sanityCheckPaths'):

            kernel_name = get_kernel_name()

            sharedlib_ext = get_shared_lib_ext()

            common_infix = 'gcc/%s/%s' % (self.platform_lib, self.version())

            bin_files = ["gcov"]
            lib64_files = ["libgomp.%s" % sharedlib_ext, "libgomp.a"]
            if kernel_name == 'Linux':
                lib64_files.extend(["libgcc_s.%s" % sharedlib_ext, "libmudflap.%s" % sharedlib_ext, "libmudflap.a"])
            libexec_files = []
            dirs = ['lib/%s' % common_infix]
            if kernel_name == 'Linux':
                dirs.append('lib64')

            if not self.getcfg('languages'):
                # default languages are c, c++, fortran
                bin_files = ["c++", "cpp", "g++", "gcc", "gcov", "gfortran"]
                lib64_files.extend(["libstdc++.%s" % sharedlib_ext, "libstdc++.a"])
                libexec_files = ['cc1', 'cc1plus', 'collect2', 'f951']

            if 'c' in self.getcfg('languages'):
                bin_files.extend(['cpp', 'gcc'])

            if 'c++' in self.getcfg('languages'):
                bin_files.extend(['c++', 'g++'])
                dirs.append('include/c++/%s' % self.version())
                lib64_files.extend(["libstdc++.%s" % sharedlib_ext, "libstdc++.a"])

            if 'fortran' in self.getcfg('languages'):
                bin_files.append('gfortran')
                lib64_files.extend(['libgfortran.%s' % sharedlib_ext, 'libgfortran.a'])

            if 'lto' in self.getcfg('languages'):
                libexec_files.extend(['lto1', 'lto-wrapper'])
                if kernel_name in ['Linux']:
                    libexec_files.append('liblto_plugin.%s' % sharedlib_ext)

            bin_files = ["bin/%s" % x for x in bin_files]
            if kernel_name in ['Darwin']:
                lib64_files = ["lib/%s" % x for x in lib64_files]
            else:
                lib64_files = ["lib64/%s" % x for x in lib64_files]
            libexec_files = ["libexec/%s/%s" % (common_infix, x) for x in libexec_files]

            self.setcfg('sanityCheckPaths', {
                                             'files': bin_files + lib64_files + libexec_files,
                                             'dirs': dirs
                                            })

            self.log.info("Customized sanity check paths: %s" % self.getcfg('sanityCheckPaths'))

        Application.sanitycheck(self)

    def makeModuleReqGuess(self):
        """
        Make sure all GCC libs are in LD_LIBRARY_PATH
        """
        return {
                'PATH': ['bin'],
                'LD_LIBRARY_PATH': ['lib', 'lib64',
                                    'lib/gcc/%s' % (self.platform_lib, self.getcfg('version'))],
                'MANPATH': ['man', 'share/man']
               }
