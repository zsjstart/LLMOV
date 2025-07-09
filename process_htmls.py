import requests
import json
from bs4 import BeautifulSoup
import random

'''
Geolocation	https://stat.ripe.net/data/geoloc/data.json?resource=8.8.8.0/24
Organization	https://stat.ripe.net/data/whois/data.json?resource=8.8.8.0/24
Visibility	https://stat.ripe.net/data/routing-status/data.json?resource=8.8.8.0/24
prefix overview https://stat.ripe.net/data/prefix-overview/data.json?resource=8.8.8.0/24
BGP state https://stat.ripe.net/data/bgp-state/data.json?resource=8.8.8.0/24
transfer history https://stat.ripe.net/data/transfer-history/data.json?resource=8.8.8.0/24
'''

'''
https://stat.ripe.net/data/routing-status/data.json?resource=AS8100
https://stat.ripe.netdata/transfer-history/data.json?resource=AS8100
https://stat.ripe.net/data/asn-neighbours/data.json?resource=AS8100
https://stat.ripe.net/data/as-overview/data.json?resource=AS8100
https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS8100
https://stat.ripe.net/data/as-routing-consistency/data.json?resource=AS8100
https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS8100

'''

def fetch_ripestat_prefix_html(prefix):

    urls = [f"https://stat.ripe.net/data/prefix-overview/data.json?resource={prefix}", f"https://stat.ripe.net/data/geoloc/data.json?resource={prefix}", f"https://stat.ripe.net/data/whois/data.json?resource={prefix}", f"https://stat.ripe.net/data/routing-status/data.json?resource={prefix}", f"https://stat.ripe.net/data/looking-glass/data.json?resource={prefix}", f"https://stat.ripe.net/data/related-prefixes/data.json?resource={prefix}", f"https://stat.ripe.net/data/transfer-history/data.json?resource={prefix}"]
    
    new_res = dict()
    for url in urls:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch HTML for {prefix}")
        
        res = response.json()
        
        if res['data_call_name']== "prefix-overview":
            new_res['prefix_overview'] = res.get("data", {})
        elif res['data_call_name']== "geoloc":
            new_res['geolocation'] = res.get("data", {}).get("located_resources", [])
        elif res['data_call_name']== "whois":
            new_res['irr_records'] = res.get("data", {}).get("irr_records", [])
        elif res['data_call_name']== "routing-status":
            new_res['routing_status'] = res.get("data", {})
        elif res['data_call_name']== "looking-glass":
            if not res.get("data", {}).get("rrcs", []): continue
            new_res['BGP_looking_glass'] = random.sample(res.get("data", {}).get("rrcs", []), 1)
        elif res['data_call_name']== "related-prefixes":
            new_res['related_prefixes'] = res.get("data", {})
        elif res['data_call_name']== "transfer-history":
            new_res['transfer_history'] = res.get("data", {})
    return new_res
# f"https://stat.ripe.net/data/as-routing-consistency/data.json?resource=AS{asn}"
def fetch_ripestat_asn_html(asn):

    urls = [f"https://stat.ripe.net/data/as-overview/data.json?resource=AS{asn}", f"https://stat.ripe.net/data/routing-status/data.json?resource=AS{asn}", f"https://stat.ripe.net/data/transfer-history/data.json?resource=AS{asn}", f"https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}", f"https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS{asn}"]
    new_res = dict()
    for url in urls:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            continue
        res = response.json()
        
        if res['data_call_name']== "as-overview":
            new_res['as_overview'] = res.get("data", {})
        
        elif res['data_call_name']== "routing-status":
            new_res['routing_status'] = res.get("data", {})
        
        elif res['data_call_name']== "transfer-history":
            new_res['transfer_history'] = res.get("data", {})
            
        elif res['data_call_name']== "announced-prefixes":
            new_res['announced-prefixes'] = res.get("data", {})
        
        elif res['data_call_name']== "maxmind-geo-lite-announced-by-as":
            new_res['geolocation'] = res.get("data", {}).get("located_resources", [])
        
       
        
    
    return new_res
    
def build_prompt(json, prefix):
    return f"""
You are a network routing analyst. Below is json data from the RIPEstat for the BGP prefix `{prefix}`.
Here is the HTML content: {json}
Can you understand it and explain briefly.
"""

TOGETHER_API_KEY = "5f71d0762fb272b44bd4163f02394d3aba0f0bc388eb617dfb7e58b9383e9be8"
TOGETHER_URL = "https://api.together.xyz/v1/chat/completions"
MODEL_NAME = "deepseek-ai/DeepSeek-R1"

def query_together(prompt):
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are an expert in BGP routing and RPKI analysis."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6,
        "max_tokens": 1024
    }
    
    print(data)
    response = requests.post(TOGETHER_URL, headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"API request failed: {response.status_code} {response.text}")

    try:
        return response.json()["choices"][0]["message"]["content"]
    except KeyError:
        print("Unexpected response format:")
        print(response.text)
        return None



            


'''
prefix = "8.8.8.0/24"
html = fetch_ripestat_html(prefix)
prompt = build_prompt(html, prefix)
response = query_together(prompt)
print(response)
'''





