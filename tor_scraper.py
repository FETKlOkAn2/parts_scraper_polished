
"""THIS IS A TESTING SCRIPT FOR TOR"""


import os
import re
import time
import socket
import tempfile
from pathlib import Path
import subprocess

import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    SessionNotCreatedException,
)

from stem import Signal
from stem.control import Controller
from stem.process import launch_tor_with_config
from dotenv import load_dotenv
load_dotenv()


def _find_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _port_open(host: str, port: int, timeout_s: float = 1.0) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout_s)
        return s.connect_ex((host, port)) == 0


class Parser:
    def __init__(self):
        # --- configurable bits ---
        self.image_path = "C:/Users/dazet/OneDrive/Projects/parts_scraper/images/images"
        self.duckduckgo_url = "https://duckduckgo.com/?q="
        self.duck_tag = "&t=h_&iar=images"
        # Use HTTP here (simpler over proxies)
        self.check_ip_url = "http://checkip.amazonaws.com"
        self.search_list = [
            "TORQUE ROD BUSHING ATRTS38000",
            "ROTELLA T5 10W30 CK4 550045130",
        ]

        # Chrome version from env (default to 139); keep as INT
        self.version = int(os.getenv("CHROME_VERSION", "139"))

        # --- start embedded Tor (no torrc needed) ---
        self.tor_cmd = os.getenv("TOR_PATH")  # e.g. r"C:\path\to\tor\tor.exe"
        if not self.tor_cmd or not Path(self.tor_cmd).exists():
            raise FileNotFoundError("TOR_PATH env var must point to tor.exe (Tor Expert Bundle).")

        self.socks_port, self.control_port, self.tor_proc = self._start_tor()

        self.driver = None
        self.links = []

        # Example run: check IP 10 times
        self.run_driver(function=self.check_ip, iterations=10)

        # Or: image search
        # self.run_driver(function=lambda: self.duck_image_search(self.search_list[0], 10), iterations=1)

    # ---------------------------
    # Tor lifecycle
    # ---------------------------
    def _start_tor(self):
        socks = _find_free_port()
        ctrl = _find_free_port()
        data_dir = Path(tempfile.mkdtemp(prefix="tor-data-"))

        print(f"Starting Tor: SOCKS {socks}, Control {ctrl}, Data {data_dir}")

        # Optional: point to geoip files if bundled next to tor.exe (silences warnings)
        tor_dir = Path(self.tor_cmd).parent
        geoip = tor_dir / "geoip"
        geoip6 = tor_dir / "geoip6"

        config = {
            "SOCKSPort": str(socks),
            "ControlPort": str(ctrl),
            "CookieAuthentication": "1",
            "DataDirectory": str(data_dir),  # critical to avoid collisions
        }
        if geoip.exists():
            config["GeoIPFile"] = str(geoip)
        if geoip6.exists():
            config["GeoIPv6File"] = str(geoip6)

        tor = launch_tor_with_config(
            tor_cmd=self.tor_cmd,
            config=config,
            take_ownership=True,
            init_msg_handler=print,  # show bootstrap logs
        )

        # Wait briefly to avoid racing control port
        for _ in range(20):
            if _port_open("127.0.0.1", ctrl):
                break
            time.sleep(0.1)

        return socks, ctrl, tor

    def renew_tor(self, min_wait=3):
        # 1) If Tor died, relaunch it
        if self.tor_proc and (self.tor_proc.poll() is not None):
            print("Tor process is not running. Relaunching...")
            self.socks_port, self.control_port, self.tor_proc = self._start_tor()

        # 2) Try control port, with one retry
        for attempt in range(2):
            try:
                with Controller.from_port(port=self.control_port) as c:
                    c.authenticate()  # CookieAuthentication 1
                    wait_needed = c.get_newnym_wait()
                    if wait_needed > 0:
                        time.sleep(wait_needed)
                    c.signal(Signal.NEWNYM)
                time.sleep(max(min_wait, 3))  # allow new circuits to build
                return
            except Exception as e:
                if attempt == 0:
                    print(f"renew_tor: control connection failed ({e}); retrying once...")
                    time.sleep(1)
                    continue
                raise

    # ---------------------------
    # Driver lifecycle
    # ---------------------------
    def initiate_driver(self):
        """
        Start undetected Chrome through Tor.
        - Clean SOCKS proxy arg (no auth in URL to avoid ERR_NO_SUPPORTED_PROXIES).
        - Auto-heals Chrome/driver version mismatches by parsing Selenium error.
        - Persists corrected version to CHROME_VERSION for future runs.
        """
        last_err = None
        for attempt in range(3):
            try:
                opts = uc.ChromeOptions()

                # Route via Tor SOCKS proxy (no username/creds)
                opts.add_argument(f"--proxy-server=socks5://127.0.0.1:{self.socks_port}")

                # Prevent DNS leaks
                opts.add_argument('--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1')
                opts.add_argument("--proxy-bypass-list=<-loopback>")
                opts.add_argument("--dns-prefetch-disable")

                # Start uc with version pin
                self.driver = uc.Chrome(options=opts, version_main=self.version)
                break

            except SessionNotCreatedException as e:
                last_err = e
                msg = str(e)
                print(f"Session not created with version_main={self.version}")

                # Extract current browser major version
                m = re.search(r"Current browser version is (\d+)", msg)
                if not m:
                    m = re.search(r"only supports Chrome version (\d+)", msg, re.IGNORECASE)
                if m:
                    new_version = int(m.group(1))
                    print(f"Updating version_main to {new_version} and retrying...")
                    self.version = new_version
                    try:
                        subprocess.run(["setx", "CHROME_VERSION", str(new_version)], shell=True)
                    except Exception as se:
                        print("Warning: failed to persist CHROME_VERSION via setx:", se)
                    time.sleep(0.5)
                    continue
                else:
                    # Can't parse → rethrow
                    raise

        if not self.driver:
            raise RuntimeError(f"Could not start ChromeDriver after retries. Last error: {last_err}")

        self.driver.set_page_load_timeout(60)
        self.driver.implicitly_wait(3)

    def run_driver(self, function, iterations: int = 0):
        for i in range(iterations):
            # 1) Rotate identity first (optional)
            self.renew_tor()

            # 2) Start driver (so it picks up fresh circuit)
            self.initiate_driver()

            try:
                function()
            finally:
                try:
                    self.driver.quit()
                except Exception:
                    pass

            self.links = []

    # ---------------------------
    # Tasks
    # ---------------------------
    def check_ip(self):
        """Check exit IP in the browser (goes through Tor)."""
        self.driver.get(self.check_ip_url)
        time.sleep(0.8)
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            print("Exit IP:", body.text.strip())
        except Exception as e:
            print("Exit IP: <unable to read>", e)

    def duck_image_search(self, search_string: str, total_images: int):
        """DuckDuckGo image search and collect image links."""
        self.driver.get(self.duckduckgo_url + search_string.replace(" ", "+") + self.duck_tag)
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "SZ76bwIlqO8BBoqOLqYV"))
        )

        for i in range(total_images):
            try:
                tiles = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, "SZ76bwIlqO8BBoqOLqYV"))
                )
                if i >= len(tiles):
                    break

                tile = tiles[i]
                self.driver.execute_script("arguments[0].scrollIntoView(true);", tile)
                WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CLASS_NAME, "SZ76bwIlqO8BBoqOLqYV"))
                )
                tile.click()
            except (StaleElementReferenceException, TimeoutException):
                print(f"⚠️ Tile #{i} failed — skipping.")
                continue

            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.ACez7bVvgYxZ9w0qR8ne"))
                )
                file = self.driver.find_element(By.CSS_SELECTOR, "a.ACez7bVvgYxZ9w0qR8ne")
                href = file.get_attribute("href")
                if href:
                    self.links.append(href)
            except Exception as e:
                print(f"Error on tile #{i} grabbing file: {e}")

    def download_images(self, iterator: int):
        """Download collected links via Tor (requests, in-memory)."""
        session = requests.Session()
        session.proxies = {
            "http": f"socks5h://127.0.0.1:{self.socks_port}",
            "https": f"socks5h://127.0.0.1:{self.socks_port}",
        }

        try:
            info = self.search_list[iterator]
            print("Downloading for:", info)
            j = 0
            while self.links:
                url = self.links.pop()
                file_name = info.replace(" ", "_") + f"_{j}.png"
                path = f"{self.image_path}/{file_name}"

                session.headers.update({
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/114.0.0.0 Safari/537.36"
                    ),
                    "Referer": f'https://www.google.com/search?tbm=isch&q={info.replace(" ","+")}',
                })

                try:
                    with session.get(url, stream=True, timeout=15) as resp:
                        if resp.status_code == 403:
                            j += 1
                            continue
                        resp.raise_for_status()
                        os.makedirs(self.image_path, exist_ok=True)
                        with open(path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                except Exception as e:
                    print("ERROR", e)

                j += 1

        except Exception as e:
            print("Request failed", e)


if __name__ == "__main__":
    scraper = Parser()
