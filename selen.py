import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import stem.process, stem.control
import pandas as pd
import time

"""
ROTELLA T5 10W30 CK4 550045130
AIR BRAKE TUBING, NYLON, BD10863FT 
TORQUE ROD BUSHING ATRTS38000 
TERM- BOWMA SEAL 3/8 STUD BD238232 
"""

class Parser:
    def __init__(self):
        self.base_url = 'https://duckduckgo.com/'
        self.search = 'hello+world' # must have + for spaces
        self.tag = f"?q={self.search}&iar=images"
        self.test_url = 'https://check.torproject.org'
        self.check_ip_url = 'https://checkip.amazonaws.com'
        self.driver = None
        self.tor_proc = None

        for i in range(5):
            self.initiate_driver()
            self.run_driver()
            self.renew_tor()
            self.driver.quit()
            self.tor_proc.kill()


    def initiate_driver(self):
        self.tor_proc = stem.process.launch_tor_with_config(
            tor_cmd = r"C:\Users\dazet\OneDrive\Desktop\Tor Browser\Tor Expert\tor\tor.exe",
            config = {
                'SocksPort': '9050',
                'ControlPort': '9051',
                'CookieAuthentication': '1',
                'MaxCircuitDirtiness': '0'
            },
            take_ownership=True
        )
        time.sleep(1)

        # opts = Options()
        # opts.add_argument("--no-sandbox")
        # opts.add_argument("--disable-dev-shm-usage")
        opts = uc.ChromeOptions()
        opts.add_argument("--proxy-server=socks5://127.0.0.1:9050")
        opts.add_argument('--host-resolver-rules="MAP * `NOTFOUND, EXCLUDE 127.0.0.1"')
        opts.add_argument("--dns-prefetch-disable")
        self.driver = uc.Chrome(options=opts)
        self.driver.set_page_load_timeout(60)
        self.driver.implicitly_wait(3)
    
    def run_driver(self):

        self.driver.get(self.check_ip_url)
        time.sleep(3)
        body = self.driver.find_element(By.TAG_NAME, "body")
        print(body.text)


    def renew_tor(self):
        with stem.control.Controller.from_port(port=9051) as controller:
            controller.authenticate()
            controller.signal(stem.Signal.NEWNYM)
        time.sleep(10)
        # self.driver.execute_cdp_cmd("Network.enable", {})
        # self.driver.execute_cdp_cmd("Network.clearBrowserCache", {})
        # self.driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
        # self.driver.execute_cdp_cmd("Network.clearNetworkQueues", {})  # Chrome 90+


if __name__ == "__main__":
    scraper = Parser()