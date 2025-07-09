import os
import urllib.request
import bz2
import sqlite3
import datetime
from collections import defaultdict

def get_latest_caida_url():
    # Get the latest month in YYYYMM format
    today = datetime.date.today()
    latest_month = today.replace(day=1)
    date_str = latest_month.strftime("%Y%m01")
    filename = f"{date_str}.as-rel2.txt.bz2"
    url = f"https://data.caida.org/datasets/as-relationships/serial-2/{filename}"
    return url, filename

def download_caida_data(save_dir="data/caida"):
    os.makedirs(save_dir, exist_ok=True)

    url, filename = get_latest_caida_url()
    save_path = os.path.join(save_dir, filename)

    print(f"📥 Downloading from: {url}")
    print(f"💾 Saving to: {save_path}")

    try:
        urllib.request.urlretrieve(url, save_path)
        print("✅ Download completed successfully.")
    except Exception as e:
        print(f"❌ Download failed: {e}")

    return save_path

def load_data_into_sqlite(bz2_file, db_path="caida.db"):
    print("Updating local database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS as_relationships (
            asn1 INTEGER,
            asn2 INTEGER,
            relationship INTEGER,
            PRIMARY KEY (asn1, asn2)
        )
    ''')
    # rel=-1: p2c, rel=1: c2p, rel=0: p2p
    with bz2.open(bz2_file, 'rt') as f:
        for line in f:
            if line.startswith('#'):
                continue
            parts = line.strip().split('|')
            
            if len(parts) == 4:
                a, b, rel = map(int, parts[:3])
                
                
                cursor.execute('REPLACE INTO as_relationships VALUES (?, ?, ?)', (a, b, rel))
                
                if rel == -1:
                    cursor.execute('REPLACE INTO as_relationships VALUES (?, ?, ?)', (b, a, 1))
                    
                elif rel == 0:
                    cursor.execute('REPLACE INTO as_relationships VALUES (?, ?, ?)', (b, a, 0))
                    

    conn.commit()
    conn.close()
    print("Database updated.")



def get_relationship(asn1, asn2, db_path="caida.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT relationship FROM as_relationships
        WHERE asn1 = ? AND asn2 = ?
    ''', (asn1, asn2))

    result = cursor.fetchone()
    conn.close()

    if result:
        return result[0]  # relationship is an integer (-1, 0, or 1)
    else:
        return None  # no relationship found

def get_relationship_dict(db_path="caida.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT asn1, asn2, relationship FROM as_relationships")
    
    result = {}
    for asn1, asn2, rel in cursor.fetchall():
        result[(asn1, asn2)] = rel
    
    conn.close()
    return result

def get_caida_rels(asn, all_relationships):
    res = defaultdict(lambda: {'peers': set(), 'providers': set(), 'customers': set()})
    
    for t in all_relationships:
        
        if asn in t:
            
            if all_relationships[t] == 0:
                position = t.index(asn)
                if position == 0:
                    res[asn]['peers'].add(t[1])
                else:
                    res[asn]['peers'].add(t[0])
                    
            elif all_relationships[t] == 1:
                position = t.index(asn)
                if position == 0:
                    res[asn]['providers'].add(t[1])
                else:
                    res[asn]['customers'].add(t[0])
    
    res[asn]['peers'] = list(res[asn]['peers'])
    res[asn]['providers'] = list(res[asn]['providers'])
    res[asn]['customers'] = list(res[asn]['customers'])
    
    return res
                
    

if __name__ == "__main__":
    #file = download_caida_data()
    #load_data_into_sqlite(file)
    # Example usage
    rel = get_relationship(15169, 3356)
    if rel == -1:
        print("15169 is a provider of 3356")
    elif rel == 1:
        print("15169 is a customer of 3356")
    elif rel == 0:
        print("15169 and 3356 are peers")
    else:
        print("No relationship found between 15169 and 3356")
    
    all_relationships = get_relationship_dict()
    #print(all_relationships[(15169, 3356)])
    print(get_caida_rels(2914, all_relationships))
    

