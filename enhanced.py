import cv2
import numpy as np
import pytesseract
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import json
from pathlib import Path

class IndustrialWatermarkRemover:
    def __init__(self, tesseract_cmd=None, max_workers=4):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        self.max_workers = max_workers
        self.processed_count = 0
        self.failed_images = []
        
    def detect_salient_regions(self, img):
        """Detect salient/prominent regions that could be logos or watermarks"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Method 1: Saliency detection using spectral residual
        saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
        success, saliency_map = saliency.computeSaliency(img)
        
        if success:
            saliency_map = (saliency_map * 255).astype(np.uint8)
            _, saliency_thresh = cv2.threshold(saliency_map, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        else:
            saliency_thresh = np.zeros_like(gray)
        
        return saliency_thresh
    
    def detect_color_clusters(self, img, n_clusters=8):
        """Detect uniform color regions that could be logos"""
        # Reshape image for clustering
        data = img.reshape((-1, 3))
        data = np.float32(data)
        
        # Apply KMeans clustering
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        _, labels, centers = cv2.kmeans(data, n_clusters, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        
        # Convert back to uint8 and reshape
        centers = np.uint8(centers)
        segmented_data = centers[labels.flatten()]
        segmented_img = segmented_data.reshape(img.shape)
        
        # Find regions with solid colors (potential logos)
        gray_seg = cv2.cvtColor(segmented_img, cv2.COLOR_BGR2GRAY)
        mask = np.zeros_like(gray_seg)
        
        # Create mask for each cluster
        for i in range(n_clusters):
            cluster_mask = (labels == i).reshape(img.shape[:2]).astype(np.uint8) * 255
            
            # Check if cluster forms compact regions
            contours, _ = cv2.findContours(cluster_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = cv2.contourArea(contour)
                # Filter by area and compactness
                if 300 < area < 50000:
                    perimeter = cv2.arcLength(contour, True)
                    if perimeter > 0:
                        circularity = 4 * np.pi * area / (perimeter * perimeter)
                        # Check if region is compact (could be a logo)
                        if circularity > 0.3:  # Adjust threshold as needed
                            cv2.fillPoly(mask, [contour], 255)
        
        return mask
    
    def detect_edge_density_regions(self, img):
        """Detect regions with high edge density (logos, text, watermarks)"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Multiple edge detection methods
        edges1 = cv2.Canny(gray, 50, 150)
        edges2 = cv2.Canny(gray, 30, 100)
        
        # Combine edges
        edges_combined = cv2.bitwise_or(edges1, edges2)
        
        # Calculate local edge density
        kernel_size = 31  # Adjust based on expected watermark size
        kernel = np.ones((kernel_size, kernel_size), np.float32) / (kernel_size * kernel_size)
        edge_density = cv2.filter2D(edges_combined.astype(np.float32), -1, kernel)
        
        # Threshold high density regions
        _, density_mask = cv2.threshold(edge_density, 0.15 * 255, 255, cv2.THRESH_BINARY)
        density_mask = density_mask.astype(np.uint8)
        
        # Clean up mask
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        density_mask = cv2.morphologyEx(density_mask, cv2.MORPH_CLOSE, kernel)
        
        return density_mask
    
    def detect_corner_and_edge_watermarks(self, img):
        """Detect watermarks in typical locations (corners, edges)"""
        h, w = img.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        
        # Define regions to check (corners and edges)
        corner_size = min(h, w) // 4
        edge_width = min(h, w) // 8
        
        regions = [
            # Corners
            (0, 0, corner_size, corner_size),  # top-left
            (w - corner_size, 0, w, corner_size),  # top-right  
            (0, h - corner_size, corner_size, h),  # bottom-left
            (w - corner_size, h - corner_size, w, h),  # bottom-right
            # Edges
            (0, 0, w, edge_width),  # top edge
            (0, h - edge_width, w, h),  # bottom edge
            (0, 0, edge_width, h),  # left edge
            (w - edge_width, 0, w, h),  # right edge
            # Center region
            (w//3, h//3, 2*w//3, 2*h//3),  # center
        ]
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        for (x1, y1, x2, y2) in regions:
            region = img[y1:y2, x1:x2]
            region_gray = gray[y1:y2, x1:x2]
            
            if region.size == 0:
                continue
                
            # Check for text using OCR
            try:
                text = pytesseract.image_to_string(region_gray, config='--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789')
                if len(text.strip()) > 2:  # Found significant text
                    cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
                    continue
            except:
                pass
            
            # Check for logo-like regions using color variance
            if region.shape[0] > 10 and region.shape[1] > 10:
                # Calculate color statistics
                mean_color = np.mean(region.reshape(-1, 3), axis=0)
                color_std = np.std(region.reshape(-1, 3), axis=0)
                
                # Check if region has distinctive colors (potential logo)
                if np.any(color_std > 40) and np.any(mean_color > 50):
                    # Additional check: edge density in region
                    edges = cv2.Canny(region_gray, 50, 150)
                    edge_ratio = np.sum(edges > 0) / edges.size
                    
                    if edge_ratio > 0.05:  # Has sufficient edge content
                        cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
        
        return mask
    
    def detect_repeating_patterns(self, img):
        """Detect repeating watermark patterns"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Use template matching with small regions to find repeating elements
        h, w = gray.shape
        mask = np.zeros_like(gray)
        
        # Extract potential templates from corners and center
        template_regions = [
            gray[10:60, 10:60],  # top-left corner
            gray[h-60:h-10, w-60:w-10],  # bottom-right corner
            gray[h//2-25:h//2+25, w//2-25:w//2+25],  # center
        ]
        
        for template in template_regions:
            if template.shape[0] > 20 and template.shape[1] > 20:
                # Check if template has enough variation
                if np.std(template) > 20:
                    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                    locations = np.where(result >= 0.8)  # High threshold for exact matches
                    
                    th, tw = template.shape
                    for pt in zip(*locations[::-1]):
                        cv2.rectangle(mask, pt, (pt[0] + tw, pt[1] + th), 255, -1)
        
        return mask
    
    def remove_watermark_single(self, image_path, output_path, save_mask=False):
        """Remove watermarks from a single image"""
        try:
            img = cv2.imread(image_path)
            if img is None:
                return False, f"Could not load image: {image_path}"
            
            # Apply all detection methods
            mask1 = self.detect_salient_regions(img)
            mask2 = self.detect_color_clusters(img)
            mask3 = self.detect_edge_density_regions(img)
            mask4 = self.detect_corner_and_edge_watermarks(img)
            mask5 = self.detect_repeating_patterns(img)
            
            # Combine all masks
            combined_mask = mask1.copy()
            for mask in [mask2, mask3, mask4, mask5]:
                combined_mask = cv2.bitwise_or(combined_mask, mask)
            
            # Clean up the mask
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel)
            combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)
            
            # Remove small noise
            contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                if cv2.contourArea(contour) < 200:  # Remove small artifacts
                    cv2.fillPoly(combined_mask, [contour], 0)
            
            # Inpaint to remove watermarks
            if np.any(combined_mask > 0):
                cleaned = cv2.inpaint(img, combined_mask, 7, cv2.INPAINT_TELEA)
            else:
                cleaned = img.copy()
            
            # Save results
            cv2.imwrite(output_path, cleaned)
            
            if save_mask:
                mask_path = output_path.replace('.', '_mask.')
                cv2.imwrite(mask_path, combined_mask)
            
            return True, "Success"
            
        except Exception as e:
            return False, str(e)
    
    def process_batch(self, input_folder, output_folder, file_extensions=('.jpg', '.jpeg', '.png', '.bmp'), 
                     save_masks=False, progress_callback=None):
        """Process all images in a folder"""
        
        # Create output directory
        Path(output_folder).mkdir(parents=True, exist_ok=True)
        
        # Get list of image files
        image_files = []
        for ext in file_extensions:
            image_files.extend(Path(input_folder).glob(f'*{ext}'))
            image_files.extend(Path(input_folder).glob(f'*{ext.upper()}'))
        
        total_files = len(image_files)
        print(f"Found {total_files} images to process")
        
        if total_files == 0:
            print("No images found!")
            return
        
        # Process images in parallel
        self.processed_count = 0
        self.failed_images = []
        start_time = time.time()
        
        def process_single_image(img_path):
            try:
                output_path = Path(output_folder) / f"cleaned_{img_path.name}"
                success, message = self.remove_watermark_single(str(img_path), str(output_path), save_masks)
                
                self.processed_count += 1
                
                if progress_callback:
                    progress_callback(self.processed_count, total_files)
                
                if not success:
                    self.failed_images.append((str(img_path), message))
                
                # Print progress every 100 images
                if self.processed_count % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = self.processed_count / elapsed
                    remaining = (total_files - self.processed_count) / rate
                    print(f"Processed {self.processed_count}/{total_files} "
                          f"({rate:.1f} img/sec, ~{remaining/60:.1f} min remaining)")
                
                return success, str(img_path), message
                
            except Exception as e:
                self.failed_images.append((str(img_path), str(e)))
                return False, str(img_path), str(e)
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(process_single_image, img_path) for img_path in image_files]
            
            # Wait for all tasks to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error in thread: {e}")
        
        # Print final statistics
        elapsed_time = time.time() - start_time
        success_count = total_files - len(self.failed_images)
        
        print(f"\n=== BATCH PROCESSING COMPLETE ===")
        print(f"Total images: {total_files}")
        print(f"Successfully processed: {success_count}")
        print(f"Failed: {len(self.failed_images)}")
        print(f"Total time: {elapsed_time/60:.1f} minutes")
        print(f"Average rate: {total_files/elapsed_time:.1f} images/second")
        
        # Save failed images list
        if self.failed_images:
            failed_log = Path(output_folder) / "failed_images.json"
            with open(failed_log, 'w') as f:
                json.dump(self.failed_images, f, indent=2)
            print(f"Failed images list saved to: {failed_log}")
    
    def preview_detection(self, image_path, save_preview=True):
        """Preview watermark detection on a single image"""
        img = cv2.imread(image_path)
        if img is None:
            print(f"Could not load image: {image_path}")
            return
        
        # Get all detection masks
        mask1 = self.detect_salient_regions(img)
        mask2 = self.detect_color_clusters(img)
        mask3 = self.detect_edge_density_regions(img)
        mask4 = self.detect_corner_and_edge_watermarks(img)
        mask5 = self.detect_repeating_patterns(img)
        
        combined_mask = mask1.copy()
        for mask in [mask2, mask3, mask4, mask5]:
            combined_mask = cv2.bitwise_or(combined_mask, mask)
        
        # Create preview
        fig, axes = plt.subplots(2, 4, figsize=(16, 8))
        axes = axes.flatten()
        
        axes[0].imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        axes[0].set_title('Original Image')
        axes[0].axis('off')
        
        axes[1].imshow(mask1, cmap='gray')
        axes[1].set_title('Saliency Detection')
        axes[1].axis('off')
        
        axes[2].imshow(mask2, cmap='gray')
        axes[2].set_title('Color Clustering')
        axes[2].axis('off')
        
        axes[3].imshow(mask3, cmap='gray')
        axes[3].set_title('Edge Density')
        axes[3].axis('off')
        
        axes[4].imshow(mask4, cmap='gray')
        axes[4].set_title('Location-Based')
        axes[4].axis('off')
        
        axes[5].imshow(mask5, cmap='gray')
        axes[5].set_title('Pattern Matching')
        axes[5].axis('off')
        
        axes[6].imshow(combined_mask, cmap='gray')
        axes[6].set_title('Combined Mask')
        axes[6].axis('off')
        
        # Show result
        if np.any(combined_mask > 0):
            result = cv2.inpaint(img, combined_mask, 7, cv2.INPAINT_TELEA)
            axes[7].imshow(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))
            axes[7].set_title('Final Result')
        else:
            axes[7].imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            axes[7].set_title('No Watermark Detected')
        axes[7].axis('off')
        
        plt.tight_layout()
        
        if save_preview:
            preview_path = f"preview_{Path(image_path).stem}.png"
            plt.savefig(preview_path, dpi=150, bbox_inches='tight')
            print(f"Preview saved to: {preview_path}")
        
        plt.show()

# Usage functions
def progress_callback(current, total):
    """Simple progress callback"""
    percentage = (current / total) * 100
    print(f"Progress: {current}/{total} ({percentage:.1f}%)")

# Example usage for large dataset processing
if __name__ == "__main__":
    # Initialize the remover
    # For Windows with Tesseract installed:
    remover = IndustrialWatermarkRemover(
        tesseract_cmd=r'C:/Program Files/Tesseract-OCR/tesseract.exe',
        max_workers=8  # Adjust based on your CPU cores
    )
    
    # For Linux/Mac:
    # remover = IndustrialWatermarkRemover(max_workers=8)
    
    # Preview detection on a single image first
    print("Previewing detection on a sample image...")
    # remover.preview_detection("sample_image.jpg")
    
  
    input_folder = "images" 
    output_folder = "cleaned_images"  # Output folder
    
    print(f"Starting batch processing of {input_folder}")
    print("This will process all images in parallel...")
    
    # Start batch processing
    remover.process_batch(
        input_folder=input_folder,
        output_folder=output_folder,
        file_extensions=('.jpg', '.jpeg', '.png', '.bmp', '.tiff'),
        save_masks=False,  # Set to True if you want to save detection masks
        progress_callback=progress_callback
    )
    
    print("Batch processing completed!")