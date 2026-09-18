import json
import base64

with open("RAWS/raw request.dump", "r", encoding="utf-8") as f:
    lines = f.readlines()

orari_base64 = lines[154].strip()
orari_json = base64.b64decode(orari_base64).decode('utf-8')
data = json.loads(orari_json)

found = False
for item in data:
    for pr in item.get("Pr", []):
        if pr.get("No") != "":
            print("Found reservation:", pr)
            found = True

if not found:
    print("No reservations found in OrariGet.")
