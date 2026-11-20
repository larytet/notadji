"""Test sequences: camera motion (pan, slow zoom) over real photographs, with sensor noise (not real flight video)."""
import numpy as np
from PIL import Image

PHOTOS = ["/usr/share/backgrounds/Cherry_Tree_in_Lakones_by_elenastravoravdi.jpg", "/usr/share/backgrounds/DSC2943_by_kcpru.jpg",
          "/usr/share/backgrounds/Mirror_by_Uday_Nakade.jpg"]


def load(i, W=1400):
    im = Image.open(PHOTOS[i % len(PHOTOS)]).convert("L")
    h = int(im.height * W / im.width)
    return im.resize((W, h), Image.LANCZOS)


def sequence(i, n, W=320, H=256, vx=3.1, vy=1.3, zoom=0.0006, noise=2.0, seed=1):
    im = load(i)
    rng = np.random.default_rng(seed)
    out = []
    x0 = im.width * 0.3
    y0 = im.height * 0.3
    for k in range(n):
        z = 1.0 + zoom * k
        cx = x0 + vx * k
        cy = y0 + vy * k
        # affine: output (u, v) -> input (cx + (u - W/2) z, cy + (v - H/2) z)
        a = z
        c = cx - (W / 2) * z
        f = cy - (H / 2) * z
        crop = im.transform((W, H), Image.AFFINE, (a, 0, c, 0, a, f), resample=Image.BILINEAR)
        arr = np.asarray(crop, dtype=np.float64) + rng.normal(0, noise, (H, W))
        out.append(np.clip(np.round(arr), 0, 255).astype(np.int64))
    return out
