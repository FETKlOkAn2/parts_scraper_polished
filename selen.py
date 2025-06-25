import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import stem.process, stem.control
import time
import os
import requests
from dotenv import load_dotenv
load_dotenv()

"""
ROTELLA T5 10W30 CK4 550045130
AIR BRAKE TUBING, NYLON, BD10863FT 
TORQUE ROD BUSHING ATRTS38000 
TERM- BOWMA SEAL 3/8 STUD BD238232 
"""

class Parser:
    def __init__(self):
        self.duckduckgo_url = 'https://duckduckgo.com/?q='
        self.duck_tag = '&t=h_&iar=images'

        self.check_ip_url = 'https://checkip.amazonaws.com'

        self.search_list = ['TORQUE ROD BUSHING ATRTS38000','ROTELLA T5 10W30 CK4 550045130'] # must have + for spaces
        self.driver = None
        self.tor_proc = self.launch_tor_with_retries()
        self.links = []



        self.run_driver(function=self.check_ip, iterations= 10)
        # self.run_driver(
        #     function=self.duck_image_search,
        #     iterations=len(self.search_list))


    def run_driver(self, function, iterations:int=0):
        for i in range(iterations):
            self.initiate_driver()

            #function(self.search_list[i-1], 10)
            function()
            self.download_images()

            self.driver.quit()
            #self.tor_proc.kill()

    def launch_tor_with_retries(self,max_backoff=60):
        tor_cmd = os.getenv("TOR_PATH")
        """Keep trying to launch Tor until success, with exponential back-off."""
        attempt = 0
        while True:
            try:
                self.tor_proc = stem.process.launch_tor_with_config(
                    tor_cmd=tor_cmd,
                    config={
                        'SocksPort': '9050',
                        'ControlPort': '9051',
                        'CookieAuthentication': '1',
                        'MaxCircuitDirtiness': '1'
                    },
                    take_ownership=True
                )

                time.sleep(1)
                return

            except OSError as e:
                attempt += 1
                backoff = min(max_backoff, 2 ** attempt)
                print(f"⚠️  Launch attempt #{attempt} failed: {e!r}. retrying in {backoff}s…")
                time.sleep(backoff)

    def initiate_driver(self):
        """initiates the Undetected Chrome Browser"""
        opts = uc.ChromeOptions()
        opts.add_argument("--proxy-server=socks5://127.0.0.1:9050")
        opts.add_argument('--host-resolver-rules="MAP * `NOTFOUND, EXCLUDE 127.0.0.1"')
        opts.add_argument("--dns-prefetch-disable")
        self.driver = uc.Chrome(options=opts, version_main=137)
        self.driver.set_page_load_timeout(60)
        self.driver.implicitly_wait(3)

    def renew_tor(self):
        with stem.control.Controller.from_port(port=9051) as controller:
            controller.authenticate()
            controller.signal(stem.Signal.NEWNYM)
        time.sleep(1)

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

        self.driver.get(self.duckduckgo_url + search_string.replace(' ', '+') + self.duck_tag)
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "SZ76bwIlqO8BBoqOLqYV"))
        )

        # tiles = self.driver.find_elements(By.CLASS_NAME, 'SZ76bwIlqO8BBoqOLqYV')
        for i in range(0,total_images):
            try:
                # re-find the tile each iteration to avoid stale-element errors
                tile = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, 'SZ76bwIlqO8BBoqOLqYV'))
                )[i]

                # scroll it into view (helps if it’s off-screen)
                self.driver.execute_script("arguments[0].scrollIntoView(true);", tile)

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
        self.download_images()

    def download_images(self):
        # self.launch_tor_with_retries()
        session = requests.Session()
        session.proxies = {
            'http':  'socks5h://127.0.0.1:9050',
            'https': 'socks5h://127.0.0.1:9050'
        }
        try:
            resp = session.get('https://httpbin.org/ip', timeout=10)
            resp.raise_for_status()
            print("Your IP via Tor is:", resp.json()['origin'])
        except Exception as e:
            print("Request failed:", e)



if __name__ == "__main__":
    scraper = Parser()