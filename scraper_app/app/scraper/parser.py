from PIL import Image
import boto3
import io, json, os, requests, subprocess, time, sys
from dotenv import load_dotenv
import pandas as pd
from bs4 import BeautifulSoup

pd.set_option("display.max_colwidth", None)
load_dotenv()

class Parser:
    def __init__(self, db, text):
        username = os.getenv("DECODO_USERNAME")
        password = os.getenv("DECODO_PASSWORD")

        self.query = text
        self.url = f"https://www.bing.com/images/search?q={self.query}&form=HDRSC2"
        self.proxy = f"http://{username}:{password}@gate.decodo.com:7000"
        self.headers = {"User-Agent": "Mozilla/5.0"}
        
        self.db = db
        self.s3 = boto3.client("s3")

        self.links = []
        self.tor = None
        self.max_images = 10
        self.images_downloaded = 0

    def tor_start(self):
        exe_path = os.getenv("TOR_PATH")
        self.tor = subprocess.Popen(exe_path,stdout=subprocess.DEVNULL)
        time.sleep(8)
    
    def terminate_tor(self):
        self.tor.terminate()
        time.sleep(2)

    def get_links(self):
        response = requests.get(self.url, headers=self.headers, proxies={
            'http':self.proxy,
            'https':self.proxy
        })

        soup = BeautifulSoup(response.text, "html.parser")
        all_links = []
        for a in soup.select("a.iusc"):
            m = a.get("m")
            if m:
                data = json.loads(m)
                all_links.append(data.get("murl"))
        self.links = all_links[:30]


    def download_images(self, keep_bytes=True):
        """ Downloads from requests resizes to 600x600 and saves them to s3 buckets"""

        self.tor_start()

        session = requests.Session()
        session.proxies = {
            'http':  'socks5h://127.0.0.1:9050',
            'https': 'socks5h://127.0.0.1:9050'
        }

        tag_values = []
        part_id = None

        try:
            info = self.query
            print(info)
            part_number = info.split(" ")[0]
            part_id = self.db.read_sql_query(f"SELECT part_id FROM parts WHERE number = '{part_number}'")
            part_id = int(part_id["part_id"].iat[0])

            while self.images_downloaded < self.max_images:
                url = self.links.pop()
                #tag = url.split('.')[-1]
                file_name = info.replace(" ", "_") + "_" + str(self.images_downloaded) + ".png"
                file_name = file_name.replace('/',"_")
                file_name = file_name.replace(',','')
                s3_key = f"images/{file_name}"

                session.headers.update({
                    "User-Agent": (
                        "Mozilla/5.0 (Windows Nt 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/114.0.0.0 Safari/537.36"
                    ),
                    "Referer": f'https://www.google.com/search?tbm=isch&q={info.replace(" ","+")}'
                })
                try:
                    with session.get(url, stream=True, timeout=10) as resp:
                        if resp.status_code == 403:
                            continue
                        resp.raise_for_status()

                        img = Image.open(io.BytesIO(resp.content))
                        img = img.convert("RGBA") if img.mode in ("P", "LA") else img.convert("RGB")
                        img = img.resize((600, 600), Image.LANCZOS)

                        buf = io.BytesIO()
                        img.save(buf, format='PNG')
                        buf.seek(0)

                        self.s3.put_object(
                            Bucket='partsbucket0000',
                            Key=s3_key,
                            Body=buf.getvalue(),
                            ContentType='image/png'
                        )
                        print(f'uploaded to s3://partsbucket0000/{s3_key}')
                        self.images_downloaded += 1
   
    
                except Exception as e:
                    print('ERROR', e)

                else:
                    url_value = f"https://partsbucket0000.s3.us-east-1.amazonaws.com/{s3_key}"
                    tag_values.append(url_value)

        except Exception as e:
            print("Request failed", e)
        
        self.terminate_tor()

        return part_id, tag_values

if __name__ == "__main__":
    scraper = Parser()
    scraper.run_driver(
        function=scraper.duck_image_search,
        iterations=4)# can do len(self.df)
