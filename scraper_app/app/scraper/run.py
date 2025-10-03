import csv
from parser import Parser


def process_shard(csv_path: str):

    try:
        with open(csv_path, newline="") as f:
            reader = csv.reader(f)
            for list_line in reader:
                line = list_line[0]
                parser = Parser(line)

                parser.get_links()
                parser.download_images()

    except Exception as e:
        print(f"Error processing shard {csv_path}: {e}")
