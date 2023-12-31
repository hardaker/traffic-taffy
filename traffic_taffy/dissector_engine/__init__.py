"""Base class for a dissection engine with subclasses overriding load()"""

from traffic_taffy.dissection import Dissection, PCAPDissectorLevel


class DissectionEngine:
    def __init__(
        self,
        pcap_file,
        pcap_filter: str = "",
        maximum_count: int = 0,
        bin_size: int = 0,
        dissector_level: PCAPDissectorLevel = PCAPDissectorLevel.DETAILED,
        cache_file_suffix: str = "pkl",
        ignore_list: list = [],
    ):
        self.pcap_file = pcap_file
        self.dissector_level = dissector_level
        self.bin_size = bin_size
        self.maximum_count = maximum_count
        self.pcap_filter = pcap_filter
        self.cache_file_suffix = cache_file_suffix
        self.ignore_list = set(ignore_list)

    def init_dissection(self) -> Dissection:
        self.dissection = Dissection(
            pcap_file=self.pcap_file,
            dissector_level=self.dissector_level,
            bin_size=self.bin_size,
            pcap_filter=self.pcap_filter,
            maximum_count=self.maximum_count,
            cache_file_suffix=self.cache_file_suffix,
            ignore_list=self.ignore_list,
        )
        return self.dissection
