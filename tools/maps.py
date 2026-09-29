"""Builds the scene maps for source/caletta.jpg.

Outputs (img/):
  sky.png      8-bit sky alpha, same size as the photo
  skyfill.png  the photo sky extended under the land and blurred (no halos, no holes)
  maps.png     RGB data map: R disparity (0 far .. 255 near), G sway weight, B water
Review overlays go to tools/out/.

The thresholds are tuned by eye for this photo; rerun after changing the image.
"""
import os
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'source', 'caletta.jpg')
OUT = os.path.join(ROOT, 'img')
DBG = os.path.join(ROOT, 'tools', 'out')

# shoreline of the far coast and first row of open sea, in photo pixels
SHORE_Y = 373


def guided(I, p, r, eps):
    """He et al. guided filter, grey guide."""
    mean = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))
    mI, mp = mean(I), mean(p)
    a = (mean(I * p) - mI * mp) / (mean(I * I) - mI * mI + eps)
    b = mp - a * mI
    return np.clip(mean(a) * I + mean(b), 0, 1)


def largest_touching(mask, seeds):
    n, lab = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros_like(mask, bool)
    for (x, y) in seeds:
        if lab[y, x] > 0:
            keep |= lab == lab[y, x]
    return keep


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DBG, exist_ok=True)
    im = cv2.imread(SRC)
    h, w = im.shape[:2]
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV).astype(np.float32)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    grey = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    yy, xx = np.mgrid[0:h, 0:w]

    # ---- sky: pale, low saturation, connected to the top right corner
    skyish = (S < 82) & (V > 178) & (H > 80) & (H < 118) & (yy < SHORE_Y)
    skyish = cv2.morphologyEx(skyish.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    sky = largest_touching(skyish, [(w - 5, 5), (w - 5, 200), (800, 40)])
    sky_a = guided(grey, sky.astype(np.float32), 6, 2e-3)
    sky_a[yy >= SHORE_Y] = 0
    sky_a = np.where(sky_a < 0.04, 0, sky_a)

    # ---- water: turquoise and blue below the far shore
    waterish = (H >= 79) & (H <= 110) & (S > 45) & (V > 25)
    waterish &= ~((yy < SHORE_Y))
    waterish = cv2.morphologyEx(waterish.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)
    water = largest_touching(waterish, [(600, 900), (1050, 420), (500, 1100), (950, 700), (300, 1000)])
    water_s = cv2.GaussianBlur(water.astype(np.float32), (0, 0), 1.2)

    # ---- vegetation: greens and olives that are not water or sky
    veg = (H >= 22) & (H < 80) & (S > 55) & (V > 18) & ~water & (sky_a < 0.5)
    veg = cv2.morphologyEx(veg.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)).astype(bool)

    # foreground foliage: the plants along the bottom and the branch hanging on the right
    fg_zone = (yy > 960) | ((xx > 790) & (yy > 430)) | ((xx < 110) & (yy > 800))
    fg = largest_touching(veg & fg_zone, [(x, h - 3) for x in range(0, w, 12)] +
                          [(w - 3, y) for y in range(440, h, 12)] + [(3, y) for y in range(800, h, 12)])
    # the hanging branch: over bright open water every dark or green pixel is a leaf
    zone = np.zeros((h, w), np.uint8)
    cv2.fillPoly(zone, [np.array([(1086, 440), (955, 440), (935, 610), (885, 720), (830, 790),
                                  (800, 850), (800, 1000), (1086, 1000)], np.int32)], 1)
    right_zone = zone.astype(bool)
    bright_sea = (H >= 84) & (H <= 112) & (V > 100) & (S > 40)
    leaves = right_zone & ~bright_sea
    leaves = cv2.morphologyEx(leaves.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(leaves, connectivity=8)
    big = np.zeros(n, bool)
    big[1:] = stats[1:, cv2.CC_STAT_AREA] > 60
    fg |= big[lab]
    water &= ~fg
    water_s = cv2.GaussianBlur(water.astype(np.float32), (0, 0), 1.2)
    fg = cv2.dilate(fg.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & ~(sky_a > 0.5)
    fg_s = guided(grey, fg.astype(np.float32), 3, 1e-3)

    # ---- disparity (1 near, 0 far)
    t = np.clip((yy - SHORE_Y) / (h - SHORE_Y), 0, 1)
    d_sea = 0.10 + 0.62 * t
    d_land = 0.34 + 0.16 * np.clip((yy - 80) / 620, 0, 1)
    far = (xx > 885) & (yy < SHORE_Y) & (sky_a < 0.5) & ~veg
    d = np.where(water, d_sea, d_land)
    d = np.where(far, 0.05, d)
    d = d * (1 - sky_a)
    d = np.maximum(d, fg_s * 1.0)
    d = cv2.GaussianBlur(d.astype(np.float32), (0, 0), 1.0)
    # grow the foreground by 2 px so mixed edge pixels travel with it
    d = np.maximum(d, cv2.dilate(d, np.ones((5, 5), np.uint8)) * (fg_s > 0.05))

    sway = np.where(fg_s > 0.2, 1.0, 0.0) + np.where(veg & ~fg, 0.35, 0.0)
    sway = cv2.GaussianBlur(np.clip(sway, 0, 1).astype(np.float32), (0, 0), 1.5)

    water_b = cv2.GaussianBlur(water.astype(np.float32), (0, 0), 2.0)
    maps = np.dstack([water_b, sway, d])  # BGR order for OpenCV: B water, G sway, R disparity
    cv2.imwrite(os.path.join(OUT, 'maps.png'), np.clip(maps * 255 + 0.5, 0, 255).astype(np.uint8))
    cv2.imwrite(os.path.join(OUT, 'sky.png'), np.clip(sky_a * 255 + 0.5, 0, 255).astype(np.uint8))

    # ---- sky fill: pull-push from confident sky pixels, then blurred
    conf = (sky_a > 0.97).astype(np.float32)
    col = im.astype(np.float32) * conf[..., None]
    acc, wgt = col, conf
    levels = []
    while min(acc.shape[:2]) > 4:
        levels.append((acc, wgt))
        acc = cv2.resize(acc, (acc.shape[1] // 2, acc.shape[0] // 2), interpolation=cv2.INTER_AREA)
        wgt = cv2.resize(wgt, (wgt.shape[1] // 2, wgt.shape[0] // 2), interpolation=cv2.INTER_AREA)
    fill = acc / np.maximum(wgt, 1e-6)[..., None]
    for acc_l, wgt_l in reversed(levels):
        up = cv2.resize(fill, (acc_l.shape[1], acc_l.shape[0]), interpolation=cv2.INTER_LINEAR)
        known = acc_l / np.maximum(wgt_l, 1e-6)[..., None]
        a = np.clip(wgt_l, 0, 1)[..., None]
        fill = known * a + up * (1 - a)
    fill = cv2.GaussianBlur(fill, (0, 0), 6)
    small = cv2.resize(fill, (256, int(256 * h / w)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(OUT, 'skyfill.png'), np.clip(small, 0, 255).astype(np.uint8))

    # ---- review overlays
    ov = im.astype(np.float32)
    ov = ov * (1 - 0.6 * sky_a[..., None]) + np.array([255, 0, 255]) * 0.6 * sky_a[..., None]
    ov = ov * (1 - 0.45 * water_s[..., None]) + np.array([255, 128, 0]) * 0.45 * water_s[..., None]
    ov = ov * (1 - 0.6 * fg_s[..., None]) + np.array([0, 0, 255]) * 0.6 * fg_s[..., None]
    cv2.imwrite(os.path.join(DBG, 'masks.jpg'), ov.astype(np.uint8))
    cv2.imwrite(os.path.join(DBG, 'disparity.jpg'), (d * 255).astype(np.uint8))
    cv2.imwrite(os.path.join(DBG, 'sway.jpg'), (sway * 255).astype(np.uint8))


if __name__ == '__main__':
    main()
