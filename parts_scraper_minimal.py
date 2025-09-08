#!/usr/bin/env python3
"""
Ultra-minimal Parts Scraper GUI to avoid PyInstaller issues
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys

class MinimalPartsScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Parts Scraper GUI - Minimal Build")
        self.root.geometry("600x400")
        
        # Create basic interface
        self.create_widgets()
    
    def create_widgets(self):
        """Create minimal GUI widgets"""
        # Title
        title_label = tk.Label(self.root, 
                              text="Parts Scraper GUI", 
                              font=("Arial", 16, "bold"))
        title_label.pack(pady=20)
        
        # Status
        status_label = tk.Label(self.root, 
                               text="Minimal build version - basic functionality only")
        status_label.pack(pady=10)
        
        # File selection
        file_frame = tk.Frame(self.root)
        file_frame.pack(pady=20)
        
        tk.Label(file_frame, text="Select image file:").pack(side=tk.LEFT)
        
        self.file_path_var = tk.StringVar()
        file_entry = tk.Entry(file_frame, textvariable=self.file_path_var, width=40)
        file_entry.pack(side=tk.LEFT, padx=5)
        
        browse_button = tk.Button(file_frame, text="Browse", command=self.browse_file)
        browse_button.pack(side=tk.LEFT)
        
        # Process button
        process_button = tk.Button(self.root, 
                                 text="Process Image", 
                                 command=self.process_image,
                                 bg="lightblue")
        process_button.pack(pady=20)
        
        # Results area
        results_label = tk.Label(self.root, text="Results:")
        results_label.pack(anchor=tk.W, padx=20)
        
        self.results_text = tk.Text(self.root, height=10, width=70)
        self.results_text.pack(padx=20, pady=10)
        
        scrollbar = tk.Scrollbar(self.results_text)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.results_text.yview)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = tk.Label(self.root, 
                            textvariable=self.status_var, 
                            relief=tk.SUNKEN, 
                            anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def browse_file(self):
        """Browse for image file"""
        filename = filedialog.askopenfilename(
            title="Select image file",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff"),
                ("All files", "*.*")
            ]
        )
        if filename:
            self.file_path_var.set(filename)
    
    def process_image(self):
        """Process the selected image"""
        file_path = self.file_path_var.get()
        
        if not file_path:
            messagebox.showerror("Error", "Please select an image file first")
            return
        
        if not os.path.exists(file_path):
            messagebox.showerror("Error", "Selected file does not exist")
            return
        
        self.status_var.set("Processing...")
        self.root.update()
        
        try:
            # Basic file info
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            
            results = f"File: {file_name}\n"
            results += f"Size: {file_size:,} bytes\n"
            results += f"Path: {file_path}\n\n"
            
            # Try basic image processing if opencv is available
            try:
                import cv2
                import numpy as np
                
                img = cv2.imread(file_path)
                if img is not None:
                    height, width = img.shape[:2]
                    results += f"Image dimensions: {width} x {height}\n"
                    results += f"Channels: {img.shape[2] if len(img.shape) == 3 else 1}\n"
                    
                    # Try OCR if pytesseract is available
                    try:
                        import pytesseract
                        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        text = pytesseract.image_to_string(gray)
                        
                        if text.strip():
                            results += f"\nExtracted text:\n{text}\n"
                        else:
                            results += "\nNo text detected in image\n"
                            
                    except Exception as ocr_e:
                        results += f"\nOCR Error: {ocr_e}\n"
                        results += "Make sure Tesseract OCR is installed\n"
                
                else:
                    results += "Could not load image\n"
                    
            except Exception as cv_e:
                results += f"Image processing error: {cv_e}\n"
            
            # Display results
            self.results_text.delete(1.0, tk.END)
            self.results_text.insert(tk.END, results)
            self.status_var.set("Processing complete")
            
        except Exception as e:
            messagebox.showerror("Error", f"Processing failed: {e}")
            self.status_var.set("Error occurred")

def main():
    """Main function"""
    root = tk.Tk()
    app = MinimalPartsScraperGUI(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
    except Exception as e:
        print(f"Application error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
