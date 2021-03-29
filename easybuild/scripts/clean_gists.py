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

from easybuild.base import fancylogger
from easybuild.base.generaloption import simple_option
from easybuild.base.rest import RestClient
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.github import GITHUB_API_URL, HTTP_STATUS_OK, GITHUB_EASYCONFIGS_REPO, GITHUB_EASYBLOCKS_REPO
from easybuild.tools.github import GITHUB_EB_MAIN, fetch_github_token
from easybuild.tools.options import EasyBuildOptions
from easybuild.tools.py2vs3 import HTTPError, URLError

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
        'dry-run': ("Only show which gists will be deleted but don't actually delete them", None, 'store_true', False),
    }

    go = simple_option(options)
    log = go.log

    if not (go.options.all or go.options.closed_pr or go.options.orphans):
        raise EasyBuildError("Please tell me what to do?")

    if go.options.github_user is None:
        EasyBuildOptions.DEFAULT_LOGLEVEL = None  # Don't overwrite log level
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
    re_eb_gist = re.compile(r"(EasyBuild test report|EasyBuild log for failed build)(.*?)$")
    re_pr_nr = re.compile(r"(EB )?PR #([0-9]+)")

    pr_cache = {}
    num_deleted = 0

    for gist in all_gists:
        if not gist["description"]:
            continue

        gist_match = re_eb_gist.search(gist["description"])

        if not gist_match:
            log.debug("Found a non-Easybuild gist (id=%s)", gist["id"])
            continue

        log.debug("Found an Easybuild gist (id=%s)", gist["id"])

        pr_data = gist_match.group(2)

        pr_nrs_matches = re_pr_nr.findall(pr_data)

        if go.options.all:
            delete_gist = True
        elif not pr_nrs_matches:
            log.debug("Found Easybuild test report without PR (id=%s).", gist["id"])
            delete_gist = go.options.orphans
        elif go.options.closed_pr:
            # All PRs must be closed
            delete_gist = True
            for pr_nr_match in pr_nrs_matches:
                eb_str, pr_num = pr_nr_match
                if eb_str or GITHUB_EASYBLOCKS_REPO in pr_data:
                    repo = GITHUB_EASYBLOCKS_REPO
                else:
                    repo = GITHUB_EASYCONFIGS_REPO

                cache_key = "%s-%s" % (repo, pr_num)

                if cache_key not in pr_cache:
                    try:
                        status, pr = gh.repos[GITHUB_EB_MAIN][repo].pulls[pr_num].get()
                    except HTTPError as e:
                        status, pr = e.code, e.msg
                    if status != HTTP_STATUS_OK:
                        raise EasyBuildError("Failed to get pull-request #%s: error code %s, message = %s",
                                             pr_num, status, pr)
                    pr_cache[cache_key] = pr["state"]

                if pr_cache[cache_key] == "closed":
                    log.debug("Found report from closed %s PR #%s (id=%s)", repo, pr_num, gist["id"])
                elif delete_gist:
                    if len(pr_nrs_matches) > 1:
                        log.debug("Found at least 1 PR, that is not closed yet: %s/%s (id=%s)",
                                  repo, pr_num, gist["id"])
                    delete_gist = False
        else:
            delete_gist = True

        if delete_gist:
            if go.options.dry_run:
                log.info("DRY-RUN: Delete gist with id=%s", gist["id"])
                num_deleted += 1
                continue
            try:
                status, del_gist = gh.gists[gist["id"]].delete()
            except HTTPError as e:
                status, del_gist = e.code, e.msg
            except URLError as e:
                status, del_gist = None, e.reason

            if status != HTTP_DELETE_OK:
                log.warning("Unable to remove gist (id=%s): error code %s, message = %s",
                            gist["id"], status, del_gist)
            else:
                log.info("Deleted gist with id=%s", gist["id"])
                num_deleted += 1

    if go.options.dry_run:
        log.info("DRY-RUN: Would delete %s gists", num_deleted)
    else:
        log.info("Deleted %s gists", num_deleted)


if __name__ == '__main__':
    main()
