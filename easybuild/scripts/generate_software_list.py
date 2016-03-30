#!/usr/bin/env python
##
# Copyright 2012-2016 Ghent University
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
This script will try to generate a list of supported software packages
by walking over a directory of easyconfig files and parsing them all

Sine this script will actually parse all easyconfigs and easyblocks
it will only produce a list of Packages that can actually be handled
correctly by easybuild.

@author: Jens Timmerman (Ghent University)
"""
from datetime import date
from optparse import OptionParser

import easybuild.tools.config as config
import easybuild.tools.options as eboptions
from easybuild.framework.easyconfig.easyconfig import EasyConfig, get_easyblock_class
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.github import Githubfs
from vsc.utils import fancylogger

# parse options
parser = OptionParser()
parser.add_option("-v", "--verbose", action="count", dest="verbose",
     help="Be more verbose, can be used multiple times.")
parser.add_option("-q", "--quiet", action="store_true", dest="quiet",
     help="Don't be verbose, in fact, be quiet.")
parser.add_option("-b", "--branch", action="store", dest="branch",
     help="Choose the branch to link to (default develop).")
parser.add_option("-u", "--username", action="store", dest="username",
     help="Choose the user to link to (default hpcugent).")
parser.add_option("-r", "--repo", action="store", dest="repo",
     help="Choose the branch to link to (default easybuild-easyconfigs).")
parser.add_option("-p", "--path", action="store", dest="path",
     help="Specify a path inside the repo (default easybuild/easyconfigs).")
parser.add_option("-l", "--local", action="store_true", dest="local",
     help="Use a local path, not on github.com (Default false)")

options, args = parser.parse_args()

# get and configure logger
log = fancylogger.getLogger(__name__)
if options.verbose == 1:
    fancylogger.setLogLevelWarning()
elif options.verbose == 2:
    fancylogger.setLogLevelInfo()
elif options.verbose >= 3:
    fancylogger.setLogLevelDebug()

if options.quiet:
    fancylogger.logToScreen(False)
else:
    fancylogger.logToScreen(True)

# other options
if not options.branch:
    options.branch = "develop"
if not options.username:
    options.username = "hpcugent"
if not options.repo:
    options.repo = "easybuild-easyconfigs"
if not options.path:
    options.path = "easybuild/easyconfigs"
if options.local:
    import os
    walk = os.walk
    join = os.path.join
    read = lambda ec_file : ec_file

    log.info('parsing easyconfigs from location %s' % options.path)
else:
    fs = Githubfs(options.username, options.repo, options.branch)
    walk = Githubfs(options.username, options.repo, options.branch).walk
    join = fs.join
    read = lambda ec_file : fs.read(ec_file, api=False)

    log.info('parsing easyconfigs from user %s reponame %s' % (options.username, options.repo))


# configure EasyBuild, by parsing options
eb_go = eboptions.parse_options(args=args)
config.init(eb_go.options, eb_go.get_options_by_section('config'))
config.init_build_options({'validate': False, 'external_modules_metadata': {}})


configs = []
names = []


# fs.walk yields the same results as os.walk, so should be interchangable
# same for fs.join and os.path.join

for root, subfolders, files in walk(options.path):
    if '.git' in subfolders:
        log.info("found .git subfolder, ignoring it")
        subfolders.remove('.git')
    for ec_file in files:
        if not ec_file.endswith('.eb') or ec_file in ["TEMPLATE.eb"]:
            log.warning("SKIPPING %s/%s" % (root, ec_file))
            continue
        ec_file = join(root, ec_file)
        ec_file = read(ec_file)
        try:
            ec = EasyConfig(ec_file)
            log.info("found valid easyconfig %s" % ec)
            if not ec.name in names:
                log.info("found new software package %s" % ec.name)
                ec.easyblock = None
                # check if an easyblock exists
                ebclass = get_easyblock_class(None, name=ec.name, default_fallback=False)
                if ebclass is not None:
                    module = ebclass.__module__.split('.')[-1]
                    if module != "configuremake":
                        ec.easyblock = module
                configs.append(ec)
                names.append(ec.name)
        except Exception, err:
            raise EasyBuildError("faulty easyconfig %s: %s", ec_file, err)

log.info("Found easyconfigs: %s" % [x.name for x in configs])
# sort by name
configs = sorted(configs, key=lambda config : config.name.lower())
firstl = ""

# print out the configs in markdown format for the wiki
print "Click on ![easyconfig logo](http://hpc.ugent.be/easybuild/images/easyblocks_configs_logo_16x16.png) "
print "to see to the list of easyconfig files."
print "And on ![easyblock logo](http://hpc.ugent.be/easybuild/images/easyblocks_easyblocks_logo_16x16.png) "
print "to go to the easyblock for this package."
print "## Supported Packages (%d in %s as of %s) " % (len(configs), options.branch, date.today().isoformat())
print "<center>"
print " - ".join(["[%(letter)s](#%(letter)s)" % \
    {'letter': x} for x in  sorted(set([config.name[0].upper() for config in configs]))])
print "</center>"

for config in configs:
    if config.name[0].lower() != firstl:
        firstl = config.name[0].lower()
        # print the first letter and the number of packages starting with this letter we support
        print "\n### %(letter)s (%(count)d packages) <a name='%(letter)s'/>\n" % {
                'letter': firstl.upper(),
                'count': len([x for x in configs if x.name[0].lower() == firstl]),
            }
    print "* [![EasyConfigs](http://hpc.ugent.be/easybuild/images/easyblocks_configs_logo_16x16.png)] "
    print "(https://github.com/hpcugent/easybuild-easyconfigs/tree/%s/easybuild/easyconfigs/%s/%s)" % \
            (options.branch, firstl, config.name)
    if config.easyblock:
        print "[![EasyBlocks](http://hpc.ugent.be/easybuild/images/easyblocks_easyblocks_logo_16x16.png)] "
        print " (https://github.com/hpcugent/easybuild-easyblocks/tree/%s/easybuild/easyblocks/%s/%s.py)" % \
            (options.branch, firstl, config.easyblock)
    else:
        print "&nbsp;&nbsp;&nbsp;&nbsp;"
    if config['homepage'] != "(none)":
        print "[ %s](%s)" % (config.name, config['homepage'])
    else:
        print config.name

