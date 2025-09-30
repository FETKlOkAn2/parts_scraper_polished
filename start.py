"""Once everything step of the program is working this will be where
we call all the functions"""
from scraper_app.app.selen import Parser
from image_proc_app.app.image_processing import Img_Proc

class Start:
    def __init__(self):
        self.parse = Parser()
        self.db = self.parse.db

    def start_program(self):
        
        # function gets images and saves them to s3 buckets
        # self.parse.run_driver(
        #     function=self.parse.duck_image_search,
        #     iterations=5)# can do len(self.df) for the entire database
        
        #downloads from s3, processes images, saves to final s3 bucket
        self.db.retrieve_from_s3("partsbucket0000","images", run_img_proc=True, run_water_remove=False)

        # deletes all the unused images
        #self.db.send_delete_request()
        

if __name__ == "__main__":
    start = Start()
    start.start_program()