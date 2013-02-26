# #
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
# #
"""
Unit tests for eb command line options.

@author: Kenneth Hoste (Ghent University)
"""

import os
import re
import sys
import tempfile
from unittest import TestCase, TestLoader
from unittest import main as unittestmain

from easybuild.main import main
from easybuild.tools.options import EasyBuildOptions
from vsc import fancylogger

class CommandLineOptionsTest(TestCase):
    """Testcases for command line options."""

    logfile = None

    def setUp(self):
        """Prepare for running unit tests."""
        # create log file
        fd, self.logfile = tempfile.mkstemp(suffix='.log', prefix='eb-options-test-')
        os.close(fd)
        # open(self.logfile, 'w').write('')  # clear logfile

    def tearDown(self):
        """Post-test cleanup."""
        # removing of self.logfile can't be done here, because it breaks logging
        os.remove(self.logfile)

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
            main(([], self.logfile))
        except:
            pass
        outtxt = open(self.logfile, 'r').read()

        error_msg = "ERROR .* Please provide one or multiple easyconfig files,"
        error_msg += " or use software build options to make EasyBuild search for easyconfigs"
        self.assertTrue(re.search(error_msg, outtxt), "Error message when eb is run without arguments")

    def test_debug(self):
        """Test enabling debug logging."""

        for debug_arg in ['-d', '--debug']:
            args = [
                    '--software-name=somethingrandom',
                    debug_arg,
                   ]
            try:
                main((args, self.logfile))
            except Exception, err:
                myerr = err
            outtxt = open(self.logfile, 'r').read()

            for log_msg_type in ['DEBUG', 'INFO', 'ERROR']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(res, "%s log messages are included when using %s" % (log_msg_type, debug_arg))

    def test_info(self):
        """Test enabling info logging."""

        for info_arg in ['--info']:
            args = [
                    '--software-name=somethingrandom',
                    info_arg,
                   ]
            myerr = None
            try:
                main((args, self.logfile))
            except Exception, err:
                myerr = err
            outtxt = open(self.logfile, 'r').read()

            for log_msg_type in ['INFO', 'ERROR']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(res, "%s log messages are included when using %s (err: %s, out: %s)" % (log_msg_type, info_arg, myerr, outtxt))

            for log_msg_type in ['DEBUG']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(not res, "%s log messages are *not* included when using %s" % (log_msg_type, info_arg))

    def test_quiet(self):
        """Test enabling quiet logging (errors only)."""

        for quiet_arg in ['--quiet']:
            args = [
                    '--software-name=somethingrandom',
                    quiet_arg,
                   ]
            try:
                main((args, self.logfile))
            except:
                pass
            outtxt = open(self.logfile, 'r').read()

            for log_msg_type in ['ERROR']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(res, "%s log messages are included when using %s (outtxt: %s)" % (log_msg_type, quiet_arg, outtxt))

            for log_msg_type in ['DEBUG', 'INFO']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(not res, "%s log messages are *not* included when using %s (outtxt: %s)" % (log_msg_type, quiet_arg, outtxt))

    def test_force(self):
        """Test forcing installation even if the module is already available."""

        # set MODULEPATH to included modules
        orig_modulepath = os.getenv('MODULEPATH', None)
        os.environ['MODULEPATH'] = os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules'))

        # use GCC-4.6.3.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'GCC-4.6.3.eb')

        # check log message without --force
        args = [
                eb_file,
               ]

        error_thrown = False
        try:
            main((args, self.logfile))
        except Exception, err:
            error_thrown = err

        outtxt = open(self.logfile, 'r').read()

        self.assertTrue(not error_thrown, "No error is thrown if software is already installed (error_thrown: %s)" % error_thrown)

        already_msg = "GCC \(version 4.6.3\) is already installed"
        self.assertTrue(re.search(already_msg, outtxt), "Already installed message without --force, outtxt: %s" % outtxt)

        # clear log file
        open(self.logfile, 'w').write('')

        # check that --force works
        args = [
                eb_file,
                '--force',
               ]
        try:
            main((args, self.logfile))
        except:
            pass
        outtxt = open(self.logfile, 'r').read()

        self.assertTrue(not re.search(already_msg, outtxt), "Already installed message not there with --force")

        # restore original MODULEPATH
        if orig_modulepath is not None:
            os.environ['MODULEPATH'] = orig_modulepath
        else:
            os.environ.pop('MODULEPATH')

    def test_job(self):
        """Test submitting build as a job."""

        # set MODULEPATH to included modules
        orig_modulepath = os.getenv('MODULEPATH', None)
        os.environ['MODULEPATH'] = os.path.join(os.path.dirname(__file__), 'modules')

        # use gzip-1.4.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'gzip-1.4.eb')

        # check log message with --job
        for job_args in [  # options passed are reordered, so order here matters to make tests pass
                         ['--debug'],
                         ['--debug', '--stop=configure', '--try-software-name=foo'],
                        ]:

            # clear log file
            outtxt = open(self.logfile, 'w').write('')

            args = [
                    eb_file,
                    '--job',
                   ] + job_args
            try:
                main((args, self.logfile))
            except:
                pass  # main may crash
            outtxt = open(self.logfile, 'r').read()
            # print '\n\n\n\n%s\n\n\n\n\n' % outtxt

            job_msg = "INFO.* Command template for jobs: .* && eb %%\(spec\)s %s\n" % ' '.join(job_args)
            self.assertTrue(re.search(job_msg, outtxt), "Info log message with job command template when using --job (job_msg: %s)" % job_msg)

        # restore original MODULEPATH
        if orig_modulepath is not None:
            os.environ['MODULEPATH'] = orig_modulepath
        else:
            os.environ.pop('MODULEPATH')

    # 'zzz' prefix in the test name is intentional to make this test run last,
    # since it fiddles with the logging infrastructure which may break things
    def test_zzz_logtostdout(self):
        """Testing redirecting log to stdout."""

        for stdout_arg in ['--logtostdout', '-l']:

            _stdout = sys.stdout

            myerr = None
            fd, fn = tempfile.mkstemp()
            fh = os.fdopen(fd, 'w')
            sys.stdout = fh

            args = [
                    '--software-name=somethingrandom',
                    '--robot=.',
                    '--debug',
                    stdout_arg,
                   ]
            try:
                main((args, None))
            except Exception, err:
                myerr = err

            # make sure we restore
            sys.stdout.flush()
            sys.stdout = _stdout
            fancylogger.logToScreen(enable=False, stdout=True)

            outtxt = open(fn, 'r').read()

            self.assertTrue(len(outtxt) > 100, "Log messages are printed to stdout when %s is used (outtxt: %s)" % (stdout_arg, outtxt))

            # cleanup
            os.remove(fn)

        fancylogger.logToFile(self.logfile)

    def test_list_toolchains(self):
        """Test listing known compiler toolchains."""

        args = [
                '--list-toolchains',
                '--unittest-file=%s' % self.logfile,
               ]
        try:
            main((args, None))
        except:
            pass
        outtxt = open(self.logfile, 'r').read()

        info_msg = r"INFO List of known toolchains \(toolchainname: module\[,module\.\.\.\]\):"
        self.assertTrue(re.search(info_msg, outtxt), "Info message with list of known compiler toolchains")
        for tc in ["dummy", "goalf", "ictce"]:
            self.assertTrue(re.search("%s: " % tc, outtxt), "Toolchain %s is included in list of known compiler toolchains")

    def test_no_such_software(self):
        """Test using no arguments."""

        args = [
                '--software-name=nosuchsoftware',
                '--robot=.',
                '--debug',
               ]
        myerr = None
        try:
            main((args, self.logfile))
        except Exception, err:
            myerr = err
        outtxt = open(self.logfile, 'r').read()

        # error message when template is not found
        error_msg1 = "ERROR .* No easyconfig files found for software nosuchsoftware, and no templates available. I'm all out of ideas."
        # error message when template is found
        error_msg2 = "ERROR .* Unable to find an easyconfig for the given specifications"
        msg = "Error message when eb can't find software with specified name (myerr: %s, outtxt: %s)" % (myerr, outtxt)
        self.assertTrue(re.search(error_msg1, outtxt) or re.search(error_msg2, outtxt), msg)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(CommandLineOptionsTest)

if __name__ == '__main__':
    unittestmain()
