def get_relationship(as1, as2, caida_data):

    as1 = str(as1)
    #as2 = str(as2)

    if as1 not in caida_data:
        return "unknown"

    data = caida_data[as1]
    
    if as2 in data["providers"]:
        return "provider"

    if as2 in data["customers"]:
        return "customer"

    if as2 in data["peers"]:
        return "peer"

    return "none"
    
'''
caida_data = {"270168": {"peers": [], "providers": [270186, 28458, 28398], "customers": []}}
origin_as = 270168
ROA_as = 28458
rel = get_relationship(270168, 28458, caida_data)
print(f"The authorized AS in the ROA (AS{ROA_as}) is a {rel} of the origin AS in the announcement (AS{origin_as})."+"Done!")
'''
'''
caida_data = {"270168": {"peers": [], "providers": [270186, 28458, 28398], "customers": [11]}}
origin_asn = 270168
roa_asns = [111, 228458]
caida_as_rel = ""
for roa_asn in roa_asns:
    rel = get_relationship(origin_asn, roa_asn, caida_data)
    if rel != "none" and rel != "unknown":
        caida_as_rel = caida_as_rel + f"The authorized AS in ROAs (AS{roa_asn}) is a {rel} of the origin AS in the announcement (AS{origin_asn}). "

print(caida_as_rel)
'''
