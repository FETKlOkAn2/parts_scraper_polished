import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import os
import sys
import threading
import pandas as pd
from pathlib import Path
import cv2
from wm_remover import AdvancedWatermarkRemover
import pytesseract
import math

class PartsScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Parts Scraper - Watermark Remover")
        self.root.geometry("850x700")
        self.root.resizable(True, True)
        
        # Variables
        self.csv_file_path = tk.StringVar()
        self.output_folder = tk.StringVar(value="output")
        self.processing = False
        self.csv_loaded = False
        self.total_rows = 0
        
        # Instance variables
        self.instance_count = tk.IntVar(value=1)
        self.max_instances = 1
        self.images_per_instance = 100
        
        # Setup GUI
        self.create_widgets()
        self.setup_tesseract()
        self.toggle_controls(False)  # Start with controls disabled
        
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
        
    def toggle_controls(self, enabled):
        """Enable/disable all controls except CSV browse button"""
        state = tk.NORMAL if enabled else tk.DISABLED
        
        # Output folder controls
        self.output_entry.config(state=state)
        self.output_browse_btn.config(state=state)
        
        # Processing options
        for widget in self.options_frame.winfo_children():
            if isinstance(widget, ttk.Checkbutton):
                widget.config(state=state)
        
        # Sensitivity settings
        for widget in self.sensitivity_frame.winfo_children():
            if isinstance(widget, ttk.Radiobutton):
                widget.config(state=state)
        
        # Instance slider
        self.instance_slider.config(state=state)
        
        # Process button
        if enabled and self.csv_loaded:
            self.process_btn.config(state=tk.NORMAL)
        else:
            self.process_btn.config(state=tk.DISABLED)
        
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
        
        # CSV Info Label
        self.csv_info_var = tk.StringVar(value="No CSV file loaded")
        self.csv_info_label = ttk.Label(main_frame, textvariable=self.csv_info_var, 
                                       font=('Arial', 9), foreground='gray')
        self.csv_info_label.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        
        # Output Folder Selection
        ttk.Label(main_frame, text="Output Folder:").grid(row=3, column=0, sticky=tk.W, pady=5)
        
        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=3, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        output_frame.columnconfigure(0, weight=1)
        
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_folder, width=60)
        self.output_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        self.output_browse_btn = ttk.Button(output_frame, text="Browse", command=self.browse_output)
        self.output_browse_btn.grid(row=0, column=1)
        
        # Instance Control
        instance_frame = ttk.LabelFrame(main_frame, text="Processing Instances", padding="10")
        instance_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        instance_frame.columnconfigure(1, weight=1)
        
        ttk.Label(instance_frame, text="Number of Instances:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        
        # Instance info label
        self.instance_info_var = tk.StringVar(value="1 instance (100 images per instance)")
        self.instance_info_label = ttk.Label(instance_frame, textvariable=self.instance_info_var, 
                                            font=('Arial', 9), foreground='blue')
        self.instance_info_label.grid(row=0, column=2, sticky=tk.E, padx=(10, 0))
        
        # Instance slider
        self.instance_slider = ttk.Scale(instance_frame, from_=1, to=1, 
                                        variable=self.instance_count, orient=tk.HORIZONTAL,
                                        command=self.update_instance_info)
        self.instance_slider.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 0))
        
        # Processing Options
        self.options_frame = ttk.LabelFrame(main_frame, text="Processing Options", padding="10")
        self.options_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        self.options_frame.columnconfigure(1, weight=1)
        
        self.remove_watermarks = tk.BooleanVar(value=True)
        self.save_masks = tk.BooleanVar(value=False)
        self.debug_mode = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(self.options_frame, text="Remove Watermarks", 
                       variable=self.remove_watermarks).grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(self.options_frame, text="Save Detection Masks", 
                       variable=self.save_masks).grid(row=0, column=1, sticky=tk.W)
        ttk.Checkbutton(self.options_frame, text="Debug Mode", 
                       variable=self.debug_mode).grid(row=0, column=2, sticky=tk.W)
        
        # Sensitivity Settings
        self.sensitivity_frame = ttk.LabelFrame(main_frame, text="Detection Sensitivity", padding="10")
        self.sensitivity_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        self.sensitivity = tk.StringVar(value="Balanced")
        sensitivity_options = ["Conservative", "Balanced", "Aggressive"]
        
        for i, option in enumerate(sensitivity_options):
            ttk.Radiobutton(self.sensitivity_frame, text=option, 
                           variable=self.sensitivity, value=option).grid(row=0, column=i, padx=10)
        
        # Progress Bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, 
                                           maximum=100, length=400)
        self.progress_bar.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # Status Label
        self.status_var = tk.StringVar(value="Please load a CSV file to begin...")
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var)
        self.status_label.grid(row=8, column=0, columnspan=3, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=9, column=0, columnspan=3, pady=20)
        
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
        log_frame.grid(row=10, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(10, weight=1)
        
        self.log_text = ScrolledText(log_frame, height=12, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
    def update_instance_info(self, value=None):
        """Update instance information label"""
        instances = int(self.instance_count.get())
        if self.csv_loaded:
            images_per_instance = math.ceil(self.total_rows / instances)
            info_text = f"{instances} instance{'s' if instances != 1 else ''} ({images_per_instance} images per instance)"
        else:
            info_text = f"{instances} instance{'s' if instances != 1 else ''}"
        self.instance_info_var.set(info_text)
        
    def validate_csv_structure(self, df):
        """Validate CSV structure and return validation result"""
        required_columns = ['image_path']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return False, f"Missing required columns: {', '.join(missing_columns)}"
        
        # Check if image paths exist
        valid_paths = 0
        total_paths = len(df)
        
        for idx, row in df.head(10).iterrows():  # Check first 10 for validation
            if pd.notna(row['image_path']) and os.path.exists(str(row['image_path'])):
                valid_paths += 1
        
        if valid_paths == 0:
            return False, "No valid image paths found in the first 10 rows"
        
        return True, f"Valid CSV with {total_paths} rows, {valid_paths}/10 sample paths verified"
        
    def browse_csv(self):
        """Browse for CSV file"""
        file_path = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            self.csv_file_path.set(file_path)
            self.load_csv_info(file_path)
            
    def load_csv_info(self, csv_path):
        """Load CSV file and update UI accordingly"""
        try:
            # Read CSV
            df = pd.read_csv(csv_path)
            self.total_rows = len(df)
            
            # Validate CSV structure
            is_valid, message = self.validate_csv_structure(df)
            
            if not is_valid:
                messagebox.showerror("Invalid CSV", message)
                self.csv_loaded = False
                self.csv_info_var.set("Invalid CSV file")
                self.toggle_controls(False)
                return
            
            # Update CSV info
            self.csv_info_var.set(f"✓ {message}")
            
            # Calculate max instances (max 1 instance per 100 images, minimum 1)
            self.max_instances = max(1, math.ceil(self.total_rows / self.images_per_instance))
            
            # Update slider
            self.instance_slider.config(to=self.max_instances)
            self.instance_count.set(min(self.instance_count.get(), self.max_instances))
            
            # Update instance info
            self.update_instance_info()
            
            # Enable controls
            self.csv_loaded = True
            self.toggle_controls(True)
            self.status_var.set("Ready to process...")
            
            self.log_message(f"CSV loaded: {self.total_rows} images, max {self.max_instances} instances recommended")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load CSV file:\n{str(e)}")
            self.csv_loaded = False
            self.csv_info_var.set("Failed to load CSV")
            self.toggle_controls(False)
            self.log_message(f"Error loading CSV: {str(e)}")
            
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
            instances = self.instance_count.get()
            
            # Create output directories
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            if self.save_masks.get():
                Path(os.path.join(output_dir, "masks")).mkdir(exist_ok=True)
            if self.remove_watermarks.get():
                Path(os.path.join(output_dir, "cleaned")).mkdir(exist_ok=True)
                
            # Read CSV
            self.log_message(f"Reading CSV file: {csv_path}")
            df = pd.read_csv(csv_path)
            image_paths = df['image_path'].tolist()
            total_images = len(image_paths)
            
            self.log_message(f"Processing {total_images} images using {instances} instance(s)")
            
            # Split images into chunks for instances
            chunk_size = math.ceil(total_images / instances)
            
            for instance_idx in range(instances):
                if not self.processing:
                    break
                    
                start_idx = instance_idx * chunk_size
                end_idx = min(start_idx + chunk_size, total_images)
                chunk_paths = image_paths[start_idx:end_idx]
                
                self.log_message(f"\n--- Instance {instance_idx + 1}/{instances} ---")
                self.log_message(f"Processing images {start_idx + 1} to {end_idx}")
                
                # Initialize watermark remover for this instance
                remover = AdvancedWatermarkRemover()
                self.configure_remover(remover)
                
                # Process images in this chunk
                for i, img_path in enumerate(chunk_paths):
                    if not self.processing:
                        break
                        
                    global_idx = start_idx + i
                    progress = (global_idx / total_images) * 100
                    self.update_progress(progress, f"Instance {instance_idx + 1}: Processing {i+1}/{len(chunk_paths)}")
                    
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
            self.toggle_controls(True)
            self.stop_btn.config(state=tk.DISABLED)
            
    def start_processing(self):
        """Start processing in a separate thread"""
        if not self.csv_loaded:
            messagebox.showerror("Error", "Please load a valid CSV file first")
            return
            
        self.processing = True
        self.toggle_controls(False)
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