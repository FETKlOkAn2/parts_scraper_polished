import csv
from image_processing import Img_Proc


def process_shard(csv_path: str):

    try:
        with open(csv_path, newline="") as f:
            reader = csv.reader(f)
            for line in reader:
                
                img_proc = Img_Proc()


    except Exception as e:
        print(f"Error processing shard {csv_path}: {e}")
