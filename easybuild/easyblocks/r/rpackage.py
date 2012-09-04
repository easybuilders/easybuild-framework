##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
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
EasyBuild support for R packages, implemented as an easyblock
"""
from easybuild.framework.application import ApplicationPackage

def mkInstallOptionR(opt, xs):
    """
    Make option list for install.packages, to specify in R environment. 
    """
    s = ""
    if xs:
        s = "%s=c(\"%s" % (opt, xs[0])
        for x in xs[1:]:
            s += " %s" % x
        s += "\")"
    return s

def mkInstallOptionCmdLine(opt, xs):
    """
    Make option list for "R CMD INSTALL", to specify on command line.
    """
    s = ""
    if xs:
        s = " --%s=\"%s" % (opt, xs[0])
        for x in xs[1:]:
            s += " %s" % x
        s += "\""
    return s

class EB_RPackage(ApplicationPackage):
    def __init__(self, mself, pkg, pkginstalldeps):
        ApplicationPackage.__init__(self, mself, pkg, pkginstalldeps)
        self.configurevars = []
        self.configureargs = []

    def setconfigureargs(self, a):
        self.configureargs = a

    def setconfigurevars(self, a):
        self.configurevars = a

    def makeRCmd(self):
        confvars = "confvars"
        confargs = "confargs"
        confvarsList = mkInstallOptionR(confvars, self.configurevars)
        confargsList = mkInstallOptionR(confargs, self.configureargs)
        confvarsStr = ""
        if confvarsList:
            confvarsList = confvarsList + "; names(%s)=\"%s\"" % (confvars, self.name)
            confvarsStr = ", configure.vars=%s" % confvars
        confargsStr = ""
        if confargsList:
            confargsList = confargsList + "; names(%s)=\"%s\"" % (confargs, self.name)
            confargsStr = ", configure.args=%s" % confargs

        if self.pkginstalldeps:
            installdeps = "TRUE"
        else:
            installdeps = "FALSE"

        Rcmd = """
        options(repos=c(CRAN="http://www.freestatistics.org/cran"))
        %s
        %s
        install.packages("%s",dependencies = %s%s%s)
        """ % (confvarsList, confargsList, self.name, installdeps, confvarsStr, confargsStr)
        cmd = "R -q --no-save"

        self.log.debug("makeRCmd returns %s with input %s" % (cmd, Rcmd))

        return (cmd, Rcmd)

    def makeCmdLineCmd(self):

        confvars = ""
        if self.configurevars:
            confvars = "--configure-vars='%s'" % ' '.join(self.configurevars)
        confargs = ""
        if self.configureargs:
            confargs = "--configure-args='%s'" % ' '.join(self.configureargs)

        cmd = "R CMD INSTALL %s %s %s" % (self.src, confargs, confvars)
        self.log.debug("makeCmdLineCmd returns %s" % cmd)

        return cmd, None

    def run(self):
        if self.src:
            self.log.debug("Installing package %s version %s." % (self.name, self.version))
            cmd, stdin = self.makeCmdLineCmd()
        else:
            self.log.debug("Installing most recent version of package %s (source not found)." % self.name)
            cmd, stdin = self.makeRCmd()

        (cmdStdouterr, _) = run_cmd(cmd, log_all=True, simple=False, inp=stdin, regexp=False)

        cmdErrors = parselogForError(cmdStdouterr, regtxt="^ERROR:", stdout=True)
        if cmdErrors:
            cmd = "R -q --no-save"
            stdin = """
            remove.library(%s)
            """ % self.name
            # remove library if errors were detected
            # it's possible that some of the dependencies failed, but the library itself was installed
            run_cmd(cmd, log_all=False, log_ok=False, simple=False, inp=stdin, regexp=False)
            self.log.error("Errors detected during installation of package %s!" % self.name)
        else:
            self.log.debug("Package %s installed succesfully" % self.name)
