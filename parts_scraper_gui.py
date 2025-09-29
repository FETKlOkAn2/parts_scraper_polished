import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import threading
import pandas as pd
import math
from selen import Parser
from database import Database

class PartsScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Parts Scraper - Watermark Remover")
        self.root.geometry("850x700")
        self.root.resizable(True, True)
        
        # Variables
        self.csv_file_path = tk.StringVar()
        self.processing = False
        self.csv_loaded = False
        self.total_rows = 0
        self.dataframe = None

        # States
        self.image_search_state = False
        self.image_watermark_detection = False
        self.image_hashing = False
        
        # Setup GUI
        self.create_widgets()
        self.determine_state()
        self.toggle_controls(False)  # Start with controls disabled

        self.db = Database()

    def determine_state(self):
        with open 

    def toggle_controls(self, enabled):
        """Enable/disable all controls except CSV browse button"""
        state = tk.NORMAL if enabled else tk.DISABLED
        
        # # Output folder controls
        # self.output_entry.config(state=state)
        # self.output_browse_btn.config(state=state)
        
        # Processing options
        for widget in self.options_frame.winfo_children():
            if isinstance(widget, ttk.Checkbutton):
                widget.config(state=state)
        
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
          

        # Processing Options
        self.options_frame = ttk.LabelFrame(main_frame, text="Processing Options", padding="10")
        self.options_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        self.options_frame.columnconfigure(1, weight=1)


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
        required_columns = ['number', 'description']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return False, f"Missing required columns: {', '.join(missing_columns)}"

        total_paths = len(df)
        
        return True, f"Valid CSV with {total_paths} rows."
        
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
            df = pd.read_csv(csv_path, sep=',', header=0, index_col=0)
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
            self.db.upsert_append_new_only(df)

            
            # Enable controls
            self.csv_loaded = True
            self.toggle_controls(True)
            self.status_var.set("Ready to process...")
            
            self.log_message(f"CSV loaded: {self.total_rows} images")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load CSV file:\n{str(e)}")
            self.csv_loaded = False
            self.csv_info_var.set("Failed to load CSV")
            self.toggle_controls(False)
            self.log_message(f"Error loading CSV: {str(e)}")
            
            
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

            
    def process_images(self):
        """Main processing function"""
        self.parse = Parser()
        try:
            # function gets images and saves them to s3 buckets
            self.parse.run_driver(
                function=self.parse.duck_image_search,
                iterations=len(self.df))# can do len(self.df) for the entire database
            
            #downloads from s3, processes images, saves to final s3 bucket
            self.db.retrieve_from_s3("partsbucket0000","images", run_img_proc=True, run_water_remove=False)

            # deletes all the unused images
            #self.db.send_delete_request()         
            
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