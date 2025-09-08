
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('skimage')
hiddenimports = collect_submodules('skimage')
hiddenimports += [
    'skimage.io._plugins',
    'skimage.filters.rank.core_cy',
    'skimage.morphology._skeletonize_cy',
    'skimage.restoration._denoise_cy',
]
