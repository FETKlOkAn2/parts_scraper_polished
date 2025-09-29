"""Enhanced main program with AI watermark detection integration"""
from selen import Parser
from image_processing import Img_Proc
from batch_watermark_detector import BatchWatermarkDetector, EnhancedDatabase
import os
from typing import Dict, List

class EnhancedStart:
    def __init__(self, openai_api_key=None):
        self.parse = Parser()
        self.db = self.parse.db  # Your existing Database instance
        self.watermark_detector = BatchWatermarkDetector(openai_api_key)
        self.img_proc = Img_Proc()
        
        # Processing modes
        self.use_ai_watermark_detection = True
        self.use_traditional_watermark_removal = False
        self.use_image_deduplication = True
        
    def start_program(self, mode="full"):
        """
        Enhanced start program with multiple processing modes:
        - 'collect': Only collect images
        - 'ai_detect': Only run AI watermark detection
        - 'process': Only process images (deduplicate, traditional watermark removal)
        - 'full': Complete pipeline
        """
        
        if mode in ["collect", "full"]:
            self.collect_images()
        
        if mode in ["ai_detect", "full"]:
            self.ai_watermark_detection()
        
        if mode in ["process", "full"]:
            self.process_images()
        
        if mode in ["full"]:
            self.cleanup()
    
    def collect_images(self):
        """Collect images and save to S3"""
        print("=== Phase 1: Image Collection ===")
        self.parse.run_driver(
            function=self.parse.duck_image_search,
            iterations=5  # Adjust as needed
        )
    
    def ai_watermark_detection(self):
        """Run AI-powered watermark detection"""
        print("=== Phase 2: AI Watermark Detection ===")
        
        # Run batch watermark detection
        results = self.watermark_detector.process_images_batch("partsbucket0000", "images/")
        
        # Save results to database
        self.save_watermark_results_to_db(results)
        
        # Print summary
        summary = self.watermark_detector.get_watermark_summary(results)
        self.print_watermark_summary(summary)
        
        return results
    
    def process_images(self):
        """Process images based on watermark detection results"""
        print("=== Phase 3: Image Processing ===")
        
        # Load watermark detection results
        watermark_results = self.load_watermark_results()
        
        if self.use_ai_watermark_detection and watermark_results:
            # Process based on AI detection
            self.process_with_ai_results(watermark_results)
        else:
            # Fallback to traditional processing
            self.process_traditional()
    
    def process_with_ai_results(self, watermark_results: Dict[str, dict]):
        """Process images using AI watermark detection results"""
        
        # Separate images by watermark status
        clean_images = []
        watermarked_images = []
        
        for filename, result in watermark_results.items():
            if result.get("has_watermark", False) and result.get("confidence") in ["high", "medium"]:
                watermarked_images.append(filename)
            else:
                clean_images.append(filename)
        
        print(f"Clean images: {len(clean_images)}")
        print(f"Watermarked images: {len(watermarked_images)}")
        
        # Process clean images first (faster)
        if clean_images:
            self.process_image_group(clean_images, apply_watermark_removal=False)
        
        # Process watermarked images with traditional removal
        if watermarked_images and self.use_traditional_watermark_removal:
            self.process_image_group(watermarked_images, apply_watermark_removal=True)
    
    def process_image_group(self, image_list: List[str], apply_watermark_removal: bool = False):
        """Process a group of images"""
        # Download images
        self.db.download_group("partsbucket0000", image_list)
        
        # Apply watermark removal if needed
        if apply_watermark_removal:
            self.apply_traditional_watermark_removal(image_list)
        
        # Image deduplication
        if self.use_image_deduplication:
            keep = self.img_proc.hash_and_compare_group(
                image_list, 
                method='phash', 
                hash_size=8,
                distance_thresh=10, 
                testing=True
            )
            
            # Fallback with higher threshold if no duplicates found
            if not keep or len(keep) == len(image_list):
                keep = self.img_proc.hash_and_compare_group(
                    image_list,
                    method='phash',
                    hash_size=8,
                    distance_thresh=14,
                    testing=True
                )
            
            if keep:
                # Mark others for deletion
                self.db.save_data_for_deletion(image_list, keep)
                
                # Upload best image to final bucket
                self.db.upload_to_folder('partsbucket0000', 'final', keep[0])
                print(f"Selected {keep[0]} from {len(image_list)} similar images")
            else:
                print(f"No suitable image found in group of {len(image_list)}")
        
        # Clean up local files
        self.db.empty_dir('images/images')
    
    def apply_traditional_watermark_removal(self, image_list: List[str]):
        """Apply traditional watermark removal to images"""
        from wm_remover import AdvancedWatermarkRemover
        
        remover = AdvancedWatermarkRemover("Tesseract-OCR/tesseract.exe")
        
        # Configure for balanced detection
        remover.tesseract_confidence = 60
        remover.easyocr_confidence = 0.7
        remover.text_padding = 1
        remover.enable_pattern_detection = False
        remover.corner_edge_threshold = 30
        remover.dilation_iterations = 0
        
        for filename in image_list:
            path = f"images/images/{filename}"
            output_path = f"images/cleaned/{filename}"
            
            try:
                # Check if watermark removal is needed
                mask = remover.detect_watermark_mask_only(path)
                has_watermark = remover.has_meaningful_watermark(mask)
                
                if has_watermark:
                    print(f"Applying watermark removal to {filename}")
                    remover.remove_watermark(path, output_path)
                    # Replace original with cleaned version
                    os.replace(output_path, path)
                else:
                    print(f"No watermark detected in {filename}")
                    
            except Exception as e:
                print(f"Error processing {filename}: {e}")
    
    def process_traditional(self):
        """Fallback to traditional processing without AI"""
        print("Using traditional processing mode")
        self.db.retrieve_from_s3(
            "partsbucket0000", 
            "images", 
            run_img_proc=self.use_image_deduplication, 
            run_water_remove=self.use_traditional_watermark_removal
        )
    
    def cleanup(self):
        """Clean up unused images"""
        print("=== Phase 4: Cleanup ===")
        self.db.send_delete_request()
        print("Cleanup completed")
    
    def save_watermark_results_to_db(self, results: Dict[str, dict]):
        """Save watermark detection results to database"""
        import pandas as pd
        
        data = []
        for filename, result in results.items():
            data.append({
                'filename': filename,
                'has_watermark': result.get('has_watermark', False),
                'confidence': result.get('confidence', 'unknown'),
                'watermark_type': result.get('watermark_type', 'unknown'),
                'description': result.get('description', ''),
                'status': result.get('status', 'unknown'),
                'error_message': result.get('error', ''),
                'detection_date': pd.Timestamp.now()
            })
        
        df = pd.DataFrame(data)
        
        # Create table if it doesn't exist
        self.db.create_table_if_not_exists("watermark_detection", df)
        
        # Save to database
        self.db.to_sql(df, "watermark_detection", if_exists='append')
        print(f"Saved {len(data)} watermark detection results to database")
    
    def load_watermark_results(self) -> Dict[str, dict]:
        """Load most recent watermark detection results from database"""
        try:
            query = """
            SELECT filename, has_watermark, confidence, watermark_type, description 
            FROM watermark_detection 
            WHERE detection_date = (
                SELECT MAX(detection_date) FROM watermark_detection
            )
            """
            df = self.db.read_sql_query(query)
            
            results = {}
            for _, row in df.iterrows():
                results[row['filename']] = {
                    'has_watermark': row['has_watermark'],
                    'confidence': row['confidence'],
                    'watermark_type': row['watermark_type'],
                    'description': row['description']
                }
            
            print(f"Loaded {len(results)} watermark detection results from database")
            return results
            
        except Exception as e:
            print(f"Could not load watermark results from database: {e}")
            return {}
    
    def print_watermark_summary(self, summary: dict):
        """Print watermark detection summary"""
        print("\n" + "="*50)
        print("WATERMARK DETECTION SUMMARY")
        print("="*50)
        print(f"Total images processed: {summary['total_images']:,}")
        print(f"Images with watermarks: {summary['images_with_watermarks']:,} ({summary['watermark_percentage']:.1f}%)")
        print(f"Images without watermarks: {summary['images_without_watermarks']:,}")
        print(f"Processing errors: {summary['errors']:,}")
        
        print(f"\nConfidence distribution:")
        for conf, count in summary['confidence_distribution'].items():
            print(f"  {conf}: {count:,}")
        
        print(f"\nWatermark type distribution:")
        for wm_type, count in summary['watermark_type_distribution'].items():
            print(f"  {wm_type}: {count:,}")
        print("="*50)
    
    def get_processing_cost_estimate(self, num_images: int) -> dict:
        """Estimate processing costs"""
        # OpenAI pricing (approximate)
        cost_per_1000_images = 10.0  # $10 per 1M tokens, roughly
        ai_cost = (num_images / 1000) * cost_per_1000_images
        
        return {
            "num_images": num_images,
            "estimated_ai_cost_usd": ai_cost,
            "cost_per_image_cents": (ai_cost / num_images) * 100 if num_images > 0 else 0
        }


if __name__ == "__main__":
    # Set your OpenAI API key
    openai_key = os.getenv("OPENAI_API_KEY")  # Set this in your environment
    
    # Initialize enhanced start program
    start = EnhancedStart(openai_key)
    
    # Configure processing options
    start.use_ai_watermark_detection = True
    start.use_traditional_watermark_removal = True  # For images AI identifies as watermarked
    start.use_image_deduplication = True
    
    # Run different modes:
    
    # Full pipeline
    # start.start_program(mode="full")
    
    # Or run individual phases:
    start.start_program(mode="collect")     # Just collect images
    # start.start_program(mode="ai_detect")   # Just run AI detection
    # start.start_program(mode="process")     # Just process existing images