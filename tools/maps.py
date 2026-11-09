"""Builds the scene maps for source/caletta.jpg.

Outputs (img/):
  sky.png      8-bit sky alpha, same size as the photo
  skyfill.png  the photo sky extended under the land and blurred (no halos, no holes)
  maps.png     RGB data map at half resolution (the fields are smooth): R disparity (0 far .. 255 near),
               G sway weight, B drift (how much of the photo's ripples travel: 1 open water, 0.5 shallow, 0 land)
  plate.webp   the photo with the foreground leaves painted out (what is behind a swaying leaf)
  leaf.png     8-bit soft matte of the foreground leaves; leafrgb.webp their colour
  poster.webp  a small copy of the photo the page shows until the scene's first frame
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


def pull_push(img, known):
    """Fills the unknown pixels with a smooth blend of the known ones around them."""
    conf = known.astype(np.float32)
    acc, wgt = img.astype(np.float32) * conf[..., None], conf
    levels = []
    while min(acc.shape[:2]) > 4:
        levels.append((acc, wgt))
        acc = cv2.resize(acc, (acc.shape[1] // 2, acc.shape[0] // 2), interpolation=cv2.INTER_AREA)
        wgt = cv2.resize(wgt, (wgt.shape[1] // 2, wgt.shape[0] // 2), interpolation=cv2.INTER_AREA)
    fill = acc / np.maximum(wgt, 1e-6)[..., None]
    for acc_l, wgt_l in reversed(levels):
        up = cv2.resize(fill, (acc_l.shape[1], acc_l.shape[0]), interpolation=cv2.INTER_LINEAR)
        a = np.clip(wgt_l * 4, 0, 1)[..., None]
        fill = (acc_l / np.maximum(wgt_l, 1e-6)[..., None]) * a + up * (1 - a)
    return fill


def fill_small_holes(mask, max_area):
    """Turns the small islands of 'not mask' inside the mask into mask."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats((~mask).astype(np.uint8), connectivity=8)
    small = np.zeros(n, bool)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] <= max_area
    return mask | small[lab]


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
    # the twigs: thin dark lines against the bright sea, hanging off the leaves
    V_local = cv2.GaussianBlur(V, (0, 0), 6)
    twigs = right_zone & (V < 0.62 * V_local) & ~bright_sea
    n, lab = cv2.connectedComponents(twigs.astype(np.uint8), connectivity=8)
    touching = np.unique(lab[cv2.dilate(fg.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & twigs])
    fg |= np.isin(lab, touching[touching > 0])

    # ---- the boom: a floating barrier crossing the bay, behind the hanging branch. It stays still
    # (no ripples drift over it) and goes on behind the leaves, so a swinging leaf uncovers it.
    B0, B1 = np.array([798.0, 623.0]), np.array([1066.0, 683.0])
    u = (B1 - B0) / np.linalg.norm(B1 - B0)
    along = (xx - B0[0]) * u[0] + (yy - B0[1]) * u[1]
    across = -(xx - B0[0]) * u[1] + (yy - B0[1]) * u[0]
    boom = (np.abs(across) <= 3.5) & (along >= -2) & (along <= np.linalg.norm(B1 - B0))
    boom_wide = (np.abs(across) <= 6.0) & (along >= -6) & (along <= np.linalg.norm(B1 - B0) + 6)
    fg &= ~(boom & ~right_zone)

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

    # Sway amplitude. The foreground branches hang from the frame: still where they enter the
    # picture, freer towards the tips. The field is widened and softened well beyond the leaves,
    # so a leaf never gets cut at the edge of its mask: a thin margin of background bends with it.
    hinge = np.minimum.reduce([np.clip((w - xx) / 260.0, 0, 1), np.clip((h - yy) / 200.0, 0, 1),
                               np.clip(xx / 180.0, 0, 1)]) ** 1.2
    fg_wide = cv2.GaussianBlur(cv2.dilate(fg.astype(np.float32), np.ones((15, 15), np.uint8)), (0, 0), 9)
    fg_wide = np.clip(fg_wide * 1.4, 0, 1)
    hill = cv2.GaussianBlur((veg & ~fg).astype(np.float32), (0, 0), 3) * 0.06
    sway = np.maximum(fg_wide * (0.15 + 0.85 * hinge), hill)
    sway = np.clip(sway, 0, 1).astype(np.float32)

    # ---- shallow water in front of the villas, where the sea floor shows through: an authored
    # outline of the waterline (photo pixels), closed through the deep water below it
    outline = np.array([(28, 845), (24, 762), (60, 736), (95, 744), (190, 744), (192, 716),
                        (232, 713), (380, 713), (386, 701), (430, 697), (470, 691), (520, 685),
                        (590, 677), (640, 664), (700, 650), (722, 641), (745, 700), (600, 800),
                        (300, 860), (120, 880), (40, 880)], np.int32)
    poly = np.zeros((h, w), np.uint8)
    cv2.fillPoly(poly, [outline], 1)
    shallow = poly.astype(bool) & ~water & ~fg

    # ---- drift: how much of the photo's own ripples may travel. All of it on open water and
    # behind the leaves that hang over it, half over the visible sea floor (the rocks stay sharp),
    # none within a few pixels of anything that is not sea: rocks, the boom, the boat, the swimmer.
    near_water = cv2.dilate(water.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    # sparkles, sprigs and dark patches the colour test left out are still sea
    deep = fill_small_holes(water | (fg & near_water) | shallow, 900) & ~shallow
    # ...but the swimmer, the boat and the buoy are not, and must not drift away with the ripples
    things = np.zeros((h, w), np.uint8)
    for (cx, cy, rx, ry) in [(243, 983, 26, 16), (1027, 442, 22, 9), (936, 486, 7, 7)]:
        cv2.ellipse(things, (cx, cy), (rx, ry), 0, 0, 360, 1, -1)
    deep &= ~(things.astype(bool) | (boom_wide & ~fg))
    barrier = ~(deep | shallow | fg)
    dist = cv2.distanceTransform((~barrier).astype(np.uint8), cv2.DIST_L2, 5)
    drift = np.where(deep, 1.0, np.where(shallow, 0.5, 0.0)) * np.clip((dist - 2.0) / 4.0, 0, 1)
    drift = cv2.GaussianBlur(drift.astype(np.float32), (0, 0), 1.5)

    # ---- plate: the photo with the foreground leaves painted out, so a leaf can sway over the
    # water and the rocks without leaving a copy of itself behind
    # The leaf layer is the photo seen through a tight soft matte (the leaves and their edge
    # pixels); the plate replaces exactly what that matte covers, plus one pixel, so at rest the
    # picture is the photo. Behind the leaves over the sea the colours come from the sea only and
    # the ripples (fine and mid scale) are borrowed from open water further along, so a leaf that
    # swings away uncovers sea, not a smooth patch.
    leaf = np.clip((fg_s - 0.04) / 0.9, 0, 1).astype(np.float32)
    # pixels that are mostly sea (matte under 0.12) keep the photo: the faint edge they carry is invisible
    hole = leaf >= 0.12
    known = ~cv2.dilate(hole.astype(np.uint8), np.ones((13, 13), np.uint8)).astype(bool)
    img = im.astype(np.float32)
    sea_fill = pull_push(img, (deep | shallow) & ~boom_wide & known)
    any_fill = pull_push(img, known)
    detail = img - cv2.GaussianBlur(img, (0, 0), 6.0)
    source = water & known & ~boom_wide & ~things.astype(bool)
    borrowed = np.zeros_like(img)
    got = np.zeros((h, w), bool)
    offsets = [(-140, 0), (-230, 0), (0, -130), (-90, -90), (0, -220), (-320, 0), (-180, 60),
               (-60, 150), (140, 0), (0, 130), (-400, -40), (-260, 120), (-120, 220), (-480, 0)]
    for (dx, dy) in offsets:
        ok = np.roll(source, (-dy, -dx), axis=(0, 1))
        if dy: ok[(slice(h - dy, h) if dy > 0 else slice(0, -dy))] = False
        if dx: ok[:, (slice(w - dx, w) if dx > 0 else slice(0, -dx))] = False
        take = hole & ~got & ok
        borrowed[take] = np.roll(detail, (-dy, -dx), axis=(0, 1))[take]
        got |= take
    rng = np.random.default_rng(7)
    for _ in range(200):                               # whatever is left: any offset that lands on sea
        if not (hole & ~got).any(): break
        dx, dy = int(rng.integers(-500, 200)), int(rng.integers(-300, 300))
        ok = np.roll(source, (-dy, -dx), axis=(0, 1))
        if dy: ok[(slice(h - dy, h) if dy > 0 else slice(0, -dy))] = False
        if dx: ok[:, (slice(w - dx, w) if dx > 0 else slice(0, -dx))] = False
        take = hole & ~got & ok
        borrowed[take] = np.roll(detail, (-dy, -dx), axis=(0, 1))[take]
        got |= take
    over_sea = hole & (right_zone | cv2.dilate(water.astype(np.uint8), np.ones((61, 61), np.uint8)).astype(bool))
    print('fill: leaf pixels over the sea without borrowed ripples:', int((over_sea & ~got).sum()))
    behind = np.where(over_sea[..., None], sea_fill + borrowed, any_fill)
    # the boom goes on behind the leaves: its cross profile, taken where it is in plain view
    seen = boom & ~hole
    prof = {}
    for k in range(-4, 5):
        sel = seen & (np.round(across) == k)
        if sel.any(): prof[k] = img[sel].mean(0)
    under = boom & hole
    for k, c in prof.items():
        sel = under & (np.round(across) == k)
        behind[sel] = c
    plate = np.clip(np.where(hole[..., None], behind, img), 0, 255)
    cv2.imwrite(os.path.join(OUT, 'plate.webp'), plate.astype(np.uint8), [cv2.IMWRITE_WEBP_QUALITY, 85])
    # The leaves' own colour, without the sea mixed into their edge pixels (photo = leaf*a + plate*(1-a)),
    # so the picture at rest is the photo and a swinging leaf carries no sea with it.
    plate_q = cv2.imread(os.path.join(OUT, 'plate.webp')).astype(np.float32)
    a = leaf[..., None]
    F = np.where(hole[..., None], np.clip((img - (1 - a) * plate_q) / np.maximum(a, 0.12), 0, 255), img)
    # outside the leaves the colour is never seen: keep it smooth so the file stays small
    F = np.where((leaf > 0.002)[..., None], F, cv2.GaussianBlur(pull_push(F, leaf > 0.002), (0, 0), 4))
    cv2.imwrite(os.path.join(OUT, 'leafrgb.webp'), F.astype(np.uint8), [cv2.IMWRITE_WEBP_QUALITY, 85])
    cv2.imwrite(os.path.join(OUT, 'leaf.png'), np.clip(leaf * 255 + 0.5, 0, 255).astype(np.uint8))

    maps = np.dstack([drift, sway, d])  # BGR order for OpenCV: B drift, G sway, R disparity
    half = cv2.resize(maps.astype(np.float32), (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(OUT, 'maps.png'), np.clip(half * 255 + 0.5, 0, 255).astype(np.uint8), [cv2.IMWRITE_PNG_COMPRESSION, 9])
    poster = cv2.resize(im, (400, round(400 * h / w)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(OUT, 'poster.webp'), poster, [cv2.IMWRITE_WEBP_QUALITY, 62])
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
    ov = ov * (1 - 0.45 * drift[..., None]) + np.array([255, 128, 0]) * 0.45 * drift[..., None]
    ov = ov * (1 - 0.6 * fg_s[..., None]) + np.array([0, 0, 255]) * 0.6 * fg_s[..., None]
    cv2.imwrite(os.path.join(DBG, 'masks.jpg'), ov.astype(np.uint8))
    cv2.imwrite(os.path.join(DBG, 'disparity.jpg'), (d * 255).astype(np.uint8))
    cv2.imwrite(os.path.join(DBG, 'sway.jpg'), (sway * 255).astype(np.uint8))
    cv2.imwrite(os.path.join(DBG, 'drift.jpg'), (drift * 255).astype(np.uint8))

    # what tools/sea.py builds on
    return dict(im=im, plate=plate, water=water, shallow=shallow, deep=deep, fg=fg, leaf=leaf, hole=hole,
                things=things.astype(bool), boom=boom, boom_wide=boom_wide, across=across, along=along,
                right_zone=right_zone, sky_a=sky_a, veg=veg)


if __name__ == '__main__':
    main()
