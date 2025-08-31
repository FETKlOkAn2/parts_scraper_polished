#!/usr/bin/env python3
"""
Minimal Parts Scraper GUI - Emergency Build Version
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import numpy as np
import pytesseract
from pathlib import Path
import threading
import os

class MinimalPartsScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Parts Scraper - Minimal Version")
        self.root.geometry("600x400")
        
        # Create simple UI
        self.create_widgets()
    
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # File selection
        ttk.Label(main_frame, text="Select Image:").grid(row=0, column=0, sticky=tk.W)
        
        file_frame = ttk.Frame(main_frame)
        file_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.file_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_var, width=50)
        self.file_entry.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        ttk.Button(file_frame, text="Browse", command=self.browse_file).grid(row=0, column=1, padx=(5, 0))
        
        # Process button
        ttk.Button(main_frame, text="Remove Watermark", command=self.process_image).grid(row=2, column=0, pady=10)
        
        # Status
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, textvariable=self.status_var).grid(row=3, column=0, sticky=tk.W)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        file_frame.columnconfigure(0, weight=1)
    
    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff")]
        )
        if file_path:
            self.file_var.set(file_path)
    
    def simple_watermark_removal(self, image_path):
        """Very basic watermark removal using OpenCV"""
        # Load image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError("Could not load image")
        
        # Convert to grayscale for text detection
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Simple text detection using Tesseract
        try:
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
            
            # Create mask for detected text
            mask = np.zeros(gray.shape, dtype=np.uint8)
            
            for i, text in enumerate(data["text"]):
                if text.strip() != "" and len(text.strip()) > 2:
                    confidence = int(data["conf"][i]) if data["conf"][i] != '-1' else 0
                    if confidence > 30:
                        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                        cv2.rectangle(mask, (x-2, y-2), (x+w+2, y+h+2), 255, -1)
            
            # Inpaint to remove text
            if mask.any():
                result = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)
            else:
                result = img.copy()
                
            return result
            
        except Exception as e:
            print(f"Tesseract error: {e}")
            # Fallback: simple blur on bright regions
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            kernel = np.ones((5,5), np.uint8)
            mask = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            result = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)
            return result
    
    def process_image(self):
        file_path = self.file_var.get()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid image file")
            return
        
        def process_thread():
            try:
                self.status_var.set("Processing...")
                self.root.update()
                
                # Process image
                result = self.simple_watermark_removal(file_path)
                
                # Save result
                path = Path(file_path)
                output_path = path.parent / f"{path.stem}_cleaned{path.suffix}"
                cv2.imwrite(str(output_path), result)
                
                self.status_var.set(f"Saved: {output_path}")
                messagebox.showinfo("Success", f"Cleaned image saved as:\n{output_path}")
                
            except Exception as e:
                self.status_var.set("Error occurred")
                messagebox.showerror("Error", f"Processing failed:\n{str(e)}")
        
        # Run in thread to prevent GUI freezing
        threading.Thread(target=process_thread, daemon=True).start()

def main():
    root = tk.Tk()
    app = MinimalPartsScraperApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
