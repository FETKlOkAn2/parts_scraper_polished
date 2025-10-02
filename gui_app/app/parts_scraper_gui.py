import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import threading
import pandas as pd
import math
from database import Database
from statedb import StateDB
from math import ceil
import io
import time
import os
from helpers import Helper
from batch_watermark_detector import BatchWatermarkDetector
from dotenv import load_dotenv
load_dotenv()


class PartsScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Parts Scraper - Watermark Remover")
        self.root.geometry("850x700")
        self.root.resizable(True, True)
        
        # Constants
        self.open_ai_key = os.getenv("OPENAI_API_KEY")
        self.bucket = "partsbucket0000"
        self.search_job_key = 'search_jobs'
        self.process_job_key = 'proc_jobs'
        self.search_queue = 'https://sqs.us-east-1.amazonaws.com/390403858209/scraper_queue'
        self.process_queue = ''
        self.search_chunk_size = 250
        self.processing_chunk_size = 500

        # Tests
        self.test_input_key = 'jobs'
        self.test_queue = "https://sqs.us-east-1.amazonaws.com/390403858209/Dazetestqueue"

        # Variables
        self.csv_file_path = tk.StringVar()
        self.processing = False
        self.csv_loaded = False
        self.total_rows = 0
        self.dataframe = None

        
        # Setup GUI
        self.create_widgets()

        self.db = Database()
        self.detector = BatchWatermarkDetector(self.db, self.open_ai_key)
        self.helper = Helper(self.db, self.detector)
        self.state = StateDB()


        self.determine_state()


    def perform_watermark(self):
        self.progress_bar.start(30)
        self.status_var.set("Performing AI watermark detection")
        self.ai_watermark_btn.configure(state=tk.DISABLED)

        ids = self.helper.organize_and_submit_batch()
        self.state.set(batch_ids=ids)
        self.poll_open_ai()
        self.db.send_delete_request()

        self.progress_bar.stop()


    def poll_open_ai(self):
        current = self.state.read()
        batch_ids = current.get("batch_ids")

        completed = False
        count = 0
        all_results = []
        time.sleep(30)

        while not completed:
            time.sleep(60)
            count += 1
            for batch_id in batch_ids:
                result, status = self.detector.poll_multiple_batch_completion(batch_id)
                self.log_message(f"Batch {batch_id} status: {status}")
                all_results.append(result)
            if all(all_results):
                completed = True
            self.log_message('\n')
        
        self.log_message("AI has determined which images have watermarks and they are being deleted...")

        self.helper.parse_ai_results(batch_ids)

    def perform_filter(self):
        self.progress_bar.start(30)
        self.filter_images_btn.configure(state=tk.DISABLED)
        self.status_var.set("Performing Hash Similiarity")

        self.log_message("Gathering Remaining Images...")
        
        all_data = self.db.read_sql_query("SELECT tag_value FROM part_tags ORDER BY tag_value ASC;")

        num_chunks = self.helper.split_group_upload(
            df=all_data,
            bucket=self.bucket,
            prefix=self.process_job_key,
            chunk_size = self.processing_chunk_size
        )


        self.log_message("Instances being created in the Cloud Please Wait...")

        self.status_var.set("COMPLETED: Images are Ready for Deployment")

    def process_images(self):
        """Main processing function"""
        # uploading to database
        self.status_var.set("Performing Image Search...")
        self.progress_bar.start(30)
        self.log_message('Uploading CSV to Database...')
        self.db.upsert_append_new_only(self.dataframe)

        # retriving data from database 
        self.log_message('Gathering all parts without an image...')
        all_data = self.db.read_sql_query("SELECT number, description FROM parts WHERE final_tag IS NULL;")

        # spliting data into chucks and upload to s3
        self.log_message("splitting data into jobs...")
        num_chunks = self.helper.split_data_and_upload_jobs(
            df=all_data,
            bucket=self.bucket,
            prefix=self.search_job_key,
            chunk_size = self.search_chunk_size) 
        
        self.clear_log()

        self.helper.send_chunk_messages(    # real
            job_id = "Testing",             #images_search
            queue_url = self.test_queue,    #self.search_queue
            num_chunks =  10,               #num_chunks
            key = self.test_input_key)      #self.search_key


        self.log_message("Watermark Button will become clickable when all images have been downloaded...")
        self.log_message(f"{num_chunks} Instances being created in cloud please wait...")

        all_terminated = False
        count = 0
        time.sleep(30)
        while not all_terminated:
            time.sleep(60)
            all_terminated,state = self.helper.determine_instance_state()
            count += 1
            self.clear_log()
            self.log_message("Watermark Button will become clickable when all images have been downloaded...")
            self.log_message(f"\nStill downloading images...\n\tStatus: {state}\n\tMinutes: {count}")
        
        # Deletes the CSV files from search_jobs
        self.db.empty_prefix(self.bucket, self.search_job_key)

        self.clear_log()
        self.log_message("All images have been downloaded.\nYou can now start the watermark")
        self.ai_watermark_btn.configure(state=tk.Normal)
        self.process_btn.configure(state=tk.DISABLED)
        self.progress_bar.stop()

    def determine_state(self):
        current = self.state.read()
        if current.get("image_search_state"):
            self.log_message("Retreiving Images via Cloud will update when finished")
            self.toggle_controls(False, True)

        elif current.get("image_watermark_detection"):
            self.log_message("Waiting for completion of AI Watermark detector via Cloud will update when finished")
            self.toggle_controls(False, True)

        elif current.get("image_hashing"):
            self.log_message("Image Hashing is talking place via Cloud will update whne finished")
            self.toggle_controls(False, True)
        else:
            self.log_message("No jobs yet performed")
            self.toggle_controls(False)



    def toggle_controls(self, enabled, full_lock=False):
        """Enable/disable all controls except CSV browse button"""
        state = tk.NORMAL if enabled else tk.DISABLED
        
        # Processing options
        for widget in self.options_frame.winfo_children():
            if isinstance(widget, ttk.Checkbutton):
                widget.config(state=state)
        if full_lock:
            # needs to set CSV to disable
            self.csv_browse_btn.configure(state=tk.DISABLED)
            
        
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
        
        self.csv_browse_btn = ttk.Button(csv_frame, text="Browse", command=self.browse_csv)
        self.csv_browse_btn.grid(row=0, column=1)
        

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
        # self.progress_var = tk.DoubleVar()
        # self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, 
        #                                    maximum=100, length=400)
        # self.progress_bar.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)

        self.progress_bar = ttk.Progressbar(main_frame, mode=['indeterminate'], 
                                           length=400)
        self.progress_bar.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        

        # Status Label
        self.status_var = tk.StringVar(value="Please load a CSV file to begin...")
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var)
        self.status_label.grid(row=8, column=0, columnspan=3, pady=5)
        

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=9, column=0, columnspan=3, pady=20)
        
        self.process_btn = ttk.Button(button_frame, text="Start Image Search", 
                                     command=self.start_processing, style="Accent.TButton")
        self.process_btn.pack(side=tk.LEFT, padx=5)

        self.ai_watermark_btn = ttk.Button(button_frame, text='AI Watermark',
                                           command=self.start_watermark, style='Accent.TButton', state=tk.DISABLED)  
        self.ai_watermark_btn.pack(side=tk.LEFT, padx=5)

        self.filter_images_btn = ttk.Button(button_frame, text="Filter Images",
                                            command=self.start_filter, style='Accent.TButton', state=tk.DISABLED)
        self.filter_images_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(button_frame, text="Stop", 
                                  command=self.stop_processing, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.RIGHT, padx=5)
        
        clear_btn = ttk.Button(button_frame, text="Clear Log", command=self.clear_log)
        clear_btn.pack(side=tk.RIGHT, padx=5)



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
        self.file_path = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if self.file_path:
            self.csv_file_path.set(self.file_path)
            self.load_csv_info(self.file_path)

        # Enable controls
        self.csv_loaded = True
        self.toggle_controls(True)
        self.status_var.set("Ready to process...")
        self.log_message(f"CSV loaded: {self.total_rows} images")

            
    def load_csv_info(self, csv_path):
        """Load CSV file and update UI accordingly"""
        try:
            # Read CSV
            self.dataframe = pd.read_csv(csv_path, sep=',', header=0, index_col=0)
            self.total_rows = len(self.dataframe)
            
            # Validate CSV structure
            is_valid, message = self.validate_csv_structure(self.dataframe)
            
            if not is_valid:
                messagebox.showerror("Invalid CSV", message)
                self.csv_loaded = False
                self.csv_info_var.set("Invalid CSV file")
                self.toggle_controls(False)
                return
            
            # Update CSV info
            self.csv_info_var.set(f"✓ {message}")
            self.clear_log()
            self.log_message('\nHere is a view of the data.')
            self.log_message(self.dataframe.head(5).to_string())
            self.log_message('..........................................')
            self.log_message('..........................................')
            self.log_message(self.dataframe.tail(5).to_string())


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

    def start_filter(self):
        self.clear_log()
        self.log_message("Starting filter process of remaining images...")
        self.start_threading(self.perform_filter)

    def start_watermark(self):
        self.clear_log()
        self.log_message('Sending data to AI for watermark detection...')
        self.start_threading(self.perform_watermark)

    def start_processing(self):
        """Start processing in a separate thread"""
        if not self.csv_loaded:
            messagebox.showerror("Error", "Please load a valid CSV file first")
            return
        result = messagebox.askyesno("Confirm", "This will upload the parts to the Database and start Cloud Instances to Process all the images.\nIf the part and number is already in the database it will not be duplicated. \n\nMAKE SURE THE DATA IS CORRECT BEFORE CHOOSING YES.", default='no')
        if result:
            
            self.processing = True
            self.toggle_controls(False)
            self.stop_btn.config(state=tk.NORMAL)
            #self.progress_var.set(0)


            # Start processing thread
            self.clear_log()
            self.log_message("Starting to Process...")

            self.start_threading(self.process_images)
        else:
            pass

    def start_threading(self, function, params=None):
        if params is not None:
            threading.Thread(target=function(params), daemon=True).start()

        else:
            threading.Thread(target=function, daemon=True).start()

                            
        
    def stop_processing(self):
        """Stop processing"""
        self.processing = False
        self.status_var.set("Stopping...")
        self.log_message("Processing stopped by user")
        self.progress_bar.stop()


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