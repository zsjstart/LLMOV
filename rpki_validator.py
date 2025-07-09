# rpki_validator.py
import requests
#curl "http://127.0.0.1:8323/validity?asn=15169&prefix=8.8.8.0/24"

def get_rpki_status(prefix, origin_as):
    url = f"http://127.0.0.1:8323/api/v1/validity/{origin_as}/{prefix}"
    r = requests.get(url)
  
    if r.status_code == 200:
        result = r.json()
        return result.get("validated_route", {}).get("validity", {}).get("state", "unknown")
    return None #"Error: Routinator API unreachable"

def validate_prefix_asn(prefix, origin_as):
    url = f"http://127.0.0.1:8323/api/v1/validity/{origin_as}/{prefix}"
    r = requests.get(url)
  
    if r.status_code == 200:
        result = r.json()
        #return result.get("validated_route", {}).get("validity", {}).get("state", "unknown")  
        return result
    return None #"Error: Routinator API unreachable"

def extract_roa_asns(res):
    asns = set()
    vrps = res.get("validated_route", {}).get("validity", {}).get("VRPs", {}).get("unmatched_as", [])
    for vrp in vrps:
        asns.add(''.join(filter(str.isdigit, vrp['asn'])))
    return vrps, asns
    


'''
prefix = "8.8.8.0/25"
origin_as = "15169"

response = validate_prefix_asn(prefix, origin_as)
print(response)
'''



