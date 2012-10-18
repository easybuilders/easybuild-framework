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
"""
import os
import sys
from optparse import OptionParser
from datetime import date

sys.path.append('../..')
sys.path.append('.')
sys.path.append('..')

from easybuild.framework.easyconfig import EasyConfig
from easybuild.framework import easyblock
from vsc import fancylogger

# parse options
parser = OptionParser()
parser.add_option("-v", "--verbose", action="count", dest="verbose", help="Be more verbose, can be used multiple times")

options, args = parser.parse_args()

if len(args) < 2:
    print "Usage: %s [-v [-v [-v [-v]]]] easyconfigs_dir easyblocks_dir"

# get and configure logger
log = fancylogger.getLogger(__name__)
if options.verbose >= 1:
    fancylogger.setLogLevelWarning()
if options.verbose >= 2:
    fancylogger.setLogLevelInfo()
if options.verbose >= 3:
    fancylogger.setLogLevelDebug()
log.info('parsing easyconfigs from %s' % args[0])
log.info('parsing easyblocks from %s' % args[1])

configs = []
names = []
# TODO: Do this with the github repository
for root, subfolders, files in os.walk(sys.argv[1]):    
    # TODO: do this for all hidden folders
    if '.git' in subfolders:
        log.info("found .git subfolder, ignoring it")
        subfolders.remove('.git')
    for file in files:
        file = os.path.join(root,file)
        try:
            ec = EasyConfig(file, validate=False)
            log.info("found valid easyconfig %s" % ec) 
            if not ec.name in names:
                log.info("found new software package %s" % ec)
                # check if an easyblock exists
                module = easyblock.get_class(None, log, name=ec.name).__module__.split('.')[-1]
                if module != "configuremake":
                    ec.easyblock = module
                else:
                    ec.easyblock = None
                configs.append(ec)
                names.append(ec.name)
        except Exception, e:
            log.warning("faulty easyconfig %s" % file)
            log.debug(e)

log.info("Found easyconfigs: %s" % [x.name for x in configs])
# remove example configs
configs = [config for config in configs if not "example.com" in config['homepage']]
# sort by name
configs = sorted(configs, key=lambda config : config.name.lower())
firstl = ""

# print out the configs in markdown format for the wiki
print "Click on ![easyconfig logo](http://hpc.ugent.be/easybuild/images/easyblocks_configs_logo_16x16.png) " 
print "to see to the list of easyconfig files."
print "And on ![easyblock logo](http://hpc.ugent.be/easybuild/images/easyblocks_easyblocks_logo_16x16.png) "
print "to go to the easyblock for this package." 
print "## Supported Packages (%d as of %s) " % (len(configs), date.today().isoformat()) 

for config in configs: 
    if config.name[0].lower() != firstl:
        firstl = config.name[0].lower()
        # print the first letter and the number of packages starting with this letter we support
        print "\n### %s (%d)\n" % (firstl.upper(), len([x for x in configs if x.name[0].lower() == firstl]))
    print "* [![EasyConfigs](http://hpc.ugent.be/easybuild/images/easyblocks_configs_logo_16x16.png)] " 
    print "(https://github.com/hpcugent/easybuild-easyconfigs/tree/develop/easybuild/easyconfigs/%s/%s)" % (firstl, config.name)
    if config.easyblock:
        print "[![EasyBlocks](http://hpc.ugent.be/easybuild/images/easyblocks_easyblocks_logo_16x16.png)] "
        print " (https://github.com/hpcugent/easybuild-easyblocks/tree/develop/easybuild/easyblocks/%s/%s.py)" % (firstl, config.easyblock)
    else:
        print "&nbsp;&nbsp;&nbsp;&nbsp;"
    print "[ %s](%s)" % (config.name, config['homepage'])

