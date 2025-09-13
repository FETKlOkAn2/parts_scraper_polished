import cv2
import pytesseract
import numpy as np
from scipy import ndimage
from skimage import morphology, measure
import easyocr

class AdvancedWatermarkRemover:
    def __init__(self, tesseract_cmd=None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
        # Initialize EasyOCR reader for better text detection
        self.reader = easyocr.Reader(['en'])
        
        # TUNABLE PARAMETERS - Adjust these for different sensitivity levels
        self.tesseract_confidence = 45      # Text confidence threshold (0-100)
        self.easyocr_confidence = 0.4       # EasyOCR confidence (0.0-1.0)
        self.min_text_length = 3            # Minimum text length to consider
        self.text_padding = 2               # Pixels to pad around detected text
        
        # Pattern detection parameters
        self.enable_pattern_detection = True    # Enable/disable pattern detection
        self.pattern_threshold = 25             # Threshold for pattern detection
        self.min_pattern_area = 300             # Minimum area for patterns
        self.max_pattern_area = 15000           # Maximum area for patterns
        self.text_aspect_ratio_min = 1.2       # Min width/height ratio for text
        self.text_aspect_ratio_max = 10.0      # Max width/height ratio for text
        
        # Corner detection parameters
        self.corner_size_ratio = 0.20           # Corner size as % of image
        self.corner_edge_threshold = 20         # Edge density threshold for corners
        
        # Morphological operations
        self.morph_kernel_size = 3              # Kernel size for cleanup
        self.enable_dilation = True             # Enable mask dilation
        self.dilation_iterations = 1            # Number of dilation iterations
    
        self.watermark_images = []  # List to store detected watermark images

    def has_meaningful_watermark(self, mask, min_pixels=100, min_percentage=0.01):
        """
        Check if a mask contains enough content to be considered a meaningful watermark.
        
        Args:
            mask: Binary mask (numpy array)
            min_pixels: Minimum number of white pixels
            min_percentage: Minimum percentage of image that should be masked
        
        Returns:
            bool: True if mask contains meaningful watermark content
        """
        if mask is None:
            return False
        
        # Count white pixels (watermark regions)
        white_pixels = np.sum(mask > 0)
        total_pixels = mask.shape[0] * mask.shape[1]
        percentage = white_pixels / total_pixels
        
        # Check both absolute and relative thresholds
        has_enough_pixels = white_pixels >= min_pixels
        has_enough_percentage = percentage >= min_percentage
        
        return has_enough_pixels and has_enough_percentage

    def save_watermark_images(self, output_folder):
        """Save detected watermark images to the specified folder."""
        for i, img in enumerate(self.watermark_images):
            cv2.imwrite(f"{output_folder}/watermark_{i}.png", img)
        print(f"Saved {len(self.watermark_images)} watermark images to {output_folder}")

    def detect_text_regions_tesseract(self, image):
        """Detect text regions using Tesseract OCR"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Multiple preprocessing approaches for better text detection
        masks = []
        
        # Approach 1: Standard thresholding
        _, thresh1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        data1 = pytesseract.image_to_data(thresh1, output_type=pytesseract.Output.DICT, config='--psm 6')
        masks.append(self._create_text_mask(data1, gray.shape))
        
        # Approach 2: Adaptive thresholding
        thresh2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        data2 = pytesseract.image_to_data(thresh2, output_type=pytesseract.Output.DICT, config='--psm 6')
        masks.append(self._create_text_mask(data2, gray.shape))
        
        # Approach 3: Morphological operations for text enhancement
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        morph = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        _, thresh3 = cv2.threshold(morph, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        data3 = pytesseract.image_to_data(thresh3, output_type=pytesseract.Output.DICT, config='--psm 6')
        masks.append(self._create_text_mask(data3, gray.shape))
        
        return np.maximum.reduce(masks)
    
    def detect_text_regions_easyocr(self, image):
        """Detect text regions using EasyOCR"""
        try:
            results = self.reader.readtext(image)
            mask = np.zeros(image.shape[:2], dtype=np.uint8)
            
            for (bbox, text, confidence) in results:
                if confidence > self.easyocr_confidence and len(text.strip()) >= self.min_text_length:
                    # Convert bbox to rectangle coordinates
                    points = np.array(bbox, dtype=np.int32)
                    
                    # Create tight bounding box
                    x_min, y_min = points.min(axis=0)
                    x_max, y_max = points.max(axis=0)
                    
                    # Apply padding
                    cv2.rectangle(mask, 
                                (max(0, x_min-self.text_padding), max(0, y_min-self.text_padding)),
                                (min(image.shape[1], x_max+self.text_padding), min(image.shape[0], y_max+self.text_padding)),
                                255, -1)
            
            return mask
        except Exception as e:
            print(f"EasyOCR detection failed: {e}")
            return np.zeros(image.shape[:2], dtype=np.uint8)
    
    def _create_text_mask(self, data, shape):
        """Create mask from OCR data"""
        mask = np.zeros(shape, dtype=np.uint8)
        
        for i, text in enumerate(data["text"]):
            if text.strip() != "" and len(text.strip()) >= self.min_text_length:
                confidence = int(data["conf"][i]) if data["conf"][i] != '-1' else 0
                if confidence > self.tesseract_confidence:
                    x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    # Apply padding
                    x1 = max(0, x - self.text_padding)
                    y1 = max(0, y - self.text_padding)
                    x2 = min(shape[1], x + w + self.text_padding)
                    y2 = min(shape[0], y + h + self.text_padding)
                    cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
        
        return mask
    
    def detect_watermark_patterns(self, image):
        """Detect potential watermark patterns using image processing"""
        if not self.enable_pattern_detection:
            return np.zeros(image.shape[:2], dtype=np.uint8)
            
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        mask = np.zeros(gray.shape, dtype=np.uint8)
        
        # Look for semi-transparent overlays with text-like characteristics
        blur = cv2.GaussianBlur(gray, (9, 9), 0)
        diff = cv2.absdiff(gray, blur)
        _, watermark_thresh = cv2.threshold(diff, self.pattern_threshold, 255, cv2.THRESH_BINARY)
        
        # Find contours and be selective
        contours, _ = cv2.findContours(watermark_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            # Filter by area range
            if self.min_pattern_area < area < self.max_pattern_area:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h
                
                # Check if it looks like text
                if (self.text_aspect_ratio_min < aspect_ratio < self.text_aspect_ratio_max 
                    and h > 8):  # Minimum height for text
                    self.watermark_images.append(image[y:y+h, x:x+w])
                    cv2.rectangle(mask, (x-2, y-2), (x+w+2, y+h+2), 255, -1)
        
        return mask
    
    def _detect_repetitive_patterns(self, gray):
        """Detect repetitive patterns that might be watermarks"""
        mask = np.zeros(gray.shape, dtype=np.uint8)
        
        # Use template matching to find repetitive elements
        h, w = gray.shape
        
        # Sample small regions and look for matches
        sample_size = 50
        step = 25
        
        for y in range(0, h - sample_size, step):
            for x in range(0, w - sample_size, step):
                template = gray[y:y+sample_size, x:x+sample_size]
                
                # Skip if template is too uniform
                if np.std(template) < 10:
                    continue
                
                # Find matches
                result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                locations = np.where(result >= 0.8)
                
                # If we find multiple matches, it might be a repeated watermark
                if len(locations[0]) > 2:
                    self.watermark_images.append(template)
                    for pt_y, pt_x in zip(locations[0], locations[1]):
                        cv2.rectangle(mask, (pt_x, pt_y), (pt_x + sample_size, pt_y + sample_size), 255, -1)
        
        return mask
    
    def detect_corner_watermarks(self, image):
        """Corner watermark detection"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        h, w = gray.shape
        mask = np.zeros(gray.shape, dtype=np.uint8)
        
        # Corner size based on parameter
        corner_size = int(min(h, w) * self.corner_size_ratio)
        
        corners = [
            (0, 0, corner_size, corner_size),  # Top-left
            (w - corner_size, 0, w, corner_size),  # Top-right
            (0, h - corner_size, corner_size, h),  # Bottom-left
            (w - corner_size, h - corner_size, w, h),  # Bottom-right
        ]
        
        for (x1, y1, x2, y2) in corners:
            region = gray[y1:y2, x1:x2]
            
            # Check for obvious text/logo content
            edges = cv2.Canny(region, 100, 200)
            edge_density = edges.mean()
            
            # Use threshold parameter
            if edge_density > self.corner_edge_threshold:
                # Verify it's text-like by checking for horizontal patterns
                horizontal_projection = np.sum(edges, axis=1)
                if np.max(horizontal_projection) > corner_size * 0.2:  # Text-like patterns
                    cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
        
        return mask
    
    def remove_watermark(self, image_path, output_path, mask_path=None, debug=False):
        """Main function to remove watermarks and text"""
        if isinstance(image_path, str):
            print(f"Processing image: {image_path}")
            
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Could not load image from {image_path}")
        else:
            img = image_path
        
        # Create combined mask from all detection methods
        print("Detecting text with Tesseract...")
        text_mask_tesseract = self.detect_text_regions_tesseract(img)
        
        print("Detecting text with EasyOCR...")
        text_mask_easyocr = self.detect_text_regions_easyocr(img)
        
        print("Detecting watermark patterns...")
        pattern_mask = self.detect_watermark_patterns(img)
        
        print("Detecting corner watermarks...")
        corner_mask = self.detect_corner_watermarks(img)
        
        # Combine all masks based on parameters
        masks_to_combine = [text_mask_tesseract, text_mask_easyocr]
        
        if self.enable_pattern_detection:
            masks_to_combine.append(pattern_mask)
            
        masks_to_combine.append(corner_mask)
        
        combined_mask = np.maximum.reduce(masks_to_combine)
        
        # Morphological operations based on parameters
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, 
                                         (self.morph_kernel_size, self.morph_kernel_size))
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)
        
        if self.enable_dilation:
            combined_mask = cv2.dilate(combined_mask, kernel, iterations=self.dilation_iterations)
        
        if debug:
            cv2.imwrite(image_path.replace('.', '_debug_mask.'), combined_mask)
            print(f"Debug mask saved")
        
        # Inpainting with multiple methods for better results
        print("Performing inpainting...")
        
        # Method 1: TELEA
        cleaned_telea = cv2.inpaint(img, combined_mask, 7, cv2.INPAINT_TELEA)
        
        # Method 2: NS (Navier-Stokes)
        cleaned_ns = cv2.inpaint(img, combined_mask, 7, cv2.INPAINT_NS)
        
        # Combine results - use the one with better local features
        cleaned = self._combine_inpaint_results(cleaned_telea, cleaned_ns, combined_mask)
        
        # Post-processing to improve results
        cleaned = self._post_process(cleaned, combined_mask)
        
        # Save results
        cv2.imwrite(output_path, cleaned)
        if mask_path:
            cv2.imwrite(mask_path, combined_mask)
        
        print(f"Watermark removal completed. Saved to {output_path}")
        return cleaned
    
    def _combine_inpaint_results(self, result1, result2, mask):
        """Combine two inpainting results for better quality"""
        # Simple combination - can be enhanced with more sophisticated methods
        combined = np.where(mask[..., np.newaxis] > 0, 
                          (result1.astype(np.float32) + result2.astype(np.float32)) / 2,
                          result1)
        return combined.astype(np.uint8)
    
    def _post_process(self, image, mask):
        """Post-process the inpainted image"""
        # Apply slight blur to inpainted regions to blend better
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dilated_mask = cv2.dilate(mask, kernel, iterations=1)
        
        # Apply bilateral filter only to inpainted regions
        filtered = cv2.bilateralFilter(image, 9, 75, 75)
        
        result = np.where(dilated_mask[..., np.newaxis] > 0, filtered, image)
        
        return result

# Usage example with parameter tuning
def main():
    # Initialize remover
    remover = AdvancedWatermarkRemover()
    #pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"
    pytesseract.pytesseract.tesseract_cmd = "Tesseract-OCR/tesseract.exe"
    # EASY TUNING - Adjust these based on your needs:
    
    # For STRONGER detection (catches more watermarks but might be aggressive):
    # remover.tesseract_confidence = 35      # Lower = more text detected
    # remover.easyocr_confidence = 0.3       # Lower = more text detected  
    # remover.text_padding = 4               # Higher = bigger masks around text
    # remover.enable_pattern_detection = True
    # remover.corner_edge_threshold = 15     # Lower = detects more corners
    # remover.dilation_iterations = 2        # Higher = bigger final masks
    
    # For WEAKER detection (more conservative, less false positives):
    # remover.tesseract_confidence = 60      # Higher = only confident text
    # remover.easyocr_confidence = 0.6       # Higher = only confident text
    # remover.text_padding = 1               # Lower = tighter masks
    # remover.enable_pattern_detection = False
    # remover.corner_edge_threshold = 30     # Higher = only obvious corners
    # remover.dilation_iterations = 0        # No mask expansion
    
    # BALANCED settings (current defaults):
    remover.tesseract_confidence = 60
    remover.easyocr_confidence = 0.7
    remover.text_padding = 1
    remover.enable_pattern_detection = False
    remover.corner_edge_threshold = 30
    remover.dilation_iterations = 0
    
    # Process image
    try:
        result = remover.remove_watermark(
            image_path='images\images\TORQUE_ROD_BUSHING_ATRTS38000_8.png',
            output_path='output_cleaned.jpg',
            mask_path='detection_mask.jpg',
            debug=True
        )

        print("Processing completed successfully!")
        print(f"Settings used:")
        print(f"  - Tesseract confidence: {remover.tesseract_confidence}")
        print(f"  - EasyOCR confidence: {remover.easyocr_confidence}")
        print(f"  - Text padding: {remover.text_padding}")
        print(f"  - Pattern detection: {remover.enable_pattern_detection}")
        print(f"  - Corner threshold: {remover.corner_edge_threshold}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()