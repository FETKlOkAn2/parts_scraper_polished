from cx_Freeze import setup, Executable
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
