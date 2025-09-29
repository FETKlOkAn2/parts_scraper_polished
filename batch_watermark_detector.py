# batch_watermark_detector.py
import json
import time
import os
import urllib.parse
from openai import OpenAI
import boto3
from typing import Dict, List
import pandas as pd
from database import Database 
class BatchWatermarkDetector:
    def __init__(self, openai_api_key=None):
        self.client = OpenAI(api_key=openai_api_key)
        self.s3 = boto3.client("s3")
        self.poll_interval = 30
        self.backoff_max = 300
        self.chunk_size = 10000  # OpenAI batch limit
        
    def get_s3_image_urls(self, bucket: str, prefix: str = 'images/') -> List[str]:
        """Get all image URLs from S3 bucket"""
        urls = []
        paginator = self.s3.get_paginator("list_objects_v2")
        
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj['Key']
                # Create presigned URL that's valid for 7 days
                url = self.s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket, 'Key': key},
                    ExpiresIn=604800  # 7 days
                )
                urls.append(url)
        
        return urls
    
    def basename_from_url(self, url: str) -> str:
        """Extract filename from S3 URL"""
        return os.path.basename(urllib.parse.urlparse(url).path)
    
    def create_batch_requests(self, urls: List[str]) -> List[dict]:
        """Create OpenAI batch API requests"""
        requests = []
        for url in urls:
            filename = self.basename_from_url(url)
            request = {
                "custom_id": filename,
                "method": "POST",
                "url": "/v1/chat/completions",  # Fixed: was "/v1/responses"
                "body": {
                    "model": "gpt-4o-mini",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "text", 
                                "text": (
                                    "Analyze this image for watermarks, logos, or overlaid text that are NOT part of the product itself. "
                                    "Look for semi-transparent overlays, repeated patterns, brand logos, or text that appears to be added on top of the product image. "
                                    "Product labels, part numbers, or text that's physically printed on the product should NOT be considered watermarks. "
                                    "Return ONLY valid JSON with the specified schema. If uncertain, use false."
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": url}
                            }
                        ]
                    }],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "watermark_detection",
                            "strict": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "has_watermark": {"type": "boolean"},
                                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                    "watermark_type": {"type": "string", "enum": ["logo", "text", "pattern", "overlay", "none"]},
                                    "description": {"type": "string"}
                                },
                                "required": ["has_watermark", "confidence", "watermark_type"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "temperature": 0.1,
                    "max_tokens": 200
                }
            }
            requests.append(request)
        
        return requests
    
    def submit_batch(self, requests: List[dict], batch_name: str) -> str:
        """Submit batch to OpenAI API"""
        # Create JSONL file
        jsonl_path = f"batch_{batch_name}.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for request in requests:
                f.write(json.dumps(request) + "\n")
        
        # Upload file
        with open(jsonl_path, "rb") as f:
            upload_file = self.client.files.create(file=f, purpose="batch")
        
        # Create batch
        batch = self.client.batches.create(
            input_file_id=upload_file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata={"description": f"Watermark detection batch {batch_name}"}
        )
        
        print(f"Submitted batch {batch_name}: {batch.id} ({len(requests)} requests)")
        return batch.id
    
    def poll_batch_completion(self, batch_id: str):
        """Poll until batch is complete"""
        backoff = self.poll_interval
        
        while True:
            batch = self.client.batches.retrieve(batch_id)
            print(f"Batch {batch_id} status: {batch.status}")
            
            if batch.status in ("completed", "failed", "expired", "cancelling", "cancelled"):
                return batch
            
            time.sleep(backoff)
            backoff = min(int(backoff * 1.5), self.backoff_max)
    
    def download_results(self, output_file_id: str, output_path: str):
        """Download batch results"""
        content = self.client.files.content(output_file_id).text
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
    
    def parse_results(self, jsonl_path: str) -> Dict[str, dict]:
        """Parse batch results into dictionary"""
        results = {}
        
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                
                try:
                    obj = json.loads(line)
                    filename = obj["custom_id"]
                    
                    # Handle successful responses
                    if obj.get("response", {}).get("status_code") == 200:
                        content = obj["response"]["body"]["choices"][0]["message"]["content"]
                        watermark_data = json.loads(content)
                        results[filename] = {
                            "status": "success",
                            "has_watermark": watermark_data["has_watermark"],
                            "confidence": watermark_data.get("confidence", "medium"),
                            "watermark_type": watermark_data.get("watermark_type", "none"),
                            "description": watermark_data.get("description", "")
                        }
                    else:
                        # Handle errors
                        results[filename] = {
                            "status": "error",
                            "has_watermark": False,  # Default to no watermark on error
                            "error": obj.get("response", {}).get("body", {}).get("error", {}).get("message", "Unknown error")
                        }
                        
                except Exception as e:
                    print(f"Error parsing result: {e}")
                    continue
        
        return results
    
    def process_images_batch(self, bucket: str, prefix: str = 'images/') -> Dict[str, dict]:
        """Main function to process all images in batches"""
        print(f"Getting image URLs from s3://{bucket}/{prefix}")
        urls = self.get_s3_image_urls(bucket, prefix)
        print(f"Found {len(urls)} images")
        
        if not urls:
            return {}
        
        # Split into chunks
        batch_ids = []
        for i in range(0, len(urls), self.chunk_size):
            chunk_urls = urls[i:i + self.chunk_size]
            batch_name = f"{i // self.chunk_size:03d}"
            requests = self.create_batch_requests(chunk_urls)
            batch_id = self.submit_batch(requests, batch_name)
            batch_ids.append((batch_id, batch_name))
        
        # Wait for all batches to complete and collect results
        all_results = {}
        for batch_id, batch_name in batch_ids:
            print(f"Waiting for batch {batch_name} to complete...")
            batch = self.poll_batch_completion(batch_id)
            
            if batch.status == "completed" and batch.output_file_id:
                output_path = f"batch_{batch_name}_output.jsonl"
                self.download_results(batch.output_file_id, output_path) 
                batch_results = self.parse_results(output_path)
                all_results.update(batch_results)
                print(f"Batch {batch_name} completed: {len(batch_results)} results")
            else:
                print(f"Batch {batch_name} failed with status: {batch.status}")
        
        # Save consolidated results
        with open("watermark_detection_results.json", "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2)
        
        print(f"Processed {len(all_results)} images total")
        return all_results
    
    def get_watermark_summary(self, results: Dict[str, dict]) -> dict:
        """Get summary statistics of watermark detection"""
        total = len(results)
        with_watermarks = sum(1 for r in results.values() if r.get("has_watermark", False))
        errors = sum(1 for r in results.values() if r.get("status") == "error")
        
        confidence_counts = {}
        type_counts = {}
        
        for result in results.values():
            if result.get("status") == "success":
                conf = result.get("confidence", "unknown")
                wm_type = result.get("watermark_type", "unknown")
                confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
                type_counts[wm_type] = type_counts.get(wm_type, 0) + 1
        
        return {
            "total_images": total,
            "images_with_watermarks": with_watermarks,
            "images_without_watermarks": total - with_watermarks - errors,
            "errors": errors,
            "watermark_percentage": (with_watermarks / total * 100) if total > 0 else 0,
            "confidence_distribution": confidence_counts,
            "watermark_type_distribution": type_counts
        }


# Enhanced Database class additions
class EnhancedDatabase(Database):
    """Add these methods to your existing Database class"""
    
    def __init__(self):
        super().__init__()
        self.watermark_detector = BatchWatermarkDetector()
    
    def detect_watermarks_ai(self, bucket: str, prefix: str = 'images/') -> Dict[str, dict]:
        """Use AI to detect watermarks in batch"""
        return self.watermark_detector.process_images_batch(bucket, prefix)
    
    def filter_images_by_watermark_status(self, detection_results: Dict[str, dict], 
                                            keep_with_watermarks: bool = False) -> List[str]:
        """Filter images based on watermark detection results"""
        filtered_images = []
        
        for filename, result in detection_results.items():
            has_watermark = result.get("has_watermark", False)
            
            # Keep images based on watermark status preference
            if keep_with_watermarks and has_watermark:
                filtered_images.append(filename)
            elif not keep_with_watermarks and not has_watermark:
                filtered_images.append(filename)
        
        return filtered_images
    
    def save_watermark_results_to_db(self, results: Dict[str, dict], table_name: str = "watermark_detection"):
        """Save watermark detection results to database"""
        # Convert results to DataFrame
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
        self.create_table_if_not_exists(table_name, df)
        
        # Save to database
        self.to_sql(df, table_name, if_exists='append')
        print(f"Saved {len(data)} watermark detection results to {table_name}")


# Usage example
if __name__ == "__main__":
    # Initialize detector
    detector = BatchWatermarkDetector()
    
    # Process all images in S3 bucket
    results = detector.process_images_batch("partsbucket0000", "images/")
    
    # Get summary
    summary = detector.get_watermark_summary(results)
    print("\nSummary:")
    print(f"Total images: {summary['total_images']}")
    print(f"With watermarks: {summary['images_with_watermarks']} ({summary['watermark_percentage']:.1f}%)")
    print(f"Without watermarks: {summary['images_without_watermarks']}")
    print(f"Errors: {summary['errors']}")
    print(f"Confidence distribution: {summary['confidence_distribution']}")
    print(f"Watermark types: {summary['watermark_type_distribution']}")