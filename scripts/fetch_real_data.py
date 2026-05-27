import requests
import json
import csv
import time

BBOX = "47.370,8.535,47.375,8.545" # Zurich center (Lindenhof/Rathaus area)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Overpass API requires a valid User-Agent to prevent 504s/blocks
HEADERS = {
    'User-Agent': 'GeoProxyAnalysis/1.0 (Research / Student Project)'
}

def fetch_osm_data(query):
    print(f"Fetching data from Overpass API...\nQuery: {query[:50]}...")
    try:
        response = requests.get(OVERPASS_URL, params={'data': query}, headers=HEADERS, timeout=60)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"Connection failed: {e}")
        return None

def main():
    print("1. Fetching REAL Street Network Data from Zurich...")
    street_query = f"""
    [out:json][timeout:50];
    way["highway"]({BBOX});
    (._;>;);
    out body;
    """
    street_data = fetch_osm_data(street_query)
    
    if street_data and 'elements' in street_data:
        nodes = {}
        ways = []
        for element in street_data['elements']:
            if element['type'] == 'node':
                nodes[element['id']] = (element['lat'], element['lon'])
            elif element['type'] == 'way':
                if 'nodes' in element and len(element['nodes']) > 1:
                    ways.append({
                        'id': element['id'],
                        'name': element.get('tags', {}).get('name', 'Unknown'),
                        'type': element.get('tags', {}).get('highway', 'Unknown'),
                        'nodes': element['nodes']
                    })
        
        print(f"Processing {len(ways)} real streets into segments...")
        with open('/workspaces/GEO/data/zurich_streets.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['segment_id', 'street_name', 'start_lat', 'start_lon', 'end_lat', 'end_lon'])
            
            seg_count = 0
            for way in ways:
                for i in range(len(way['nodes']) - 1):
                    n1 = way['nodes'][i]
                    n2 = way['nodes'][i+1]
                    if n1 in nodes and n2 in nodes:
                        writer.writerow([
                            f"{way['id']}_{i}",
                            way['name'],
                            nodes[n1][0], nodes[n1][1],
                            nodes[n2][0], nodes[n2][1]
                        ])
                        seg_count += 1
        print(f"Saved {seg_count} authentic street segments to data/zurich_streets.csv")
    else:
        print("Failed to fetch street data.")

    print("\nWaiting 5 seconds to respect limits...")
    time.sleep(5)
    
    print("\n2. Fetching REAL POI Data (used as sound proxies) from Zurich...")
    # Fetching real POIs to use as proxies for our sound tags
    poi_query = f"""
    [out:json][timeout:50];
    (
      node["amenity"]({BBOX});
      node["leisure"]({BBOX});
      node["shop"]({BBOX});
      node["tourism"]({BBOX});
      node["public_transport"]({BBOX});
    );
    out body;
    """
    poi_data = fetch_osm_data(poi_query)
    
    if poi_data and 'elements' in poi_data:
        pois = []
        for element in poi_data['elements']:
            if element['type'] == 'node':
                tags = element.get('tags', {})
                # Just formatting real OSM tags as our proxy "sound descriptions"
                tag_text = " ".join([f"{k}={v}" for k, v in tags.items()]).lower()
                
                # Adding some textual hints based on actual POI types so our classifier works
                if 'public_transport' in tags or tags.get('amenity') in ['parking', 'bus_station']:
                    tag_text += " car train bus traffic vehicle"
                elif 'leisure' in tags or tags.get('tourism') in ['park', 'viewpoint']:
                    tag_text += " bird water wind leaves tree"
                elif 'amenity' in tags in ['cafe', 'restaurant', 'bar', 'pub', 'nightclub']:
                    tag_text += " talk laugh crowd music"
                elif 'shop' in tags:
                    tag_text += " indoor fan ac hum"
                    
                pois.append({
                    'id': element['id'],
                    'lat': element['lat'],
                    'lon': element['lon'],
                    'tags': tag_text
                })
        
        print(f"Processing {len(pois)} real POIs...")
        with open('/workspaces/GEO/data/zurich_sounds.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['id', 'lat', 'lon', 'tags'])
            writer.writeheader()
            writer.writerows(pois)
        print(f"Saved {len(pois)} real sound proxy data points to data/zurich_sounds.csv")
    else:
        print("Failed to fetch POI data.")

if __name__ == '__main__':
    main()
