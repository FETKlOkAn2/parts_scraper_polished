import requests
import time
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
from bs4 import BeautifulSoup
from database import Database
import subprocess
import os
import json
import random

CHECKPOINT_FILE = "data/scrape_checkpoint.json"

def save_checkpoint(start: int):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"last_start": int(start)}, f)

def load_checkpoint(default_start: int = 0) -> int:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            return int(json.load(open(CHECKPOINT_FILE)).get("last_start", default_start))
        except Exception:
            pass
    return default_start

class Soup:
    def __init__(self):
        self.db = Database()
        self.tor = None        
        self.exe_path = os.getenv("TOR_PATH")
        self.counter = 0
        self.scrape_all()

    def fetch_page(self, session, start=0, sz=12):
        url = "https://www.truckpartsdirect.com/on/demandware.store/Sites-TruckPartsDirect-Site/en_US/Search-UpdateGrid"
        params = {"cgid": "part-categories", "start": start, "sz": sz}
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        return soup.select(".tile-body.align-items-start")

    def parse_tile(self, tile):
        # You can adjust this if the site changes—this is your current logic.
        splits = tile.text.split()
        description = ' '.join(splits[:-2]).strip()
        number = splits[-2].strip()
        # Normalize number a little to reduce dup risk from whitespace/case
        number = number.upper()
        return {"number": number, "description": description}

    def insert_rows(self, df_new: pd.DataFrame):
        """
        Prefer a write that honors the UNIQUE constraint without throwing.
        If you're on SQLite, use INSERT OR IGNORE. If you’re on Postgres, use ON CONFLICT DO NOTHING.
        Fall back to to_sql if your Database wrapper doesn’t support raw executes.
        """
        # Try a raw executemany upsert for performance
        try:
            rows = list(df_new.itertuples(index=False, name=None))  # (number, description)
            # SQLite
            self.db.executemany(
                "INSERT OR IGNORE INTO parts (number, description) VALUES (?, ?)",
                rows
            )
        except Exception:
            # Fallback if your Database() wrapper only exposes to_sql
            # (DB unique constraint will still prevent duplicates, though it might raise)
            self.db.to_sql(df_new, "parts", if_exists="append", index=False)

    def scrape_all(self):
        session = requests.Session()
        batch_size = 12
        start = load_checkpoint(default_start=0)  # resume from last_start if present
        print(f"Resuming at start={start}")


        # 2) Load already-known numbers into a set for quick skip (optional speed-up)
        try:
            existing_df = self.db.read_sql("SELECT number FROM parts")
            known_numbers = set(existing_df["number"].astype(str).str.upper().tolist())
            print(f"Loaded {len(known_numbers)} existing part numbers")
        except Exception:
            known_numbers = set()
            print("No existing table rows—starting fresh")

        while True:
            try:
                if self.tor is None:
                    self.tor = subprocess.Popen(self.exe_path,stdout=subprocess.DEVNULL)
                    time.sleep(8)

                    session = requests.Session()
                    session.proxies = {
                        'http':  'socks5h://127.0.0.1:9050',
                        'https': 'socks5h://127.0.0.1:9050'
                    }
                    session.headers.update({
                        "User-Agent": (
                            "Mozilla/5.0 (Windows Nt 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/114.0.0.0 Safari/537.36"
                        )
                    })
                    self.print_exit_ip(session, label='fresh IP')

                tiles = self.fetch_page(session, start=start, sz=batch_size)
            except requests.HTTPError as e:
                # Transient errors happen; small backoff and try the same window again
                code = getattr(e.response, "status_code", None)
                wait = 2.0 if code in (502, 503, 504) else 1.0
                time.sleep(wait + random.uniform(0, 1.0))
                # You could add a retry counter; for now, just skip this window after one backoff:
                print(f"HTTP {code} at start={start}; skipping this window.")
                start += batch_size
                save_checkpoint(start)
                continue

            if not tiles:
                print("Reached the end (no tiles).")
                break

            # 3) Parse & dedupe by number (fast path)
            batch = [self.parse_tile(t) for t in tiles]
            batch = [r for r in batch if r["number"]]  # drop empties just in case

            new_rows = [r for r in batch if r["number"] not in known_numbers]

            if not new_rows:
                print(f"Batch at start={start}: 0 new rows, skipping DB write")
            else:
                df_new = pd.DataFrame(new_rows, columns=["number", "description"])
                self.insert_rows(df_new)
                print(f"Batch at start={start}: inserted {len(df_new)} new rows")
                # Update in-memory set so reruns in the same process don’t double-insert
                known_numbers.update(df_new["number"].tolist())

            # 4) Advance & checkpoint so you can resume later
            start += batch_size
            save_checkpoint(start)
            if self.counter >= 200:
                self.tor.terminate()
                self.tor = None
                self.counter = 0
            self.counter += 1

            # (Optional) rotate Tor/IP here if you want:
            time.sleep(.8)

        print("✅ scrape_all complete")

    def print_exit_ip(self, session, label=None):
        try:
            r = session.get("https://checkip.amazonaws.com", timeout=15)
            ip = r.text.strip()
            tag = f" [{label}]" if label else ""
            print(f"Tor exit IP{tag}: {ip}")
        except Exception as e:
            print(f"Tor exit IP check failed: {e}")

if __name__ == "__main__":
    Soup()
