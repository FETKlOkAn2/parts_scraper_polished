from image_processing import Img_Proc
import cv2
import numpy as np

def debug_hash_pipeline():
    img_proc = Img_Proc()
    
    # Load image
    print("=== DEBUGGING HASH PIPELINE ===")
    img_path = "images/images/ATRMA37000_LOAD_PAD_(UPPER)_1.png"
    print(f"Loading: {img_path}")
    
    # Step 1: Load with OpenCV
    img = cv2.imread(img_path)
    print(f"1. Raw CV2 image shape: {img.shape}")
    print(f"   Raw CV2 dtype: {img.dtype}")
    print(f"   Raw CV2 min/max: {img.min()}/{img.max()}")
    
    # Step 2: Process with load_and_resize_cv
    img_resized = img_proc.load_and_resize_cv(img_path)
    print(f"2. After load_and_resize_cv:")
    print(f"   Shape: {img_resized.shape}")
    print(f"   Dtype: {img_resized.dtype}")
    print(f"   Min/max: {img_resized.min()}/{img_resized.max()}")
    
    # Step 3: Convert to gray uint8
    gray_uint8 = img_proc.to_gray2d_uint8(img_resized)
    print(f"3. After to_gray2d_uint8:")
    print(f"   Shape: {gray_uint8.shape}")
    print(f"   Dtype: {gray_uint8.dtype}")
    print(f"   Min/max: {gray_uint8.min()}/{gray_uint8.max()}")
    
    # Step 4: Convert to grayscale float for hashing
    try:
        gray_float = img_proc.to_grayscale(gray_uint8.astype(np.float32) / 255.0)
        print(f"4. After to_grayscale:")
        print(f"   Shape: {gray_float.shape}")
        print(f"   Dtype: {gray_float.dtype}")
        print(f"   Min/max: {gray_float.min()}/{gray_float.max()}")
        
        # Step 5: Resize to 16x16
        small = img_proc.resize_image(gray_float, shape=(16, 16))
        print(f"5. After resize to 16x16:")
        print(f"   Shape: {small.shape}")
        print(f"   Dtype: {small.dtype}")
        print(f"   Min/max: {small.min()}/{small.max()}")
        
        # Step 6: Orient top-left
        oriented, desc, score = img_proc.orient_top_left(small)
        print(f"6. After orient_top_left ({desc}):")
        print(f"   Shape: {oriented.shape}")
        print(f"   Dtype: {oriented.dtype}")
        print(f"   Min/max: {oriented.min()}/{oriented.max()}")
        
        # Step 7: Compute hash
        hash_val = img_proc.compute_hash(oriented, method="phash", hash_size=8)
        print(f"7. Final hash: 0x{hash_val:016X}")
        
        # Test with different methods
        hash_ahash = img_proc.compute_hash(oriented, method="ahash", hash_size=8)
        hash_dhash = img_proc.compute_hash(oriented, method="dhash", hash_size=8)
        print(f"   ahash: 0x{hash_ahash:016X}")
        print(f"   dhash: 0x{hash_dhash:016X}")
        
    except Exception as e:
        print(f"Error in hash pipeline: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_hash_pipeline()