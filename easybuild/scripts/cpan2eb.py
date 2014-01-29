##
# Copyright 2013 Ghent University
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
##
"""
This script takes a Perl module name as argument, and generates
a string compatible with the easyconfig 1.x format with metadata about the module
and all it's dependencies

@author: Jens Timmerman
"""
import sys

from easybuild.tools.agithub import Client

from vsc.utils.generaloption import simple_option
from vsc.utils import fancylogger


logger = fancylogger.getLogger()


class CpanMeta(object):
    """This class gets meta information from cpan

    This uses the metacpan.org api
    """
    def __init__(self):
        """Constructor"""
        dummy = {'download_url': 'example.com/bla', 'release': '0', 'version': '0', 'distribution': 'ExtUtils-MakeMaker',
                 'modulename': 'ExtUtils::MakeMaker'}
        self.cache = {'ExtUtils::MakeMaker': dummy,  'perl': dummy}
        self.graph = {'ExtUtils::MakeMaker': [], 'perl': []}
        self.client = Client('api.metacpan.org')

    def get_module_data(self, modulename):
        """Get some metadata about the current version of the module"""
        json = self.client.get("/v0/module/%s" % modulename)[1]
        depsjson = self.client.get("/v0/release/%(author)s/%(release)s" % json)
        depsjson = depsjson[1]
        depsjson.update(json)
        depsjson.update({'modulename': modulename})
        return depsjson

    def get_recursive_data(self, modulename):
        """Recursively get all data (so for all dependencies)"""
        # check if we have been here before
        if modulename in self.cache:
            logger.info('%s module cached ', modulename)
            return self.graph
        data = self.get_module_data(modulename)
        self.cache[modulename] = data
        # module's are somtimes included in a release we already know, so skip this also
        if data['release'] in self.cache:
            logger.info('%s release cached', data['release'])
            return self.graph
        self.cache[data['release']] = data
        dependencies = set()
        # do the recursive thing
        for dep in data['dependency']:
            if "requires" in dep["relationship"]:
                cpan.get_recursive_data(dep['module'])
                # if for some reason you get to many hits here, you might want to filter on build and confirure in phase: (To be further tested)
                # if "build" in dep["phase"] or "configure" in dep["phase"]:
                dependencies.add(dep['module'])
        self.graph[modulename] = dependencies
        return self.graph


def post_order(graph, root):
    """Walk the graph from the given root in a post-order manner, by providing the correspoding generator."""
    for node in graph[root]:
        for child in post_order(graph, node):
            yield child
    yield root


def topological_sort(graph, root):
    """Perform a topological sorting of the given graph.

    The graph needs to be in the following format:

        g = { t1: [t2, t3],
              t2: [t4, t5, t6],
              t3: []
              t4: []
              t5: [t3]
              t6: [t5]
            }

    where each node is mapped to a list of nodes it has an edge to.

    @returns: generator for traversing the graph in the desired order
    """
    visited = set()
    for node in post_order(graph, root):
        if node not in visited:
            yield node
            visited.add(node)  # been there, done that.


go = simple_option()

cpan = CpanMeta()
modules = cpan.get_recursive_data(go.args[0])
print modules

# topological soft, so we get correct dependencies order
for module in topological_sort(modules, go.args[0]):
    data = cpan.cache[module]
    url, name = data['download_url'].rsplit("/", 1)
    data.update({'url': url, 'tarball': name})  # distribution sometimes contains subdirs
    if data['release'] is not '0' and data['version'] is not '0':
        print    """('%(modulename)s', '%(version)s', {
                    'source_tmpl': '%(tarball)s',
                    'source_urls': ['%(url)s'],
                }),""" % data
