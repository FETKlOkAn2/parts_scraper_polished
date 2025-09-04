# Parts Scraper App - Setup Instructions

## Step 1: Prepare Your Environment

1. **Install Python 3.8-3.11** (if not already installed)
   - Download from: https://python.org/downloads/
   - Make sure to check "Add Python to PATH" during installation

2. **Install Tesseract OCR**
   - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
   - Linux: `sudo apt install tesseract-ocr`
   - macOS: `brew install tesseract`

## Step 2: Setup Project Files

1. **Create project folder**
   ```
   parts_scraper/
   ├── parts_scraper_gui.py    (main GUI app)
   ├── wm_remover.py           (your existing watermark remover)
   ├── requirements.txt        (dependencies)
   ├── build_exe.py           (build script)
   └── test_data/             (optional: test images/CSV)
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Step 3: Test the GUI Application

1. **Run the GUI app**
   ```bash
   python parts_scraper_gui.py
   ```

2. **Test with sample data**
   - Create a CSV file with image paths
   - Test the functionality before building EXE

## Step 4: Build Executable

1. **Run the build script**
   ```bash
   python build_exe.py
   ```

2. **Find your executable**
   - Location: `dist/PartsScraperApp.exe`
   - Size: ~200-300MB (includes all dependencies)

## Step 5: Distribution

### Option 1: GitHub Release
1. Create a new release on GitHub
2. Upload `PartsScraperApp.exe`
3. Include `INSTALLATION_INSTRUCTIONS.md` in the release notes

### Option 2: Direct Download
1. Upload the EXE to a file sharing service
2. Provide download link and instructions

## Sample CSV Format

Your CSV file should look like this:
```csv
image_path,part_name,category
C:\images\part1.jpg,Brake Pad,Brakes
C:\images\part2.png,Oil Filter,Engine
C:\images\part3.jpg,Spark Plug,Engine
```

**Important**: The 'image_path' column is required!

## Troubleshooting Build Issues

### Common Problems:

1. **ModuleNotFoundError during build**
   ```bash
   pip install --upgrade pyinstaller
   pip install -r requirements.txt
   ```

2. **Large EXE file size**
   - Normal for first build (includes Python + all libraries)
   - Can be reduced with `--exclude-module` flags if needed

3. **Missing DLLs**
   - Make sure all dependencies are installed via pip
   - Use `--collect-all` flag for problematic modules

4. **Tesseract not found**
   - The app will auto-detect common Tesseract paths
   - Users need to install Tesseract separately

## Advanced Build Options

For smaller file size (creates folder instead of single EXE):
```bash
pyinstaller --name=PartsScraperApp --windowed parts_scraper_gui.py
```

For debugging build issues:
```bash
pyinstaller --name=PartsScraperApp --onefile --windowed --debug all parts_scraper_gui.py
```

## Distribution Checklist

- [ ] EXE file created successfully
- [ ] Tested on clean Windows machine
- [ ] Installation instructions created
- [ ] Sample CSV file provided
- [ ] Tesseract installation requirements documented
- [ ] GitHub release created (optional)

## File Size Expectations

- **Single EXE**: ~200-300MB (includes Python runtime + all libraries)
- **Folder distribution**: ~150-250MB (separate files)
- **Compressed**: ~80-150MB (using ZIP/7z)

The large size is normal because it includes:
- Python interpreter
- OpenCV
- TensorFlow (from EasyOCR)
- NumPy, SciPy
- All other dependencies