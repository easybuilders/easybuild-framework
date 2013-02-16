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
"""Unit tests for eb command line options.

@author: Kenneth Hoste (Ghent University)
"""

import os
import re
import tempfile
from unittest import TestCase, TestLoader

from easybuild.main import main
from easybuild.tools.build_log import init_logger
from easybuild.tools.options import EasyBuildOptions

class CommandLineOptionsTest(TestCase):
    """Testcases for command line options."""

    # create log file
    fd, logfile = tempfile.mkstemp(suffix='.log', prefix='eb-options-test-')
    os.close(fd)

    def setUp(self):
        """Prepare for running unit tests."""
        open(self.logfile, 'w').write('')  # clear logfile

    def tearDown(self):
        """Post-test cleanup."""
        # removing of self.logfile can't be done here, because it breaks logging
        pass

    def test_help_short(self, txt=None):
        """Test short help message."""

        if txt is None:
            topt = EasyBuildOptions(
                                    go_args=['-h'],
                                    go_nosystemexit=True,  # when printing help, optparse ends with sys.exit
                                    go_columns=100,  # fix col size for reproducible unittest output
                                    help_to_string=True,  # don't print to stdout, but to StingIO fh,
                                    prog='easybuildoptions_test',  # generate as if called from generaloption.py
                                   )

            outtxt = topt.parser.help_to_file.getvalue()
        else:
            outtxt = txt
       
        self.assertTrue(re.search(' -h ', outtxt), "Only short options included in short help")
        self.assertTrue(re.search("show short help message and exit", outtxt), "Documentation included in short help")
        self.assertEqual(re.search("--short-help ", outtxt), None, "Long options not included in short help")
        self.assertEqual(re.search("Software search and build options", outtxt), None, "Not all option groups included in short help (1)")
        self.assertEqual(re.search("Regression test options", outtxt), None, "Not all option groups included in short help (2)")

    def test_help_long(self):
        """Test long help message."""
        
        topt = EasyBuildOptions(
                                go_args=['-H'],
                                go_nosystemexit=True,  # when printing help, optparse ends with sys.exit
                                go_columns=100,  # fix col size for reproducible unittest output
                                help_to_string=True,  # don't print to stdout, but to StingIO fh,
                                prog='easybuildoptions_test',  # generate as if called from generaloption.py
                               )
        outtxt = topt.parser.help_to_file.getvalue()
        
        self.assertTrue(re.search("-H, --help", outtxt), "Long documentation expanded in long help")
        self.assertTrue(re.search("show short help message and exit", outtxt), "Documentation included in long help")
        self.assertTrue(re.search("Software search and build options", outtxt), "Not all option groups included in short help (1)")
        self.assertTrue(re.search("Regression test options", outtxt), "Not all option groups included in short help (2)")

    def test_no_args(self):
        """Test using no arguments."""

        try:
            main(args=[], exit_on_error=False, logfile=self.logfile, keep_logs=True)
        except:
            pass
        outtxt = open(self.logfile, 'r').read()

        error_msg = "ERROR .* Please provide one or multiple easyconfig files,"
        error_msg += " or use software build options to make EasyBuild search for easyconfigs"
        self.assertTrue(re.search(error_msg, outtxt), "Error message when eb is run without arguments")

    def test_no_such_software(self):
        """Test using no arguments."""

        args = [
                '--software-name=nosuchsoftware',
                '--robot',
               ]
        try:
            main(args=args, exit_on_error=False, logfile=self.logfile, keep_logs=True)
        except:
            pass
        outtxt = open(self.logfile, 'r').read()

        error_msg = "ERROR .* Unable to find an easyconfig for the given specifications"
        self.assertTrue(re.search(error_msg, outtxt), "Error message when eb can't find software with specified name")


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(CommandLineOptionsTest)
