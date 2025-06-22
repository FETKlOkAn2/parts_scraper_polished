import requests
import time
import pandas as pd
import stem.process, stem.control
from dotenv import load_dotenv
load_dotenv()
from bs4 import BeautifulSoup
from database import Database


class Soup:
    def __init__(self):
        self.db = Database()
        self.scrape_all()


    def fetch_page(self,session, start=0, sz=12):
        """
        Fetch the HTML snippet of product tiles from the AJAX endpoint.
        Returns a list of BeautifulSoup Tag objects (each one tile).
        """
        url = "https://www.truckpartsdirect.com/on/demandware.store/Sites-TruckPartsDirect-Site/en_US/Search-UpdateGrid"
        params = {
            "cgid": "part-categories",
            "start": start,
            "sz": sz
        }
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # each tile has classes "tile-body align-items-start"
        return soup.select(".tile-body.align-items-start")

    def parse_tile(self, tile):
        """
        Extract whatever you need from a single <div class="tile-body …">.
        Here’s an example that grabs the product name and link:
        """
        splits = tile.text.split()

        name = ' '.join(splits[:-2])
        part =  splits[-2]
        price = splits[-1]

        return {"name": name, "part": part, "price": price}


    def scrape_all(self):
        session = requests.Session()
        session.proxies.update({
            "http":  "socks5h://127.0.0.1:9050",
            "https": "socks5h://127.0.0.1:9050",
        })
        start = 0
        batch_size = 12

        # 1) Load everything that’s already in parts_list
        try:
            existing_df = self.db.read_sql("SELECT name, part, price FROM parts_list")
            existing = set(map(tuple, existing_df.values))
            first_write = False
            print(f"Loaded {len(existing)} existing rows")
        except Exception:
            # table doesn’t exist yet
            existing = set()
            first_write = True
            print("No existing table—will create on first batch")

        while True:
            tiles = self.fetch_page(session, start=start, sz=batch_size)
            if not tiles:
                break

            # 2) Parse this batch
            batch = [self.parse_tile(t) for t in tiles]

            # 3) Filter out rows we’ve already saved
            new_rows = [r for r in batch
                        if (r["name"], r["part"], r["price"]) not in existing]
            if not new_rows:
                print(f"Batch at start={start}: 0 new rows, skipping DB write")
            else:
                df_new = pd.DataFrame(new_rows, columns=["name","part","price"])

                # 4) On the very first write, create the table if needed
                if first_write:
                    self.db.create_table_if_not_exists("parts_list", df_new)
                    first_write = False

                # 5) Append only the new rows
                self.db.to_sql(df_new, "parts_list", if_exists="append")
                print(f"Batch at start={start}: inserted {len(df_new)} new rows")

                # 6) Remember them so we don’t re-insert if we rerun
                existing.update(map(tuple, df_new.values))

            start += batch_size
            self.renew_tor()       # request a new circuit/IP
            # r = session.get("https://checkip.amazonaws.com")
            # print(r.text)    # should be different
            time.sleep(1)

        print("✅ scrape_all complete")
    
    def renew_tor(self):
        with stem.control.Controller.from_port(port=9051) as controller:
            controller.authenticate(password="your_tor_control_password")
            controller.signal(stem.Signal.NEWNYM)

if __name__ == "__main__":
    soup = Soup()

