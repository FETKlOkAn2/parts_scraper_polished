import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, SessionNotCreatedException
from PIL import Image
from database import Database
import stem.process, stem.control
import time
import boto3
import io
import os
import re
import sys
import requests
import subprocess
from dotenv import load_dotenv
from contextlib import suppress
load_dotenv()

class Parser:
    def __init__(self):
        
        self.db = Database()
        self.s3 = boto3.client("s3")
        self.image_path = "C:/Users/dazet/OneDrive/Projects/parts_scraper/images"
        self.duckduckgo_url = 'https://duckduckgo.com/?q='
        self.duck_tag = '&t=h_&iar=images'

        self.check_ip_url = 'https://checkip.amazonaws.com'

        #self.search_list = ['TORQUE ROD BUSHING ATRTS38000','ROTELLA T5 10W30 CK4 550045130'] # must have + for spaces
        self.df = self.db.read_sql_query("SELECT number, description FROM parts")
        self.driver = None

        self.links = []
        self.tor = None


        #self.run_driver(function=self.check_ip, iterations= 10)

        # self.run_driver(
        #     function=self.duck_image_search,
        #     iterations=4)# can do len(self.df)

    def run_driver(self, function, iterations:int=0):
        for i in range(iterations):
            self.initiate_driver()
            
            function(' '.join(list(self.df.iloc[i])), 10)
            #function()
            self.download_images(iterator = i)

            self.links = []
            self.tor.terminate()


    def initiate_driver(self):

        exe_path = os.getenv("TOR_PATH")
        self.tor = subprocess.Popen(exe_path,stdout=subprocess.DEVNULL)

        time.sleep(1)
        """initiates the Undetected Chrome Browser"""

        opts = uc.ChromeOptions()
        opts.add_argument("--proxy-server=socks5://127.0.0.1:9050")
        opts.add_argument('--host-resolver-rules="MAP * `NOTFOUND, EXCLUDE 127.0.0.1"')
        opts.add_argument("--dns-prefetch-disable")
        
        self.driver = uc.Chrome(options=opts, headless=False)
        self.driver.set_page_load_timeout(60)
        self.driver.implicitly_wait(3)


    def check_ip(self):
        """process for checking ip address switching"""
        self.driver.get(self.check_ip_url)
        time.sleep(1)
        body = self.driver.find_element(By.TAG_NAME, "body")
        print(body.text)

    def duck_image_search(self, search_string:str, total_images):
        ''' Process for searching duckduckgo images'''
        # tile_class = "SZ76bwIlqO8BBoqOLqYV"
        # image_after_click = "Gr22SUHQb8xKdEwTxIxe ffON2NH02oMAcqyoh2UU vcOFkrrvuSYp7xsAur2Y q7VhSk71XgyB1xYfeChb ACez7bVvgYxZ9w0qR8ne"
        try:
            self.driver.get(self.duckduckgo_url + search_string.replace(' ', '+') + self.duck_tag)
            self.driver.execute_script("window.scrollTo(0,400)") # headless

            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "SZ76bwIlqO8BBoqOLqYV"))
            )

            # tiles = self.driver.find_elements(By.CLASS_NAME, 'SZ76bwIlqO8BBoqOLqYV')
            for i in range(0,total_images):
                single_html_list = []
                try:
                    # re-find the tile each iteration to avoid stale-element errors
                    tile = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_all_elements_located((By.CLASS_NAME, 'SZ76bwIlqO8BBoqOLqYV'))
                    )[i]

                    # scroll it into view (helps if it’s off-screen)
                    #self.driver.execute_script("arguments[0].scrollIntoView(true);", tile)
                    self.driver.execute_script("window.scrollTo(0,400)") # headless

                    # wait until it’s actually clickable, then click
                    WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CLASS_NAME, 'SZ76bwIlqO8BBoqOLqYV'))
                    )
                    tile.click()

                except (StaleElementReferenceException, TimeoutException):
                    print(f"⚠️  Tile #{i} failed to click or load — skipping.")
                    continue
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'a.ACez7bVvgYxZ9w0qR8ne'))
                    )
                    file = self.driver.find_element(By.CSS_SELECTOR, 'a.ACez7bVvgYxZ9w0qR8ne')

                    self.links.append(file.get_attribute("href"))

                except Exception as e:
                    print(f'Error on tile #{i} grabbing the file: {e}')

                #self.links.append(single_html_list)
        finally:
            with suppress(Exception):
                self.driver.quit()  # ensures UC doesn't try during teardown

    def download_images(self, iterator, keep_bytes=True):
        """ Downloads from requests resizes to 600x600 and saves them to s3 buckets"""
        session = requests.Session()
        session.proxies = {
            'http':  'socks5h://127.0.0.1:9050',
            'https': 'socks5h://127.0.0.1:9050'
        }
        idx = 0
        try:
            info = ' '.join(list(self.df.iloc[iterator]))
            print(info)

            while self.links:
                url = self.links.pop()
                #tag = url.split('.')[-1]
                file_name = info.replace(" ", "_") + "_" + str(idx) + ".png"
                file_name = file_name.replace('/',"_")
                file_name = file_name.replace(',','')
                s3_key = f"images/{file_name}"
                idx+=1

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
                        print(f'uploaded to s3://partsbucket000/{s3_key}')

                        # with open(path, 'wb') as f:
                        #     for chunk in resp.iter_content(chunk_size=8192):
                        #         if chunk:
                        #             f.write(chunk) 
                        
                except Exception as e:
                    print('ERROR', e)

        except Exception as e:
            print("Request failed", e)


if __name__ == "__main__":
    scraper = Parser()