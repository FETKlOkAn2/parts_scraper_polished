"""
Enhanced build script with PyInstaller error fixes and multiple fallback strategies
"""
import os
import sys
import subprocess
import shutil
import platform

def check_dependencies():
    """Check if required tools are available"""
    print("Checking dependencies...")
    
    # Check Python version
    python_version = sys.version_info
    print(f"Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 8):
        print("⚠️  Warning: Python 3.8+ recommended for PyInstaller")
    
    # Check PyInstaller
    try:
        result = subprocess.run(["pyinstaller", "--version"], capture_output=True, text=True)
        print(f"PyInstaller version: {result.stdout.strip()}")
    except FileNotFoundError:
        print("❌ PyInstaller not found. Install with: pip install pyinstaller")
        return False
    
    return True

def upgrade_pyinstaller():
    """Upgrade PyInstaller to latest version"""
    print("\n=== Upgrading PyInstaller ===")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"], check=True)
        print("✓ PyInstaller upgraded successfully")
        return True
    except subprocess.CalledProcessError:
        print("✗ Failed to upgrade PyInstaller")
        return False

def create_minimal_spec_file():
    """Create a minimal .spec file to avoid dis.py issues"""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['parts_scraper_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('wm_remover.py', '.')],
    hiddenimports=[
        'cv2',
        'pytesseract',
        'numpy',
        'pandas',
        'scipy',
        'skimage',
        'matplotlib.pyplot',
        'PIL.Image',
        'PIL.ImageTk',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'pathlib',
        'threading',
        'queue',
        'json',
        'logging'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib.tests',
        'numpy.tests',
        'scipy.tests',
        'test',
        'tests',
        'unittest',
        'pytest',
        'IPython',
        'jupyter',
        'notebook'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove problematic modules that cause dis.py issues
a.pure = [x for x in a.pure if not any(exclude in x[0] for exclude in [
    'IPython', 'jupyter', 'notebook', 'qtconsole', 'spyder'
])]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PartsScraperApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PartsScraperApp',
)
'''
    
    with open('PartsScraperApp_minimal.spec', 'w') as f:
        f.write(spec_content)
    
    print("✓ Created minimal .spec file")

def create_ultra_simple_version():
    """Create version with absolute minimum dependencies"""
    print("Creating ultra-simple version...")
    
    # Read original file
    with open('parts_scraper_gui.py', 'r') as f:
        content = f.read()
    
    # Create minimal version
    minimal_content = '''#!/usr/bin/env python3
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
                messagebox.showinfo("Success", f"Cleaned image saved as:\\n{output_path}")
                
            except Exception as e:
                self.status_var.set("Error occurred")
                messagebox.showerror("Error", f"Processing failed:\\n{str(e)}")
        
        # Run in thread to prevent GUI freezing
        threading.Thread(target=process_thread, daemon=True).start()

def main():
    root = tk.Tk()
    app = MinimalPartsScraperApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
'''
    
    with open('parts_scraper_minimal.py', 'w') as f:
        f.write(minimal_content)
    
    print("✓ Created ultra-simple version")

def build_method_1_minimal():
    """Build minimal version with basic dependencies only"""
    print("\n=== Method 1: Minimal Build (Essential dependencies only) ===")
    
    create_ultra_simple_version()
    
    cmd = [
        "pyinstaller",
        "--name=PartsScraperApp_Minimal",
        "--onefile",
        "--windowed",
        "--hidden-import=cv2",
        "--hidden-import=pytesseract",
        "--hidden-import=numpy",
        "--hidden-import=PIL",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=skimage", 
        "--exclude-module=pandas",
        "--exclude-module=easyocr",
        "--exclude-module=torch",
        "--exclude-module=IPython",
        "--exclude-module=jupyter",
        "--exclude-module=notebook",
        "--clean",
        "parts_scraper_minimal.py"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("✓ Minimal build completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Minimal build failed: {e}")
        return False

def build_method_2_folder_safe():
    """Build folder version with safe parameters"""
    print("\n=== Method 2: Safe Folder Build ===")
    
    cmd = [
        "pyinstaller",
        "--name=PartsScraperApp_Folder",
        "--onedir",
        "--windowed",
        "--add-data=wm_remover.py;." if platform.system() == "Windows" else "--add-data=wm_remover.py:.",
        "--hidden-import=cv2",
        "--hidden-import=pytesseract",
        "--exclude-module=IPython",
        "--exclude-module=jupyter", 
        "--exclude-module=notebook",
        "--exclude-module=qtconsole",
        "--exclude-module=spyder",
        "--clean",
        "parts_scraper_gui.py"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("✓ Safe folder build completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Safe folder build failed: {e}")
        return False

def build_method_3_spec_minimal():
    """Build using minimal spec file"""
    print("\n=== Method 3: Minimal Spec Build ===")
    
    create_minimal_spec_file()
    
    try:
        subprocess.run(["pyinstaller", "--clean", "PartsScraperApp_minimal.spec"], check=True)
        print("✓ Minimal spec build completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Minimal spec build failed: {e}")
        return False

def build_method_4_cx_freeze():
    """Alternative: cx_Freeze setup"""
    print("\n=== Method 4: cx_Freeze Setup (Alternative) ===")
    
    cx_setup = '''from cx_Freeze import setup, Executable
import sys

build_exe_options = {
    "packages": ["cv2", "pytesseract", "numpy", "tkinter", "PIL"],
    "excludes": ["matplotlib", "scipy", "pandas", "IPython", "jupyter"],
    "include_files": ["wm_remover.py"]
}

base = None
if sys.platform == "win32":
    base = "Win32GUI"

setup(
    name="PartsScraperApp",
    version="1.0",
    description="Parts Scraper Application",
    options={"build_exe": build_exe_options},
    executables=[Executable("parts_scraper_gui.py", base=base, target_name="PartsScraperApp.exe")]
)
'''
    
    with open('setup_cx.py', 'w') as f:
        f.write(cx_setup)
    
    print("✓ Created cx_Freeze setup file")
    print("To use cx_Freeze:")
    print("1. pip install cx_Freeze")
    print("2. python setup_cx.py build")
    
    return False  # Don't auto-run, just provide the option

def clean_build_artifacts():
    """Clean up build artifacts"""
    print("\nCleaning build artifacts...")
    
    folders_to_clean = ['build', '__pycache__']
    files_to_clean = ['*.spec']
    
    for folder in folders_to_clean:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"✓ Removed {folder}")
    
    import glob
    for pattern in files_to_clean:
        for file in glob.glob(pattern):
            os.remove(file)
            print(f"✓ Removed {file}")

def main():
    """Enhanced build process with error handling"""
    print("=== Enhanced Parts Scraper App Build Script ===\n")
    
    if not check_dependencies():
        return
    
    # Try to upgrade PyInstaller first
    print("Attempting to fix PyInstaller issues...")
    upgrade_pyinstaller()
    
    # Clean previous builds
    clean_build_artifacts()
    
    methods = [
        ("Minimal Build (Recommended for errors)", build_method_1_minimal),
        ("Safe Folder Build", build_method_2_folder_safe), 
        ("Minimal Spec Build", build_method_3_spec_minimal),
        ("cx_Freeze Setup (Manual)", build_method_4_cx_freeze)
    ]
    
    success = False
    
    for method_name, method_func in methods:
        print(f"\nTrying {method_name}...")
        try:
            if method_func():
                success = True
                print(f"\n✓ SUCCESS: {method_name} worked!")
                break
            else:
                print(f"✗ {method_name} failed or skipped, trying next method...")
        except Exception as e:
            print(f"✗ {method_name} encountered error: {e}")
            continue
    
    if success:
        print("\n=== Build Complete ===")
        print("Check the 'dist' folder for your executable.")
        
        if os.path.exists("dist"):
            print("\nFiles created:")
            for item in os.listdir("dist"):
                path = os.path.join("dist", item)
                if os.path.isfile(path):
                    size = os.path.getsize(path) / (1024*1024)
                    print(f"- dist/{item} ({size:.1f} MB)")
                else:
                    print(f"- dist/{item}/ (folder)")
    else:
        print("\n=== All PyInstaller methods failed ===")
        print("\nTroubleshooting recommendations:")
        print("1. Try the cx_Freeze method (setup_cx.py was created)")
        print("2. Use a fresh virtual environment:")
        print("   python -m venv fresh_env")
        print("   fresh_env\\Scripts\\activate")
        print("   pip install opencv-python pytesseract numpy pillow pyinstaller")
        print("3. Consider using auto-py-to-exe GUI tool")
        print("4. Check for conflicting packages in your environment")

if __name__ == "__main__":
    main()