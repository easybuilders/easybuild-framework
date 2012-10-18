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
"""
import os
import sys
from optparse import OptionParser
from datetime import date

sys.path.append('../..')
sys.path.append('.')
sys.path.append('..')

from easybuild.framework.easyconfig import EasyConfig
from vsc import fancylogger

# parse options
parser = OptionParser()
parser.add_option("-v", "--verbose", action="count", dest="verbose", help="Be more verbose, can be used multiple times")

options, args = parser.parse_args()
# get and configure logger
log = fancylogger.getLogger(__name__)
if options.verbose >= 1:
    fancylogger.setLogLevelWarning()
if options.verbose >= 2:
    fancylogger.setLogLevelInfo()
if options.verbose >= 3:
    fancylogger.setLogLevelDebug()
log.info('starting parsing from %s' % sys.argv[1])

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
print "Click on the ![easyconfig logo](http://hpc.ugent.be/easybuild/images/easyblocks_configs_logo_16x16.png) " 
print "to see to the list of easyconfig files."
print "## Supported Packages (%d as of %s) " % (len(configs), date.today().isoformat()) 

for config in configs: 
    if config.name[0].lower() != firstl:
        firstl = config.name[0].lower()
        # print the first letter and the number of packages starting with this letter we support
        print "\n### %s (%d)\n" % (firstl.upper(), len([x for x in configs if x.name[0].lower() == firstl]))
    #TODO: add a link to the easyblock if there is one available.
    print "* [![EasyConfigs](http://hpc.ugent.be/easybuild/images/easyblocks_configs_logo_16x16.png)] " \
          "(https://github.com/hpcugent/easybuild-easyconfigs/tree/develop/easybuild/easyconfigs/%s/%s)" \
          "[ %s](%s)" % \
          (firstl, config.name, config.name, config['homepage'])

