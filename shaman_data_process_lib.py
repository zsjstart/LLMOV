import rpki_validator
import csv
from datetime import datetime

def extract_prefix_unexpected_from_csv(csv_file):
    """
    Extract unique (prefix, unexpected_origin_asn) pairs from CSV.

    Expected columns:
        time,prefix,unexpected_origin_asn

    Returns:
        set of tuples: {(prefix, asn), ...}
    """

    results = list()

    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            time = row.get("time")
            prefix = row.get("prefix")
            asn = row.get("unexpected_origin_asn")

            if prefix and asn:
                results.append((time.strip(), prefix.strip(), asn.strip()))

    return results
    
def extract_invalid_routes(csv_file):
    n = 0
    results = extract_prefix_unexpected_from_csv(csv_file)
    origin_conflicting_routes = list()
    
    for res in results:
        data = dict()
        response = rpki_validator.validate_prefix_asn(res[1], res[2])
        if response.get("validated_route", {}).get("validity", {}).get("state", "unknown") == "valid":
            n = n + 1
            dt = datetime.strptime(res[0], '%Y-%m-%d %H:%M')
            data['timestamp'] = str(dt)
            data['prefix'] = res[1]
            data['origin_as'] = int(res[2])
            data['as_path'] = []
            origin_conflicting_routes.append(data)
        
        
        
            
            
    print("Still invalid: ", n, n/len(results))
    
    return origin_conflicting_routes
   


if __name__ == "__main__":
    extract_invalid_routes("./shaman/test_output.csv")



