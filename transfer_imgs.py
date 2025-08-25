import os
import cv2
import numpy as np
from collections import defaultdict

class ImageTransfer:
    def __init__(self, source_folder="source_images", target_folder="images"):
        self.source_folder = source_folder
        self.target_folder = target_folder
        self.images = [f for f in os.listdir(self.source_folder) if os.path.isfile(os.path.join(self.source_folder, f))]
        self.grouped = defaultdict(list)
        self.group_images()

    def group_images(self):
        for name in self.images:
            base_name = '_'.join(name.split('_')[:-1])  # strip the numeric suffix
            self.grouped[base_name].append(name)

    def transfer_images(self):
        for group_name, files in self.grouped.items():
            if len(files) < 2:
                continue
            print(f"\n=== Transferring group: {group_name} ===")
            for fn in files:
                src_path = os.path.join(self.source_folder, fn)
                dst_path = os.path.join(self.target_folder, fn)
                if not os.path.exists(dst_path):
                    img = cv2.imread(src_path)
                    if img is None:
                        print(f"Could not load image from {src_path}")
                        continue
                    cv2.imwrite(dst_path, img)
                    print(f"Transferred: {dst_path}")
                else:
                    print(f"File already exists, skipping: {dst_path}")

                delete_path = os.path.join(self.source_folder, fn)
                if os.path.exists(delete_path):
                    os.remove(delete_path)
                    print(f"Deleted original: {delete_path}")
                else:
                    print(f"Original file not found for deletion: {delete_path}")

if __name__ == "__main__":
    transfer = ImageTransfer("images", "images/images")
    transfer.transfer_images()