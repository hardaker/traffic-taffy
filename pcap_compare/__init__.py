"""Takes a set of pcap files to compare and dumps a report"""

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List
import logging
from collections import defaultdict, Counter

# TODO: make scapy optional or use dpkt for shallow but faster
from scapy.all import rdpcap
from rich import print
from rich.console import Console
from logging import debug, warning
import pickle


def parse_args():
    "Parse the command line arguments."
    parser = ArgumentParser(
        formatter_class=ArgumentDefaultsHelpFormatter,
        description=__doc__,
        epilog="Exmaple Usage: ",
    )

    parser.add_argument(
        "-n",
        "--packet-count",
        default=-1,
        type=int,
        help="Maximum number of packets to analyze",
    )

    parser.add_argument(
        "-t",
        "--print-threshold",
        default=None,
        type=float,
        help="Don't print results with abs(value) less than threshold",
    )

    parser.add_argument(
        "-m",
        "--print-match-string",
        default=None,
        type=str,
        help="Only report on data with this substring in the header",
    )

    parser.add_argument(
        "-s",
        "--save-report",
        default=None,
        type=str,
        help="Where to save a report file for quicker future loading",
    )

    parser.add_argument(
        "-l",
        "--load-report",
        default=None,
        type=str,
        help="Load a report from a pickle file rather than use pcaps",
    )

    parser.add_argument(
        "-c",
        "--print-minimum-count",
        default=None,
        type=float,
        help="Don't print results without this high of a count",
    )

    parser.add_argument(
        "-P", "--only-positive", action="store_true", help="Only show positive entries"
    )

    parser.add_argument(
        "-N", "--only-negative", action="store_true", help="Only show negative entries"
    )

    parser.add_argument(
        "--log-level",
        "--ll",
        default="info",
        help="Define the logging verbosity level (debug, info, warning, error, ...).",
    )

    parser.add_argument("pcap_files", type=str, nargs="*", help="PCAP files to analyze")

    args = parser.parse_args()
    log_level = args.log_level.upper()
    logging.basicConfig(level=log_level, format="%(levelname)-10s:\t%(message)s")
    return args


class PcapCompare:
    "Takes a set of PCAPs to then perform various comparisons upon"

    REPORT_VERSION: int = 2

    def __init__(
        self,
        pcaps: List[str],
        maximum_count: int | None = None,
        deep: bool = True,
        print_threshold: float | None = None,
        print_minimum_count: int | None = None,
        print_match_string: str | None = None,
        only_positive: bool = False,
        only_negative: bool = False,
    ) -> None:

        self.pcaps = pcaps
        self.deep = deep
        self.maximum_count = maximum_count
        self.print_threshold = print_threshold
        self.print_minimum_count = print_minimum_count
        self.print_match_string = print_match_string
        self.only_positive = only_positive
        self.only_negative = only_negative

    def add_layer(self, layer, storage: dict, prefix: str | None = "") -> None:
        "Analyzes a layer to add counts to each layer sub-component"

        if hasattr(layer, "fields_desc"):
            name_list = [field.name for field in layer.fields_desc]
        elif hasattr(layer, "fields"):
            name_list = [field.name for field in layer.fields]
        else:
            warning(f"unavailable to deep dive into: {layer}")
            return

        for field_name in name_list:
            field_value = getattr(layer, field_name)
            if isinstance(field_value, list):
                if len(field_value) > 0:
                    # if it's a list of tuples, count the (eg TCP option) names
                    # TODO: values can be always the same or things like timestamps
                    #       that will always change
                    if isinstance(field_value[0], tuple):
                        for item in field_value:
                            storage[prefix + field_name][item[0]] += 1
                    else:
                        warning(f"ignoring non-zero list: {field_name}")
                else:
                    debug(f"ignoring empty-list: {field_name}")
            elif isinstance(field_value, str) or isinstance(field_value, int):
                storage[prefix + field_name][field_value] += 1

            elif hasattr(field_value, "fields"):
                self.add_layer(field_value, storage, prefix + field_name + ".")
            else:
                debug(f"ignoring field value of {str(field_value)}")

    def load_pcap(self, pcap_file: str | None = None) -> dict:
        "Loads a pcap file into a nested dictionary of statistical counts"
        results = defaultdict(Counter)
        packets = rdpcap(pcap_file, count=self.maximum_count)

        for packet in packets:
            prefix = "."
            for payload in packet.iterpayloads():
                results[prefix[1:-1]][payload.name] += 1  # count the prefix itself too
                prefix = f"{prefix}{payload.name}."
                self.add_layer(payload, results, prefix[1:])

        return results

    def compare_results(self, report1: dict, report2: dict) -> dict:
        "compares the results from two reports"

        # TODO: handle recursive depths, where items are subtrees rather than Counters

        report = {}

        for key in report1:
            # TODO: deal with missing keys from one set
            report1_total = report1[key].total()
            report2_total = report2[key].total()
            report[key] = {}

            for subkey in report1[key].keys():
                delta = 0.0
                total = 0
                if subkey in report1[key] and subkey in report2[key]:
                    delta = (
                        report2[key][subkey] / report2_total
                        - report1[key][subkey] / report1_total
                    )
                    total = report2[key][subkey] + report1[key][subkey]
                    ref_count = report1[key][subkey]
                    comp_count = report2[key][subkey]
                else:
                    delta = -1.0
                    total = report1[key][subkey]
                    ref_count = report1[key][subkey]
                    comp_count = 0

                report[key][subkey] = {
                    "delta": delta,
                    "total": total,
                    "ref_count": ref_count,
                    "comp_count": comp_count,
                }

            for subkey in report2[key].keys():
                if subkey not in report[key]:
                    delta = 1.0
                    total = report2[key][subkey]
                    ref_count = 0
                    comp_count = report2[key][subkey]

                    report[key][subkey] = {
                        "delta": delta,
                        "total": total,
                        "ref_count": ref_count,
                        "comp_count": comp_count,
                    }

        return report

    def print_report(self, report: dict) -> None:
        "prints a report to the console"
        console = Console()
        for key in sorted(report):
            reported: bool = False

            if self.print_match_string and self.print_match_string not in key:
                continue

            for subkey, data in sorted(
                report[key].items(), key=lambda x: x[1]["delta"]
            ):
                delta: float = data["delta"]
                total: int = data["total"]
                comp_count: int = data["comp_count"]
                ref_count: int = data["ref_count"]
                print_it: bool = False

                if self.only_positive and delta <= 0:
                    continue

                if self.only_negative and delta >= 0:
                    continue

                if not self.print_threshold and not self.print_minimum_count:
                    # always print
                    print_it = True
                elif self.print_threshold and not self.print_minimum_count:
                    # check print_threshold as a fraction
                    if abs(delta) > self.print_threshold:
                        print_it = True
                elif not self.print_threshold and self.print_minimum_count:
                    # just check print_minimum_count
                    if total > self.print_minimum_count:
                        print_it = True
                else:
                    # require both
                    if (
                        total > self.print_minimum_count
                        and abs(delta) > self.print_threshold
                    ):
                        print_it = True

                if print_it:
                    # print the header
                    if not reported:
                        print(f"====== {key}")
                        reported = True
                    style = ""
                    if delta < -0.5:
                        style = "[bold red]"
                    elif delta < 0.0:
                        style = "[red]"
                    elif delta > 0.5:
                        style = "[bold green]"
                    elif delta > 0.0:
                        style = "[green]"
                    endstyle = style.replace("[]", "[/")
                    line = f"  {style}{subkey:<50}{endstyle}"
                    line += f"{delta:>6.3f} {total:>8} "
                    line += f"{comp_count:>8} {ref_count:>8}"
                    console.print(line)

    def print(self) -> None:
        "outputs the results"
        for n, report in enumerate(self.reports):
            print(f"************ report #{n}")
            self.print_report(report)

    def compare(self) -> None:
        "Compares each pcap against the original source"

        reports = []

        # TODO: use parallel processes to load multiple at a time

        # load the first as a reference pcap
        reference = self.load_pcap(self.pcaps[0])
        for pcap in self.pcaps[1:]:

            # load the next pcap
            other = self.load_pcap(pcap)

            # compare the two
            reports.append(self.compare_results(reference, other))

        self.reports = reports

    def save_report(self, where: str) -> None:
        "Saves the generated reports to a pickle file"

        # wrap the report in a version header
        versioned_report = {
            "PCAP_COMPARE_VERSION": self.REPORT_VERSION,
            "reports": self.reports,
            "files": self.pcaps,
        }

        # save it
        pickle.dump(versioned_report, open(where, "wb"))

    def load_report(self, where: str) -> None:
        "Loads a previous saved report from a file instead of re-parsing pcaps"
        self.reports = pickle.load(open(where, "rb"))

        # check that the version header matches something we understand
        if self.reports["PCAP_COMPARE_VERSION"] != self.REPORT_VERSION:
            raise ValueError(
                "improper saved version: report version = "
                + str(self.reports["PCAP_COMPARE_VERSION"])
                + ", our version: "
                + str(self.REPORT_VERSION)
            )

        # proceed as normal beyond this
        self.reports = self.reports["reports"]


def main():
    args = parse_args()
    pc = PcapCompare(
        args.pcap_files,
        maximum_count=args.packet_count,
        print_threshold=args.print_threshold,
        print_minimum_count=args.print_minimum_count,
        print_match_string=args.print_match_string,
        only_positive=args.only_positive,
        only_negative=args.only_negative,
    )

    # TODO: throw an error when both pcaps and load files are specified

    if args.load_report:
        # load a previous saved dump
        pc.load_report(args.load_report)
    else:
        # actually compare the pcaps
        pc.compare()

    # print the results
    pc.print()

    # maybe save them
    # TODO: loading and saving both makes more sense, throw error
    if args.save_report:
        pc.save_report(args.save_report)


if __name__ == "__main__":
    main()
