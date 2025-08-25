from collections import defaultdict
import matplotlib.pyplot as plt
import os
import sys
from skimage.io import imread
from skimage.transform import resize
from skimage.metrics import structural_similarity as ssim
from skimage import img_as_float
import numpy as np
import cv2
import pytesseract
from wm_remover import AdvancedWatermarkRemover

pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"

class WaterMark:
    def __init__(self, testing=False):
        self.testing = testing
        self.folder = "images"
        self.images = [f for f in os.listdir(self.folder) if os.path.isfile(os.path.join(self.folder, f))]
        self.grouped = defaultdict(list)

        self.remove_watermark = False  # Set to True to enable watermark removal
        
        # Create necessary directories
        self.create_output_directories()
        
        self.group_images()

    def create_output_directories(self):
        """Create output directories if they don't exist"""
        directories = [
            os.path.join(self.folder, 'watermarks'),
            os.path.join(self.folder, 'cleaned'), 
            os.path.join(self.folder, 'mask')
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"Created directory: {directory}")

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
            print(f"Processing file: {fn}")
            
            # Check if file exists
            image_path = os.path.join(self.folder, fn)
            if not os.path.exists(image_path):
                print(f"  ERROR: File not found: {image_path}")
                continue
            
            # Initialize remover with correct tesseract path
            remover = AdvancedWatermarkRemover(tesseract_cmd=r"C:/Program Files/Tesseract-OCR/tesseract.exe")
            
            # Make remover more sensitive to detect watermarks
            remover.tesseract_confidence = 30  # Lower threshold
            remover.easyocr_confidence = 0.2   # Lower threshold
            remover.text_padding = 5           # More padding
            remover.pattern_threshold = 15     # Lower threshold for patterns
            remover.min_pattern_area = 100     # Smaller minimum area
            remover.corner_edge_threshold = 10 # Lower threshold for corners
            
            image_path = os.path.join(self.folder, fn)
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Could not load image from {image_path}")
            
            # Clear previous watermark images
            remover.watermark_images = []
            
            print("  - Detecting text with Tesseract...")
            text_mask = remover.detect_text_regions_tesseract(img)
            
            print("  - Detecting text with EasyOCR...")
            easyocr_mask = remover.detect_text_regions_easyocr(img)
            
            print("  - Detecting watermark patterns...")
            pattern_mask = remover.detect_watermark_patterns(img)
            
            print("  - Detecting corner watermarks...")
            corner_mask = remover.detect_corner_watermarks(img)
            
            # Save individual masks for debugging
            base_name = os.path.splitext(fn)[0]
            cv2.imwrite(f"{self.folder}/watermarks/tesseract/{base_name}_tesseract_mask.png", text_mask)
            cv2.imwrite(f"{self.folder}/watermarks/easyocr/{base_name}_easyocr_mask.png", easyocr_mask)
            cv2.imwrite(f"{self.folder}/watermarks/pattern/{base_name}_pattern_mask.png", pattern_mask)
            cv2.imwrite(f"{self.folder}/watermarks/corner/{base_name}_corner_mask.png", corner_mask)
            
            # Combine all masks
            combined_mask = np.maximum.reduce([text_mask, easyocr_mask, pattern_mask, corner_mask])
            cv2.imwrite(f"{self.folder}/watermarks/combined/{base_name}_combined_mask.png", combined_mask)
            
            # Save detected watermark regions as separate images
            if len(remover.watermark_images) > 0:
                print(f"  - Found {len(remover.watermark_images)} watermark regions")
                for i, watermark_img in enumerate(remover.watermark_images):
                    watermark_path = f"{self.folder}/watermarks/separate-watermark/{base_name}_watermark_{i}.png"
                    cv2.imwrite(watermark_path, watermark_img)
                    print(f"    Saved: {watermark_path}")
            else:
                print("  - No watermark regions detected")
            
            # Check if any masks have content
            mask_stats = {
                'tesseract': np.sum(text_mask > 0),
                'easyocr': np.sum(easyocr_mask > 0),
                'pattern': np.sum(pattern_mask > 0),
                'corner': np.sum(corner_mask > 0),
                'combined': np.sum(combined_mask > 0)
            }
            
            print(f"  - Mask statistics: {mask_stats}")
            
            if self.remove_watermark and np.sum(combined_mask) > 0:
                output_path = f"{self.folder}/cleaned/{fn}"
                mask_path = f"{self.folder}/mask/{base_name}_mask.png"
                
                print(f"  - Removing watermarks...")
                remover.remove_watermark(image_path, output_path, mask_path)
                print(f"  - Cleaned image saved to: {output_path}")
            
            print(f"  - Finished processing {fn}\n")

    def show_image(self, img, title="Image", cmap=None):
        plt.figure()
        plt.imshow(img, cmap=cmap)
        plt.title(title)
        plt.axis('off')
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    water_mark = WaterMark(testing=True)
    water_mark.run_watermark()