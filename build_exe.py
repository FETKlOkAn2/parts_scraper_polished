"""
Build script for creating executable using PyInstaller
Run this script to create the EXE file
"""
import os
import sys
import subprocess

def install_pyinstaller():
    """Install PyInstaller if not already installed"""
    try:
        import PyInstaller
        print("PyInstaller already installed")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller installed")

def create_executable():
    """Create the executable file"""
    
    # PyInstaller command with better compatibility
    cmd = [
        "pyinstaller",
        "--name=PartsScraperApp",
        "--onedir",  # Create folder instead of single file (more stable)
        "--windowed",  # No console window (GUI app)
        "--add-data=wm_remover.py;.",  # Include watermark remover module
        "--hidden-import=cv2",
        "--hidden-import=pytesseract", 
        "--hidden-import=easyocr",
        "--hidden-import=torch",  # EasyOCR dependency
        "--hidden-import=torchvision",  # EasyOCR dependency
        "--hidden-import=scipy",
        "--hidden-import=skimage",
        "--hidden-import=pandas",
        "--hidden-import=numpy",
        "--hidden-import=matplotlib",
        "--hidden-import=PIL",
        "--hidden-import=Pillow",
        "--collect-all=easyocr",  # Collect all EasyOCR files
        "--collect-all=torch",    # Collect all PyTorch files
        "--collect-all=torchvision",
        "--exclude-module=matplotlib.tests",
        "--exclude-module=scipy.tests",
        "--exclude-module=numpy.tests",
        "--noconfirm",  # Overwrite without asking
        "--clean",  # Clean cache
        "parts_scraper_gui.py"  # Main script
    ]
    
    print("Building executable...")
    print("Command:", " ".join(cmd))
    
    try:
        subprocess.run(cmd, check=True)
        print("\nBuild completed successfully!")
        print("Executable created: dist/PartsScraperApp.exe")
        print("\nTo distribute your app:")
        print("1. Copy dist/PartsScraperApp.exe")
        print("2. Make sure users have Tesseract OCR installed")
        print("3. Provide installation instructions")
        
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        return False
        
    return True

def create_installer_instructions():
    """Create installation instructions for end users"""
    instructions = """
# Parts Scraper App - Installation Instructions

## Prerequisites
Before running the Parts Scraper App, you need to install Tesseract OCR:

### Windows:
1. Download Tesseract OCR from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install it (default location: C:\\Program Files\\Tesseract-OCR\\)
3. The app will automatically detect Tesseract

### Linux (Ubuntu/Debian):
```bash
sudo apt install tesseract-ocr
```

### macOS:
```bash
brew install tesseract
```

## Running the App
1. Download PartsScraperApp.exe
2. Double-click to run
3. If Windows shows a security warning, click "More info" then "Run anyway"

## Usage
1. Click "Browse" to select your CSV file (must contain 'image_path' column)
2. Choose output folder for results
3. Select processing options:
   - **Remove Watermarks**: Actually removes watermarks from images
   - **Save Detection Masks**: Saves the detection masks for debugging
   - **Debug Mode**: Provides more detailed output
4. Choose sensitivity level:
   - **Conservative**: Less aggressive, fewer false positives
   - **Balanced**: Good balance of detection vs accuracy
   - **Aggressive**: More thorough detection, may catch more text
5. Click "Start Processing"

## CSV Format
Your CSV file should have at least an 'image_path' column with full paths to image files:
```
image_path
C:\\path\\to\\image1.jpg
C:\\path\\to\\image2.png
```

## Support
If you encounter issues:
1. Check that Tesseract OCR is installed correctly
2. Verify your CSV file format
3. Make sure image paths in CSV are correct and accessible
"""
    
    with open("INSTALLATION_INSTRUCTIONS.md", "w") as f:
        f.write(instructions)
    
    print("Created INSTALLATION_INSTRUCTIONS.md")

def main():
    """Main build function"""
    print("=== Parts Scraper App Build Script ===\n")
    
    # Check if required files exist
    required_files = ["parts_scraper_gui.py", "wm_remover.py"]
    for file in required_files:
        if not os.path.exists(file):
            print(f"Required file missing: {file}")
            return
    
    # Install PyInstaller
    install_pyinstaller()
    
    # Create executable
    if create_executable():
        create_installer_instructions()
        print("\n=== Build Complete ===")
        print("Your app is ready for distribution!")
        print("Files created:")
        print("- dist/PartsScraperApp.exe (main executable)")
        print("- INSTALLATION_INSTRUCTIONS.md (user guide)")
    else:
        print("Build failed. Please check the error messages above.")

if __name__ == "__main__":
    main()