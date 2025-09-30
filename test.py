# test_watermark_detector.py
"""
Safe testing script for watermark detection
Tests with only a small number of images first
"""
from gui_app.app.batch_watermark_detector import BatchWatermarkDetector
import json, os
from dotenv import load_dotenv
from scraper_app.app.database import Database

load_dotenv()

def test_small_batch(num_images=5):
    """Test with a small number of images"""
    
    print("="*60)
    print("SAFE TEST MODE - Limited to {} images".format(num_images))
    print("="*60)
    
    # Initialize detector
    open_api_key = os.getenv("OPENAI_API_KEY")
    detector = BatchWatermarkDetector(openai_api_key=open_api_key)
    
    # Step 1: Get all URLs but don't process yet
    print("\n[Step 1] Fetching image list from Database...")
    all_urls = detector.get_urls_from_db()
    print(f"Found {len(all_urls)} total images in bucket")
    
    # Step 2: Limit to test size
    test_urls = all_urls[:num_images]
    print(f"\n[Step 2] Selected {len(test_urls)} images for testing")
    
    # Show which images will be processed
    print("\nImages to be analyzed:")
    for i, url in enumerate(test_urls, 1):
        filename = detector.basename_from_url(url)
        print(f"  {i}. {filename}")
    
    # Step 3: Confirm before proceeding
    print("\n" + "="*60)
    print("COST ESTIMATE:")
    cost = (len(test_urls) / 1000) * 10  # Rough estimate
    print(f"Processing {len(test_urls)} images will cost approximately: ${cost:.4f}")
    print("="*60)
    
    response = input("\nProceed with test? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Test cancelled. No API calls were made.")
        return None
    
    # Step 4: Create and submit batch
    print("\n[Step 3] Creating batch requests...")
    requests = detector.create_batch_requests(test_urls)
    
    print("[Step 4] Submitting to OpenAI...")
    batch_id = detector.submit_batch(requests, "TEST_BATCH")
    
    print(f"\n✓ Batch submitted successfully!")
    print(f"Batch ID: {batch_id}")
    print(f"Processing {len(requests)} images...")
    
    # Step 5: Wait for completion
    print("\n[Step 5] Waiting for batch to complete...")
    print("(This may take several minutes)")
    batch = detector.poll_batch_completion(batch_id)
    
    # Step 6: Download and parse results
    if batch.status == "completed":
        print("\n[Step 6] Downloading results...")

        # Re-retrieve to ensure we have latest fields
        batch = detector.client.batches.retrieve(batch_id)

        if not getattr(batch, "output_file_id", None):
            print("Batch completed but no output_file_id present.")
            if getattr(batch, "error_file_id", None):
                print(f"Errors were generated. Downloading error file: {batch.error_file_id}")
                err_path = "test_batch_errors.jsonl"
                detector.download_results(batch.error_file_id, err_path)
                print(f"Saved errors to {err_path}")
            raise RuntimeError("No output_file_id on completed batch—check error file and individual request statuses.")

        output_path = "test_batch_output.jsonl"
        detector.download_results(batch.output_file_id, output_path)
        print(f"Saved results to {output_path}")

        print("[Step 7] Parsing results...")
        results = detector.parse_results(output_path)

        with open("test_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print("Parsed results written to test_results.json")
        
        # Display summary
        print("\n" + "="*60)
        print("TEST RESULTS SUMMARY")
        print("="*60)
        
        summary = detector.get_watermark_summary(results)
        print(f"Total images: {summary['total_images']}")
        print(f"With watermarks: {summary['images_with_watermarks']} ({summary['watermark_percentage']:.1f}%)")
        print(f"Without watermarks: {summary['images_without_watermarks']}")
        print(f"Errors: {summary['errors']}")
        
        if summary['confidence_distribution']:
            print(f"\nConfidence levels:")
            for conf, count in summary['confidence_distribution'].items():
                print(f"  {conf}: {count}")
        
        if summary['watermark_type_distribution']:
            print(f"\nWatermark types detected:")
            for wm_type, count in summary['watermark_type_distribution'].items():
                print(f"  {wm_type}: {count}")
        
        # Show individual results
        print("\n" + "="*60)
        print("DETAILED RESULTS")
        print("="*60)
        for filename, result in results.items():
            status = "✓" if result['status'] == 'success' else "✗"
            watermark = "YES" if result.get('has_watermark') else "NO"
            conf = result.get('confidence', 'N/A')
            print(f"{status} {filename}")
            print(f"   Watermark: {watermark} | Confidence: {conf}")
            if result.get('description'):
                print(f"   Note: {result['description']}")
            print()
        
        print("="*60)
        print(f"✓ Test completed successfully!")
        print(f"Results saved to: test_results.json")
        print(f"Raw output saved to: {output_path}")
        print("="*60)
        
        return results
    else:
        print(f"\n✗ Batch failed with status: {batch.status}")
        return None


def test_url_generation_only():
    """
    Super safe test - just check URL generation without any API calls
    """
    print("="*60)
    print("SUPER SAFE TEST - No API calls, just checking S3 access")
    print("="*60)
    
    detector = BatchWatermarkDetector()
    
    print("\nFetching image list from S3...")
    urls = detector.get_s3_image_urls("partsbucket0000", "images/")
    
    print(f"\n✓ Successfully accessed S3 bucket")
    print(f"Found {len(urls)} images")
    
    # Show first 5
    print("\nFirst 5 images:")
    for i, url in enumerate(urls[:5], 1):
        filename = detector.basename_from_url(url)
        print(f"  {i}. {filename}")
    
    print("\n" + "="*60)
    print("Test completed - no changes made to S3 or database")
    print("="*60)


if __name__ == "__main__":
    print("Choose test mode:")
    print("1. Super safe - just list images (no API calls)")
    print("2. Small batch test - process 5 images")
    print("3. Medium batch test - process 20 images")
    print("4. Custom - specify number of images")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == "1":
        test_url_generation_only()
    elif choice == "2":
        test_small_batch(num_images=5)
    elif choice == "3":
        test_small_batch(num_images=20)
    elif choice == "4":
        try:
            num = int(input("Enter number of images to test: "))
            if num > 100:
                print(f"\nWarning: {num} images is quite a lot for a test.")
                confirm = input("Are you sure? (yes/no): ").strip().lower()
                if confirm != 'yes':
                    print("Test cancelled")
                else:
                    test_small_batch(num_images=num)
            else:
                test_small_batch(num_images=num)
        except ValueError:
            print("Invalid number entered")
    else:
        print("Invalid choice")