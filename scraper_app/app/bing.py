import requests, re, json
from bs4 import BeautifulSoup

q = "ATRMA37000 LOAD PAD (UPPER)"
url = f"https://www.bing.com/images/search?q={q}&form=HDRSC2"
headers = {"User-Agent": "Mozilla/5.0"}
r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.text, "html.parser")

links = []
for a in soup.select("a.iusc"):
    m = a.get("m")
    if m:
        data = json.loads(m)
        links.append(data.get("murl"))
print(links[:20])
