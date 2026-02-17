#!/usr/bin/env python

import os
import sys
import runpy
import subprocess

from easybuild.tools.build_log import print_msg
from easybuild.tools.filetools import mkdir


EASYBUILD_MAIN = 'easybuild.main'


def verbose(msg):
    """Prints verbose messages if EB_VERBOSE is set."""
    if os.environ.get("EB_VERBOSE"):
        print(f">> {msg}")


if __name__ == "__main__":
    # runpy.run_module mimics `python -m`
    # its return value is the module’s globals dictionary
    # EB returns only if its exit code is 0 and `--bwrap` is set
    verbose(f'runpy.run_module({EASYBUILD_MAIN}, run_name="__main__", alter_sys=True)')
    result = runpy.run_module(EASYBUILD_MAIN, run_name="__main__", alter_sys=True)

    bwrap_info = result['BWRAP_INFO']
    bwrap_modules = bwrap_info['modules_to_install']

    if bwrap_modules:
        verbose(f'bwrap info: {bwrap_info}')
        installpath_software = bwrap_info['installpath_software']
        installpath_modules = bwrap_info['installpath_modules']
        bwrap_installpath = bwrap_info['bwrap_installpath']
        bwrap_installpath_modules = os.path.join(bwrap_installpath, 'modules')
        bwrap_cmd = ['bwrap', '--dev-bind', '/', '/']

        for mod in bwrap_modules:
            spath = os.path.join(os.path.realpath(installpath_software), mod)
            bwrap_spath = os.path.join(bwrap_installpath, 'software', mod)
            mkdir(spath, parents=True)
            mkdir(bwrap_spath, parents=True)
            bwrap_cmd.extend(['--bind', bwrap_spath, spath])

        eb_cmd = ['python', '-m', EASYBUILD_MAIN] + sys.argv[1:]
        bwrap_options = ['--disable-bwrap', f'--installpath-modules={bwrap_installpath_modules}']
        cmd = bwrap_cmd + eb_cmd + bwrap_options
        verbose(' '.join(cmd))
        print_msg(f'Building/installing in bubblewrap namespace at {bwrap_installpath}')
        sys.exit(subprocess.run(cmd).returncode)
