##
# Copyright 2012 Jens Timmerman
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild. If not, see <http://www.gnu.org/licenses/>.
##
import os
from easybuild.framework.application import Application
from easybuild.tools.filetools import run_cmd, parselogForError

class EB_R(Application):
    """
    Install R, including list of packages specified
    Install specified version of packages, install hard-coded package version 
    or latest package version (in that order of preference) 
    """
    def extra_packages_pre(self):
        """
        We set some default configs here for extentions for R.
        """
        self.setcfg('pkgtemplate', "%s_%s.tar.gz")
        self.setcfg('pkgdefaultclass', ["R", "EB_RPackage"])
        self.setcfg('pkgfilter', ["R -q --no-save", "library(%(name)s)"])

#
#class bioconductor(DefaultRpackage):
#    def makeCmdLineCmd(self):
#        self.log.error("bioconductor.run: Don't know how to install a specific version of a bioconductor package.")
#
#    def makeRCmd(self):
#        name = self.pkg['name']
#
#        blName = ""
#        if name == "bioconductor":
#            self.log.debug("Installing bioconductor package")
#        else:
#            self.log.debug("Installing bioconductor package %s." % name)
#            blName = "\"%s\"" % name
#
#        Rcmd = """
#        source("http://bioconductor.org/biocLite.R")
#        biocLite(%s)
#        """ % (blName)
#        cmd = "R -q --no-save"
#
#        return cmd, Rcmd
#
## special cases of bioconductor packages
## handled by class aliases
#BSgenome = bioconductor
#GenomeGraphs = bioconductor
#ShortRead = bioconductor
#exonmap = bioconductor
#
#class Rserve(DefaultRpackage):
#    def run(self):
#        self.setconfigurevars(['LIBS="$LIBS -lpthread"'])
#        DefaultRpackage.run(self)
#
#class rsprng(DefaultRpackage):
#    def run(self):
#        self.log.debug("Setting configure args for %s" % self.name)
#        self.setconfigurevars(['LIBS=\\"%s %s\\"' % (os.environ["LIBS"], os.environ["LDFLAGS"])])
#        self.setconfigureargs(["--with-sprng=%s" % os.environ["SOFTROOTSPRNG"]])
#        DefaultRpackage.run(self)
#
#
#class rgdal(DefaultRpackage):
#    def run(self):
#        self.log.debug("Setting configure args for %s" % self.name)
#        softrootproj = os.environ["SOFTROOTPROJ"]
#        self.setconfigureargs(["--with-proj-include=%s/include --with-proj-lib=%s/lib" % (softrootproj, softrootproj)])
#        DefaultRpackage.run(self)
#
#
#class Rmpi(DefaultRpackage):
#    def run(self):
#        if os.environ.has_key('SOFTROOTICTCE'):
#            self.log.debug("Setting configure args for Rmpi")
#            self.setconfigureargs(["--with-Rmpi-include=%s/intel64/include" % os.environ["SOFTROOTIMPI"],
#                                   "--with-Rmpi-libpath=%s/intel64/lib" % os.environ["SOFTROOTIMPI"],
#                                   "--with-Rmpi-type=MPICH"])
#            DefaultRpackage.run(self)
#        elif os.environ.has_key('SOFTROOTIQACML'):
#            self.log.debug("Installing most recent version of package %s (iqacml toolkit)." % self.name)
#            self.setconfigureargs(["--with-Rmpi-include=%s/include" % os.environ["SOFTROOTQLOGICMPI"],
#                                   "--with-Rmpi-libpath=%s/lib64" % os.environ["SOFTROOTQLOGICMPI"],
#                                   "--with-mpi=%s" % os.environ["SOFTROOTQLOGICMPI"],
#                                   "--with-Rmpi-type=MPICH"])
#            cmd, inp = self.makeRCmd()
#
#            fn = os.path.join("/tmp", "inputRmpi_install.R")
#            f = open(fn, "w")
#            f.write(inp)
#            f.close()
#            cmd = "mpirun -np 1 -H localhost %s -f %s" % (cmd, fn)
#            run_cmd(cmd, log_all=True, simple=False)
#            os.remove(fn)
#        else:
#            self.log.error("Unknown toolkit, don't know how to install Rmpi with this toolkit! Giving up...")
#
#class VIM(DefaultRpackage):
#    def makeCmdLineCmd(self):
#        # fancy trick to install VIM dependencies first, without installing VIM
#        # then install source of VIM with specified version 
#        Rcmd = """
#        options(repos=c(CRAN="http://www.freestatistics.org/cran"))
#        install.packages("%s", dependencies="Depends", INSTALL_opts="--fake")
#        install.packages("%s")
#        """ % (self.name, self.src)
#        cmd = "R -q --no-save"
#
#        self.log.debug("makeRCmd returns %s with input %s" % (cmd, Rcmd))
#
#        return (cmd, Rcmd)
#
#class rJava(DefaultRpackage):
#
#    def run(self):
#
#        if not os.getenv('SOFTROOTJAVA'):
#            self.log.error("Java module not loaded, required as dependency for %s." % self.name())
#
#        java_home = os.getenv('JAVA_HOME')
#        if not java_home.endswith("jre"):
#            new_java_home = os.path.join(java_home, "jre")
#            os.putenv("JAVA_HOME", new_java_home)
#        else:
#            new_java_home = java_home
#
#        path = os.getenv('PATH')
#        os.putenv("PATH", "%s:%s/bin" % (path, new_java_home))
#
#        os.putenv("_JAVA_OPTIONS", "-Xmx512M")
#
#        txt = '# stuff required by rJava R package\n'
#        txt += 'setenv JAVA_HOME %s\n' % new_java_home
#        txt += 'setenv _JAVA_OPTIONS -Xmx512M\n'
#        txt += 'prepend-path PATH %s/bin\n' % new_java_home
#
#        DefaultRpackage.run(self)
#
#        return txt
