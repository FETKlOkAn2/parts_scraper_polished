
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('easyocr')
hiddenimports = collect_submodules('easyocr')

# Add specific torch/vision imports that easyocr needs
hiddenimports += [
    'torch.nn.functional',
    'torchvision.transforms',
    'torchvision.models',
]
