import requests
from process_htmls import fetch_ripestat_prefix_html, fetch_ripestat_asn_html, build_prompt
import json
from get_caida_data import get_relationship, get_relationship_dict, get_caida_rels
from rpki_validator import validate_prefix_asn, extract_roa_asns
from load_ihr_hegemony import get_heg_dependency
from gemini_agent import analyze_with_gemini
import pickle
from datetime import datetime
from extract_json import extract_origin_conflict_routes



TOGETHER_API_KEY = "tgp_v1_8Y3DAJ-NGohHEvtH2rgCu6j5rSeGU6-Da84EQs6BKtM"
TOGETHER_URL = "https://api.together.xyz/v1/chat/completions"




def analyze_with_together(context, query):
    template = f"""
You are a BGP routing analyst. Use the following context to address the tasks:

Context:
{context}

Tasks:
{query}

Answer:
"""

    payload = {
        #"model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
        
        "model": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        "temperature": 0.6,
        "messages": [
            {"role": "user", "content": template}
        ]
    }
    
    print(payload)
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post(TOGETHER_URL, headers=headers, json=payload)
    response_json = response.json()
    
    if "choices" in response_json:
        return response_json["choices"][0]["message"]["content"]
    else:
        print("Error or unexpected responses!")
        return response_json

def examine_invalid_routes():
    origin_conflicting_routes = list()
    with open("invalid_routes_list.json", "r") as file:
        invalid_routes = json.load(file)
        for route in invalid_routes:
            prefix = route['prefix']
            origin_asn = route['origin_as']
            rpki_data = validate_prefix_asn(prefix, origin_asn)
            
            if rpki_data.get("validated_route", {}).get("validity", {}).get('description', '') == 'At least one VRP Covers the Route Prefix, but no VRP ASN matches the route origin ASN':
                origin_conflicting_routes.append(route)
            else:
                print(rpki_data)
            
           
        
    return origin_conflicting_routes
    
    
def together_agent():
    #{'timestamp': '2025-05-31 00:35:01', 'prefix': '41.87.31.0/24', 'as_path': (49673, 3216, 6453, 6762, 30844, 36969), 'origin_as': 36969}
    #Possible as path manipulation: [49673, 20485, 6762, 17494, 150748, 150748, 139026, 23923, 23923] 23923 is announcing a prefix authorized by 139026.
    
    
    origin_conflicting_routes = examine_invalid_routes()
    checked = set()
    num = 0
    for i in range(0, len(origin_conflicting_routes)):
        
        timestamp = origin_conflicting_routes[i]['timestamp']
        prefix = origin_conflicting_routes[i]['prefix']
        origin_asn = origin_conflicting_routes[i]['origin_as']
        as_path = list(origin_conflicting_routes[i]['as_path'])
        rpki_data = validate_prefix_asn(prefix, origin_asn)
        if (prefix, origin_asn) in checked: continue
        checked.add((prefix, origin_asn))
        num = num + 1
        
        
        
        #print(rpki_data)
        
        
        
        f = open('./results/benign_conflicts/gemini_reasoning_origin_conflicting_routes_('+str(num)+').txt', 'w')
        

        vrps, roa_asns = extract_roa_asns(rpki_data)
        #get_relationship(origin_asn, roa_asn)
        all_relationships = get_relationship_dict()
        caida_data = get_caida_rels(origin_asn, all_relationships)
        
        
        hege_data = get_heg_dependency(origin_asn, roa_asns, timestamp) # Hegemony data can support the Caida data as there are possible errors in caida data.
        

        rpki_json = json.dumps(rpki_data)
        caida_json = json.dumps(caida_data)
        RIPEstat_prefix_json = fetch_ripestat_prefix_html(prefix)
        RIPEstat_origin_asn_json = fetch_ripestat_asn_html(origin_asn)

        RIPEstat_roas_asn_list = []
        for roa_asn in roa_asns:
            RIPEstat_roas_asn_list.append(fetch_ripestat_asn_html(roa_asn))
            
        RIPEstat_roas_asn_json = json.dumps(RIPEstat_roas_asn_list)



        #print(RIPEstat_roas_asn_json)


        ##CAIDA AS rank data: {}
        Context = f'''RPKI enforces strict origin validation, which can reject legitimate announcements due to origin-AS mismatches. Some invalid routes stem from operator misconfigurations between closely related ASes (e.g., customer-provider or sibling relationships), known as benign origin conflicts. The closer the AS-level relationship between the two conflicting origins, the more likely the route is benign. Please infer the relation level between the origin AS in the announcement and the authorized AS in the ROA based on the information provided. You can examine it from aspects of economic/policy distance and geographical distance between the origin AS in the announcement and the authorized AS in the ROA, and reevaluate the following RPKI-invalid BGP route (If the route is identified as RPKI-valid, please only output "This is an RPKI-valid route."):

            Announcement timestamp: {timestamp}
            
            Prefix: {prefix}

            Origin AS in BGP update: AS{origin_asn}

            AS path: {as_path}

        NOTE: please take care of the announcement timestamp, particularly when analyzing transfer history, and consider possible AS path manipulation in case of analyzing AS path. Also, you may need to take account of possible errors in CAIDA data.
        
        Extra information collected for this prefix:

            RPKI data (VRPs): {vrps}
            
            CAIDA AS relationship data: {caida_json}
            
            IHR Hegemony (AS dependency) data: {hege_data}
            
            RIPEstat json data of the announced prefix: {RIPEstat_prefix_json}
            
            RIPEstat json data of the origin AS in BGP update: {RIPEstat_origin_asn_json}
            
            RIPEstat json data of the authorized ASes in ROAs: {RIPEstat_roas_asn_json}
            
            


        '''
        #query = "Does this invalid route appear to be benign conflicts or suspicious hijacks? Briefly explain."
        query = '''
        - First, summarize this BGP route.
        - Evaluate the likelihood that this invalid BGP announcement is benign.
        - Provide a level value ("Low", "Medium", or "High") representing the possibility that it is benign:
        
            "Low": No relationship and no circumstantial support (e.g. totally unrelated ASes in different regions);
            "Medium": Ambiguous case with some circumstantial clues but no confirmation;
            "High": Strong evidence of benign relationship (e.g. same org, clear provider-customer tie).

        - Explain how and why you assigned the level value to the route.
        - Provide a possible reason (e.g., traffic engineering) for why this conflict occurred.
        - Finally, summarize it in the following JSON format:
        
        {
              "prefix": "string",
              "as_path": "string",
              "origin_as": "string",
              "authorized_as in ROAs": "string",
              "benign_level": "High | Medium | Low",
              "explanation": "string",
              "possible_reason": "string"
        }

        
        '''
        #in some case, I did see the origin as is a customer of a major upstream (like a tier1 as)

        #response = analyze_with_together(Context, query)
        response = analyze_with_gemini(Context, query)
        
        f.write(response+'\n')
        f.close()
        if num==100: break
        
        
    

if __name__ == "__main__":
    '''
    origin_conflicting_routes = examine_invalid_routes()
    checked = set()
    num = 0
    f = open('./100_origin_conflicts.csv', 'w')
    #1601401585,191.101.242.0/24,None,1221,14618+16509
    for i in range(0, len(origin_conflicting_routes)):
        
        timestamp = origin_conflicting_routes[i]['timestamp']
        prefix = origin_conflicting_routes[i]['prefix']
        origin_asn = origin_conflicting_routes[i]['origin_as']
        as_path = list(origin_conflicting_routes[i]['as_path'])
        rpki_data = validate_prefix_asn(prefix, origin_asn)
        vrps, roa_asns = extract_roa_asns(rpki_data)
        if (prefix, origin_asn) in checked: continue
        checked.add((prefix, origin_asn))
        num = num + 1
        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        timestamp = int(dt.timestamp())
        f.write(str(timestamp)+','+prefix+','+ '+'.join(map(str, as_path)) +','+ str(origin_asn)+ ',' + '+'.join(list(roa_asns))+'\n')
        if num == 100: break
        
        
    f.close()
    '''
    
    #examine_invalid_routes()
    #together_agent()
    
    Context = extract_origin_conflict_routes()
    print(len(Context))
    query = '''
    please classify the RPKI-invalid routes included in the Context based on possible root causes. RPKI-invalid routes described individually.

Each route entry includes fields such as:

    prefix

    origin_as

    authorized_as in ROAs

    explanation

    possible_reason. 
    
    
How many routes are there in total? Please answer how many routes involve customer-provider relationship, how many involve the same organizations, how many involve AS dependency, how many involve Transfer/Ownership changes. If a route falls into multiple categores, the counts should be non-exclusive. How many involve traffic engineering?
    
    
    '''
    response = analyze_with_together(Context, query)
    print(response)
  
    



