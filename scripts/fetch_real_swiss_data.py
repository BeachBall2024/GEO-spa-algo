import requests
import csv
import time
import json
import ssl

BBOX = "47.37,8.535,47.375,8.54"
# Swiss specific instance of overpass API which might be more reliable and faster here
URLS = [
    "https://overpass-api.de/api/interpreter",
    "http://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter"
]

def fetch_with_retries(query):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    for url in URLS:
        print(f"Trying {url} ...")
        try:
            resp = requests.post(url, data={'data': query}, headers=headers, timeout=20)
            if resp.status_code == 200:
                print("Success!")
                return resp.json()
            else:
                print(f"Failed with {resp.status_code}")
        except Exception as e:
            print(f"Exception: {e}")
    return None

def main():
    print("Fetching Real Data for Zurich...")
    street_q = f"[out:json][timeout:15];way[\"highway\"]({BBOX});(._;>;);out body;"
    poi_q = f"[out:json][timeout:15];(node[\"amenity\"]({BBOX});node[\"leisure\"]({BBOX});node[\"shop\"]({BBOX}););out body;"
    
    st_data = fetch_with_retries(street_q)
    if st_data:
        nodes = {e['id']: (e['lat'], e['lon']) for e in st_data['elements'] if e['type'] == 'node'}
        ways = [e for e in st_data['elements'] if e['type'] == 'way' and 'nodes' in e]
        
        with open('/workspaces/GEO/data/zurich_streets_real.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['segment_id', 'street_name', 'start_lat', 'start_lon', 'end_lat', 'end_lon'])
            for idx, way in enumerate(ways):
                name = way.get('tags', {}).get('name', f"Unknown_{idx}")
                for i in range(len(way['nodes'])-1):
                    n1, n2 = way['nodes'][i], way['nodes'][i+1]
                    if n1 in nodes and n2 in nodes:
                        w.writerow([f"{way['id']}_{i}", name, nodes[n1][0], nodes[n1][1], nodes[n2][0], nodes[n2][1]])
                        
    poi_data = fetch_with_retries(poi_q)
    if poi_data:
        with open('/workspaces/GEO/data/zurich_sounds_real.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['id', 'lat', 'lon', 'tags'])
            w.writeheader()
            for e in poi_data.get('elements', []):
                if e['type'] == 'node':
                    tags_str = " ".join(f"{k}={v}" for k,v in e.get('tags', {}).items()).lower()
                    if 'parking' in tags_str or 'station' in tags_str: tags_str += " car bus train traffic"
                    if 'park' in tags_str or 'tree' in tags_str: tags_str += " bird water leaves"
                    if 'restaurant' in tags_str or 'bar' in tags_str: tags_str += " talk laugh crowd music"
                    if 'shop' in tags_str: tags_str += " indoor fan hum"
                    w.writerow({'id': e['id'], 'lat': e['lat'], 'lon': e['lon'], 'tags': tags_str})
                    
if __name__ == '__main__': main()
