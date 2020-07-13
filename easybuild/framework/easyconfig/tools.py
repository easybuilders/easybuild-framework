# #
# Copyright 2009-2020 Ghent University
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
Easyconfig module that provides functionality for dealing with easyconfig (.eb) files,
alongside the EasyConfig class to represent parsed easyconfig files.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
:author: Ward Poelmans (Ghent University)
:author: Johannes Hoermann (University of Freiburg)
"""
import copy
import glob
import itertools
import logging
import math
import os
import re
import sys
import tempfile
from distutils.version import LooseVersion

from easybuild.base import fancylogger
from easybuild.framework.easyconfig import EASYCONFIGS_PKG_SUBDIR
from easybuild.framework.easyconfig.easyconfig import EASYCONFIGS_ARCHIVE_DIR, ActiveMNS, EasyConfig
from easybuild.framework.easyconfig.easyconfig import create_paths, get_easyblock_class, process_easyconfig
from easybuild.framework.easyconfig.format.yeb import quote_yaml_special_chars
from easybuild.framework.easyconfig.style import cmdline_easyconfigs_style_check
from easybuild.tools.build_log import EasyBuildError, print_msg, print_warning
from easybuild.tools.config import build_option
from easybuild.tools.environment import restore_env
from easybuild.tools.filetools import find_easyconfigs, is_patch_file, read_file, resolve_path, which, write_file
from easybuild.tools.github import fetch_easyconfigs_from_pr, download_repo
from easybuild.tools.multidiff import multidiff
from easybuild.tools.py2vs3 import OrderedDict
from easybuild.tools.toolchain.toolchain import is_system_toolchain
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.utilities import only_if_module_is_available, quote_str
from easybuild.tools.version import VERSION as EASYBUILD_VERSION

# optional Python packages, these might be missing
# failing imports are just ignored
# a NameError should be caught where these are used

try:
    # PyGraph (used for generating dependency graphs)
    # https://pypi.python.org/pypi/python-graph-core
    from pygraph.classes.graph import graph
    from pygraph.classes.digraph import digraph
    from pygraph.algorithms.accessibility import connected_components
    from pygraph.algorithms.critical import critical_path
    from pygraph.algorithms.minmax import shortest_path_bellman_ford
    from pygraph.algorithms.searching import depth_first_search
    # https://pypi.python.org/pypi/python-graph-dot
    import pygraph.readwrite.dot as dot
    # graphviz (used for creating dependency graph images)
    sys.path.append('..')
    sys.path.append('/usr/lib/graphviz/python/')
    sys.path.append('/usr/lib64/graphviz/python/')
    # Python bindings to Graphviz (http://www.graphviz.org/),
    # see https://pypi.python.org/pypi/graphviz-python
    # graphviz-python (yum) or python-pygraphviz (apt-get)
    # or brew install graphviz --with-bindings (OS X)
    import gv
except ImportError:
    pass

_log = fancylogger.getLogger('easyconfig.tools', fname=False)


def skip_available(easyconfigs, modtool):
    """Skip building easyconfigs for existing modules."""
    module_names = [ec['full_mod_name'] for ec in easyconfigs]
    modules_exist = modtool.exist(module_names, maybe_partial=False)
    retained_easyconfigs = []
    for ec, mod_name, mod_exists in zip(easyconfigs, module_names, modules_exist):
        if mod_exists:
            _log.info("%s is already installed (module found), skipping" % mod_name)
        else:
            _log.debug("%s is not installed yet, so retaining it" % mod_name)
            retained_easyconfigs.append(ec)
    return retained_easyconfigs


def find_resolved_modules(easyconfigs, avail_modules, modtool, retain_all_deps=False):
    """
    Find easyconfigs in 1st argument which can be fully resolved using modules specified in 2nd argument

    :param easyconfigs: list of parsed easyconfigs
    :param avail_modules: list of available modules
    :param retain_all_deps: retain all dependencies, regardless of whether modules are available for them or not
    """
    ordered_ecs = []
    new_easyconfigs = []
    # copy, we don't want to modify the origin list of available modules
    avail_modules = avail_modules[:]
    _log.debug("Finding resolved modules for %s (available modules: %s)", easyconfigs, avail_modules)

    ec_mod_names = [ec['full_mod_name'] for ec in easyconfigs]
    for easyconfig in easyconfigs:
        if isinstance(easyconfig, EasyConfig):
            easyconfig._config = copy.copy(easyconfig._config)
        else:
            easyconfig = easyconfig.copy()
        deps = []
        for dep in easyconfig['dependencies']:
            dep_mod_name = dep.get('full_mod_name', ActiveMNS().det_full_module_name(dep))

            # always treat external modules as resolved,
            # since no corresponding easyconfig can be found for them
            if dep.get('external_module', False):
                _log.debug("Treating dependency marked as external module as resolved: %s", dep_mod_name)

            elif retain_all_deps and dep_mod_name not in avail_modules:
                # if all dependencies should be retained, include dep unless it has been already
                _log.debug("Retaining new dep %s in 'retain all deps' mode", dep_mod_name)
                deps.append(dep)

            # retain dep if it is (still) in the list of easyconfigs
            elif dep_mod_name in ec_mod_names:
                _log.debug("Dep %s is (still) in list of easyconfigs, retaining it", dep_mod_name)
                deps.append(dep)

            # retain dep if corresponding module is not available yet;
            # fallback to checking with modtool.exist is required,
            # for hidden modules and external modules where module name may be partial
            elif dep_mod_name not in avail_modules and not modtool.exist([dep_mod_name], skip_avail=True)[0]:
                # no module available (yet) => retain dependency as one to be resolved
                _log.debug("No module available for dep %s, retaining it", dep)
                deps.append(dep)

        # update list of dependencies with only those unresolved
        easyconfig['dependencies'] = deps

        # if all dependencies have been resolved, add module for this easyconfig in the list of available modules
        if not easyconfig['dependencies']:
            _log.debug("Adding easyconfig %s to final list" % easyconfig['spec'])
            ordered_ecs.append(easyconfig)
            mod_name = easyconfig['full_mod_name']
            avail_modules.append(mod_name)
            # remove module name from list, so dependencies can be marked as resolved
            ec_mod_names.remove(mod_name)

        else:
            new_easyconfigs.append(easyconfig)

    return ordered_ecs, new_easyconfigs, avail_modules


# isnpired by
# https://github.com/networkx/networkx/blob/9aedc31d291ac11eb0bb374c1ce8ad5cbcce02d3/networkx/algorithms/dag.py#L581
# transitive reduction removes all degenerate edges from a DAG while preserving dependency relations
@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph_transitive_reduction(dgr):
    """Generate transitive reduction and dump to file if desired."""
    tr = digraph()
    tr.add_nodes(dgr.nodes())
    descendants = {}

    check_count = {v: len(dgr.incidents(v)) for v in dgr.nodes()}
    _log.debug("Incident degrees: %s" % check_count)
    for u in dgr.nodes():
        u_nbrs = set(dgr.neighbors(u))
        _log.debug("neighbors of %s: %s" % (u, u_nbrs))
        for v in dgr.neighbors(u):
            if v in u_nbrs:
                if v not in descendants:
                    # v is not descendant of itself
                    descendants[v] = set(depth_first_search(dgr, v)[2]) - set([v])
                    _log.debug("sub-graph in %s: %s" % (v, descendants[v]))
                u_nbrs -= descendants[v]
            check_count[v] -= 1
            if check_count[v] == 0:
                _log.debug("Remove %s: %s from descendants" % (v, descendants[v]))
                del descendants[v]

        _log.debug("Descendants: %s" % descendants)
        _log.debug("u_nbrs: %s" % u_nbrs)
        for v in u_nbrs:
            tr.add_edge((u, v))

    if _log.isEnabledFor(logging.DEBUG):
        roots = dep_graph_roots(tr)
        filename = '_'.join(sorted([os.path.splitext(r)[0] for r in roots], key=str.lower)) + '_dep-graph-tr.dot'
        _dep_graph_dump(tr, filename)

    return tr


@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph_sub(dgr, root):
    """Return subgraph of DAG at specific 'root'-node"""
    _, pre, _ = depth_first_search(dgr, root)
    sub = digraph()
    sub.add_nodes(pre)
    for u in sub.nodes():
        for v in dgr.neighbors(u):
            if sub.has_node(v):
                sub.add_edge((u, v))
    _log.info("Subgraph at root %s has %d nodes and %d edges." % (root, len(sub.nodes()), len(sub.edges())))
    _log.debug("Nodes: %s" % sub.nodes())
    _log.debug("Edges: %s" % sub.edges())
    return sub


@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph_roots(dgr):
    """Return list of nodes with no incoming edges."""
    nodes = dgr.nodes()
    roots = set(nodes)
    for node in nodes:
        roots = roots - set(dgr.neighbors(node))
    roots = list(roots)
    _log.info("Found %d roots: %s" % (len(roots), roots))
    return roots


# https://stackoverflow.com/questions/43108481/maximum-common-subgraph-in-a-directed-graph
# not the maximum common subgraph, just common subgraph of two graphs g1 and g2
@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph_pairwise_common_subgraph(g1, g2):
    """Return common subgraph of two DAGs g1 and g2."""
    sub = digraph()

    # iterate over edges in g1 and add if edge in g2 as well
    for n1, n2 in g1.edges():
        if g2.has_edge((n1, n2)):
            if not sub.has_node(n1):
                sub.add_node(n1)
            if not sub.has_node(n2):
                sub.add_node(n2)
            sub.add_edge((n1, n2))
    return sub


# recursively divide and conquer set of graphs to find all common subragphs
@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph_common_subgraph(dgr_list):
    """Find common subgraph for arbitrary number of graphs."""
    n = len(dgr_list)
    if n < 1:
        raise EasyBuildError("len(dgr_list) < 1!")
    elif n == 1:
        return dgr_list[0]
    else:  # len(dgr_list) >= 2:
        return dep_graph_pairwise_common_subgraph(
            dep_graph_common_subgraph(dgr_list[:n//2]),
            dep_graph_common_subgraph(dgr_list[n//2:]))


# When layering a dependency graph G with multiple roots, we will have to branch
# the stacked layers at some point earlier or later. We would like
# to branch as "late" as possible when climbing down from leaves
# towards roots [r1, ..., rN]. In other words, we might want a high "degeneracy"
# of grouped subgraphs, thus we construct some penalty metric: A subgraph's g
# penalty metric is determined by the number of nodes n_g within the subgraph g
# divided by the number of roots N that share the subgraph n_g/N.
#
# This partition strategy implements a brute force approach to minimize that
# metric by recursive Y-branching of "fibre bundles". A bundle pair (gl, gr) is
# created by the union of all subgraphs spanned by an n-tuple and the complementary
# (N-n)-tuple of roots after removing the common subgraph gc induced by all roots.
# Note that gc may have multiple disconnected components.
# The "best" metric is found from all possible tuple pairings for n = 1 .. N//2,
# but only pairwise branchings are considered. The approach is repeated recursively.
#
# Thereby a graph of graphs is constructed, where a node represents one
# recursion step's gc edges represent necessary branching in the layer stack.
@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph_partition(dgr):
    """Only one of many possible partitioning strategies.

    Returns:
        graph, metric
    """
    roots = dep_graph_roots(dgr)
    n_roots = len(roots)

    _log.info("n_roots = %d: graph with roots %s has %d nodes and %d edges."
              % (n_roots, roots, len(dgr.nodes()), len(dgr.edges())))
    _log.debug("Nodes: %s" % dgr.nodes())
    _log.debug("Edges: %s" % dgr.edges())

    if n_roots == 1:
        meta_dgr = digraph()
        node_id = os.path.splitext(roots[0])[0]
        meta_dgr.add_node(node_id)
        meta_dgr.add_node_attribute(node_id, ('dgr', dgr))
        return meta_dgr, len(dgr.nodes())

    # subgraphs induced by each root
    subs = [dep_graph_sub(dgr, r) for r in roots]
    # common subgraph of all roots
    common_sub = dep_graph_common_subgraph(subs)
    metric = len(common_sub.nodes())/n_roots

    _log.info("n_roots = %d: metric = %.2f common subgraph induced by roots %s has %d nodes and %d edges."
              % (n_roots, metric, roots, len(common_sub.nodes()), len(common_sub.edges())))
    _log.debug("Nodes: %s" % common_sub.nodes())
    _log.debug("Edges: %s" % common_sub.edges())

    # remove common subgraph from graph
    reduced_dgr = digraph()
    for u in dgr.nodes():
        if (not common_sub.has_node(u)):
            reduced_dgr.add_node(u)

    for u in reduced_dgr.nodes():
        for v in dgr.neighbors(u):
            if reduced_dgr.has_node(v):
                reduced_dgr.add_edge((u, v))

    # recreate subgraphs induced by each root, this time without common subgraph
    reduced_subs = [dep_graph_sub(reduced_dgr, r) for r in roots]
    indices = [i for i in range(n_roots)]
    # some impossible worst case
    best_metric = len(reduced_dgr.nodes())*n_roots
    # iterate over possible fibre bundles
    for tuple_size in range(1, n_roots//2+1):
        _log.info("n_roots = %d: tuple size %d." % (n_roots, tuple_size))
        for left_tuple in itertools.combinations(indices, tuple_size):
            right_tuple = tuple(i for i in indices if i not in left_tuple)

            _log.info("n_roots = %d: looking at %s : %s partitioning." % (n_roots, left_tuple, right_tuple))

            left_reduced_dgr = digraph()
            left_nodes = set()
            left_edges = set()
            for i in left_tuple:
                left_nodes |= set(reduced_subs[i].nodes())
                left_edges |= set(reduced_subs[i].edges())

            for u in list(left_nodes):
                if not left_reduced_dgr.has_node(u):
                    left_reduced_dgr.add_node(u)
            for (u, v) in list(left_edges):
                left_reduced_dgr.add_edge((u, v))

            _log.info("n_roots = %d: left reduced graph has %d nodes and %d edges."
                      % (n_roots, len(left_reduced_dgr.nodes()), len(left_reduced_dgr.edges())))
            _log.debug("Nodes: %s" % left_reduced_dgr.nodes())
            _log.debug("Edges: %s" % left_reduced_dgr.edges())

            right_reduced_dgr = digraph()
            right_nodes = set()
            right_edges = set()
            for i in right_tuple:
                right_nodes |= set(reduced_subs[i].nodes())
                right_edges |= set(reduced_subs[i].edges())

            for u in list(right_nodes):
                if not right_reduced_dgr.has_node(u):
                    right_reduced_dgr.add_node(u)
            for (u, v) in list(right_edges):
                right_reduced_dgr.add_edge((u, v))

            _log.info("n_roots = %d: right reduced graph has %d nodes and %d edges."
                      % (n_roots, len(right_reduced_dgr.nodes()), len(right_reduced_dgr.edges())))
            _log.debug("Nodes: %s" % right_reduced_dgr.nodes())
            _log.debug("Edges: %s" % right_reduced_dgr.edges())

            left_meta_dgr, left_metric = dep_graph_partition(left_reduced_dgr)
            right_meta_dgr, right_metric = dep_graph_partition(right_reduced_dgr)

            cur_metric = left_metric + right_metric

            if cur_metric < best_metric:
                _log.info("n_roots = %d: found better metric %d < previous best %d."
                          % (n_roots, cur_metric, best_metric))
                best_metric = cur_metric
                best_child_meta_dgr = [left_meta_dgr, right_meta_dgr]

    metric += best_metric
    _log.info("n_roots = %d: total metric %d." % (n_roots, best_metric))

    meta_dgr = digraph()
    node_id = '_'.join(sorted([os.path.splitext(r)[0] for r in roots], key=str.lower))
    _log.info("n_roots = %d: node_id %s." % (n_roots, node_id))
    meta_dgr.add_node(node_id)
    meta_dgr.add_node_attribute(node_id, ('dgr', common_sub))

    for i, child_meta_dgr in enumerate(best_child_meta_dgr):
        child_roots = dep_graph_roots(child_meta_dgr)
        assert len(child_roots) == 1
        child_node_id = child_roots[0]
        _log.info("n_roots = %d: child %d node_id %s." % (n_roots, i, child_node_id))
        meta_dgr.add_graph(child_meta_dgr)
        # attributes and labels not preserved
        for u in child_meta_dgr.nodes():
            for (label, content) in child_meta_dgr.node_attributes(u):
                meta_dgr.add_node_attribute(u, (label, content))
        meta_dgr.add_edge((node_id, child_node_id))

    return meta_dgr, metric


@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph_grouped_layers(specs, print_result=True, terse=False):
    """Return list of dependency tree(s) layers."""
    # Let's call targets without further dependencies (usually the eb files
    # specified on command line) "roots" and targets that do not have any other
    # dependencies themselves "leaves" of the dependency DAG.
    # The aim of this alogrithm is to provide all targets within the dep. DAG
    # binned in layers, with as many targets as possible close to root(s).
    # The motivation is to build linearly 'stacked' container images with as
    # many reusable layers twoards the leaves as possible.
    dgr = dep_graph_obj(specs)
    _log.info("Dependency graph has %d nodes and %d edges." % (len(dgr.nodes()), len(dgr.edges())))
    _log.debug("Nodes: %s" % dgr.nodes())
    _log.debug("Edges: %s" % dgr.edges())

    # the transitive reduction drops all obsolete edges while preserving all
    # dependencies

    tr = dep_graph_transitive_reduction(dgr)
    roots = dep_graph_roots(tr)
    # n_roots = len(roots)
    # if n_roots == 0:
    #    raise EasyBuildError("Graph has no root!")
    # else:
    #    _log.info("Dependency DAG has %d roots %s." % (len(roots), roots))

    meta_dgr, metric = dep_graph_partition(tr)
    _log.info("Best partitioning with metric %d." % (metric))

    if _log.isEnabledFor(logging.DEBUG):
        filename = '_'.join(sorted([os.path.splitext(r)[0] for r in roots], key=str.lower)) + '_dep-graph-meta.dot'
        _dep_graph_dump(meta_dgr, filename)

    layer_lists = dep_graph_layer_lists(meta_dgr, parallel=True)
    _log.info("Number of layer lists: %d." % (len(layer_lists)))

    if print_result:
        # prepare output format
        lines = []
        if terse:
            for layers in layer_lists:
                lines.extend([' '.join(l) for l in layers])
                lines.extend([''])
        else:
            for i, layers in enumerate(layer_lists):
                digits = int(math.floor(math.log(len(layers), 10)))+1
                lines.extend(['#{block_id:0{width:d}d}'.format(block_id=i, width=2)])
                lines.extend(['#{layer_id:0{width:d}d}: {layer_content}'
                              .format(layer_id=j, layer_content=l, width=digits) for j, l in enumerate(layers)])
        print('\n'.join(lines))


@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph_layer_lists(meta_dgr, root=None, parallel=True):
    """Process meta graph of dep graph subgraphs."""
    if not root:
        roots = dep_graph_roots(meta_dgr)
        # meta_dgr must have exactly one root
        assert len(roots) == 1
        root = roots[0]

    attr_dict = dict(meta_dgr.node_attributes(root))
    dgr = attr_dict['dgr']

    if _log.isEnabledFor(logging.DEBUG):
        filename = root + '_dep-graph-sub.dot'
        _dep_graph_dump(dgr, filename)

    # there might be disconnected components.
    # we may stack or merge, (serial or parallel arrangements)
    # https://en.wikipedia.org/wiki/Series-parallel_graph

    # connected_components yields unexpected behaviort on directed graphs
    gr = graph()
    gr.add_graph(dgr)
    # connected_components returns node: component dict
    cc_dict = connected_components(gr)
    _log.info("%s - connected component assignemnts: %s" % (root, cc_dict))
    # number of connected components:
    n_cc = len(set(cc_dict.values()))
    _log.info("%s - %d connected components." % (root, n_cc))
    dgr_components = [digraph() for _ in range(n_cc)]
    for v, cc in cc_dict.items():
        _log.info("%s - component %d: %s" % (root, cc, v))
        dgr_components[cc-1].add_node(v)

    for dgr_component in dgr_components:
        for u in dgr_component.nodes():
            for v in dgr.neighbors(u):
                dgr_component.add_edge((u, v))

    # now we have serial ordering
    blocks = [dep_graph_layers(dgr_component) for dgr_component in dgr_components]
    _log.info("%s: serial arrangement:" % (root))
    for i, block in enumerate(blocks):
        _log.info("%s -block %d:" % (root, i))
        for j, layer in enumerate(block):
            _log.info("%s- block %d - layer %d: %s." % (root, i, j, layer))

    # we make it parallel for fewer total number of layers
    if parallel:
        merged_blocks = []
        for i, block in enumerate(blocks):
            for j, layer in enumerate(reversed(block)):
                if j >= len(merged_blocks):
                    merged_blocks.append(layer)
                else:
                    merged_blocks[j].extend(layer)
        blocks = [list(reversed(merged_blocks))]
        _log.info("%s - parallel arrangement:" % (root))
        for j, layer in enumerate(blocks[0]):
            _log.info("%s - layer %d: %s." % (root, j, layer))

    # preserve aphabetical sorting
    layer_list = [list(sorted(l, key=str.lower)) for b in blocks for l in b]
    _log.info("%s - blocks: %s" % (root, blocks))
    _log.info("%s - layer list prefix: %s" % (root, layer_list))

    # handle dependent blocks
    layer_lists = []
    for i, child in enumerate(meta_dgr.neighbors(root)):
        _log.info("%s - descend to child %d: %s." % (root, i, child))
        child_layer_lists = dep_graph_layer_lists(meta_dgr, child, parallel)
        _log.info("%s - child %d: %s returned %d layer lists." % (root, i, child, len(child_layer_lists)))
        for j, child_layer_list in enumerate(child_layer_lists):
            _log.info("%s - child %d - layer list %d: %s" % (root, i, j, child_layer_list))
            layer_lists.append([*layer_list, *child_layer_list])

    if len(layer_lists) == 0:  # no children
        layer_lists = [layer_list]

    _log.info("%s - return %d layer lists." % (root, len(layer_lists)))
    for j, layer_list in enumerate(layer_lists):
        _log.info("%s - layer list %d: %s" % (root, j, layer_list))

    return layer_lists


@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph_layers(dgr):
    """Return list of dependency tree(s) layers."""
    # for logging only: the critical path is the longest path from a root to
    # a leaf, thus its length will determine the total number of layers
    cp = critical_path(dgr)
    n = len(cp)
    _log.info("Critical %s path has length %d." % (cp, n))

    # for logging only: roots and leaves
    roots = dep_graph_roots(dgr)
    if len(roots) == 0:
        raise EasyBuildError("Graph has no root!")
    else:
        _log.info("Dependency DAG has %d roots %s." % (len(roots), roots))

    # the reverse just turns around the directions of all edges in the DAG
    rev_dgr = dgr.reverse()

    leaves = dep_graph_roots(rev_dgr)
    if len(leaves) == 0:
        raise EasyBuildError("Graph has no leaves!")
    else:
        _log.info("Dependency DAG has %d leaves %s." % (len(leaves), leaves))

    # set weights negative, get longest paths from each node in reverse graph
    for e in rev_dgr.edges():
        rev_dgr.set_edge_weight(e, -1)

    layers = [[] for _ in range(n)]
    for v in rev_dgr.nodes():
        path, dist = shortest_path_bellman_ford(rev_dgr, v)
        _log.debug("%s v is reached by paths %s with distances %s." % (v, path, dist))
        layer = -min(dist.values())
        _log.info("%s v is assigned to layer %d." % (v, layer))
        dgr.add_node_attribute(v, ('layer', layer))
        layers[layer].append(v)

    layers.reverse()

    # assure alphabetical sorting
    layers = [list(sorted(l, key=str.lower)) for l in layers]
    _log.info("Filled %d layers with %s." % (n, layers))
    return layers


@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph_obj(specs):
    """
    Return a dependency graph pygraph object for the given easyconfigs.
    Nodes are identified by their full module names and labeled with
    corresponding EasyConfig file names. Dump graph file if desired.
    """
    def mk_node_name(spec):
        # _log.info("EC spec: %s" % spec)
        return ActiveMNS().det_full_module_name(spec)

    def mk_node_label(spec):
        return spec.filename()

    # enhance list of specs
    all_nodes = set()
    label_dict = {}
    for i, spec in enumerate(specs):
        _log.debug("#%d spec ec filename: %s" % (i, spec['ec'].filename()))
        spec['module'] = mk_node_name(spec['ec'])
        node_name = mk_node_label(spec['ec'])
        label_dict[spec['module']] = node_name
        all_nodes.add(node_name)

        for j, s in enumerate(spec['ec'].all_dependencies):
            _log.debug("spec %d- all dep %d spec: %s" % (i, j, s))

        spec['ec']._all_dependencies = [mk_node_name(s) for s in spec['ec'].all_dependencies]
        # all_nodes.update(spec['ec'].all_dependencies)
        # under what circumstances would it be necessary to explicitly add dependencies to node set?

        # Get the build dependencies for each spec so we can distinguish them later
        for j, s in enumerate(spec['ec'].builddependencies()):
            _log.debug("spec %d - build dep %d spec: %s" % (i, j, s))

        spec['ec'].build_dependencies = [mk_node_name(s) for s in spec['ec'].builddependencies()]
        # all_nodes.update(spec['ec'].build_dependencies)

    # build directed graph
    dgr = digraph()
    dgr.add_nodes(all_nodes)

    edge_attrs = [('style', 'dotted'), ('color', 'blue'), ('arrowhead', 'diamond')]
    for spec in specs:
        for dep in spec['ec'].all_dependencies:
            # NOTE: we assign negative weights here for finding longest paths
            dgr.add_edge((label_dict[spec['module']], label_dict[dep]))
            if dep in spec['ec'].build_dependencies:
                dgr.add_edge_attributes((label_dict[spec['module']], label_dict[dep]), attrs=edge_attrs)

    if _log.isEnabledFor(logging.DEBUG):
        roots = dep_graph_roots(dgr)
        filename = '_'.join(sorted([os.path.splitext(r)[0] for r in roots], key=str.lower)) + '_dep-graph.dot'
        _dep_graph_dump(dgr, filename)

    return dgr


@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph(filename, specs):
    """
    Create a dependency graph for the given easyconfigs.
    """
    # check whether module names are unique
    # if so, we can omit versions in the graph
    names = set()
    for spec in specs:
        names.add(spec['ec']['name'])
    omit_versions = len(names) == len(specs)

    def mk_node_name(spec):
        if spec.get('external_module', False):
            node_name = "%s (EXT)" % spec['full_mod_name']
        elif omit_versions:
            node_name = spec['name']
        else:
            node_name = ActiveMNS().det_full_module_name(spec)

        return node_name

    # enhance list of specs
    all_nodes = set()
    for spec in specs:
        spec['module'] = mk_node_name(spec['ec'])
        all_nodes.add(spec['module'])
        spec['ec']._all_dependencies = [mk_node_name(s) for s in spec['ec'].all_dependencies]
        all_nodes.update(spec['ec'].all_dependencies)

        # Get the build dependencies for each spec so we can distinguish them later
        spec['ec'].build_dependencies = [mk_node_name(s) for s in spec['ec'].builddependencies()]
        all_nodes.update(spec['ec'].build_dependencies)

    # build directed graph
    edge_attrs = [('style', 'dotted'), ('color', 'blue'), ('arrowhead', 'diamond')]
    dgr = digraph()
    dgr.add_nodes(all_nodes)
    edge_attrs = [('style', 'dotted'), ('color', 'blue'), ('arrowhead', 'diamond')]
    for spec in specs:
        for dep in spec['ec'].all_dependencies:
            dgr.add_edge((spec['module'], dep))
            if dep in spec['ec'].build_dependencies:
                dgr.add_edge_attributes((spec['module'], dep), attrs=edge_attrs)

    _dep_graph_dump(dgr, filename)

    if not build_option('silent'):
        print_msg("Wrote dependency graph for %d easyconfigs to %s" % (len(specs), filename))


@only_if_module_is_available('pygraph.readwrite.dot', pkgname='python-graph-dot')
def _dep_graph_dump(dgr, filename):
    """Dump dependency graph to file, in specified format."""
    # write to file
    dottxt = dot.write(dgr)
    if os.path.splitext(filename)[-1] == '.dot':
        # create .dot file
        write_file(filename, dottxt)
    else:
        _dep_graph_gv(dottxt, filename)


@only_if_module_is_available('gv', pkgname='graphviz-python')
def _dep_graph_gv(dottxt, filename):
    """Render dependency graph to file using graphviz."""
    # try and render graph in specified file format
    gvv = gv.readstring(dottxt)
    gv.layout(gvv, 'dot')
    gv.render(gvv, os.path.splitext(filename)[-1], filename)


def get_paths_for(subdir=EASYCONFIGS_PKG_SUBDIR, robot_path=None):
    """
    Return a list of absolute paths where the specified subdir can be found, determined by the PYTHONPATH
    """

    paths = []

    # primary search path is robot path
    path_list = []
    if isinstance(robot_path, list):
        path_list = robot_path[:]
    elif robot_path is not None:
        path_list = [robot_path]
    # consider Python search path, e.g. setuptools install path for easyconfigs
    path_list.extend(sys.path)

    # figure out installation prefix, e.g. distutils install path for easyconfigs

    # prefer using path specified in $EB_SCRIPT_PATH (if defined), which is set by 'eb' wrapper script
    eb_path = os.getenv('EB_SCRIPT_PATH')
    if eb_path is None:
        # try to determine location of 'eb' script via $PATH, as fallback mechanism
        eb_path = which('eb')
        _log.info("Location to 'eb' script (found via $PATH): %s", eb_path)
    else:
        _log.info("Found location to 'eb' script via $EB_SCRIPT_PATH: %s", eb_path)

    if eb_path is None:
        warning_msg = "'eb' not found in $PATH, failed to determine installation prefix!"
        _log.warning(warning_msg)
        print_warning(warning_msg)
    else:
        # eb_path is location to 'eb' wrapper script, e.g. <install_prefix>/bin/eb
        # so installation prefix is usually two levels up
        install_prefix = os.path.dirname(os.path.dirname(eb_path))

        # only consider resolved path to 'eb' script if desired subdir is not found relative to 'eb' script location
        if os.path.exists(os.path.join(install_prefix, 'easybuild', subdir)):
            path_list.append(install_prefix)
            _log.info("Also considering installation prefix %s (determined via path to 'eb' script)...", install_prefix)
        else:
            _log.info("Not considering %s (no easybuild/%s subdir found)", install_prefix, subdir)

            # also consider fully resolved location to 'eb' wrapper
            # see https://github.com/easybuilders/easybuild-framework/pull/2248
            resolved_eb_path = resolve_path(eb_path)
            if eb_path != resolved_eb_path:
                install_prefix = os.path.dirname(os.path.dirname(resolved_eb_path))
                path_list.append(install_prefix)
                _log.info("Also considering installation prefix %s (via resolved path to 'eb')...", install_prefix)

    # look for desired subdirs
    for path in path_list:
        path = os.path.join(path, "easybuild", subdir)
        _log.debug("Checking for easybuild/%s at %s" % (subdir, path))
        try:
            if os.path.exists(path):
                paths.append(os.path.abspath(path))
                _log.debug("Added %s to list of paths for easybuild/%s" % (path, subdir))
        except OSError as err:
            raise EasyBuildError(str(err))

    return paths


def alt_easyconfig_paths(tmpdir, tweaked_ecs=False, from_pr=False):
    """Obtain alternative paths for easyconfig files."""

    # paths where tweaked easyconfigs will be placed, easyconfigs listed on the command line take priority and will be
    # prepended to the robot path, tweaked dependencies are also created but these will only be appended to the robot
    # path (and therefore only used if strictly necessary)
    tweaked_ecs_paths = None
    if tweaked_ecs:
        tweaked_ecs_paths = (os.path.join(tmpdir, 'tweaked_easyconfigs'),
                             os.path.join(tmpdir, 'tweaked_dep_easyconfigs'))

    # path where files touched in PR will be downloaded to
    pr_path = None
    if from_pr:
        pr_path = os.path.join(tmpdir, "files_pr%s" % from_pr)

    return tweaked_ecs_paths, pr_path


def det_easyconfig_paths(orig_paths):
    """
    Determine paths to easyconfig files.
    :param orig_paths: list of original easyconfig paths
    :return: list of paths to easyconfig files
    """
    from_pr = build_option('from_pr')
    robot_path = build_option('robot_path')

    # list of specified easyconfig files
    ec_files = orig_paths[:]

    if from_pr is not None:
        pr_files = fetch_easyconfigs_from_pr(from_pr)

        if ec_files:
            # replace paths for specified easyconfigs that are touched in PR
            for i, ec_file in enumerate(ec_files):
                for pr_file in pr_files:
                    if ec_file == os.path.basename(pr_file):
                        ec_files[i] = pr_file
        else:
            # if no easyconfigs are specified, use all the ones touched in the PR
            ec_files = [path for path in pr_files if path.endswith('.eb')]

    if ec_files and robot_path:
        # look for easyconfigs with relative paths in robot search path,
        # unless they were found at the given relative paths

        # determine which easyconfigs files need to be found, if any
        ecs_to_find = []
        for idx, ec_file in enumerate(ec_files):
            if ec_file == os.path.basename(ec_file) and not os.path.exists(ec_file):
                ecs_to_find.append((idx, ec_file))
        _log.debug("List of easyconfig files to find: %s" % ecs_to_find)

        # find missing easyconfigs by walking paths in robot search path
        for path in robot_path:
            _log.debug("Looking for missing easyconfig files (%d left) in %s..." % (len(ecs_to_find), path))
            for (subpath, dirnames, filenames) in os.walk(path, topdown=True):
                for idx, orig_path in ecs_to_find[:]:
                    if orig_path in filenames:
                        full_path = os.path.join(subpath, orig_path)
                        _log.info("Found %s in %s: %s" % (orig_path, path, full_path))
                        ec_files[idx] = full_path
                        # if file was found, stop looking for it (first hit wins)
                        ecs_to_find.remove((idx, orig_path))

                # stop os.walk insanity as soon as we have all we need (os.walk loop)
                if not ecs_to_find:
                    break

                # ignore subdirs specified to be ignored by replacing items in dirnames list used by os.walk
                dirnames[:] = [d for d in dirnames if d not in build_option('ignore_dirs')]

                # ignore archived easyconfigs, unless specified otherwise
                if not build_option('consider_archived_easyconfigs'):
                    dirnames[:] = [d for d in dirnames if d != EASYCONFIGS_ARCHIVE_DIR]

            # stop os.walk insanity as soon as we have all we need (outer loop)
            if not ecs_to_find:
                break

    return [os.path.abspath(ec_file) for ec_file in ec_files]


def parse_easyconfigs(paths, validate=True):
    """
    Parse easyconfig files
    :param paths: paths to easyconfigs
    """
    easyconfigs = []
    generated_ecs = False

    for (path, generated) in paths:
        path = os.path.abspath(path)
        # keep track of whether any files were generated
        generated_ecs |= generated
        if not os.path.exists(path):
            raise EasyBuildError("Can't find path %s", path)
        try:
            ec_files = find_easyconfigs(path, ignore_dirs=build_option('ignore_dirs'))
            for ec_file in ec_files:
                kwargs = {'validate': validate}
                # only pass build specs when not generating easyconfig files
                if not build_option('try_to_generate'):
                    kwargs['build_specs'] = build_option('build_specs')

                easyconfigs.extend(process_easyconfig(ec_file, **kwargs))

        except IOError as err:
            raise EasyBuildError("Processing easyconfigs in path %s failed: %s", path, err)

    return easyconfigs, generated_ecs


def stats_to_str(stats, isyeb=False):
    """
    Pretty print build statistics to string.
    """
    if not isinstance(stats, (OrderedDict, dict)):
        raise EasyBuildError("Can only pretty print build stats in dictionary form, not of type %s", type(stats))

    txt = "{\n"
    pref = "    "
    for key in sorted(stats):
        if isyeb:
            val = stats[key]
            if isinstance(val, tuple):
                val = list(val)
            key, val = quote_yaml_special_chars(key), quote_yaml_special_chars(val)
        else:
            key, val = quote_str(key), quote_str(stats[key])
        txt += "%s%s: %s,\n" % (pref, key, val)
    txt += "}"
    return txt


def find_related_easyconfigs(path, ec):
    """
    Find related easyconfigs for provided parsed easyconfig in specified path.

    A list of easyconfigs for the same software (name) is returned,
    matching the 1st criterion that yields a non-empty list.

    The following criteria are considered (in this order) next to common software version criterion, i.e.
    exact version match, a major/minor version match, a major version match, or no version match (in that order).

    (i)   matching versionsuffix and toolchain name/version
    (ii)  matching versionsuffix and toolchain name (any toolchain version)
    (iii) matching versionsuffix (any toolchain name/version)
    (iv)  matching toolchain name/version (any versionsuffix)
    (v)   matching toolchain name (any versionsuffix, toolchain version)
    (vi)  no extra requirements (any versionsuffix, toolchain name/version)

    If no related easyconfigs with a matching software name are found, an empty list is returned.
    """
    name = ec.name
    version = ec.version
    versionsuffix = ec['versionsuffix']
    toolchain_name = ec['toolchain']['name']
    toolchain_name_pattern = r'-%s-\S+' % toolchain_name
    toolchain_pattern = '-%s-%s' % (toolchain_name, ec['toolchain']['version'])
    if is_system_toolchain(toolchain_name):
        toolchain_name_pattern = ''
        toolchain_pattern = ''

    potential_paths = [glob.glob(ec_path) for ec_path in create_paths(path, name, '*')]
    potential_paths = sum(potential_paths, [])  # flatten
    _log.debug("found these potential paths: %s" % potential_paths)

    parsed_version = LooseVersion(version).version
    version_patterns = [version]  # exact version match
    if len(parsed_version) >= 2:
        version_patterns.append(r'%s\.%s\.\w+' % tuple(parsed_version[:2]))  # major/minor version match
    if parsed_version != parsed_version[0]:
        version_patterns.append(r'%s\.[\d-]+\.\w+' % parsed_version[0])  # major version match
    version_patterns.append(r'[\w.]+')  # any version

    regexes = []
    for version_pattern in version_patterns:
        common_pattern = r'^\S+/%s-%s%%s\.eb$' % (re.escape(name), version_pattern)
        regexes.extend([
            common_pattern % (toolchain_pattern + versionsuffix),
            common_pattern % (toolchain_name_pattern + versionsuffix),
            common_pattern % (r'\S*%s' % versionsuffix),
            common_pattern % toolchain_pattern,
            common_pattern % toolchain_name_pattern,
            common_pattern % r'\S*',
        ])

    for regex in regexes:
        res = [p for p in potential_paths if re.match(regex, p)]
        if res:
            _log.debug("Related easyconfigs found using '%s': %s" % (regex, res))
            break
        else:
            _log.debug("No related easyconfigs in potential paths using '%s'" % regex)

    return sorted(res)


def review_pr(paths=None, pr=None, colored=True, branch='develop'):
    """
    Print multi-diff overview between specified easyconfigs or PR and specified branch.
    :param pr: pull request number in easybuild-easyconfigs repo to review
    :param paths: path tuples (path, generated) of easyconfigs to review
    :param colored: boolean indicating whether a colored multi-diff should be generated
    :param branch: easybuild-easyconfigs branch to compare with
    """
    tmpdir = tempfile.mkdtemp()

    download_repo_path = download_repo(branch=branch, path=tmpdir)
    repo_path = os.path.join(download_repo_path, 'easybuild', 'easyconfigs')

    if pr:
        pr_files = [path for path in fetch_easyconfigs_from_pr(pr) if path.endswith('.eb')]
    elif paths:
        pr_files = paths
    else:
        raise EasyBuildError("No PR # or easyconfig path specified")

    lines = []
    ecs, _ = parse_easyconfigs([(fp, False) for fp in pr_files], validate=False)
    for ec in ecs:
        files = find_related_easyconfigs(repo_path, ec['ec'])
        if pr:
            pr_msg = "PR#%s" % pr
        else:
            pr_msg = "new PR"
        _log.debug("File in %s %s has these related easyconfigs: %s" % (pr_msg, ec['spec'], files))
        if files:
            lines.append(multidiff(ec['spec'], files, colored=colored))
        else:
            lines.extend(['', "(no related easyconfigs found for %s)\n" % os.path.basename(ec['spec'])])

    return '\n'.join(lines)


def dump_env_script(easyconfigs):
    """
    Dump source scripts that set up build environment for specified easyconfigs.

    :param easyconfigs: list of easyconfigs to generate scripts for
    """
    ecs_and_script_paths = []
    for easyconfig in easyconfigs:
        script_path = '%s.env' % os.path.splitext(os.path.basename(easyconfig['spec']))[0]
        ecs_and_script_paths.append((easyconfig['ec'], script_path))

    # don't just overwrite existing scripts
    existing_scripts = [s for (_, s) in ecs_and_script_paths if os.path.exists(s)]
    if existing_scripts:
        if build_option('force'):
            _log.info("Found existing scripts, overwriting them: %s", ' '.join(existing_scripts))
        else:
            raise EasyBuildError("Script(s) already exists, not overwriting them (unless --force is used): %s",
                                 ' '.join(existing_scripts))

    orig_env = copy.deepcopy(os.environ)

    for ec, script_path in ecs_and_script_paths:
        # obtain EasyBlock instance
        app_class = get_easyblock_class(ec['easyblock'], name=ec['name'])
        app = app_class(ec)

        # mimic dry run, and keep quiet
        app.dry_run = app.silent = app.toolchain.dry_run = True

        # prepare build environment (in dry run mode)
        app.check_readiness_step()
        app.prepare_step(start_dir=False)

        # compose script
        ecfile = os.path.basename(ec.path)
        script_lines = [
            "#!/bin/bash",
            "# script to set up build environment as defined by EasyBuild v%s for %s" % (EASYBUILD_VERSION, ecfile),
            "# usage: source %s" % os.path.basename(script_path),
        ]

        script_lines.extend(['', "# toolchain & dependency modules"])
        if app.toolchain.modules:
            script_lines.extend(["module load %s" % mod for mod in app.toolchain.modules])
        else:
            script_lines.append("# (no modules loaded)")

        script_lines.extend(['', "# build environment"])
        if app.toolchain.vars:
            env_vars = sorted(app.toolchain.vars.items())
            script_lines.extend(["export %s='%s'" % (var, val.replace("'", "\\'")) for (var, val) in env_vars])
        else:
            script_lines.append("# (no build environment defined)")

        write_file(script_path, '\n'.join(script_lines))
        print_msg("Script to set up build environment for %s dumped to %s" % (ecfile, script_path), prefix=False)

        restore_env(orig_env)


def categorize_files_by_type(paths):
    """
    Splits list of filepaths into a 4 separate lists: easyconfigs, files to delete, patch files and
    files with extension .py
    """
    res = {
        'easyconfigs': [],
        'files_to_delete': [],
        'patch_files': [],
        'py_files': [],
    }

    for path in paths:
        if path.startswith(':'):
            res['files_to_delete'].append(path[1:])
        elif path.endswith('.py'):
            res['py_files'].append(path)
        # file must exist in order to check whether it's a patch file
        elif os.path.isfile(path) and is_patch_file(path):
            res['patch_files'].append(path)
        else:
            # anything else is considered to be an easyconfig file
            res['easyconfigs'].append(path)

    return res


def check_sha256_checksums(ecs, whitelist=None):
    """
    Check whether all provided (parsed) easyconfigs have SHA256 checksums for sources & patches.

    :param whitelist: list of regex patterns on easyconfig filenames; check is skipped for matching easyconfigs
    :return: list of strings describing checksum issues (missing checksums, wrong checksum type, etc.)
    """
    checksum_issues = []

    if whitelist is None:
        whitelist = []

    for ec in ecs:
        # skip whitelisted software
        ec_fn = os.path.basename(ec.path)
        if any(re.match(regex, ec_fn) for regex in whitelist):
            _log.info("Skipping SHA256 checksum check for %s because of whitelist (%s)", ec.path, whitelist)
            continue

        eb_class = get_easyblock_class(ec['easyblock'], name=ec['name'])
        checksum_issues.extend(eb_class(ec).check_checksums())

    return checksum_issues


def run_contrib_checks(ecs):
    """Run contribution check on specified easyconfigs."""

    def print_result(checks_passed, label):
        """Helper function to print result of last group of checks."""
        if checks_passed:
            print_msg("\n>> All %s checks PASSed!" % label, prefix=False)
        else:
            print_msg("\n>> One or more %s checks FAILED!" % label, prefix=False)

    # start by running style checks
    style_check_ok = cmdline_easyconfigs_style_check(ecs)
    print_result(style_check_ok, "style")

    # check whether SHA256 checksums are in place
    print_msg("\nChecking for SHA256 checksums in %d easyconfig(s)...\n" % len(ecs), prefix=False)
    sha256_checksums_ok = True
    for ec in ecs:
        sha256_checksum_fails = check_sha256_checksums([ec])
        if sha256_checksum_fails:
            sha256_checksums_ok = False
            msgs = ['[FAIL] %s' % ec.path] + sha256_checksum_fails
        else:
            msgs = ['[PASS] %s' % ec.path]
        print_msg('\n'.join(msgs), prefix=False)

    print_result(sha256_checksums_ok, "SHA256 checksums")

    return style_check_ok and sha256_checksums_ok


def avail_easyblocks():
    """Return a list of all available easyblocks."""

    module_regexp = re.compile(r"^([^_].*)\.py$")
    class_regex = re.compile(r"^class ([^(]*)\(", re.M)

    # finish initialisation of the toolchain module (ie set the TC_CONSTANT constants)
    search_toolchain('')

    easyblocks = {}
    for pkg in ['easybuild.easyblocks', 'easybuild.easyblocks.generic']:
        __import__(pkg)

        # determine paths for this package
        paths = sys.modules[pkg].__path__

        # import all modules in these paths
        for path in paths:
            if os.path.exists(path):
                for fn in os.listdir(path):
                    res = module_regexp.match(fn)
                    if res:
                        easyblock_mod_name = '%s.%s' % (pkg, res.group(1))

                        if easyblock_mod_name not in easyblocks:
                            __import__(easyblock_mod_name)
                            easyblock_loc = os.path.join(path, fn)

                            class_names = class_regex.findall(read_file(easyblock_loc))
                            if len(class_names) == 1:
                                easyblock_class = class_names[0]
                            elif class_names:
                                raise EasyBuildError("Found multiple class names for easyblock %s: %s",
                                                     easyblock_loc, class_names)
                            else:
                                raise EasyBuildError("Failed to determine easyblock class name for %s", easyblock_loc)

                            easyblocks[easyblock_mod_name] = {'class': easyblock_class, 'loc': easyblock_loc}
                        else:
                            _log.debug("%s already imported from %s, ignoring %s",
                                       easyblock_mod_name, easyblocks[easyblock_mod_name]['loc'], path)

    return easyblocks
