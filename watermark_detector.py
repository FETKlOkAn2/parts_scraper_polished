from collections import defaultdict
import matplotlib.pyplot as plt
import os
import sys
from skimage.io import imread
from skimage.transform import resize
from skimage.metrics import structural_similarity as ssim
from skimage import img_as_float
import numpy as np


class WaterMark:
    def __init__(self, testing=False):
        self.testing = testing
        self.folder = "images"
        self.images = [f for f in os.listdir(self.folder) if os.path.isfile(os.path.join(self.folder, f))]
        self.grouped = defaultdict(list)

        self.group_images()

    def load_and_resize(self, path, where="(unknown)", size=(600, 600)):
        """Load image from path and resize to target size (default 600x600)."""
        path = f"images/{path}"
        img = imread(path)
        img = img_as_float(img)  # scale to [0,1]
        img = np.squeeze(img)

        if img.ndim != 2 and img.ndim != 3:
            raise ValueError(f"{where}: expected 2-D or 3-D, got {img.shape}")

        # resize to fixed dimensions
        img = resize(img, size, anti_aliasing=True)

        return img
    
    def group_images(self):
        for name in self.images:
            base_name = '_'.join(name.split('_')[:-1])  # strip the numeric suffix
            self.grouped[base_name].append(name)


    def run_watermark(self):
        """
        Iterate your grouped files, hash within each group, and print similar pairs.
        """
        for group_name, files in self.grouped.items():
            if len(files) < 2:
                continue
            print(f"\n=== group: {group_name} ===")
            self.water_mark_detector(files)

    def water_mark_detector(self, files):
        """where the programming actually goes"""
        for fn in files:
            img = self.load_and_resize(fn)
            self.show_image(img)
            
    def show_image(self, img, title="Image", cmap=None):
        plt.figure()
        plt.imshow(img, cmap=cmap)
        plt.title(title)
        plt.axis('off')
        plt.tight_layout()
        plt.show()



if __name__ == "__main__":
    water_mark = WaterMark(testing = True)
    water_mark.run_watermark()