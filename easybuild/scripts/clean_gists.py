#!/usr/bin/env python
##
# Copyright 2014 Ward Poelmans
#
# https://github.com/easybuilders/easybuild
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

:author: Ward Poelmans
"""


import re

from vsc.utils import fancylogger
from vsc.utils.generaloption import simple_option
from vsc.utils.rest import RestClient
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.github import GITHUB_API_URL, HTTP_STATUS_OK, GITHUB_EASYCONFIGS_REPO
from easybuild.tools.github import GITHUB_EB_MAIN, fetch_github_token
from easybuild.tools.options import EasyBuildOptions

HTTP_DELETE_OK = 204


def main():
    """the main function"""
    fancylogger.logToScreen(enable=True, stdout=True)
    fancylogger.setLogLevelInfo()

    options = {
        'github-user': ('Your github username to use', None, 'store', None, 'g'),
        'closed-pr': ('Delete all gists from closed pull-requests', None, 'store_true', True, 'p'),
        'all': ('Delete all gists from Easybuild ', None, 'store_true', False, 'a'),
        'orphans': ('Delete all gists without a pull-request', None, 'store_true', False, 'o'),
    }

    go = simple_option(options)
    log = go.log

    if not (go.options.all or go.options.closed_pr or go.options.orphans):
        raise EasyBuildError("Please tell me what to do?")

    if go.options.github_user is None:
        eb_go = EasyBuildOptions(envvar_prefix='EASYBUILD', go_args=[])
        username = eb_go.options.github_user
        log.debug("Fetch github username from easybuild, found: %s", username)
    else:
        username = go.options.github_user

    if username is None:
        raise EasyBuildError("Could not find a github username")
    else:
        log.info("Using username = %s", username)

    token = fetch_github_token(username)

    gh = RestClient(GITHUB_API_URL, username=username, token=token)

    all_gists = []
    cur_page = 1
    while True:
        status, gists = gh.gists.get(per_page=100, page=cur_page)

        if status != HTTP_STATUS_OK:
            raise EasyBuildError("Failed to get a lists of gists for user %s: error code %s, message = %s",
                                 username, status, gists)
        if gists:
            all_gists.extend(gists)
            cur_page += 1
        else:
            break

    log.info("Found %s gists", len(all_gists))
    regex = re.compile(r"(EasyBuild test report|EasyBuild log for failed build).*?(?:PR #(?P<PR>[0-9]+))?\)?$")

    pr_cache = {}
    num_deleted = 0

    for gist in all_gists:
        if not gist["description"]:
            continue
        re_pr_num = regex.search(gist["description"])
        delete_gist = False

        if re_pr_num:
            log.debug("Found a Easybuild gist (id=%s)", gist["id"])
            pr_num = re_pr_num.group("PR")
            if go.options.all:
                delete_gist = True
            elif pr_num and go.options.closed_pr:
                log.debug("Found Easybuild test report for PR #%s", pr_num)

                if pr_num not in pr_cache:
                    status, pr = gh.repos[GITHUB_EB_MAIN][GITHUB_EASYCONFIGS_REPO].pulls[pr_num].get()
                    if status != HTTP_STATUS_OK:
                        raise EasyBuildError("Failed to get pull-request #%s: error code %s, message = %s",
                                             pr_num, status, pr)
                    pr_cache[pr_num] = pr["state"]

                if pr_cache[pr_num] == "closed":
                    log.debug("Found report from closed PR #%s (id=%s)", pr_num, gist["id"])
                    delete_gist = True

            elif not pr_num and go.options.orphans:
                log.debug("Found Easybuild test report without PR (id=%s)", gist["id"])
                delete_gist = True

        if delete_gist:
            status, del_gist = gh.gists[gist["id"]].delete()

            if status != HTTP_DELETE_OK:
                raise EasyBuildError("Unable to remove gist (id=%s): error code %s, message = %s",
                                     gist["id"], status, del_gist)
            else:
                log.info("Delete gist with id=%s", gist["id"])
                num_deleted += 1

    log.info("Deleted %s gists", num_deleted)


if __name__ == '__main__':
    main()
