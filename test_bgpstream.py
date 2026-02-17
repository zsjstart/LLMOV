#!/usr/bin/env python

import pybgpstream
import time
import ipaddress
from datetime import datetime, UTC, timezone
import requests
from rpki_validator import validate_prefix_asn, get_rpki_status
from together_agent import analyze_with_together
from get_caida_data import get_relationship_dict
from collections import defaultdict
import json


TOGETHER_API_KEY = "5f71d0762fb272b44bd4163f02394d3aba0f0bc388eb617dfb7e58b9383e9be8"
TOGETHER_URL = "https://api.together.xyz/v1/chat/completions"


def query_together_ai(messages, model="deepseek-ai/DeepSeek-R1"):
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": messages
    }
    response = requests.post(TOGETHER_URL, headers=headers, json=data)
    print("Responses: ", response.json())
    return response.json()["choices"][0]["message"]["content"]


def analyze_bgp_data(bgp_data):
    messages = [
        {"role": "system", "content": "You are a network analyst specialized in BGP routing anomalies."},
        {"role": "user", "content": f"Analyze the following BGP updates and identify any anomalies:\n{bgp_data}"}
    ]
    return query_together_ai(messages)

def get_bgp_updates_with_specific_timeslot(prefix=None):
    '''
    stream = pybgpstream.BGPStream(
        from_time="2025-05-31 21:30:00",
        until_time="2025-05-31 23:00:00",
        collectors=["rrc00"],
        record_type="updates"
    )
    '''
    
    stream = pybgpstream.BGPStream(
        from_time="2025-05-31 18:30:00",
        until_time="2025-05-31 21:29:59",
        collectors=["rrc00"],
        record_type="updates"
    )
    
    if prefix:
        stream.add_filter("prefix", prefix)

    
    elems = defaultdict(list)
    for elem in stream:
        
        try:
            if elem.type != 'A': continue
            record_prefix = elem.fields.get("prefix", "")
            if not record_prefix or ipaddress.ip_network(record_prefix).version == 6:
                continue
                
            as_path_str = elem.fields.get("as-path", "") #"14907 3356 6453 55259 {32098}"
            if "{" in as_path_str and "}" in as_path_str: continue
            as_path = list(map(int, as_path_str.strip().split()))
            if len(as_path) == 0:
                print(elem)
                continue
                
            timestamp = datetime.utcfromtimestamp(elem.time).strftime('%Y-%m-%d %H:%M:%S')
            elems[(record_prefix, tuple(as_path))].append(timestamp)
            
        except ValueError:
            continue
        
        
    updates = []
    for item in elems:
        updates.append({
                "timestamp": elems[item][0],
                #"peer_asn": elem.peer_asn,
                #"type": elem.type,
                "prefix": item[0],
                "as_path": item[1],
                "origin_as": item[1][-1]
            })
            
    return updates

def parse_as_path(as_path_str):
    asns = []
    for token in as_path_str.strip().split():
        # remove braces and parentheses
        token = token.strip("{}()")
        if token.isdigit():
            asns.append(int(token))
    return asns


def get_bgp_updates(prefix=None, duration=300):
    now = int(time.time())
    start_time = now - duration

    start_str = datetime.fromtimestamp(start_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    end_str = datetime.fromtimestamp(now, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    
    #BGP collectors like RouteViews EQIX (route-views.eqix) or RouteViews SG (route-views.sg) peer with hundreds of ASes globally.
    stream = pybgpstream.BGPStream(
        from_time=start_str,
        until_time=end_str,
        collector = "route-views.eqix", 
        record_type="ribs",
 
    )

    if prefix:
        stream.add_filter("prefix", prefix)

    
    elems = defaultdict(list)
    checked_prefix_origins = set()
    for elem in stream:
        
        try:
            record_prefix = elem.fields.get("prefix", "")
            if not record_prefix or ipaddress.ip_network(record_prefix).version == 6:
                continue
        except ValueError:
            continue
            
        as_path_str = elem.fields.get("as-path", "")
        #as_path = list(map(int, as_path_str.strip().split()))
        as_path = parse_as_path(elem.fields["as-path"])
        origin = as_path[-1]
        if (record_prefix, origin) in checked_prefix_origins: continue
        
        
        
        timestamp = datetime.utcfromtimestamp(elem.time).strftime('%Y-%m-%d %H:%M:%S')
        elems[(record_prefix, tuple(as_path))].append(timestamp)
        checked_prefix_origins.add((record_prefix, origin))
        
   
    updates = []
    for item in elems:
        updates.append({
                "timestamp": elems[item][0],
                #"peer_asn": elem.peer_asn,
                #"type": elem.type,
                "prefix": item[0],
                "as_path": item[1],
                "origin_as": item[1][-1]
            })

    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}] Collected {len(updates)} updates.")
    return updates



def analyze_bgp(updates, prefix: str, user_query: str):  
    context_parts = []
    for upd in updates:
        status = validate_prefix_asn(upd["prefix"], upd["origin_as"])
        as_path = upd["as_path"] # A path list
        as_relationships = get_relationship_dict()
        #valley = is_valley_path(as_path, as_relationships) #Does the path violate the valley-free policy?: {valley}
        if valley is None: valley = "Cannot determine due to missing AS relationship info"
        context_parts.append(f"""
				Prefix: {upd["prefix"]}
				Origin AS: {upd["origin_as"]}
				AS Path: {upd["as_path"]}
				RPKI Validation: {status}
				""")
				
    full_context = "\n".join(context_parts[:5])
    return analyze_with_together(full_context, user_query)

def is_valley_path(as_path, as_relationships):
	if len(as_path) < 2:
		return False  # A single AS or empty path is trivially valley-free
	
	state = None  # Can be "c2p", "p2p", or "p2c"
	
	for i in range(len(as_path) - 1):
		as1, as2 = as_path[i], as_path[i + 1]
		relationship = as_relationships.get((as1, as2), None)
		#print((as1, as2), relationship)
		
		if relationship is None:
			return None 
		C2P, P2C, P2P = 1, -1, 0
		if relationship == C2P:
			if state in {P2C, P2P}:  return True  # Valley detected: customer should not follow a provider/peer
			state = C2P
		
		elif relationship == P2P:
			if state in {P2C, P2P}: return True  # Valley detected: peer should not follow provider/peer
			state = P2P
		
		elif relationship == P2C:
			state = P2C 
	
	return False  # No valleys detected
    

#start from this function, extract RPKI invalid routes....
def monitor_bgp_02(prefix: str, user_query: str, interval=300):
        
        updates = None
        
        try:
            updates = get_bgp_updates(prefix=prefix, duration=interval)
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch updates: {e}")
            
        invalid_updates = []
        if updates:
        	
            for upd in updates:
            
                #rpki_status = get_rpki_status(upd["prefix"], upd["origin_as"])
                rpki_data = validate_prefix_asn(upd["prefix"], upd["origin_as"])
                
                if rpki_data.get("validated_route", {}).get("validity", {}).get("state", "unknown") == "invalid":
                    invalid_updates.append(upd)
                    #if rpki_data.get("validated_route", {}).get("validity", {}).get('description', '') == 'At least one VRP Covers the Route Prefix, but no VRP ASN matches the route origin ASN':
                        
                       
                        
            #response = analyze_bgp(updates, prefix, user_query)
            #print("Response: ", response)
            
        else:
            print("[INFO] No BGP updates found in the last 5 minutes.")
        
        
        #Save the list to a JSON file
        with open("invalid_routes_list_large_new.json", "w") as file:
            json.dump(invalid_updates, file)

def count_invalid_updates():
    with open("invalid_routes_list_large_new.json", "r") as f:
        data = json.load(f)
    print(len(data))
    
def monitor_bgp(prefix: str, user_query: str, interval=300):
    print("[INFO] Starting BGP monitoring loop (interval: 5 minutes)...")
    num = 0
    while True:
        loop_start = time.time()
        invalid_updates = []
        #try:
            #updates = get_bgp_updates(prefix=prefix, duration=interval)
        updates = get_bgp_updates_with_specific_timeslot(prefix)
        
        if updates:
        	
            for upd in updates:
            
                #rpki_status = get_rpki_status(upd["prefix"], upd["origin_as"])
                rpki_data = validate_prefix_asn(upd["prefix"], upd["origin_as"])
                
                if rpki_data.get("validated_route", {}).get("validity", {}).get("state", "unknown") == "invalid":
                    if rpki_data.get("validated_route", {}).get("validity", {}).get('description', '') == 'At least one VRP Covers the Route Prefix, but no VRP ASN matches the route origin ASN':
                        invalid_updates.append(upd)
                        num = num + 1
                        if num == 400: break
                        
            #response = analyze_bgp(updates, prefix, user_query)
            #print("Response: ", response)
            
        else:
            print("[INFO] No BGP updates found in the last 5 minutes.")
        #except Exception as e:
        #    print(f"[ERROR] Failed to fetch updates: {e}")
        
        
            
        elapsed = time.time() - loop_start
        
        sleep_time = max(0, interval - elapsed)
        
        print("[INFO] Sleeping 5 minutes before next check...\n")
        sleep_time = 300
        #time.sleep(sleep_time)
        
        
if __name__ == "__main__":

    #prefix="103.158.6.0/24"
    prefix = None
    user_query = "Can you analyze these BGP updates?"
    #get_bgp_updates(prefix, duration=3600*2)
    #monitor_bgp_02(prefix, user_query, interval=3600*2)
    #count_invalid_updates()
    
    '''
    as_relationships = get_relationship_dict()
    as_path = [7018, 3356, 174, 1239]
    valley = is_valley_path(as_path, as_relationships)
    print(valley)
    '''
    
    '''
    bgp_updates = get_bgp_updates(prefix="38.224.21.0/24")
    
    formatted_data = "\n".join([str(update) for update in bgp_updates])
    print(formatted_data)
    response = analyze_bgp_data(formatted_data)
    print("LLM Analysis:\n", response)
    '''
