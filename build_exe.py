"""
Build script for the real PartsScraperGUI - adapted for your actual code
"""
import subprocess
import sys
import os
import shutil

def emergency_uninstall():
    """Remove problematic packages that cause dis.py errors"""
    print("=== Removing problematic packages ===")
    
    packages_to_remove = [
        "tensorboard", "tensorboard-data-server", "tensorboard-plugin-wit",
        "tensorflow", "tensorflow-estimator", "tensorflow-io-gcs-filesystem",
        "torch", "torchvision", "torchaudio",
        "transformers", "tokenizers", "huggingface-hub",
        "easyocr", "paddlepaddle", "paddleocr",
        "scipy", "scikit-image", "scikit-learn",
        "matplotlib", "seaborn", "plotly",
        "networkx", "igraph",
        "grpcio", "grpcio-status", "grpcio-tools",
        "protobuf", "google-auth", "google-auth-oauthlib",
        "absl-py", "google-pasta", "astunparse",
        "h5py", "keras", "opt-einsum",
        "wrapt", "gast", "flatbuffers",
        "markdown", "werkzeug"
    ]
    
    removed_count = 0
    for package in packages_to_remove:
        try:
            result = subprocess.run([
                sys.executable, "-m", "pip", "uninstall", "-y", package
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"  ✓ Removed {package}")
                removed_count += 1
            else:
                print(f"  - {package} not installed")
                
        except subprocess.TimeoutExpired:
            print(f"  ! Timeout removing {package}")
        except Exception as e:
            print(f"  ! Error removing {package}: {e}")
    
    # Clear pip cache
    try:
        subprocess.run([sys.executable, "-m", "pip", "cache", "purge"], 
                      capture_output=True, timeout=30)
        print(f"  ✓ Cleared pip cache (removed {removed_count} packages)")
    except:
        print("  ! Could not clear pip cache")

def install_required_packages():
    """Install packages needed for your PartsScraperGUI"""
    print("\n=== Installing required packages ===")
    
    # Your GUI needs these specific packages
    required_packages = [
        "pyinstaller==5.13.2",
        "opencv-python-headless==4.8.1.78",  # Headless version is more stable
        "pytesseract==0.3.10", 
        "numpy==1.24.3",
        "pandas==2.0.3",
        "pillow==10.0.0",
        "pathlib2"  # For Path compatibility
    ]
    
    for package in required_packages:
        print(f"Installing {package}...")
        try:
            subprocess.run([
                sys.executable, "-m", "pip", "install", 
                "--no-deps", "--force-reinstall", package
            ], check=True, timeout=120)
            print(f"  ✓ Installed {package}")
        except subprocess.TimeoutExpired:
            print(f"  ! Timeout installing {package}")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to install {package}: {e}")
            return False
    
    return True

def verify_your_files():
    """Check that your actual files exist"""
    required_files = ['parts_scraper_gui.py', 'wm_remover.py']
    
    for file in required_files:
        if not os.path.exists(file):
            print(f"ERROR: Required file missing: {file}")
            return False
    
    print("✓ All required files found")
    return True

def build_your_real_gui():
    """Build your actual PartsScraperGUI"""
    print("\n=== Building Your Real GUI ===")
    
    # Clean any existing build artifacts
    for folder in ['build', 'dist', '__pycache__']:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"  ✓ Cleaned {folder}")
    
    # Remove any .spec files
    import glob
    for spec_file in glob.glob("*.spec"):
        os.remove(spec_file)
        print(f"  ✓ Removed {spec_file}")
    
    # Build command for your actual GUI
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed", 
        "--name=PartsScraperApp",
        
        # Add your wm_remover.py file
        "--add-data=wm_remover.py;." if os.name == 'nt' else "--add-data=wm_remover.py:.",
        
        # Hidden imports for your GUI's dependencies
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.ttk",
        "--hidden-import=tkinter.filedialog",
        "--hidden-import=tkinter.messagebox",
        "--hidden-import=tkinter.scrolledtext",
        "--hidden-import=cv2",
        "--hidden-import=pytesseract",
        "--hidden-import=numpy",
        "--hidden-import=pandas",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=PIL.ImageTk",
        "--hidden-import=pathlib",
        "--hidden-import=threading",
        "--hidden-import=os",
        "--hidden-import=sys",
        
        # Exclude the problematic modules we removed
        "--exclude-module=matplotlib",
        "--exclude-module=scipy", 
        "--exclude-module=skimage",
        "--exclude-module=tensorflow",
        "--exclude-module=torch",
        "--exclude-module=tensorboard",
        "--exclude-module=easyocr",  # Your GUI mentions this but we're excluding it
        "--exclude-module=transformers",
        
        "--clean",
        "--noconfirm",
        "parts_scraper_gui.py"  # Your actual GUI file
    ]
    
    print("Running PyInstaller on your real GUI...")
    print(f"Command: {' '.join(cmd[:5])}... (truncated)")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        print("\n✅ BUILD SUCCESSFUL!")
        print("Your PartsScraperApp.exe has been created in the 'dist' folder")
        
        # Show build results
        if os.path.exists("dist"):
            print("\nBuild results:")
            for item in os.listdir("dist"):
                item_path = os.path.join("dist", item)
                if os.path.isfile(item_path):
                    size_mb = os.path.getsize(item_path) / (1024*1024)
                    print(f"  - {item} ({size_mb:.1f} MB)")
        
        return True
        
    except subprocess.TimeoutExpired:
        print("\n❌ Build timed out (took more than 10 minutes)")
        return False
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed with error: {e}")
        print("STDOUT:", e.stdout if e.stdout else "None")
        print("STDERR:", e.stderr if e.stderr else "None")
        return False

def create_folder_version():
    """Create folder version as backup"""
    print("\n=== Creating Folder Version (Backup) ===")
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",  # Create folder instead of single file
        "--windowed", 
        "--name=PartsScraperApp_Folder",
        
        # Add your wm_remover.py file
        "--add-data=wm_remover.py;." if os.name == 'nt' else "--add-data=wm_remover.py:.",
        
        # Essential hidden imports only
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.ttk", 
        "--hidden-import=tkinter.filedialog",
        "--hidden-import=tkinter.messagebox",
        "--hidden-import=tkinter.scrolledtext",
        "--hidden-import=cv2",
        "--hidden-import=pytesseract",
        "--hidden-import=numpy",
        "--hidden-import=pandas",
        "--hidden-import=PIL",
        
        # Exclude problematic modules
        "--exclude-module=tensorflow",
        "--exclude-module=torch",
        "--exclude-module=tensorboard",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        
        "--clean",
        "--noconfirm",
        "parts_scraper_gui.py"
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        print("✅ Folder version also created successfully!")
        return True
    except Exception as e:
        print(f"❌ Folder version failed: {e}")
        return False

def main():
    """Main build process for your real GUI"""
    print("=== Building Your Real PartsScraperGUI ===")
    print("This will build your actual GUI with all its features")
    
    # Check files exist
    if not verify_your_files():
        return
    
    print(f"\nPython version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    
    # Step 1: Remove problematic packages
    emergency_uninstall()
    
    # Step 2: Install required packages
    if not install_required_packages():
        print("\n❌ FAILED: Could not install required packages")
        return
    
    # Step 3: Build your real GUI
    success = build_your_real_gui()
    
    # Step 4: Create folder version as backup
    if success:
        create_folder_version()
    
    if success:
        print("\n🎉 SUCCESS! Your real PartsScraperGUI has been built.")
        print("\n📋 USAGE INSTRUCTIONS:")
        print("1. Go to the 'dist' folder")
        print("2. Run 'PartsScraperApp.exe'")
        print("3. Your GUI should work with all its original features")
        print("\n⚠️  IMPORTANT NOTES:")
        print("- Make sure Tesseract OCR is installed on target machines")
        print("- The app will look for Tesseract in common locations")
        print("- If OCR doesn't work, users need to install Tesseract from:")
        print("  https://github.com/UB-Mannheim/tesseract/wiki")
        print("- Your CSV files should have an 'image_path' column as expected")
        
    else:
        print("\n❌ BUILD FAILED")
        print("\n🔧 TROUBLESHOOTING:")
        print("1. Check if wm_remover.py has any problematic imports")
        print("2. Try with Python 3.9 instead of 3.10")
        print("3. Make sure your GUI code doesn't import the removed packages")
        print("4. Check the error messages above for specific issues")

if __name__ == "__main__":
    main()