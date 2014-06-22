#!/usr/bin/env python
##
# Copyright 2014 Ward Poelmans
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
This script cleans up old gists created by easybuild. It checks if the gists was
created from a pull-request and if that PR is closed/merged, it will delete the gist.
You need a github token for this. The script uses the same username and token
as easybuild. Optionally, you can specify a different github username.

Usage: ./clean_gists.py [<git username>]


@author: Ward Poelmans
"""


import re
import sys

from vsc.utils import fancylogger
from vsc.utils.rest import RestClient
from easybuild.tools.github import GITHUB_API_URL, HTTP_STATUS_OK, GITHUB_EASYCONFIGS_REPO, GITHUB_EB_MAIN, fetch_github_token
from easybuild.tools.options import EasyBuildOptions

HTTP_DELETE_OK = 204


def main(username=None):
    """the main function"""
    fancylogger.setLogLevelInfo()
    fancylogger.logToScreen(enable=True, stdout=True)
    log = fancylogger.getLogger()

    if username is None:
        eb_go = EasyBuildOptions(envvar_prefix='EASYBUILD', go_args=[])
        username = eb_go.options.github_user

    if username is None:
        log.error("Could not find a github username")
    else:
        log.info("Using username = %s" % username)

    token = fetch_github_token(username)

    gh = RestClient(GITHUB_API_URL, username=username, token=token)
    # ToDo: add support for pagination
    status, gists = gh.gists.get(per_page=100)

    if status != HTTP_STATUS_OK:
        log.error("Failed to get a lists of gists for user %s: error code %s, message = %s" %
                  (username, status, gists))
    else:
        log.info("Found %s gists" % len(gists))

    regex = re.compile("(EasyBuild test report for easyconfigs|EasyBuild log for failed build of).*PR #([0-9]+)")

    for gist in gists:
        re_pr_num = regex.search(gist["description"])
        if re_pr_num:
            pr_num = re_pr_num.group(2)
            log.info("Found Easybuild test report for PR #%s" % pr_num)
            status, pr = gh.repos[GITHUB_EB_MAIN][GITHUB_EASYCONFIGS_REPO].pulls[pr_num].get()

            if status != HTTP_STATUS_OK:
                log.error("Failed to get pull-request #%s: error code %s, message = %s" %
                          (pr_num, status, pr))

            if pr["state"] == "closed":
                log.debug("Found gist of closed PR #%s" % pr_num)

                status, del_gist = gh.gists[gist["id"]].delete()

                if status != HTTP_DELETE_OK:
                    log.error("Unable to remove gist (id=%s): error code %s, message = %s" %
                              (gist["id"], status, del_gist))
                else:
                    log.info("Delete gist from closed PR #%s" % pr_num)


if __name__ == '__main__':
    if len(sys.argv) == 2:
        main(username=sys.argv[1])
    else:
        main()
