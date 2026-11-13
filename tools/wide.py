"""Builds everything the scene needs for the landscape photo (source/ville.jpg), the one wide screens
show: the same pink and yellow villas from further along the cove. Same outputs as maps.py,
sea.py and foliage.py make for the portrait photo, in img/wide/:

  sky.png, skyfill.png   where the sky is (haze and the faint far coast included), and that sky
                         carried under the land and blurred
  plate.webp             the photo without the bush in the bottom left corner
  seabed.webp            the sea without its ripples, sparkles and the boat
  sea.png                R water (also under the bush), G depth, B signed distance to the shore
  maps.png               half resolution, B: how exposed each stretch of rock is to the swell
  objects.webp           the boat, cut out, to float
  leaftex.webp, rig.json the bush, drawn leaf by leaf (tools/foliage.py)
  poster.webp            a light copy for the page until the scene is ready
Review images in tools/out/wide/. The camera and the boat's box are printed: they go into
SCENES.wide in scene.html. The photo's own constants (horizon, outlines) are below.
"""
import os, json, base64
import cv2
import numpy as np
import maps
import foliage
from sea import norm_blur

ROOT = maps.ROOT
SRC = os.path.join(ROOT, 'source', 'ville.jpg')
OUT = os.path.join(ROOT, 'img', 'wide')
DBG = os.path.join(ROOT, 'tools', 'out', 'wide')

# ---- the camera: a level horizon at row 503 (where the haze turns into sea, on the right), a
# ~60 degree lens on the 1920 px width, and 20 m above the water (the boat, ~6 m, is ~95 px long)
F, CX, CY = 1663.0, 960.0, 665.5
HORIZON = 503
PITCH = float(np.arctan((CY - HORIZON) / F))
HEIGHT = 20.0
SWELL_DIR = np.array([-0.7, -0.7])        # from the open sea on the right, in towards the cove

# ---- outlines, in photo pixels (traced on the photo): the water, generously (the colour test
# then keeps only the sea), the bush in front, the boat
WATER = [(1920, 500), (1655, 500), (1648, 640), (1665, 700), (1690, 760), (1714, 800), (1702, 830),
         (1630, 852), (1560, 877), (1490, 907), (1440, 945), (1395, 985), (1372, 1012), (1352, 1040),
         (1300, 1046), (1200, 1060), (1150, 1074), (1100, 1086), (1000, 1101), (900, 1118), (800, 1142),
         (790, 1186), (600, 1188), (500, 1186), (448, 1196), (446, 1252), (262, 1252), (248, 1232),
         (212, 1250), (200, 1331), (1920, 1331)]
BUSH = [(0, 1190), (340, 1190), (340, 1331), (0, 1331)]
# the far mountains in the haze on the right, behind the pine: their ridge (below it, down to the
# sea, is land; the sun goes down behind it)
RIDGE = [(1370, 450), (1420, 440), (1450, 420), (1480, 410), (1520, 404), (1560, 402), (1600, 404), (1640, 410),
         (1680, 414), (1720, 420), (1760, 422), (1790, 412), (1820, 406), (1860, 401), (1920, 398)]
BOAT = (1790, 978, 64, 52)                 # centre x, y, half width, half height (with its shadow)


def ground(x, y):
    u, v = (x - CX) / F, (y - CY) / F
    down = v * np.cos(PITCH) + np.sin(PITCH)
    fwd = np.cos(PITCH) - v * np.sin(PITCH)
    t = np.where(down > 1e-4, HEIGHT / np.maximum(down, 1e-4), np.nan)
    return u * t, fwd * t


def poly(h, w, pts):
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [np.array(pts, np.int32)], 1)
    return m.astype(bool)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DBG, exist_ok=True)
    im = cv2.imread(SRC)
    h, w = im.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV).astype(np.float32)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    grey = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    img = im.astype(np.float32)

    # ---- sky: pale and blue, connected to the top right corner, above the horizon
    skyish = (S < 95) & (V > 205) & (H > 84) & (H < 112) & (yy < HORIZON)
    skyish = cv2.morphologyEx(skyish.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    # the big sky, and the patch of it between the trees at the top of the hill
    sky = maps.largest_touching(skyish, [(w - 5, 5), (w - 5, 300), (1300, 20), (900, 5), (960, 30)])
    mountains = poly(h, w, RIDGE + [(1920, HORIZON + 2), (1370, HORIZON + 2)])
    sky &= ~mountains
    sky_a = maps.guided(grey, sky.astype(np.float32), 6, 2e-3)
    sky_a[yy >= HORIZON] = 0
    sky_a = np.where(sky_a < 0.04, 0, sky_a).astype(np.float32)
    cv2.imwrite(os.path.join(OUT, 'sky.png'), np.clip(sky_a * 255 + 0.5, 0, 255).astype(np.uint8))
    conf = sky_a > 0.97
    fill = cv2.GaussianBlur(maps.pull_push(img, conf), (0, 0), 6)
    small = cv2.resize(fill, (256, int(256 * h / w)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(OUT, 'skyfill.png'), np.clip(small, 0, 255).astype(np.uint8))

    # ---- the bush in the bottom left corner: drawn leaf by leaf, so it comes out of the plate
    green = (H >= 20) & (H < 75) & (S > 70) & (V > 40)
    fg = poly(h, w, BUSH) & green
    fg = cv2.morphologyEx(fg.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)).astype(bool)
    fg = maps.largest_touching(fg, [(x, h - 3) for x in range(0, 330, 10)] + [(3, y) for y in range(1200, h, 10)])
    leafA = maps.guided(grey, fg.astype(np.float32), 3, 1e-3) * poly(h, w, [(0, 1170), (360, 1170), (360, h), (0, h)])
    hole = cv2.dilate((leafA >= 0.12).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    known = ~cv2.dilate(hole.astype(np.uint8), np.ones((13, 13), np.uint8)).astype(bool)

    # ---- the water
    inside = poly(h, w, WATER) & (yy > HORIZON + 1)
    seaish = (H >= 60) & (H <= 115) & (S > 35) & (V > 28)
    bx, by, brx, bry = BOAT
    boat_zone = ((xx - bx) / brx) ** 2 + ((yy - by) / bry) ** 2 <= 1
    W = inside & (seaish | boat_zone | hole)
    W = maps.fill_small_holes(W, 1500)
    # the pine leaning over the water: its needles are in front of the sea, never part of it
    pine_zone = poly(h, w, [(1540, 470), (1920, 470), (1920, 760), (1540, 760)])
    needles = pine_zone & (((H >= 15) & (H < 82) & (S > 50)) | (V < 70))
    W &= ~cv2.dilate(needles.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    W = cv2.morphologyEx(W.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    W = maps.largest_touching(W, [(1800, 700), (1500, 1250), (900, 1250), (1850, 560)])
    cover = maps.guided(grey, W.astype(np.float32), 2, 1e-3)
    cover = np.where(cv2.dilate(W.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool), cover, 0)
    cover = np.maximum(cover, cv2.erode(W.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(np.float32))

    # ---- the plate: the photo without the bush (behind it, the cliff and the sea, smoothly)
    plate = np.where(hole[..., None], maps.pull_push(img, known), img)
    cv2.imwrite(os.path.join(OUT, 'plate.webp'), np.clip(plate, 0, 255).astype(np.uint8), [cv2.IMWRITE_WEBP_QUALITY, 85])
    plate = cv2.imread(os.path.join(OUT, 'plate.webp')).astype(np.float32)

    # ---- the boat: whatever in its outline is not sea (hull, canopy, crew); its shadow is sea-blue
    # and stays in the water
    tight = ((xx - bx) / (brx * 0.85)) ** 2 + ((yy - (by - 6)) / (bry * 0.8)) ** 2 <= 1
    sea_col = (H >= 78) & (H <= 118) & (S > 45) & (V > 35)
    oa = (tight & ~sea_col).astype(np.float32)
    oa = cv2.morphologyEx(oa, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    oa = cv2.morphologyEx(oa, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    oa = cv2.GaussianBlur(oa, (0, 0), 0.7) * boat_zone
    ys, xs = np.nonzero(oa > 0.05)
    boat_box = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
    rgba = np.dstack([np.clip(plate, 0, 255), oa * 255]).astype(np.uint8)
    rgba[oa < 0.004] = 0
    cv2.imwrite(os.path.join(OUT, 'objects.webp'), rgba, [cv2.IMWRITE_WEBP_QUALITY, 90])

    # ---- the water body: ripples, sparkles and the boat taken out; blurred as wide as the ripples
    # look at each distance, less over the shallows where the floor shows
    gx, gy = ground(CX * np.ones(h, np.float32), np.arange(h, dtype=np.float32))
    dY = np.abs(np.gradient(gy))
    sig_row = np.clip(0.45 / np.maximum(dY, 1e-4) * 0.6, 1.0, 4.0)
    sig_row = np.where(np.isfinite(sig_row), sig_row, 1.0)
    sig = np.repeat(sig_row[:, None], w, 1).astype(np.float32)
    shallow = W & (H < 88) & (yy > 1000)                       # the green, where the floor shows
    sig = np.where(cv2.dilate(shallow.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool), np.minimum(sig, 1.8), sig)
    sig = cv2.GaussianBlur(sig, (0, 0), 8)
    src = cv2.medianBlur(np.clip(plate, 0, 255).astype(np.uint8), 5).astype(np.float32)
    clean = W & ~cv2.dilate(((oa > 0.02) | boat_zone).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    clean &= ~cv2.dilate(hole.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    src = np.where(clean[..., None], src, maps.pull_push(src, clean))
    levels = [1.0, 1.8, 2.8, 4.0]
    blurred = [norm_blur(src, W, s)[0] for s in levels]
    seabed = np.zeros_like(src)
    for i in range(len(levels) - 1):
        a, b = levels[i], levels[i + 1]
        t = np.clip((sig - a) / (b - a), 0, 1)[..., None]
        sel = ((sig >= a) & (sig <= b))[..., None] if i else (sig <= b)[..., None]
        seabed = np.where(sel, blurred[i] * (1 - t) + blurred[i + 1] * t, seabed)
    seabed = np.where((sig > levels[-1])[..., None], blurred[-1], seabed)
    seabed = np.where(W[..., None], seabed, maps.pull_push(seabed, W))
    cv2.imwrite(os.path.join(OUT, 'seabed.webp'), np.clip(seabed, 0, 255).astype(np.uint8), [cv2.IMWRITE_WEBP_QUALITY, 88])

    # ---- shore, depth, exposure (as tools/sea.py does for the portrait photo)
    pine = poly(h, w, [(1560, 480), (1920, 480), (1920, 720), (1560, 720)])     # the pine leaning over the water
    land = ~W & (yy > HORIZON + 30) & ~pine
    d_out = cv2.distanceTransform((~land).astype(np.uint8), cv2.DIST_L2, 5)
    d_to_water = cv2.distanceTransform((~W).astype(np.uint8), cv2.DIST_L2, 5)
    sd = np.where(W, d_out, -d_to_water)
    X, Y = ground(xx.astype(np.float32), yy.astype(np.float32))
    X = np.nan_to_num(X, nan=0.0); Y = np.nan_to_num(Y, nan=5000.0)
    mpp = np.sqrt(np.abs(np.gradient(X, axis=1)) * np.abs(np.gradient(Y, axis=0)))
    depth = 1 - np.exp(-d_out * mpp / 18.0)
    depth = np.where(shallow, np.minimum(depth, 0.18 + 0.5 * depth), depth)
    depth = np.maximum(depth, np.clip((Y - 160) / 300, 0, 1))
    depth = cv2.GaussianBlur(depth.astype(np.float32), (0, 0), 3) * W
    sds = cv2.GaussianBlur(sd.astype(np.float32), (0, 0), 3)
    gxs, gys = cv2.Sobel(sds, cv2.CV_32F, 1, 0), cv2.Sobel(sds, cv2.CV_32F, 0, 1)
    nX = gxs * np.gradient(X, axis=1) + gys * np.gradient(X, axis=0)
    nY = gxs * np.gradient(Y, axis=1) + gys * np.gradient(Y, axis=0)
    k = SWELL_DIR / np.linalg.norm(SWELL_DIR)
    face = np.clip(-(nX * k[0] + nY * k[1]) / (np.sqrt(nX ** 2 + nY ** 2) + 1e-6), 0, 1)
    band = (np.abs(sd) < 10) & (yy > HORIZON + 60) & (W | land)
    exp_ = cv2.GaussianBlur(np.where(band, 0.35 + 0.65 * face, 0).astype(np.float32), (0, 0), 4)
    exp_ = np.clip(exp_ / max(np.percentile(exp_[band], 98), 1e-3), 0, 1) * (np.abs(sd) < 24)
    exp_ = cv2.GaussianBlur(exp_.astype(np.float32), (0, 0), 2) * ~(pine & ~W)

    bgr = np.dstack([np.clip(128 + 2 * sd, 0, 255), np.clip(depth, 0, 1) * 255, np.clip(cover, 0, 1) * 255])
    cv2.imwrite(os.path.join(OUT, 'sea.png'), np.round(bgr).astype(np.uint8), [cv2.IMWRITE_PNG_COMPRESSION, 9])
    half = cv2.resize(exp_, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    # G: the far mountains in the haze; at dusk and at night they take the colour of the sky behind them
    hazy = (H >= 84) & (H <= 114) & (V > 150) & (S < 150)          # the bluish haze, not the pine in front of it
    hazy = cv2.morphologyEx(hazy.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    haze = (mountains & hazy & ~W) | (cv2.dilate(mountains.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & (sky_a > 0.02) & (sky_a < 0.98))
    haze = cv2.GaussianBlur(haze.astype(np.float32), (0, 0), 1.0)
    hz = cv2.resize(haze, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    mp = np.dstack([np.clip(half * 255 + 0.5, 0, 255), np.clip(hz * 255 + 0.5, 0, 255), np.zeros_like(half)]).astype(np.uint8)
    cv2.imwrite(os.path.join(OUT, 'maps.png'), mp, [cv2.IMWRITE_PNG_COMPRESSION, 9])

    # ---- the bush, leaf by leaf; the poster
    foliage.build(im, plate, img, leafA > 0.45, np.zeros((h, w), bool), OUT, os.path.join(DBG, 'foliage.jpg'))
    poster = cv2.resize(im, (640, round(640 * h / w)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(OUT, 'poster.webp'), poster, [cv2.IMWRITE_WEBP_QUALITY, 60])
    lq = cv2.resize(im, (36, round(36 * h / w)), interpolation=cv2.INTER_AREA)
    ok, jpg = cv2.imencode('.jpg', lq, [cv2.IMWRITE_JPEG_QUALITY, 60])

    cam = dict(f=F, cx=CX, cy=CY, horizon=HORIZON, pitch=round(PITCH, 6), height=HEIGHT,
               swell=[round(float(k[0]), 4), round(float(k[1]), 4)], boat=boat_box)
    print('camera:', json.dumps(cam))
    print('lqip:', 'data:image/jpeg;base64,' + base64.b64encode(jpg.tobytes()).decode())

    # ---- review: the sea's colour beside the photo; the maps with a 5 m grid on the water
    side = np.hstack([img, np.where(W[..., None], seabed, img * 0.35)])
    cv2.imwrite(os.path.join(DBG, 'sea-colore.jpg'), np.clip(cv2.resize(side, None, fx=0.5, fy=0.5), 0, 255).astype(np.uint8))
    ov = img * 0.45
    dep = depth[..., None]
    ov = np.where(W[..., None], ov + (np.array([255, 160, 40]) * dep + np.array([40, 220, 255]) * (1 - dep)) * 0.55, ov)
    ov = ov * (1 - 0.8 * exp_[..., None]) + np.array([40, 40, 255]) * 0.8 * exp_[..., None]
    ov = ov * (1 - oa[..., None]) + np.array([255, 0, 255]) * oa[..., None]
    ov = ov * (1 - 0.7 * sky_a[..., None]) + np.array([255, 200, 120]) * 0.7 * sky_a[..., None]
    ov = np.where((leafA > 0.45)[..., None], ov * 0.4 + np.array([0, 255, 0]) * 0.6, ov)
    gl = ((np.abs(X / 5.0 - np.round(X / 5.0)) < 0.02 * np.maximum(1, Y / 60)) |
          (np.abs(Y / 5.0 - np.round(Y / 5.0)) < 0.02 * np.maximum(1, Y / 60))) & W & (Y < 400)
    ov[gl] = (255, 255, 255)
    cv2.imwrite(os.path.join(DBG, 'sea-mappe.jpg'), np.clip(cv2.resize(ov, None, fx=0.5, fy=0.5), 0, 255).astype(np.uint8))
    for f in sorted(os.listdir(OUT)):
        print('%-14s %4d KB' % (f, os.path.getsize(os.path.join(OUT, f)) // 1024))


if __name__ == '__main__':
    main()
