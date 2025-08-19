import cv2
import pytesseract
import numpy as np

class WatermarkRemover():
    def __init__(self, tesseract_cmd):
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def remove_watermark(self, image_path, output_path, mask_path):
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)

        mask = np.zeros(gray.shape, dtype=np.uint8)

        for i, text in enumerate(data["text"]):
            if text.strip() != "":
                (x, y, w, h) = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
                cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)

        h, w = gray.shape
        corner_size = int(min(h, w) * 0.25)  
        corners = [
            (0, 0, corner_size, corner_size), 
            (w - corner_size, 0, w, corner_size),  
            (0, h - corner_size, corner_size, h),  
            (w - corner_size, h - corner_size, w, h),  
        ]
        for (x1, y1, x2, y2) in corners:
            region = gray[y1:y2, x1:x2]
            edges = cv2.Canny(region, 100, 200)
            if edges.mean() > 30:  # heuristic: "too many edges here"
                cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
        # Step 4: Inpaint
        cleaned = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)
        cv2.imwrite(mask_path, mask)
        cv2.imwrite(output_path, cleaned)
        print(f"Watermark removed and saved to {output_path}")
        return cleaned

