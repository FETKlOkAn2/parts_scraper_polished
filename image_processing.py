import os
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np
from skimage.io import imread
from skimage.transform import resize
from skimage.metrics import structural_similarity as ssim
from skimage import img_as_float
from skimage.color import rgb2gray

class Img_Proc:
    def __init__(self):
        self.folder = "images"
        self.images = [f for f in os.listdir(self.folder) if os.path.isfile(os.path.join(self.folder, f))]
        self.grouped = defaultdict(list)

        self.group_images()
        #self.perform_ssim(testing=True)  # set False to disable debug plots
        self.run_hashing(
            method= 'phash',
            hash_size= 8,
            distance_thresh= 12,
            testing=False)

    def group_images(self):
        for name in self.images:
            base_name = '_'.join(name.split('_')[:-1])  # strip the numeric suffix
            self.grouped[base_name].append(name)

    # ---------- Display helpers ----------
    def show_image(self, img, title="Image", cmap=None):
        plt.figure()
        plt.imshow(img, cmap=cmap)
        plt.title(title)
        plt.axis('off')
        plt.tight_layout()
        plt.show()

    def show_images_side_by_side(self, img1, img2, title1="Image 1", title2="Image 2", cmap=None):
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        axes[0].imshow(img1, cmap=cmap)
        axes[0].set_title(title1)
        axes[0].axis('off')
        axes[1].imshow(img2, cmap=cmap)
        axes[1].set_title(title2)
        axes[1].axis('off')
        plt.tight_layout()
        plt.show()

    # ---------- Image IO / preprocessing ----------
    def load_and_grayscale(self, path, where="(unknown)"):
        img = imread(path)
        img = img_as_float(img)             # [0,1]
        img = np.squeeze(img)

        if img.ndim == 3:
            if img.shape[2] == 4:           # drop alpha
                img = img[:, :, :3]
            img = rgb2gray(img)             # -> HxW float

        if img.ndim != 2:
            raise ValueError(f"{where}: expected 2-D, got {img.shape}")

        if img.dtype == object:
            img = np.array(img, dtype=np.float32)
        else:
            img = np.ascontiguousarray(img, dtype=np.float32)
        return img

    def resize_image(self, img, shape=(16, 16)):
        out = resize(img, shape, anti_aliasing=True)
        return np.ascontiguousarray(out, dtype=np.float32)

    # ---------- Orientation helpers (top-left bright mass) ----------
    def _make_tl_weights(self, h: int, w: int, kind: str = "gaussian"):
        yy, xx = np.mgrid[0:h, 0:w]
        if kind == "gaussian":
            sy, sx = h / 3.0, w / 3.0
            wmap = np.exp(- (yy**2)/(2*sy*sy) - (xx**2)/(2*sx*sx))
        else:
            wy = 1.0 - (yy / max(h-1, 1))
            wx = 1.0 - (xx / max(w-1, 1))
            wmap = wy * wx
        wmap /= (wmap.sum() + 1e-12)
        return wmap.astype(np.float32)

    def _score_top_left(self, img2d: np.ndarray, wmap: np.ndarray) -> float:
        return float((img2d * wmap).sum())

    def _dihedral_variants(self, img2d: np.ndarray):
        variants = []
        for k in range(4):  # 0,90,180,270
            r = np.rot90(img2d, k=k)
            variants.append((r, f"rot{k*90}"))
            variants.append((np.fliplr(r), f"rot{k*90}_fliplr"))
        return variants

    def orient_top_left(self, img2d: np.ndarray, weights_kind: str = "gaussian"):
        assert img2d.ndim == 2, f"Expected 2D image, got {img2d.shape}"
        h, w = img2d.shape
        wmap = self._make_tl_weights(h, w, kind=weights_kind)

        best_img, best_desc, best_score = None, None, -np.inf
        for v, desc in self._dihedral_variants(img2d):
            s = self._score_top_left(v, wmap)
            if s > best_score:
                best_img, best_desc, best_score = v, desc, s
        return np.ascontiguousarray(best_img, dtype=np.float32), best_desc, best_score



# --- Perceptual hashing utilities ---

    def _bits_to_int(self, bits: np.ndarray) -> int:
        """Pack a boolean/0-1 array into a single integer (row-major)."""
        # Flatten, convert to string of 0/1, then to int base-2
        return int(''.join('1' if b else '0' for b in bits.astype(bool).ravel()), 2)

    def _hamming(self, h1: int, h2: int) -> int:
        """Hamming distance between two packed integer hashes."""
        return (h1 ^ h2).bit_count()

    def compute_hash(self, img16: np.ndarray, method: str = "phash", hash_size: int = 8) -> int:
        """
        Compute a perceptual hash for a small grayscale image in [0,1].
        Supported methods:
        - 'phash' (DCT-based; preferred if SciPy available)
        - 'ahash' (average hash)
        - 'dhash' (difference hash, horizontal)
        Returns an integer with hash_size*hash_size (or hash_size*(hash_size-1) for dhash) bits.
        """
        assert img16.ndim == 2, f"Expected 2D image, got {img16.shape}"
        img = np.clip(img16, 0.0, 1.0).astype(np.float32)

        if method == "phash":
            # Prefer pHash (DCT of a slightly larger image, keep low freq)
            try:
                from scipy.fftpack import dct
            except Exception:
                # Fallback to aHash if SciPy not installed
                method = "ahash"

        if method == "phash":
            # 1) Upscale to 32x32 to capture more low-frequency detail before DCT
            big = self.resize_image(img, shape=(32, 32))

            # 2) 2D DCT (type-II) row-wise then col-wise
            from scipy.fftpack import dct
            dct_rows = dct(big, type=2, norm='ortho', axis=0)
            dct2 = dct(dct_rows, type=2, norm='ortho', axis=1)

            # 3) Take top-left low-frequency block (hash_size x hash_size)
            low = dct2[:hash_size, :hash_size]

            # 4) Zero out the DC term before computing the median (classic pHash tweak)
            low_no_dc = low.copy()
            low_no_dc[0, 0] = 0.0

            median = np.median(low_no_dc)
            bits = low > median  # boolean matrix
            return self._bits_to_int(bits)

        elif method == "ahash":
            # Average hash: resize to hash_size x hash_size, threshold at mean
            small = self.resize_image(img, shape=(hash_size, hash_size))
            mean = small.mean()
            bits = small >= mean
            return self._bits_to_int(bits)

        elif method == "dhash":
            # Difference hash (horizontal): (hash_size x (hash_size+1)) -> compare adjacent cols
            w = hash_size + 1
            small = self.resize_image(img, shape=(hash_size, w))
            diff = small[:, 1:] > small[:, :-1]  # shape (hash_size, hash_size)
            return self._bits_to_int(diff)

        else:
            raise ValueError(f"Unknown hash method: {method}")

    def hash_and_compare_group(self, files, method="phash", hash_size=8, distance_thresh=10, testing=False):
        """
        For a list of filenames, compute oriented 16x16, hash them,
        and print similar pairs (Hamming distance <= threshold).
        """
        entries = []  # (name, hash_int)
        for fn in files:
            path = os.path.join(self.folder, fn)
            try:
                gray = self.load_and_grayscale(path, where=fn)
                small = self.resize_image(gray, shape=(16, 16))
                oriented, desc, _ = self.orient_top_left(small)

                if testing:
                    self.show_images_side_by_side(small, oriented,
                        title1=f"{fn} (16×16)", title2=f"{fn} ({desc})", cmap='gray')

                h = self.compute_hash(oriented, method=method, hash_size=hash_size)
                entries.append((fn, h))
            except Exception as e:
                print(f"  [skip] {fn}: {e}")

        # Compare all pairs
        n = len(entries)
        for i in range(n):
            for j in range(i + 1, n):
                name1, h1 = entries[i]
                name2, h2 = entries[j]
                d = self._hamming(h1, h2)
                if d <= distance_thresh:
                    print(f"  similar: {name1} ↔ {name2} | {method} dist={d}")

    def run_hashing(self, method="phash", hash_size=8, distance_thresh=10, testing=False):
        """
        Iterate your grouped files, hash within each group, and print similar pairs.
        """
        for group_name, files in self.grouped.items():
            if len(files) < 2:
                continue
            print(f"\n=== Hashing group: {group_name} ({method}) ===")
            self.hash_and_compare_group(files, method=method, hash_size=hash_size,
                                        distance_thresh=distance_thresh, testing=testing)





    # ---------- ssim  ----------
    def perform_ssim(self, testing=False):
        for group_name, files in self.grouped.items():
            if len(files) < 2:
                continue
            print(f"\n=== Comparing group: {group_name} ===")

            imgs = []
            for fn in files:
                path = os.path.join(self.folder, fn)
                try:
                    gray = self.load_and_grayscale(path, where=fn)
                    small = self.resize_image(gray, shape=(16, 16))
                    oriented, desc, score = self.orient_top_left(small, weights_kind="gaussian")

                    if testing:
                        # Show 16x16 before vs oriented 16x16
                        self.show_images_side_by_side(
                            small, oriented,
                            title1=f"{fn} (16×16)",
                            title2=f"{fn} ({desc})",
                            cmap='gray'
                        )
                    imgs.append((fn, oriented, desc))
                except Exception as e:
                    print(f"  [skip] {fn}: {e}")

            # pairwise comparisons using oriented 16×16
            for i in range(len(imgs)):
                for j in range(i + 1, len(imgs)):
                    name1, im1, d1 = imgs[i]
                    name2, im2, d2 = imgs[j]
                    score = ssim(im1, im2, data_range=1.0)
                    print(f"{name1.split('_')[-1]} vs {name2.split('_')[-1]} → SSIM: {score:.4f}")


if __name__ == "__main__":
    Img_Proc()
