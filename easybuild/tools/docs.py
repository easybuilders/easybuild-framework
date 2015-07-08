# #
# Copyright 2009-2015 Ghent University
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
Documentation-related functionality

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import copy
import inspect
import os

from easybuild.framework.easyconfig.default import DEFAULT_CONFIG, HIDDEN, sorted_categories
from easybuild.framework.easyconfig.easyconfig import get_easyblock_class
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.utilities import quote_str, import_available_modules
from easybuild.tools.filetools import read_file

FORMAT_RST = 'rst'
FORMAT_TXT = 'txt'

def det_col_width(entries, title):
    """Determine column width based on column title and list of entries."""
    return max(map(len, entries + [title]))


def avail_easyconfig_params_rst(title, grouped_params):
    """
    Compose overview of available easyconfig parameters, in RST format.
    """
    # main title
    lines = [
        title,
        '=' * len(title),
        '',
    ]

    for grpname in grouped_params:
        # group section title
        lines.append("%s parameters" % grpname)
        lines.extend(['-' * len(lines[-1]), ''])

        titles = ["**Parameter name**", "**Description**", "**Default value**"]
        values = [
            ['``' + name + '``' for name in grouped_params[grpname].keys()],
            [x[0] for x in grouped_params[grpname].values()],
            [str(quote_str(x[1])) for x in grouped_params[grpname].values()]
        ]

        lines.extend(mk_rst_table(titles, values))
        lines.append('')

    return '\n'.join(lines)

def avail_easyconfig_params_txt(title, grouped_params):
    """
    Compose overview of available easyconfig parameters, in plain text format.
    """
    # main title
    lines = [
        '%s:' % title,
        '',
    ]

    for grpname in grouped_params:
        # group section title
        lines.append(grpname.upper())
        lines.append('-' * len(lines[-1]))

        # determine width of 'name' column, to left-align descriptions
        nw = max(map(len, grouped_params[grpname].keys()))

        # line by parameter
        for name, (descr, dflt) in sorted(grouped_params[grpname].items()):
            lines.append("{0:<{nw}}   {1:} [default: {2:}]".format(name, descr, str(quote_str(dflt)), nw=nw))
        lines.append('')

    return '\n'.join(lines)

def avail_easyconfig_params(easyblock, output_format):
    """
    Compose overview of available easyconfig parameters, in specified format.
    """
    params = copy.deepcopy(DEFAULT_CONFIG)

    # include list of extra parameters (if any)
    extra_params = {}
    app = get_easyblock_class(easyblock, default_fallback=False)
    if app is not None:
        extra_params = app.extra_options()
    params.update(extra_params)

    # compose title
    title = "Available easyconfig parameters"
    if extra_params:
        title += " (* indicates specific to the %s easyblock)" % app.__name__

    # group parameters by category
    grouped_params = OrderedDict()
    for category in sorted_categories():
        # exclude hidden parameters
        if category[1].upper() in [HIDDEN]:
            continue

        grpname = category[1]
        grouped_params[grpname] = {}
        for name, (dflt, descr, cat) in params.items():
            if cat == category:
                if name in extra_params:
                    # mark easyblock-specific parameters
                    name = '%s*' % name
                grouped_params[grpname].update({name: (descr, dflt)})

        if not grouped_params[grpname]:
            del grouped_params[grpname]

    # compose output, according to specified format (txt, rst, ...)
    avail_easyconfig_params_functions = {
        FORMAT_RST: avail_easyconfig_params_rst,
        FORMAT_TXT: avail_easyconfig_params_txt,
    }
    return avail_easyconfig_params_functions[output_format](title, grouped_params)

def generic_easyblocks(path_to_examples, common_params={}, doc_functions=[]):
    """
    Compose overview of all generic easyblocks
    """
    modules = import_available_modules('easybuild.easyblocks.generic')
    docs = []
    all_blocks = []

    # get all blocks
    for m in modules:
        for name,obj in inspect.getmembers(m, inspect.isclass):
            eb_class = getattr(m, name)
            # skip imported classes that are not easyblocks
            if eb_class.__module__.startswith('easybuild.easyblocks.generic') and eb_class not in all_blocks:
                all_blocks.append(eb_class)

    for eb_class in all_blocks:
        docs.append(doc_easyblock(eb_class, path_to_examples, common_params, doc_functions, all_blocks))

    toc = ['.. contents:: Available generic easyblocks', '    :depth: 1', '']

    return toc + sorted(docs)

def doc_easyblock(eb_class, path_to_examples, common_params, doc_functions, all_blocks):
    """
    Compose overview of one easyblock given class object of the easyblock in rst format
    """
    classname = eb_class.__name__

    lines = [
        '``' + classname + '``',
        '=' * (len(classname)+4),
        '',
    ]

    bases = []
    for b in eb_class.__bases__:
        base = b.__name__ + '_' if b in all_blocks else b.__name__
        bases.append(base)

    derived = '(derives from ' + ', '.join(bases) + ')'
    lines.extend([derived, ''])

    # Description (docstring)
    lines.extend([eb_class.__doc__.strip(), ''])

    # Add extra options, if any
    if eb_class.extra_options():
        extra_parameters = 'Extra easyconfig parameters specific to ``' + classname + '`` easyblock'
        lines.extend([extra_parameters, '-' * len(extra_parameters), ''])
        ex_opt = eb_class.extra_options()

        titles = ['easyconfig parameter', 'description', 'default value']
        values = [
            ['``' + key + '``' for key in ex_opt],
            [val[1] for val in ex_opt.values()],
            ['``' + str(quote_str(val[0])) + '``' for val in ex_opt.values()]
        ]

        lines.extend(mk_rst_table(titles, values))

    # Add commonly used parameters
    if classname in common_params:
        commonly_used = 'Commonly used easyconfig parameters with ``' + classname + '`` easyblock'
        lines.extend([commonly_used, '-' * len(commonly_used)])

        for opt in common_params[classname]:
            param = '* ``' + opt + '`` - ' + DEFAULT_CONFIG[opt][1]
            lines.append(param)
    lines.append('')

    # Add docstring for custom steps
    custom = []
    inh = ''
    for func in doc_functions:
        if func in eb_class.__dict__:
            f = eb_class.__dict__[func]
        elif func in eb_class.__bases__[0].__dict__:
            f = eb_class.__bases__[0].__dict__[func]
            inh = ' (inherited)'

        if f.__doc__:
            custom.append('* ``' + func + '`` - ' + f.__doc__.strip() + inh)

    if custom:
        title = 'Customised steps'
        lines.extend([title, '-' * len(title)] + custom)
        lines.append('')

    # Add example if available
    if classname + '.eb' in os.listdir(os.path.join(path_to_examples)):
        lines.extend(['', 'Example', '-' * 8, '', '::', ''])
        for line in read_file(os.path.join(path_to_examples, classname+'.eb')).split('\n'):
            lines.append('    ' + line.strip())
        lines.append('') # empty line after literal block

    return '\n'.join(lines)

def mk_rst_table(titles, values):
    """
    Returns an rst table with given titles and values (a nested list of string values for each column)
    """
    num_col = len(titles)
    table = []
    col_widths = []
    tmpl = []
    line= []

    # figure out column widths
    for i in range(0, num_col):
        col_widths.append(det_col_width(values[i], titles[i]))

        # make line template
        tmpl.append('{' + str(i) + ':{c}<' + str(col_widths[i]) + '}')
        line.append('') # needed for table line

    line_tmpl = '   '.join(tmpl)
    table_line = line_tmpl.format(*line, c="=")

    table.append(table_line)
    table.append(line_tmpl.format(*titles, c=' '))
    table.append(table_line)

    for i in range(0, len(values[0])):
        table.append(line_tmpl.format(*[v[i] for v in values], c=' '))

    table.extend([table_line, ''])

    return table

