#! /usr/bin/env python


import os
import sys
import optparse
import dendropy
import Queue
import multiprocessing
from cStringIO import StringIO
from dendropy.dataio import tree_source_iter
from dendropy.dataio import multi_tree_source_iter
from dendropy.utility.messaging import ConsoleMessenger
from dendropy.utility.cli import confirm_overwrite, show_splash

_program_name = "Tree-Prometry"
_program_subtitle = "Tree profile distance calculator"
_program_date = "Mar 02 2013"
_program_version = "Version 1.0.0 (%s)" % _program_date
_program_author = "Jeet Sukumaran"
_program_contact = "jeetsukumaran@gmail.com"
_program_copyright = "Copyright (C) 2013 Jeet Sukumaran.\n" \
                 "License GPLv3+: GNU GPL version 3 or later.\n" \
                 "This is free software: you are free to change\nand redistribute it. " \

class Profile(object):

    def __init__(self,
            key=None,
            profile_data=None):
        self.key = key
        if profile_data is None:
            self._profile_data = []
        else:
            self._profile_data = sorted(profile_data)

    def add(self, value):
        self._profile_data.append(value)
        self._profile_data = sorted(self._profile_data)

    def __len__(self):
        return len(self._profile_data)

    def get(self, idx):
        if idx >= len(self._profile_data):
            val = 0.0
        else:
            val = self._profile_data[idx]
            if val is None:
                val = 0.0
        return val

    def euclidean_distance(self, other):
        distance = 0.0
        for i in range(max(len(self._profile_data), len(other._profile_data))):
            di = pow(self.get(i) - other.get(i), 2)
            distance += di
        return distance

class ProfileMatrix(object):

    def __init__(self, title):
        self.title = title
        self._profiles = []

    def add(self, key, profile_data):
        profile = Profile(key=key,
                profile_data=profile_data)
        self._profiles.append(profile)

    def __len__(self):
        return len(self._profiles)

    def _calc_distances(self, dist_func):
        results = {}
        for idx1, profile1 in enumerate(self._profiles[:-1]):
            for idx2, profile2 in enumerate(self._profiles[idx1+1:]):
                d = dist_func(profile1, profile2)
                results[frozenset([profile1, profile2])] = d
        return results

    def calc(self):
        results = Distances(title=self.title)
        euclidean_dist_func = lambda x, y: x.euclidean_distance(y)
        d = self._calc_distances(euclidean_dist_func)
        results.add("Euclidean.Raw", d)
        return results

class Distances(object):

    def __init__(self, title):
        self.title = title
        self.distance_names = []
        self.distances = {}
        self.comparisons = set()

    def add(self, name, distance_dict):
        """
            - `name`
                string describing distance type (e.g., "Raw.Euclidean")
            - `distance_dict`
                dictionary with frozen set of Profile objects being compared
                as keys, and distance value as values
        """
        self.distance_names.append(name)
        self.distances[name] = distance_dict
        self.comparisons.update(distance_dict.keys())

    def get(self, distance_name, comparison):
        return self.distances[distance_name][frozenset(comparison)]

def read_trees(
        tree_filepaths,
        schema,
        measure_node_ages,
        ultrametricity_precision,
        log_frequency,
        messenger):
    messenger.send_info("Running in serial mode.")

    tree_offset = 0
    taxon_set = dendropy.TaxonSet()

    if tree_filepaths is None or len(tree_filepaths) == 0:
        messenger.send_info("Reading trees from standard input.")
        srcs = [sys.stdin]
    else:
        messenger.send_info("%d source(s) to be processed." % len(tree_filepaths))

        # do not want to have all files open at the same time
        #srcs = [open(f, "rU") for f in tree_filepaths]

        # store filepaths, to open individually in loop
        srcs = tree_filepaths

    profile_matrices = []
    edge_len_profiles = ProfileMatrix("Edge.Lengths")
    profile_matrices.append(edge_len_profiles)

    for sidx, src in enumerate(srcs):

        # hack needed because we do not want to open all input files at the
        # same time; if not a file object, assume it is a file path and create
        # corresponding file object
        if not isinstance(src, file):
            src = open(src, "rU")

        name = getattr(src, "name", "<stdin>")
        messenger.send_info("Processing %d of %d: '%s'" % (sidx+1, len(srcs), name), wrap=False)
        for tidx, tree in enumerate(tree_source_iter(src,
                schema=schema,
                taxon_set=taxon_set)):
            if tidx >= tree_offset:
                if (log_frequency == 1) or (tidx > 0 and log_frequency > 0 and tidx % log_frequency == 0):
                    messenger.send_info("(reading) '%s': tree at offset %d" % (name, tidx), wrap=False)
                key = "{:02d}:{:03d}:{}".format(sidx+1, tidx+1, tree.label)
                edge_len_profiles.add(
                        key=key,
                        profile_data=[e.length for e in tree.postorder_edge_iter()])
            else:
                if (log_frequency == 1) or (tidx > 0 and log_frequency > 0 and tidx % log_frequency == 0):
                    messenger.send_info("(reading) '%s': tree at offset %d (skipping)" % (name, tidx), wrap=False)
        try:
            src.close()
        except ValueError:
            # "I/O operation on closed file" if we try to close sys.stdin
            pass

    messenger.send_info("Serial processing of %d source(s) completed." % len(srcs))
    return profile_matrices

def report(profile_matrices,
        out,
        include_header_row=True):
    distance_groups = {}
    distance_group_titles = []
    distance_names = set()
    comparisons_set = set()
    for pm in profile_matrices:
        d = pm.calc()
        distance_groups[d.title] = d
        distance_group_titles.append(d.title)
        distance_names.update(d.distance_names)
        comparisons_set.update(d.comparisons)
    distance_group_titles = sorted(distance_group_titles)
    distance_names = sorted(distance_names)
    comparisons_list = []
    for comparison in comparisons_set:
        comparisons_list.append( sorted(comparison, key=lambda x: x.key) )
    comparisons_list = sorted(comparisons_list, key=lambda x: x[0].key + x[1].key)
    if include_header_row:
        row_parts = ["P1", "P2"]
        for dist_title in distance_group_titles:
            for dist_name in distance_names:
                row_parts.append("{}.{}".format(dist_title, dist_name))
        out.write("\t".join(row_parts))
        out.write("\n")
    for comparisons in comparisons_list:
        row_parts = [comparisons[0].key, comparisons[1].key]
        for dist_title in distance_group_titles:
            for dist_name in distance_names:
                distance = distance_groups[dist_title].get(dist_name, comparisons)
                row_parts.append("{}".format(distance))
        out.write("\t".join(row_parts))
        out.write("\n")


def main_cli():

    description =  "%s %s %s" % (_program_name, _program_version, _program_subtitle)
    usage = "%prog [options] TREES-FILE [TREES-FILE [TREES-FILE [...]]"

    parser = optparse.OptionParser(usage=usage,
            add_help_option=True,
            version = _program_version,
            description=description)

    source_trees_optgroup = optparse.OptionGroup(parser, "Metric Options")
    parser.add_option_group(source_trees_optgroup)
    source_trees_optgroup.add_option("--from-newick-stream",
            action="store_true",
            dest="from_newick_stream",
            default=False,
            help="trees will be streamed in newick format")
    source_trees_optgroup.add_option("--from-nexus-stream",
            action="store_true",
            dest="from_nexus_stream",
            default=False,
            help="trees will be streamed in NEXUS format")

    metrics_optgroup = optparse.OptionGroup(parser, "Metric Options")
    parser.add_option_group(metrics_optgroup)
    # metrics_optgroup.add_option("--measure-edge-lengths",
    #         action="store_true",
    #         default=True,
    #         help="use edge lengths")
    # metrics_optgroup.add_option("--measure-patristic-distance",
    #         action="store_true",
    #         default=True,
    #         help="use pairwise tip-to-tip path distances")
    metrics_optgroup.add_option("--measure-ages",
            action="store_true",
            default=False,
            help="use node ages (distance from tips); assumes ultrametric trees")
    metrics_optgroup.add_option("--normalize-global",
            action="store_true",
            default=False,
            help="normalize all measures to maximum sum of measures")

    output_filepath_optgroup = optparse.OptionGroup(parser, "Output File Options")
    parser.add_option_group(output_filepath_optgroup)
    output_filepath_optgroup.add_option("-o","--output",
            dest="output_filepath",
            default=None,
            help="path to output file (if not given, will print to standard output)")
    output_filepath_optgroup.add_option("-r", "--replace",
            action="store_true",
            dest="replace",
            default=False,
            help="replace/overwrite output file without asking if it already exists ")

    run_optgroup = optparse.OptionGroup(parser, "Program Run Options")
    parser.add_option_group(run_optgroup)
    run_optgroup.add_option("-m", "--multiprocessing",
            action="store",
            dest="multiprocess",
            metavar="NUM-PROCESSES",
            default=None,
            help="run in parallel mode with up to a maximum of NUM-PROCESSES processes " \
                    + "(specify '*' to run in as many processes as there are cores on the "\
                    + "local machine)")
    run_optgroup.add_option("-g", "--log-frequency",
            type="int",
            metavar="LOG-FREQUENCY",
            dest="log_frequency",
            default=500,
            help="tree processing progress logging frequency (default=%default; set to 0 to suppress)")
    run_optgroup.add_option("-q", "--quiet",
            action="store_true",
            dest="quiet",
            default=False,
            help="suppress ALL logging, progress and feedback messages")


    (opts, args) = parser.parse_args()

    (opts, args) = parser.parse_args()
    if opts.quiet:
        messaging_level = ConsoleMessenger.ERROR_MESSAGING_LEVEL
    else:
        messaging_level = ConsoleMessenger.INFO_MESSAGING_LEVEL
    messenger = ConsoleMessenger(name="Prometry", messaging_level=messaging_level)

    # splash
    if not opts.quiet:
        show_splash(prog_name=_program_name,
                prog_subtitle=_program_subtitle,
                prog_version=_program_version,
                prog_author=_program_author,
                prog_copyright=_program_copyright,
                dest=sys.stderr,
                extended=False)

    tree_filepaths = []
    if len(args) > 0:
        for fpath in args:
            fpath = os.path.expanduser(os.path.expandvars(fpath))
            if not os.path.exists(fpath):
                messenger.send_error("Terminating due to missing support files. "
                        + "Use the '--ignore-missing-support' option to continue even "
                        + "if some files are missing.")
                sys.exit(1)
            else:
                tree_filepaths.append(fpath)
        if len(tree_filepaths) == 0:
            messenger.send_error("No valid sources of input trees specified. "
                    + "Please provide the path to at least one (valid and existing) file "
                    + "containing trees to profile.")
            sys.exit(1)
    else:
        if not opts.from_newick_stream and not opts.from_nexus_stream:
            messenger.send_info("No sources of input trees specified. "
                    + "Please provide the path to at least one (valid and existing) file "
                    + "containing trees to profile. See '--help' for other options.")
            sys.exit(1)

    profiles = read_trees(
            tree_filepaths=tree_filepaths,
            schema="nexus/newick",
            measure_node_ages=opts.measure_ages,
            ultrametricity_precision=1e-6,
            log_frequency=opts.log_frequency,
            messenger=messenger,
            )

    report(profiles, sys.stdout)

if __name__ == "__main__":
    main_cli()
