import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time

class Parser:
    def __init__(self, url):
        self.url = url
        self.pages = 0


        self.run_driver()
        for i in range(5):
            self.extract_part_info()
            self.paginate()
                
        self.driver.quit()

    def run_driver(self):
        opts = Options()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        self.driver = uc.Chrome(options=opts)
        self.driver.set_page_load_timeout(60)
        self.driver.implicitly_wait(2)

        self.driver.get(self.url)
        time.sleep(1)
        try:
            no_thanks_btn = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button.needsclick")))
            
                # scroll it into view (in case it's off-screen or covered)
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", no_thanks_btn)

            # pause briefly so any CSS transition can finish
            time.sleep(0.5)

            # click via JS (bypasses “not clickable at point” errors)
            self.driver.execute_script("arguments[0].click();", no_thanks_btn)
        
            no_thanks_btn.click()
            print("-----dismissed pop up ------")
        except Exception:
            print('----pop did not appear-------')



    def extract_part_info(self):
        time.sleep(1)
        self.pages += 1
        print(f"----------------------  PAGE: {self.pages}  ----------------------")

        items = self.driver.find_elements(By.CSS_SELECTOR, '.tile-body.align-items-start')
        print(len(items))
        # for i, item in enumerate(items):
        #     splits = item.text.split()
        #     print(f"name: {' '.join(splits[:-2])}")
        #     print(f"part number: {splits[-2]}")
        #     print(f"price: {splits[-1]}\n")



    def paginate(self):
        time.sleep(2)
        next_page = self.driver.find_element(By.CSS_SELECTOR, "button.more")
        next_page.click()
        time.sleep(10)
        pass

if __name__ == "__main__":
    scraper = Parser("https://www.truckpartsdirect.com/allproducts.html")