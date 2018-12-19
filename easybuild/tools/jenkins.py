# #
# Copyright 2012-2018 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
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
# #
"""
Set of fucntions to help with jenkins setup

:author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import xml.dom.minidom as xml

from datetime import datetime
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.version import FRAMEWORK_VERSION, EASYBLOCKS_VERSION


_log = fancylogger.getLogger('jenkins', fname=False)


def write_to_xml(succes, failed, filename):
    """
    Create xml output, using minimal output required according to
    http://stackoverflow.com/questions/4922867/junit-xml-format-specification-that-hudson-supports
    """
    dom = xml.getDOMImplementation()
    root = dom.createDocument(None, "testsuite", None)

    def create_testcase(name):
        el = root.createElement("testcase")
        el.setAttribute("name", name)
        return el

    def create_failure(name, error_type, error):
        el = create_testcase(name)

        # encapsulate in CDATA section
        error_text = root.createCDATASection("\n%s\n" % error)
        failure_el = root.createElement("failure")
        failure_el.setAttribute("type", error_type)
        el.appendChild(failure_el)
        el.lastChild.appendChild(error_text)
        return el

    def create_success(name, stats):
        el = create_testcase(name)
        text = "\n".join(["%s=%s" % (key, value) for (key, value) in stats.items()])
        build_stats = root.createCDATASection("\n%s\n" % text)
        system_out = root.createElement("system-out")
        el.appendChild(system_out)
        el.lastChild.appendChild(build_stats)
        return el

    properties = root.createElement("properties")
    framework_version = root.createElement("property")
    framework_version.setAttribute("name", "easybuild-framework-version")
    framework_version.setAttribute("value", str(FRAMEWORK_VERSION))
    properties.appendChild(framework_version)
    easyblocks_version = root.createElement("property")
    easyblocks_version.setAttribute("name", "easybuild-easyblocks-version")
    easyblocks_version.setAttribute("value", str(EASYBLOCKS_VERSION))
    properties.appendChild(easyblocks_version)

    time = root.createElement("property")
    time.setAttribute("name", "timestamp")
    time.setAttribute("value", str(datetime.now()))
    properties.appendChild(time)

    root.firstChild.appendChild(properties)

    for (obj, fase, error, _) in failed:
        # try to pretty print
        try:
            el = create_failure(obj.full_mod_name, fase, error)
        except AttributeError:
            el = create_failure(obj, fase, error)

        root.firstChild.appendChild(el)

    for (obj, stats) in succes:
        el = create_success(obj.full_mod_name, stats)
        root.firstChild.appendChild(el)

    try:
        output_file = open(filename, "w")
        root.writexml(output_file)
        output_file.close()
    except IOError, err:
        raise EasyBuildError("Failed to write out XML file %s: %s", filename, err)


def aggregate_xml_in_dirs(base_dir, output_filename):
    """
    Finds all the xml files in the dirs and takes the testcase attribute out of them.
    These are then put in a single output file.
    """
    dom = xml.getDOMImplementation()
    root = dom.createDocument(None, "testsuite", None)
    root.documentElement.setAttribute("name", base_dir)
    properties = root.createElement("properties")
    framework_version = root.createElement("property")
    framework_version.setAttribute("name", "easybuild-framework-version")
    framework_version.setAttribute("value", str(FRAMEWORK_VERSION))
    properties.appendChild(framework_version)
    easyblocks_version = root.createElement("property")
    easyblocks_version.setAttribute("name", "easybuild-easyblocks-version")
    easyblocks_version.setAttribute("value", str(EASYBLOCKS_VERSION))
    properties.appendChild(easyblocks_version)

    time_el = root.createElement("property")
    time_el.setAttribute("name", "timestamp")
    time_el.setAttribute("value", str(datetime.now()))
    properties.appendChild(time_el)

    root.firstChild.appendChild(properties)

    dirs = filter(os.path.isdir, [os.path.join(base_dir, d) for d in os.listdir(base_dir)])

    succes = 0
    total = 0

    for d in dirs:
        xml_file = sorted(glob.glob(os.path.join(d, "*.xml")))
        if xml_file:
            # take the first one (should be only one present)
            xml_file = xml_file[0]
            try:
                dom = xml.parse(xml_file)
            except IOError, err:
                raise EasyBuildError("Failed to read/parse XML file %s: %s", xml_file, err)
            # only one should be present, we are just discarding the rest
            testcase = dom.getElementsByTagName("testcase")[0]
            root.firstChild.appendChild(testcase)

            total += 1
            if not testcase.getElementsByTagName("failure"):
                succes += 1

    comment = root.createComment("%s out of %s builds succeeded" % (succes, total))
    root.firstChild.insertBefore(comment, properties)
    try:
        output_file = open(output_filename, "w")
        root.writexml(output_file, addindent="\t", newl="\n")
        output_file.close()
    except IOError, err:
        raise EasyBuildError("Failed to write out XML file %s: %s", output_filename, err)

    print "Aggregate regtest results written to %s" % output_filename
