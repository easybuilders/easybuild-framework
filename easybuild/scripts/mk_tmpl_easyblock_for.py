#!/usr/bin/env python
##
# Copyright 2009-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
Script to create a template easyblock Python module, for a given software package.

@author: Kenneth Hoste (Ghent University)
"""

import datetime
import os
import sys
from optparse import OptionParser, OptionGroup

from easybuild.tools.filetools import encode_class_name

# parse options
parser = OptionParser()
parser.usage = "%prog <software name> [options]"
parser.description = "Generates template easyblock for given software name. " \
                     "Use -h or --help for more information."
parser.add_option("--path", help="path to easyblocks repository (default: '.')", default='.')
parser.add_option("--parent", default="EasyBlock",
                  help="Name of parent easyblock for this easyblock (default: 'EasyBlock').")
parser.add_option("--letter-prefix", default=False, action="store_true",
                  help="Whether or not to prefix the easyblock path with a letter directory (default: False)")
                 

(options, args) = parser.parse_args()

# obtain name of software to generate easyblock template for
if not len(args) == 1:
    parser.print_usage()
    sys.exit(1)

name = args[0]
print "Template easyblock for %s requested..." % name

# check whether easyblock repository path is found
easyblocks_repo_path = os.path.join(options.path, "easybuild", "easyblocks")
if not os.path.isdir(easyblocks_repo_path):
    sys.stderr.write("ERROR! Directory %s does not exist, please specify correct path "
                     "for easyblocks repository using --path.\n" % easyblocks_repo_path)
    sys.exit(1)

# determine path for easyblock
if options.letter_prefix:
    letter = name.lower()[0]
    if not ord(letter) in range(ord('a'),ord('z')+1):
        letter = '0'
    easyblock_path = os.path.join(easyblocks_repo_path, letter, "%s.py" % name.lower())
else:
    easyblock_path = os.path.join(easyblocks_repo_path, "%s.py" % name.lower())

# check whether path already exists
if os.path.exists(easyblock_path):
    sys.stderr.write("ERROR! Path %s already exists, please remove it first and try again.\n" % easyblock_path)
    sys.exit(1)

# determine parent easyblock class
parent_import = "from easybuild.framework.easyblock import EasyBlock"
if not options.parent == "EasyBlock":
    if options.parent.startswith('EB_'):
        ebmod = options.parent[3:].lower()  # FIXME: here we should actually decode the encoded class name
    else:
        ebmod = "generic.%s" % options.parent.lower()
    parent_import = "from easybuild.easyblocks.%s import %s" % (ebmod, options.parent)

tmpl = """##
# Copyright 2009-%(year)d Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
\"\"\"
EasyBuild support for building and installing %(name)s, implemented as an easyblock
\"\"\"
import os

import easybuild.tools.environment as env
import easybuild.tools.toolchain as toolchain
%(parent_import)s
from easybuild.framework.easyconfig import CUSTOM, MANDATORY
from easybuild.tools.run import run_cmd


class %(class_name)s(%(parent)s):
    \"\"\"Support for building/installing %(name)s.\"\"\"

    def __init__(self, *args, **kwargs):
        \"\"\"Initialisation of custom class variables for %(name)s.\"\"\"
        super(%(class_name)s, self).__init__(*args, **kwargs)

        self.example = None

    @staticmethod
    def extra_options():
        \"\"\"Custom easyconfig parameters for %(name)s.\"\"\"
        extra_vars = {
            'mandatory_extra_param': ['default value', "short description", MANDATORY],
            'optional_extra_param': ['default value', "short description", CUSTOM],
         }
        return %(parent)s.extra_options(extra_vars)

    def configure_step(self):
        \"\"\"Custom configuration procedure for %(name)s.\"\"\"

        # always use env.setvar instead of os.putenv or os.environ for defining environment variables
        env.setvar('CUSTOM_ENV_VAR', 'foo')
 
        cmd = "configure command" 
        run_cmd(cmd, log_all=True, simple=True, log_ok=True)

        # complete configuration with configure_method of parent
        super(%(class_name)s, self).configure_step()

    def build_step(self):
        \"\"\"Custom build procedure for %(name)s.\"\"\"

        comp_map = {
                    toolchain.INTELCOMP: 'intel',
                    toolchain.GCC: 'gcc',
                   }
        comp_fam = comp_map[self.toolchain.comp_family()]

        # enable parallel build
        par = self.cfg['parallel']
        cmd = "build command --parallel %%d --compiler-family %%s" %% (par, comp_fam)
        run_cmd(cmd, log_all=True, simple=True, log_ok=True)

    def test_step(self):
        \"\"\"Custom built-in test procedure for %(name)s.\"\"\"

        if self.cfg['runtest']:
            cmd = "test-command" 
            run_cmd(cmd, simple=True, log_all=True, log_ok=True)

    def install_step(self):
        \"\"\"Custom install procedure for %(name)s.\"\"\"
       
        cmd = "install command" 
        run_cmd(cmd, log_all=True, simple=True, log_ok=True)

    def sanity_check_step(self):
        \"\"\"Custom sanity check for %(name)s.\"\"\"

        custom_paths = {
                        'files': ['file1', 'file2'],
                        'dirs': ['dir1', 'dir2'],
                       }

        super(%(class_name)s, self).sanity_check_step(custom_paths=custom_paths)

    def make_module_req_guess(self):
        \"\"\"Custom guesses for environment variables (PATH, ...) for %(name)s.\"\"\"

        guesses = super(%(class_name)s, self).make_module_req_guess()

        guesses.update({
                        'VARIABLE': ['value1', 'value2'],
                       })

        return guesses

    def make_module_extra(self):
        \"\"\"Custom extra module file entries for %(name)s.\"\"\"

        txt = super(%(class_name)s, self).make_module_extra()

        txt += self.module_generator.set_environment("VARIABLE", 'value')
        txt += self.module_generator.prepend_paths("PATH_VAR", ['path1', 'path2'])

        return txt
"""

txt = tmpl % {
              'year': datetime.date.today().year,
              'name': name,
              'class_name': encode_class_name(name),
              'parent_import': parent_import,
              'parent': options.parent,
             }

print "Writing template easyblock for %s to %s ..." % (name, easyblock_path)
try:
    dirpath = os.path.dirname(easyblock_path)
    if not os.path.exists(dirpath):
        os.makedirs(dirpath)
    f = open(easyblock_path, "w")
    f.write(txt)
    f.close()
except (IOError, OSError), err:
    sys.stderr.write("ERROR! Writing template easyblock for %s to %s failed: %s" % (name, easyblock_path, err))
    sys.exit(1)
