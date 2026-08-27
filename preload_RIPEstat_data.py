# load_ripestat_data.py
import json
import os
import shaman_data_process_lib
from process_htmls import fetch_ripestat_prefix_html, fetch_ripestat_asn_html
from rpki_validator import validate_prefix_asn, extract_roa_asns

# ----------------------------
# Cache file paths
# ----------------------------
PREFIX_CACHE_FILE = "./cache/RIPEstat_prefix_cache.json"
ASN_CACHE_FILE = "./cache/RIPEstat_asn_cache.json"
# ----------------------------
# Cache helpers
# ----------------------------
def _load_json(filepath: str) -> dict:
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_json(filepath: str, data: dict):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def collect_route_data():
    data_file = "./shaman/real_hijacks.csv"
    origin_conflicting_routes = shaman_data_process_lib.extract_invalid_routes(data_file)
    prefixes, asns = set(), set()
    for i in range(0, len(origin_conflicting_routes)):
        prefix = origin_conflicting_routes[i]['prefix']
        prefixes.add(prefix)
        origin_asn = origin_conflicting_routes[i]['origin_as']
        asns.add(str(origin_asn))
        rpki_data = validate_prefix_asn(prefix, origin_asn)
        rpki_validation_output, roa_asns = extract_roa_asns(rpki_data)
        for roa_asn in roa_asns:
            asns.add(roa_asn)
    return prefixes, asns

# ----------------------------
# Main loader
# ----------------------------
def load_ripestat_data(
    prefixes,
    asns,
    prefix_cache_file=PREFIX_CACHE_FILE,
    asn_cache_file=ASN_CACHE_FILE,
):
    prefix_cache = _load_json(prefix_cache_file)
    asn_cache = _load_json(asn_cache_file)
    
    
    # Process prefixes
    for prefix in prefixes:
        entry = prefix_cache.setdefault(prefix, {})

        if not entry.get("RIPEstat_prefix_json"):
            entry["RIPEstat_prefix_json"] = fetch_ripestat_prefix_html(prefix)
    

    # Process ASNs
    for asn in asns:
        entry = asn_cache.setdefault(asn, {})
        if not entry.get("RIPEstat_origin_asn_json"):
            entry["RIPEstat_origin_asn_json"] = fetch_ripestat_asn_html(asn)

    _save_json(prefix_cache_file, prefix_cache)
    _save_json(asn_cache_file, asn_cache)

    print("RIPEstat caches updated successfully.")
    return

if __name__ == "__main__":
    prefixes, asns = collect_route_data()
    print(prefixes, asns)
    load_ripestat_data(prefixes, asns)
