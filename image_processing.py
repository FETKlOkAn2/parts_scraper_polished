from collections import defaultdict
import numpy as np
from skimage.io import imread
from skimage.transform import resize
from skimage.metrics import structural_similarity as ssim
from skimage import img_as_float
from skimage.color import rgb2gray
import os

class Img_Proc:
    def __init__(self):
        self.folder = "images"
        self.images = os.listdir(self.folder)
        self.grouped = defaultdict(list)

        self.group_images()
        self.perform_ssim()

    def group_images(self):
        for name in self.images:
            base_name = '_'.join(name.split('_')[:-1])  # strip the numeric suffix
            self.grouped[base_name].append(name)



    def load_and_grayscale(self, path):
        # 1) Load and convert to float
        img = img_as_float(imread(path))

        # 2) Squeeze *all* singleton dimensions:
        #    e.g. (1, H, W, 3) → (H, W, 3); (H, W, 1) → (H, W)
        img = np.squeeze(img)

        # 3) If still 3D, it's color (shape HxWx3)
        if img.ndim == 3:
            # If last dim >1, treat as RGB/RGBA
            if img.shape[2] > 1:
                img = rgb2gray(img)
            else:
                # Rare: (H, W, 1) would already be squeezed, but just in case:
                img = img[:, :, 0]

        # 4) Final check: must be 2D now
        if img.ndim != 2:
            raise ValueError(f"Unexpected image shape after squeeze/convert: {img.shape}")

        return img



    def resize_image(self, img, shape=(100, 100)):
        # at this point img.ndim == 2 guaranteed
        return resize(img, shape, anti_aliasing=True)

    def perform_ssim(self):
        for group_name, files in self.grouped.items():
            print(f"\n=== Comparing group: {group_name} ===")
            imgs = []
            for fn in files:
                path = os.path.join(self.folder, fn)
                gray = self.load_and_grayscale(path)
                imgs.append((fn, gray))

            for i in range(len(imgs)):
                for j in range(i + 1, len(imgs)):
                    name1, im1 = imgs[i]
                    name2, im2 = imgs[j]

                    r1 = self.resize_image(im1)
                    r2 = self.resize_image(im2)

                    score = ssim(r1, r2, data_range=1.0)
                    print(f"{name1} vs {name2} → SSIM: {score:.4f}")
if __name__ == "__main__":
    img_proc = Img_Proc()