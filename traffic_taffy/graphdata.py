import os
from pandas import DataFrame, to_datetime, concat


class PcapGraphData:
    def __init__(self):
        self.dissections = []
        pass

    @property
    def dissections(self):
        return self._dissections

    @dissections.setter
    def dissections(self, newvalue):
        self._dissections = newvalue

    def normalize_bins(self, dissection):
        results = {}
        time_keys = list(dissection.data.keys())
        if time_keys[0] == 0:  # likely always
            time_keys.pop(0)

        results = {"time": [], "count": [], "index": [], "key": []}

        # TODO: this could likely be made much more efficient and needs hole-filling
        for timestamp, key, subkey, value in dissection.find_data(
            timestamps=time_keys,
            match_string=self.match_string,
            match_value=self.match_value,
            minimum_count=self.minimum_count,
            make_printable=True,
        ):
            index = key + "=" + subkey
            results["count"].append(int(value))
            results["index"].append(index)
            results["key"].append(index)
            results["time"].append(timestamp)

        return results

    def get_dataframe(self):
        datasets = []
        for dissection in self.dissections:
            data = self.normalize_bins(dissection)
            data = DataFrame.from_records(data)
            data["filename"] = os.path.basename(dissection.pcap_file)
            data["time"] = to_datetime(data["time"], unit="s", utc=True)
            data["key"] = data["index"]
            datasets.append(data)
        datasets = concat(datasets, ignore_index=True)
        return datasets
