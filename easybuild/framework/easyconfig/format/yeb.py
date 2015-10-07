# #
# Copyright 2013-2015 Ghent University
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
YAML easyconfig format (.yeb)

@author: Caroline De Brouwer (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import os
from vsc.utils import fancylogger

from easybuild.framework.easyconfig.format.format import EasyConfigFormat
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file


_log = fancylogger.getLogger('easyconfig.format.yeb', fname=False)


try:
    import yaml

    def requires_yaml(fn):
        """No-op decorator."""
        return fn

except ImportError as err:
    _log.debug("'yaml' Python module (PyYAML) is not available")

    # PyYAML not available, transform method in a raised EasyBuildError
    def requires_yaml(_):
        """Decorator which raises an EasyBuildError because PyYAML is not available."""
        def fail(*args, **kwargs):
            """Raise EasyBuildError since PyYAML is not available."""
            errmsg = "Python module 'yaml' is not available. Please make sure PyYAML is installed and usable: %s"
            raise EasyBuildError(errmsg, err)

        return fail


YEB_FORMAT_EXTENSION = '.yeb'


class FormatYeb(EasyConfigFormat):
    """Support for easyconfig YAML format"""
    USABLE = True

    def __init__(self, filename):
        """FormatYeb constructor"""
        self.filename = filename
        super(FormatYeb, self).__init__()
        self.log.experimental("Parsing .yeb easyconfigs")

    def validate(self):
        """Format validation"""
        # TODO for YAML

    @requires_yaml
    def get_config_dict(self):
        """
        Return parsed easyconfig as a dictionary, based on specified arguments.
        """
        f = read_file(self.filename)
        return yaml.load(f)

    def parse(self, txt):
        """
        Pre-process txt to extract header, docstring and pyheader, with non-indented section markers enforced.
        """
        #TODO
        pass

    def dump(self, ecfg, default_values, templ_const, templ_val):
        #TODO
        pass

    def extract_comments(self,txt):
        #TODO
        pass


def is_yeb_format(filename, rawcontent):
    """
    Determine whether easyconfig is in .yeb format.
    If filename is None, rawcontent will be used to check the format.
    """
    if filename:
        return os.path.splitext(filename)[-1] == YEB_FORMAT_EXTENSION
    else:
        # FIXME: check whether file starts with '---' (and require it when parsing)
        raise NotImplementedError("Checking for .yeb format based on raw content")
