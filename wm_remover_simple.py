
import cv2
import pytesseract
import numpy as np
from scipy import ndimage
from skimage import morphology, measure

class SimpleWatermarkRemover:
    def __init__(self, tesseract_cmd=None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
        # TUNABLE PARAMETERS - Adjust these for different sensitivity levels
        self.tesseract_confidence = 45      # Text confidence threshold (0-100)
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
        
        return np.maximum.reduce(masks)
    
    def detect_text_regions_easyocr(self, image):
        """Dummy EasyOCR function - returns empty mask"""
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
        print(f"Processing image: {image_path}")
        
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not load image from {image_path}")
        
        # Create combined mask from all detection methods
        print("Detecting text with Tesseract...")
        text_mask_tesseract = self.detect_text_regions_tesseract(img)
        
        print("Detecting watermark patterns...")
        pattern_mask = self.detect_watermark_patterns(img)
        
        print("Detecting corner watermarks...")
        corner_mask = self.detect_corner_watermarks(img)
        
        # Combine all masks
        combined_mask = np.maximum.reduce([text_mask_tesseract, pattern_mask, corner_mask])
        
        # Morphological operations based on parameters
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, 
                                         (self.morph_kernel_size, self.morph_kernel_size))
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)
        
        if self.enable_dilation:
            combined_mask = cv2.dilate(combined_mask, kernel, iterations=self.dilation_iterations)
        
        if debug:
            cv2.imwrite(image_path.replace('.', '_debug_mask.'), combined_mask)
            print(f"Debug mask saved")
        
        # Inpainting
        print("Performing inpainting...")
        cleaned = cv2.inpaint(img, combined_mask, 7, cv2.INPAINT_TELEA)
        
        # Save results
        cv2.imwrite(output_path, cleaned)
        if mask_path:
            cv2.imwrite(mask_path, combined_mask)
        
        print(f"Watermark removal completed. Saved to {output_path}")
        return cleaned
