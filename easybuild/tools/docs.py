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
import re
import sys

from easybuild.framework.easyconfig.default import DEFAULT_CONFIG, HIDDEN, sorted_categories
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig.constants import EASYCONFIG_CONSTANTS
from easybuild.framework.easyconfig.easyconfig import get_easyblock_class
from easybuild.framework.easyconfig.licenses import EASYCONFIG_LICENSES_DICT
from easybuild.framework.easyconfig.templates import TEMPLATE_NAMES_CONFIG, TEMPLATE_NAMES_EASYCONFIG
from easybuild.framework.easyconfig.templates import TEMPLATE_NAMES_LOWER, TEMPLATE_NAMES_LOWER_TEMPLATE
from easybuild.framework.easyconfig.templates import TEMPLATE_NAMES_EASYBLOCK_RUN_STEP, TEMPLATE_CONSTANTS
from easybuild.framework.extension import Extension
from easybuild.tools.filetools import read_file
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.utilities import import_available_modules, mk_rst_table, quote_str, FORMAT_TXT, FORMAT_RST
from vsc.utils import fancylogger
from vsc.utils.missing import nub


_log = fancylogger.getLogger('easyblock')

DETAILED = "detailed"
SIMPLE = "simple"

### AVAIL CFGFILE CONSTANTS ###
def avail_cfgfile_constants(go_cfg_constants, output_format=FORMAT_TXT):
    """
    Return overview of constants supported in configuration files.
    """
    avail_cfgfile_constants_functions = {
        FORMAT_TXT: avail_cfgfile_constants_txt,
        FORMAT_RST: avail_cfgfile_constants_rst,
    }

    return avail_cfgfile_constants_functions[output_format](go_cfg_constants)

def avail_cfgfile_constants_txt(go_cfg_constants):
    lines = [
        "Constants available (only) in configuration files:",
        "syntax: %(CONSTANT_NAME)s",
    ]
    for section in go_cfg_constants:
        lines.append('')
        if section != go_cfg_constants['DEFAULT']:
            section_title = "only in '%s' section:" % section
            lines.append(section_title)
        for cst_name, (cst_value, cst_help) in sorted(go_cfg_constants[section].items()):
            lines.append("* %s: %s [value: %s]" % (cst_name, cst_help, cst_value))
    return '\n'.join(lines)

def avail_cfgfile_constants_rst(go_cfg_constants):
    title = "Constants available (only) in configuration files"
    lines = [title, "=" * len(title), '']

    for section in go_cfg_constants:
        lines.append('')
        if section != go_cfg_constants['DEFAULT']:
            section_title = "only in '%s' section:" %section
            lines.extend([section_title, '-' * len(section_title), ''])
        table_titles = ["Constant name", "Constant help", "Constant value"]
        table_values = [
            ['``' + name + '``' for name in go_cfg_constants[section].keys()],
            [tup[1] for tup in go_cfg_constants[section].values()],
            ['``' + tup[0] + '``' for tup in go_cfg_constants[section].values()],
        ]
        lines.extend(mk_rst_table(table_titles, table_values))

    return '\n'.join(lines)


### AVAIL EASYCONFIG CONSTANTS ###
def avail_easyconfig_constants(output_format=FORMAT_TXT):
    """Generate the easyconfig constant documentation"""
    avail_easyconfig_constants_functions = {
        FORMAT_TXT: avail_easyconfig_constants_txt,
        FORMAT_RST: avail_easyconfig_constants_rst,
    }

    return avail_easyconfig_constants_functions[output_format]()

def avail_easyconfig_constants_txt():
    """Generate easyconfig constant documentation in txt format"""
    indent_l0 = " " * 2
    indent_l1 = indent_l0 + " " * 2
    doc = []

    doc.append("Constants that can be used in easyconfigs")
    for cst, (val, descr) in EASYCONFIG_CONSTANTS.items():
        doc.append('%s%s: %s (%s)' % (indent_l1, cst, val, descr))

    return "\n".join(doc)

def avail_easyconfig_constants_rst():
    """Generate easyconfig constant documentation in rst format"""
    title = "Constants that can be used in easyconfigs"
    doc = [title, "=" * len(title), '']

    table_titles = [
        "Constant name",
        "Constant value",
        "Description",
    ]

    table_values = [
        ["``%s``" % cst for cst in EASYCONFIG_CONSTANTS.keys()],
        ["``%s``" % cst[0] for cst in EASYCONFIG_CONSTANTS.values()],
        [cst[1] for cst in EASYCONFIG_CONSTANTS.values()],
    ]

    doc.extend(mk_rst_table(table_titles, table_values))

    return "\n".join(doc)

### AVAIL EASYCONFIG LICENSES ###
def avail_easyconfig_licenses(output_format=FORMAT_TXT):
    """Generate the easyconfig licenses documentation"""
    avail_easyconfig_licenses_functions = {
        FORMAT_TXT: avail_easyconfig_licenses_txt,
        FORMAT_RST: avail_easyconfig_licenses_rst,
    }

    return avail_easyconfig_licenses_functions[output_format]()

def avail_easyconfig_licenses_txt():
    """Generate easyconfig license documentation in txt format"""
    indent_l0 = " " * 2
    indent_l1 = indent_l0 + " " * 2
    doc = []

    doc.append("Constants that can be used in easyconfigs")
    for lic_name, lic in EASYCONFIG_LICENSES_DICT.items():
        doc.append('%s%s: %s (version %s)' % (indent_l1, lic_name, lic.description, lic.version))

    return "\n".join(doc)

def avail_easyconfig_licenses_rst():
    """Generate easyconfig license documentation in rst format"""
    title = "Constants that can be used in easyconfigs"
    doc = [title, "=" * len(title), '']

    table_titles = [
        "License name",
        "License description",
        "Version",
    ]

    table_values = [
        ["``%s``" % name for name in EASYCONFIG_LICENSES_DICT.keys()],
        ["%s" % lic.description for lic in EASYCONFIG_LICENSES_DICT.values()],
        ["``%s``" % lic.version for lic in EASYCONFIG_LICENSES_DICT.values()],
    ]

    doc.extend(mk_rst_table(table_titles, table_values))

    return "\n".join(doc)


### AVAIL EASYCONFIG PARAMS ####
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
            ['``' + name + '``' for name in grouped_params[grpname].keys()],  # parameter name
            [x[0] for x in grouped_params[grpname].values()],  # description
            [str(quote_str(x[1])) for x in grouped_params[grpname].values()]  # default value
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


def avail_easyconfig_params(easyblock, output_format=FORMAT_TXT):
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


### AVAIL EASYCONFIG TEMPLATES ###
def avail_easyconfig_templates(output_format=FORMAT_TXT):
    """Generate the templating documentation"""
    template_doc_functions = {
        FORMAT_TXT: avail_easyconfig_templates_txt,
        FORMAT_RST: avail_easyconfig_templates_rst,
    }

    return template_doc_functions[output_format]()

def avail_easyconfig_templates_txt():
    """ Returns template documentation in plain text format """
    # This has to reflect the methods/steps used in easyconfig _generate_template_values
    indent_l0 = " " * 2
    indent_l1 = indent_l0 + " " * 2
    doc = []

    # step 1: add TEMPLATE_NAMES_EASYCONFIG
    doc.append('Template names/values derived from easyconfig instance')
    for name in TEMPLATE_NAMES_EASYCONFIG:
        doc.append("%s%s: %s" % (indent_l1, name[0], name[1]))

    # step 2: add remaining config
    doc.append('Template names/values as set in easyconfig')
    for name in TEMPLATE_NAMES_CONFIG:
        doc.append("%s%s" % (indent_l1, name))

    # step 3. make lower variants
    doc.append('Lowercase values of template values')
    for name in TEMPLATE_NAMES_LOWER:
        doc.append("%s%s: lower case of value of %s" % (indent_l1, TEMPLATE_NAMES_LOWER_TEMPLATE % {'name': name}, name))

    # step 4. template_values can/should be updated from outside easyconfig
    # (eg the run_setp code in EasyBlock)
    doc.append('Template values set outside EasyBlock runstep')
    for name in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP:
        doc.append("%s%s: %s" % (indent_l1, name[0], name[1]))

    doc.append('Template constants that can be used in easyconfigs')
    for cst in TEMPLATE_CONSTANTS:
        doc.append('%s%s: %s (%s)' % (indent_l1, cst[0], cst[2], cst[1]))

    return '\n'.join(doc)

def avail_easyconfig_templates_rst():
    """ Returns template documentation in rst format """
    doc = []
    titles = ['Template name', 'Template value']

    instance_title = 'Template names/values derived from easyconfig instance'
    doc.extend([instance_title, '-' * len(instance_title)])
    table_values = [
        ['``%s``' % name[0] for name in TEMPLATE_NAMES_EASYCONFIG],
        [name[1] for name in TEMPLATE_NAMES_EASYCONFIG],
    ]
    doc.extend(mk_rst_table(titles, table_values))

    config_title = 'Template names/values as set in easyconfig'
    doc.extend([config_title, '-' * len(config_title)])
    for name in TEMPLATE_NAMES_CONFIG:
        doc.append('* ``%s``' % name)
    doc.append('')

    lower_title = 'Lowercase values of template values'
    doc.extend([lower_title, '-' * len(lower_title)])
    table_values = [
        ['``%s``' % TEMPLATE_NAMES_LOWER_TEMPLATE % {'name': name} for name in TEMPLATE_NAMES_LOWER],
        ['lower case of value of %s' % name for name in TEMPLATE_NAMES_LOWER],
    ]
    doc.extend(mk_rst_table(titles, table_values))

    outside_title = 'Template values set outside EasyBlock runstep'
    doc.extend([outside_title, '-' * len(outside_title)])
    table_values = [
        ['``%s``' % name[0] for name in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP],
        [name[1] for name in TEMPLATE_NAMES_EASYBLOCK_RUN_STEP],
    ]
    doc.extend(mk_rst_table(titles, table_values))

    const_title = 'Template constants that can be used in easyconfigs'
    doc.extend([const_title, '-' * len(const_title)])
    titles = ['Constant', 'Template value', 'Template name']
    table_values = [
        ['``%s``' % cst[0] for cst in TEMPLATE_CONSTANTS],
        [cst[2] for cst in TEMPLATE_CONSTANTS],
        ['``%s``' % cst[1] for cst in TEMPLATE_CONSTANTS],
    ]
    doc.extend(mk_rst_table(titles, table_values))

    return '\n'.join(doc)


### LIST EASYBLOCKS ###
def avail_classes_tree(classes, class_names, locations, detailed, format_strings, depth=0):
    """Print list of classes as a tree."""
    txt = []

    for class_name in class_names:
        class_info = classes[class_name]
        if detailed:
            mod = class_info['module']
            loc = ''
            if mod in locations:
                loc = '@ %s' % locations[mod]
            txt.append(format_strings['zero_indent'] + format_strings['indent'] * depth +
                        format_strings['sep'] + "%s (%s %s)" % (class_name, mod, loc))
        else:
            txt.append(format_strings['zero_indent'] + format_strings['indent'] * depth + format_strings['sep'] + class_name)
        if 'children' in class_info:
            txt.extend(avail_classes_tree(classes, class_info['children'], locations, detailed, format_strings, depth + 1))
    return txt

def list_easyblocks(list_easyblocks=SIMPLE, output_format=FORMAT_TXT):
    format_strings = {
        FORMAT_TXT : {
            'det_root_templ': "%s (%s%s)",
            'root_templ': "%s",
            'zero_indent': '',
            'indent': "|   ",
            'sep': "|-- ",
        },
        FORMAT_RST : {
            'det_root_templ': "* **%s** (%s%s)",
            'root_templ': "* **%s**",
            'zero_indent': '    ',
            'indent': '    ',
            'sep': '* ',
        }
    }
    return gen_list_easyblocks(list_easyblocks, format_strings[output_format])


def gen_list_easyblocks(list_easyblocks, format_strings):
    """Get a class tree for easyblocks."""
    detailed = list_easyblocks == DETAILED
    module_regexp = re.compile(r"^([^_].*)\.py$")

    # finish initialisation of the toolchain module (ie set the TC_CONSTANT constants)
    search_toolchain('')

    locations = {}
    for package in ["easybuild.easyblocks", "easybuild.easyblocks.generic"]:
        __import__(package)

        # determine paths for this package
        paths = sys.modules[package].__path__

        # import all modules in these paths
        for path in paths:
            if os.path.exists(path):
                for f in os.listdir(path):
                    res = module_regexp.match(f)
                    if res:
                        easyblock = '%s.%s' % (package, res.group(1))
                        if easyblock not in locations:
                            __import__(easyblock)
                            locations.update({easyblock: os.path.join(path, f)})
                        else:
                            _log.debug("%s already imported from %s, ignoring %s",
                                               easyblock, locations[easyblock], path)

    def add_class(classes, cls):
        """Add a new class, and all of its subclasses."""
        children = cls.__subclasses__()
        classes.update({cls.__name__: {
            'module': cls.__module__,
            'children': [x.__name__ for x in children]
        }})
        for child in children:
            add_class(classes, child)

    roots = [EasyBlock, Extension]

    classes = {}
    for root in roots:
        add_class(classes, root)

    # Print the tree, start with the roots
    txt = []

    for root in roots:
        root = root.__name__
        if detailed:
            mod = classes[root]['module']
            loc = ''
            if mod in locations:
                loc = ' @ %s' % locations[mod]
            txt.append(format_strings['det_root_templ'] % (root, mod, loc))
        else:
            txt.append(format_strings['root_templ'] % root)

        if 'children' in classes[root]:
            txt.extend(avail_classes_tree(classes, classes[root]['children'], locations, detailed, format_strings))
            txt.append("")

    return '\n'.join(txt)


### LIST TOOLCHAINS ###
def list_toolchains(output_format=FORMAT_TXT):
    """Show list of known toolchains."""
    _, all_tcs = search_toolchain('')
    all_tcs_names = [x.NAME for x in all_tcs]
    tclist = sorted(zip(all_tcs_names, all_tcs))

    tcs = dict()
    for (tcname, tcc) in tclist:
        tc = tcc(version='1.2.3')  # version doesn't matter here, but something needs to be there
        tcs[tcname] = tc.definition()

    list_toolchains_functions = {
        FORMAT_RST: list_toolchains_rst,
        FORMAT_TXT: list_toolchains_txt,
    }

    return list_toolchains_functions[output_format](tcs)

def list_toolchains_rst(tcs):
    """ Returns overview of all toolchains in rst format """
    txt = []
    title = "List of known toolchains"
    txt.extend([title, "=" * len(title), ''])

    # figure out column names
    column_heads = ["NAME", "COMPILER", "MPI"]
    for d in tcs.values():
        column_heads.extend(d.keys())

    column_heads = nub(column_heads)

    values = [[] for i in range(len(column_heads))]
    values[0] = tcs.keys()

    for i in range(len(column_heads)-1):
        for d in tcs.values():
            values[i+1].append(', '.join(d.get(column_heads[i+1], [])))

    txt.extend(mk_rst_table(column_heads, values))

    return '\n'.join(txt)

def list_toolchains_txt(tcs):
    """ Returns overview of all toolchains in txt format """
    txt = ["List of known toolchains (toolchainname: module[,module...]):"]
    for name in sorted(tcs):
        tc_elems = nub(sorted([e for es in tcs[name].values() for e in es]))
        txt.append("\t%s: %s" % (name, ', '.join(tc_elems)))

    return '\n'.join(txt)

def gen_easyblocks_overview_rst(package_name, path_to_examples, common_params={}, doc_functions=[]):
    """
    Compose overview of all easyblocks in the given package in rst format
    """
    modules = import_available_modules(package_name)
    docs = []
    all_blocks = []

    # get all blocks
    for mod in modules:
        for name,obj in inspect.getmembers(mod, inspect.isclass):
            eb_class = getattr(mod, name)
            # skip imported classes that are not easyblocks
            if eb_class.__module__.startswith(package_name) and eb_class not in all_blocks:
                all_blocks.append(eb_class)

    for eb_class in sorted(all_blocks, key=lambda c: c.__name__):
        docs.append(gen_easyblock_doc_section_rst(eb_class, path_to_examples, common_params, doc_functions, all_blocks))

    title = 'Overview of generic easyblocks'

    heading = [
        '*(this page was generated automatically using* ``easybuild.tools.docs.gen_easyblocks_overview_rst()`` *)*',
        '',
        '=' * len(title),
        title,
        '=' * len(title),
        '',
    ]

    contents = [":ref:`" + b.__name__ + "`" for b in sorted(all_blocks, key=lambda b: b.__name__)]
    toc = ' - '.join(contents)
    heading.append(toc)
    heading.append('')

    return heading + docs


### GENERATE EASYBLOCKS DOCUMENTATION ###
def gen_easyblock_doc_section_rst(eb_class, path_to_examples, common_params, doc_functions, all_blocks):
    """
    Compose overview of one easyblock given class object of the easyblock in rst format
    """
    classname = eb_class.__name__

    lines = [
        '.. _' + classname + ':',
        '',
        '``' + classname + '``',
        '=' * (len(classname)+4),
        '',
    ]

    bases = []
    for b in eb_class.__bases__:
        base = ':ref:`' + b.__name__ +'`' if b in all_blocks else b.__name__
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
            ['``' + key + '``' for key in ex_opt],  # parameter name
            [val[1] for val in ex_opt.values()],  # description
            ['``' + str(quote_str(val[0])) + '``' for val in ex_opt.values()]  # default value
        ]

        lines.extend(mk_rst_table(titles, values))

    # Add commonly used parameters
    if classname in common_params:
        commonly_used = 'Commonly used easyconfig parameters with ``' + classname + '`` easyblock'
        lines.extend([commonly_used, '-' * len(commonly_used)])

        titles = ['easyconfig parameter', 'description']
        values = [
            [opt for opt in common_params[classname]],
            [DEFAULT_CONFIG[opt][1] for opt in common_params[classname]],
        ]

        lines.extend(mk_rst_table(titles, values))

        lines.append('')

    # Add docstring for custom steps
    custom = []
    inh = ''
    f = None
    for func in doc_functions:
        if func in eb_class.__dict__:
            f = eb_class.__dict__[func]

        if f.__doc__:
            custom.append('* ``' + func + '`` - ' + f.__doc__.strip() + inh)

    if custom:
        title = 'Customised steps in ``' + classname + '`` easyblock'
        lines.extend([title, '-' * len(title)] + custom)
        lines.append('')

    # Add example if available
    if os.path.exists(os.path.join(path_to_examples, '%s.eb' % classname)):
        title = 'Example for ``' + classname + '`` easyblock'
        lines.extend(['', title, '-' * len(title), '', '::', ''])
        for line in read_file(os.path.join(path_to_examples, classname+'.eb')).split('\n'):
            lines.append('    ' + line.strip())
        lines.append('') # empty line after literal block

    return '\n'.join(lines)
