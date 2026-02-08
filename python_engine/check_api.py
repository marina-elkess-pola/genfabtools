"""Check API response for stall geometry."""
import requests

resp = requests.post('http://localhost:8001/parking/evaluate', json={
    'siteBoundary': {'points': [{'x': 0, 'y': 0}, {'x': 200, 'y': 0}, {'x': 200, 'y': 100}, {'x': 0, 'y': 100}]},
    'parkingConfig': {'parkingType': 'surface', 'aisleDirection': 'TWO_WAY', 'setback': 5}
})
data = resp.json()
bays = data['result']['parkingResult']['bays']

print(f'Total bays: {len(bays)}')
for i, bay in enumerate(bays):
    stalls = bay['stalls']
    ada = [s for s in stalls if 'ada' in s['stallType'].lower()]
    print(f'Bay {i}: {len(stalls)} stalls, {len(ada)} ADA')

# Show first bay stalls
print()
print('Bay 0 stalls:')
for s in bays[0]['stalls']:
    geom = s['geometry']['points']
    ys = [p['y'] for p in geom]
    width = max(ys) - min(ys)
    print(
        f"  {s['id']}: {s['stallType']:10} y={min(ys):.1f}-{max(ys):.1f} width={width:.1f}ft")
    if s.get('accessAisle'):
        ap = s['accessAisle']['points']
        ays = [p['y'] for p in ap]
        print(f"    accessAisle: y={min(ays):.1f}-{max(ays):.1f}")
