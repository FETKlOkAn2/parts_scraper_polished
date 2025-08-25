from collections import defaultdict
import matplotlib.pyplot as plt
import os
import sys
import json
import pandas as pd
from skimage.io import imread
from skimage.transform import resize
from skimage.metrics import structural_similarity as ssim
from skimage import img_as_float
import numpy as np
import cv2
import pytesseract
from wm_remover import AdvancedWatermarkRemover
from datetime import datetime

pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"

class WatermarkEvaluator:
    def __init__(self, testing=False):
        self.testing = testing
        self.folder = "images"
        self.images = [f for f in os.listdir(self.folder) if os.path.isfile(os.path.join(self.folder, f))]
        self.grouped = defaultdict(list)
        
        # Detection statistics
        self.detection_stats = {
            'total_images': 0,
            'images_with_watermarks': 0,
            'detection_methods': {
                'tesseract': {'detected': 0, 'pixel_count': 0},
                'easyocr': {'detected': 0, 'pixel_count': 0},
                'pattern': {'detected': 0, 'pixel_count': 0},
                'corner': {'detected': 0, 'pixel_count': 0},
                'combined': {'detected': 0, 'pixel_count': 0}
            },
            'detailed_results': []
        }
        
        # Ground truth - you can manually set this for known watermarked images
        self.ground_truth = {}  # {'filename': True/False}
        
        # Thresholds for considering detection positive
        self.min_detection_pixels = 100  # Minimum pixels to consider a detection
        
        # Create output directories
        self.create_output_directories()
        self.group_images()

    def create_output_directories(self):
        """Create output directories if they don't exist"""
        directories = [
            os.path.join(self.folder, 'watermarks'),
            os.path.join(self.folder, 'cleaned'), 
            os.path.join(self.folder, 'mask'),
            os.path.join(self.folder, 'evaluation')
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"Created directory: {directory}")

    def group_images(self):
        for name in self.images:
            base_name = '_'.join(name.split('_')[:-1])  # strip the numeric suffix
            self.grouped[base_name].append(name)

    def set_ground_truth(self, ground_truth_dict):
        """Set ground truth for evaluation - dictionary of {filename: has_watermark}"""
        self.ground_truth = ground_truth_dict

    def load_ground_truth_from_file(self, filepath):
        """Load ground truth from JSON file"""
        try:
            with open(filepath, 'r') as f:
                self.ground_truth = json.load(f)
            print(f"Loaded ground truth for {len(self.ground_truth)} images")
        except FileNotFoundError:
            print(f"Ground truth file not found: {filepath}")

    def evaluate_single_image(self, filename, remover):
        """Evaluate watermark detection on a single image"""
        print(f"  Evaluating: {filename}")
        
        image_path = os.path.join(self.folder, filename)
        img = cv2.imread(image_path)
        if img is None:
            print(f"  ERROR: Could not load {image_path}")
            return None
        
        # Clear previous detections
        remover.watermark_images = []
        
        # Run all detection methods
        text_mask = remover.detect_text_regions_tesseract(img)
        easyocr_mask = remover.detect_text_regions_easyocr(img)
        pattern_mask = remover.detect_watermark_patterns(img)
        corner_mask = remover.detect_corner_watermarks(img)
        combined_mask = np.maximum.reduce([text_mask, easyocr_mask, pattern_mask, corner_mask])
        
        # Count pixels for each method
        pixel_counts = {
            'tesseract': np.sum(text_mask > 0),
            'easyocr': np.sum(easyocr_mask > 0),
            'pattern': np.sum(pattern_mask > 0),
            'corner': np.sum(corner_mask > 0),
            'combined': np.sum(combined_mask > 0)
        }
        
        # Determine if each method detected watermarks
        detections = {method: count > self.min_detection_pixels for method, count in pixel_counts.items()}
        
        # Overall detection (any method found something significant)
        overall_detection = detections['combined']
        
        # Save masks for review
        base_name = os.path.splitext(filename)[0]
        cv2.imwrite(f"{self.folder}/evaluation/{base_name}_combined_mask.png", combined_mask)
        
        # Create result object
        result = {
            'filename': filename,
            'pixel_counts': pixel_counts,
            'detections': detections,
            'overall_detection': overall_detection,
            'watermark_regions_found': len(remover.watermark_images),
            'image_size': img.shape[:2],
            'detection_percentage': {
                method: (count / (img.shape[0] * img.shape[1])) * 100 
                for method, count in pixel_counts.items()
            }
        }
        
        # Add ground truth comparison if available
        if filename in self.ground_truth:
            result['ground_truth'] = self.ground_truth[filename]
            result['correct_prediction'] = result['overall_detection'] == self.ground_truth[filename]
        
        return result

    def run_evaluation(self):
        """Run watermark detection evaluation on all images"""
        print("=== WATERMARK DETECTION EVALUATION ===\n")
        
        # Initialize remover with sensitive settings for evaluation
        remover = AdvancedWatermarkRemover(tesseract_cmd=r"C:/Program Files/Tesseract-OCR/tesseract.exe")
        
        # Configure for high sensitivity
        remover.tesseract_confidence = 25
        remover.easyocr_confidence = 0.3
        remover.text_padding = 3
        remover.pattern_threshold = 20
        remover.min_pattern_area = 50
        remover.corner_edge_threshold = 15
        
        self.detection_stats['total_images'] = len(self.images)
        
        for filename in self.images:
            result = self.evaluate_single_image(filename, remover)
            if result:
                self.detection_stats['detailed_results'].append(result)
                
                # Update overall stats
                if result['overall_detection']:
                    self.detection_stats['images_with_watermarks'] += 1
                
                # Update method-specific stats
                for method in self.detection_stats['detection_methods']:
                    if result['detections'][method]:
                        self.detection_stats['detection_methods'][method]['detected'] += 1
                    self.detection_stats['detection_methods'][method]['pixel_count'] += result['pixel_counts'][method]
        
        self.generate_report()

    def generate_report(self):
        """Generate comprehensive evaluation report"""
        stats = self.detection_stats
        total_images = stats['total_images']
        
        print("\n" + "="*60)
        print("WATERMARK DETECTION EVALUATION REPORT")
        print("="*60)
        
        # Overall statistics
        print(f"\nOVERALL STATISTICS:")
        print(f"  Total images processed: {total_images}")
        print(f"  Images with detected watermarks: {stats['images_with_watermarks']}")
        print(f"  Detection rate: {(stats['images_with_watermarks']/total_images)*100:.1f}%")
        
        # Method-specific statistics
        print(f"\nDETECTION METHOD PERFORMANCE:")
        for method, data in stats['detection_methods'].items():
            if method == 'combined':
                continue
            detection_rate = (data['detected'] / total_images) * 100
            avg_pixels = data['pixel_count'] / total_images if total_images > 0 else 0
            print(f"  {method.capitalize()}:")
            print(f"    - Images with detections: {data['detected']}/{total_images} ({detection_rate:.1f}%)")
            print(f"    - Average pixels detected: {avg_pixels:.0f}")
        
        # Ground truth evaluation (if available)
        if self.ground_truth:
            self.evaluate_accuracy()
        
        # Detailed per-image results
        print(f"\nDETAILED RESULTS:")
        print("-" * 80)
        print(f"{'Filename':<30} {'Detected':<10} {'Methods':<20} {'Pixels':<10} {'%':<6}")
        print("-" * 80)
        
        for result in stats['detailed_results']:
            detected_methods = [method for method, detected in result['detections'].items() 
                              if detected and method != 'combined']
            methods_str = '+'.join(detected_methods) if detected_methods else 'None'
            
            print(f"{result['filename']:<30} "
                  f"{'YES' if result['overall_detection'] else 'NO':<10} "
                  f"{methods_str:<20} "
                  f"{result['pixel_counts']['combined']:<10} "
                  f"{result['detection_percentage']['combined']:.2f}%")
        
        # Save detailed report to file
        self.save_report_to_file()
        
        # Generate visualizations
        self.create_visualizations()

    def evaluate_accuracy(self):
        """Evaluate accuracy against ground truth"""
        if not self.ground_truth:
            print("No ground truth available for accuracy evaluation")
            return
        
        true_positives = 0
        false_positives = 0
        true_negatives = 0
        false_negatives = 0
        
        print(f"\nACCURACY EVALUATION:")
        print("-" * 40)
        
        for result in self.detection_stats['detailed_results']:
            filename = result['filename']
            if filename not in self.ground_truth:
                continue
                
            predicted = result['overall_detection']
            actual = self.ground_truth[filename]
            
            if predicted and actual:
                true_positives += 1
            elif predicted and not actual:
                false_positives += 1
            elif not predicted and not actual:
                true_negatives += 1
            else:  # not predicted and actual
                false_negatives += 1
        
        total_evaluated = true_positives + false_positives + true_negatives + false_negatives
        
        if total_evaluated > 0:
            accuracy = (true_positives + true_negatives) / total_evaluated
            precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
            recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
            f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            print(f"  Accuracy: {accuracy:.3f} ({accuracy*100:.1f}%)")
            print(f"  Precision: {precision:.3f}")
            print(f"  Recall: {recall:.3f}")
            print(f"  F1-Score: {f1_score:.3f}")
            print(f"  True Positives: {true_positives}")
            print(f"  False Positives: {false_positives}")
            print(f"  True Negatives: {true_negatives}")
            print(f"  False Negatives: {false_negatives}")

    def save_report_to_file(self):
        """Save detailed report to JSON and CSV files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save as JSON
        json_path = f"{self.folder}/evaluation/evaluation_report_{timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(self.detection_stats, f, indent=2, default=str)
        
        # Save as CSV for easy analysis
        csv_data = []
        for result in self.detection_stats['detailed_results']:
            row = {
                'filename': result['filename'],
                'overall_detection': result['overall_detection'],
                'watermark_regions': result['watermark_regions_found'],
                'total_pixels': result['pixel_counts']['combined'],
                'detection_percentage': result['detection_percentage']['combined'],
                'tesseract_pixels': result['pixel_counts']['tesseract'],
                'easyocr_pixels': result['pixel_counts']['easyocr'],
                'pattern_pixels': result['pixel_counts']['pattern'],
                'corner_pixels': result['pixel_counts']['corner']
            }
            
            if 'ground_truth' in result:
                row['ground_truth'] = result['ground_truth']
                row['correct_prediction'] = result['correct_prediction']
            
            csv_data.append(row)
        
        df = pd.DataFrame(csv_data)
        csv_path = f"{self.folder}/evaluation/evaluation_results_{timestamp}.csv"
        df.to_csv(csv_path, index=False)
        
        print(f"\nReports saved:")
        print(f"  JSON: {json_path}")
        print(f"  CSV: {csv_path}")

    def create_visualizations(self):
        """Create visualization charts for the evaluation results"""
        # Detection method comparison
        methods = ['tesseract', 'easyocr', 'pattern', 'corner']
        detection_counts = [self.detection_stats['detection_methods'][method]['detected'] 
                          for method in methods]
        
        plt.figure(figsize=(12, 8))
        
        # Subplot 1: Detection method comparison
        plt.subplot(2, 2, 1)
        plt.bar(methods, detection_counts, color=['blue', 'green', 'red', 'orange'])
        plt.title('Watermark Detections by Method')
        plt.ylabel('Number of Images')
        plt.xticks(rotation=45)
        
        # Subplot 2: Detection percentage distribution
        plt.subplot(2, 2, 2)
        percentages = [result['detection_percentage']['combined'] 
                      for result in self.detection_stats['detailed_results']]
        plt.hist(percentages, bins=20, color='skyblue', alpha=0.7)
        plt.title('Distribution of Detection Percentages')
        plt.xlabel('Percentage of Image Detected as Watermark')
        plt.ylabel('Number of Images')
        
        # Subplot 3: Overall detection rate
        plt.subplot(2, 2, 3)
        labels = ['With Watermarks', 'Without Watermarks']
        sizes = [self.detection_stats['images_with_watermarks'], 
                self.detection_stats['total_images'] - self.detection_stats['images_with_watermarks']]
        colors = ['lightcoral', 'lightblue']
        plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%')
        plt.title('Overall Detection Results')
        
        # Subplot 4: Method overlap
        plt.subplot(2, 2, 4)
        method_combinations = defaultdict(int)
        for result in self.detection_stats['detailed_results']:
            detected_methods = [method for method, detected in result['detections'].items() 
                              if detected and method != 'combined']
            combination = '+'.join(sorted(detected_methods)) if detected_methods else 'None'
            method_combinations[combination] += 1
        
        combinations = list(method_combinations.keys())[:10]  # Top 10
        counts = [method_combinations[combo] for combo in combinations]
        
        plt.barh(combinations, counts, color='lightgreen')
        plt.title('Method Combination Frequency')
        plt.xlabel('Number of Images')
        
        plt.tight_layout()
        
        # Save the visualization
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plt_path = f"{self.folder}/evaluation/evaluation_charts_{timestamp}.png"
        plt.savefig(plt_path, dpi=300, bbox_inches='tight')
        plt.show()
        
        print(f"Visualization saved: {plt_path}")

    def create_ground_truth_template(self):
        """Create a template JSON file for manual ground truth annotation"""
        template = {}
        for image in self.images:
            template[image] = None  # User should fill in True/False
        
        template_path = f"{self.folder}/evaluation/ground_truth_template.json"
        with open(template_path, 'w') as f:
            json.dump(template, f, indent=2)
        
        print(f"Ground truth template created: {template_path}")
        print("Please edit this file and set True/False for each image, then load it with:")
        print(f"evaluator.load_ground_truth_from_file('{template_path}')")


if __name__ == "__main__":
    # Create evaluator
    evaluator = WatermarkEvaluator(testing=True)
    
    # Optional: Create ground truth template for manual annotation
    evaluator.create_ground_truth_template()
    
    # Optional: Load existing ground truth
    # evaluator.load_ground_truth_from_file("images/evaluation/ground_truth.json")
    
    # Run the evaluation
    evaluator.run_evaluation()