import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import os
import sys
import threading
import pandas as pd
from pathlib import Path
import cv2
from wm_remover_simple import SimpleWatermarkRemover as AdvancedWatermarkRemover
import pytesseract

class PartsScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Parts Scraper - Watermark Remover")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Variables
        self.csv_file_path = tk.StringVar()
        self.output_folder = tk.StringVar(value="output")
        self.processing = False
        
        # Setup GUI
        self.create_widgets()
        self.setup_tesseract()
        
    def setup_tesseract(self):
        """Setup Tesseract OCR path"""
        # Common Tesseract paths
        tesseract_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "/usr/bin/tesseract",  # Linux
            "/opt/homebrew/bin/tesseract",  # macOS with Homebrew
        ]
        
        for path in tesseract_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                self.log_message(f"Tesseract found at: {path}")
                return
                
        self.log_message("WARNING: Tesseract OCR not found. Please install Tesseract OCR.")
        
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Parts Scraper - Watermark Remover", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # CSV File Selection
        ttk.Label(main_frame, text="CSV File:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        csv_frame = ttk.Frame(main_frame)
        csv_frame.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        csv_frame.columnconfigure(0, weight=1)
        
        self.csv_entry = ttk.Entry(csv_frame, textvariable=self.csv_file_path, width=60)
        self.csv_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        csv_browse_btn = ttk.Button(csv_frame, text="Browse", command=self.browse_csv)
        csv_browse_btn.grid(row=0, column=1)
        
        # Output Folder Selection
        ttk.Label(main_frame, text="Output Folder:").grid(row=2, column=0, sticky=tk.W, pady=5)
        
        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        output_frame.columnconfigure(0, weight=1)
        
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_folder, width=60)
        self.output_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        output_browse_btn = ttk.Button(output_frame, text="Browse", command=self.browse_output)
        output_browse_btn.grid(row=0, column=1)
        
        # Processing Options
        options_frame = ttk.LabelFrame(main_frame, text="Processing Options", padding="10")
        options_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        options_frame.columnconfigure(1, weight=1)
        
        self.remove_watermarks = tk.BooleanVar(value=True)
        self.save_masks = tk.BooleanVar(value=False)
        self.debug_mode = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(options_frame, text="Remove Watermarks", 
                       variable=self.remove_watermarks).grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(options_frame, text="Save Detection Masks", 
                       variable=self.save_masks).grid(row=0, column=1, sticky=tk.W)
        ttk.Checkbutton(options_frame, text="Debug Mode", 
                       variable=self.debug_mode).grid(row=0, column=2, sticky=tk.W)
        
        # Sensitivity Settings
        sensitivity_frame = ttk.LabelFrame(main_frame, text="Detection Sensitivity", padding="10")
        sensitivity_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        self.sensitivity = tk.StringVar(value="Balanced")
        sensitivity_options = ["Conservative", "Balanced", "Aggressive"]
        
        for i, option in enumerate(sensitivity_options):
            ttk.Radiobutton(sensitivity_frame, text=option, 
                           variable=self.sensitivity, value=option).grid(row=0, column=i, padx=10)
        
        # Progress Bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, 
                                           maximum=100, length=400)
        self.progress_bar.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # Status Label
        self.status_var = tk.StringVar(value="Ready to process...")
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var)
        self.status_label.grid(row=6, column=0, columnspan=3, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=7, column=0, columnspan=3, pady=20)
        
        self.process_btn = ttk.Button(button_frame, text="Start Processing", 
                                     command=self.start_processing, style="Accent.TButton")
        self.process_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(button_frame, text="Stop", 
                                  command=self.stop_processing, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        clear_btn = ttk.Button(button_frame, text="Clear Log", command=self.clear_log)
        clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Log Text Area
        log_frame = ttk.LabelFrame(main_frame, text="Processing Log", padding="5")
        log_frame.grid(row=8, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(8, weight=1)
        
        self.log_text = ScrolledText(log_frame, height=15, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
    def browse_csv(self):
        """Browse for CSV file"""
        file_path = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            self.csv_file_path.set(file_path)
            
    def browse_output(self):
        """Browse for output folder"""
        folder_path = filedialog.askdirectory(title="Select Output Folder")
        if folder_path:
            self.output_folder.set(folder_path)
            
    def log_message(self, message):
        """Add message to log"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def clear_log(self):
        """Clear the log"""
        self.log_text.delete(1.0, tk.END)
        
    def update_progress(self, value, status=""):
        """Update progress bar and status"""
        self.progress_var.set(value)
        if status:
            self.status_var.set(status)
        self.root.update_idletasks()
        
    def configure_remover(self, remover):
        """Configure watermark remover based on sensitivity"""
        sensitivity = self.sensitivity.get()
        
        if sensitivity == "Conservative":
            remover.tesseract_confidence = 60
            remover.easyocr_confidence = 0.6
            remover.text_padding = 1
            remover.enable_pattern_detection = False
            remover.corner_edge_threshold = 30
            remover.dilation_iterations = 0
        elif sensitivity == "Balanced":
            remover.tesseract_confidence = 45
            remover.easyocr_confidence = 0.4
            remover.text_padding = 2
            remover.enable_pattern_detection = True
            remover.corner_edge_threshold = 20
            remover.dilation_iterations = 1
        else:  # Aggressive
            remover.tesseract_confidence = 30
            remover.easyocr_confidence = 0.2
            remover.text_padding = 4
            remover.enable_pattern_detection = True
            remover.corner_edge_threshold = 10
            remover.dilation_iterations = 2
            
    def process_images(self):
        """Main processing function"""
        try:
            csv_path = self.csv_file_path.get()
            output_dir = self.output_folder.get()
            
            if not csv_path or not os.path.exists(csv_path):
                messagebox.showerror("Error", "Please select a valid CSV file")
                return
                
            # Create output directories
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            if self.save_masks.get():
                Path(os.path.join(output_dir, "masks")).mkdir(exist_ok=True)
            if self.remove_watermarks.get():
                Path(os.path.join(output_dir, "cleaned")).mkdir(exist_ok=True)
                
            # Read CSV
            self.log_message(f"Reading CSV file: {csv_path}")
            df = pd.read_csv(csv_path)
            
            # Assume CSV has an 'image_path' column
            if 'image_path' not in df.columns:
                self.log_message("ERROR: CSV must contain 'image_path' column")
                return
                
            image_paths = df['image_path'].tolist()
            total_images = len(image_paths)
            
            self.log_message(f"Found {total_images} images to process")
            
            # Initialize watermark remover
            remover = AdvancedWatermarkRemover()
            self.configure_remover(remover)
            
            # Process each image
            for i, img_path in enumerate(image_paths):
                if not self.processing:
                    break
                    
                progress = (i / total_images) * 100
                self.update_progress(progress, f"Processing {i+1}/{total_images}: {os.path.basename(img_path)}")
                
                try:
                    if not os.path.exists(img_path):
                        self.log_message(f"WARNING: Image not found: {img_path}")
                        continue
                        
                    base_name = os.path.splitext(os.path.basename(img_path))[0]
                    
                    if self.remove_watermarks.get():
                        output_path = os.path.join(output_dir, "cleaned", f"{base_name}_cleaned.png")
                        mask_path = os.path.join(output_dir, "masks", f"{base_name}_mask.png") if self.save_masks.get() else None
                        
                        remover.remove_watermark(img_path, output_path, mask_path, debug=self.debug_mode.get())
                        self.log_message(f"  ✓ Processed: {base_name}")
                    else:
                        # Just detect watermarks without removing
                        img = cv2.imread(img_path)
                        if img is not None:
                            text_mask = remover.detect_text_regions_tesseract(img)
                            if self.save_masks.get():
                                mask_path = os.path.join(output_dir, "masks", f"{base_name}_mask.png")
                                cv2.imwrite(mask_path, text_mask)
                            self.log_message(f"  ✓ Analyzed: {base_name}")
                        
                except Exception as e:
                    self.log_message(f"  ✗ Error processing {img_path}: {str(e)}")
                    
            self.update_progress(100, "Processing completed!")
            self.log_message(f"\nProcessing completed! Results saved to: {output_dir}")
            messagebox.showinfo("Success", f"Processing completed!\nResults saved to: {output_dir}")
            
        except Exception as e:
            self.log_message(f"ERROR: {str(e)}")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
        finally:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            
    def start_processing(self):
        """Start processing in a separate thread"""
        if not self.csv_file_path.get():
            messagebox.showerror("Error", "Please select a CSV file")
            return
            
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_var.set(0)
        
        # Start processing thread
        threading.Thread(target=self.process_images, daemon=True).start()
        
    def stop_processing(self):
        """Stop processing"""
        self.processing = False
        self.status_var.set("Stopping...")
        self.log_message("Processing stopped by user")


def main():
    root = tk.Tk()
    
    # Set theme (optional)
    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "light")
    except:
        pass  # Theme not available
        
    app = PartsScraperGUI(root)
    
    # Center window
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
    root.geometry(f"+{x}+{y}")
    
    root.mainloop()


if __name__ == "__main__":
    main()