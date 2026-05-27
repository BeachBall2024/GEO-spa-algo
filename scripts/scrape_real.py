import urllib.request
import json
import csv
import ssl

BBOX="47.371,8.541,47.372,8.542"

def get_osm_data():
    q = f'[out:json][timeout:25];(way["highway"]({BBOX});node["amenity"]({BBOX});node["leisure"]({BBOX});node["shop"]({BBOX}););out body;>;out skel qt;'
    url = "https://overpass-api.de/api/interpreter"
    data = urllib.parse.urlencode({'data': q}).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    req.add_header('User-Agent', 'GeoProxy/1.0')
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    print("Scraping real data from OpenStreetMap...")
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    return json.loads(resp.read().decode('utf-8'))

def save_data(data):
    nodes = {e['id']: (e['lat'], e['lon']) for e in data['elements'] if e['type'] == 'node'}
    ways = [e for e in data['elements'] if e['type'] == 'way' and 'nodes' in e]
    pois = [e for e in data['elements'] if e['type'] == 'node' and 'tags' in e]

    with open('/workspaces/GEO/data/zurich_streets_real.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['segment_id', 'street_name', 'start_lat', 'start_lon', 'end_lat', 'end_lon'])
        for idx, way in enumerate(ways):
            name = way.get('tags', {}).get('name', f"Unknown_{idx}")
            for i in range(len(way['nodes'])-1):
                n1, n2 = way['nodes'][i], way['nodes'][i+1]
                if n1 in nodes and n2 in nodes:
                    w.writerow([f"{way['id']}_{i}", name, nodes[n1][0], nodes[n1][1], nodes[n2][0], nodes[n2][1]])

    with open('/workspaces/GEO/data/zurich_sounds_real.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['id', 'lat', 'lon', 'tags'])
        for e in pois:
            t = " ".join(f"{k}={v}" for k,v in e['tags'].items()).lower()
            if 'parking' in t or 'station' in t: t += " car bus train traffic"
            if 'park' in t or 'tree' in t: t += " bird water leaves"
            if 'restaurant' in t or 'bar' in t: t += " talk laugh crowd music"
            if 'shop' in t: t += " indoor fan hum"
            w.writerow([e['id'], e['lat'], e['lon'], t])

if __name__ == "__main__":
    try:
        data = get_osm_data()
        save_data(data)
        print("Success! Data saved to zurich_streets_real.csv and zurich_sounds_real.csv")
    except Exception as e:
        print(f"Error scraping: {e}")
