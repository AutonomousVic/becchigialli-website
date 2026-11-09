"""Builds the data the rebuilt sea is drawn from (step 1 of the new sea).

The sea is drawn in two layers: the colour of the water body, which is the photo's own sea with
its ripples and glints taken out (the floor, the turquoise shallows, the dark seagrass, the blue
of the open sea), and a simulated surface over it. This script makes the first layer and the maps
the surface needs. It runs tools/maps.py first and builds on its masks.

Outputs (img/):
  seabed.webp   the sea without ripples, sparkles or objects; extended smoothly over the land so
                a refracted lookup near the shore never picks up a rock
  sea.png       RGB data map, full resolution:
                  R  water coverage (1 water, soft one-pixel edge; water goes on under the leaves)
                  G  depth, 0 at the waterline .. 1 open sea
                  B  signed distance to the shore, 128 + 2*px (water side positive), -64..+63 px
  maps.png      (written by maps.py) its B channel becomes how exposed each stretch of shore is
                to the swell, 0..1
  objects.webp  the swimmer, the boat, the buoy and the boom, cut out (RGBA), to float on the water
Review images go to tools/out/sea-*.jpg. The camera found from the photo is printed: it goes into
SCENE.camera in scene.html.
"""
import os, json
import cv2
import numpy as np
import maps

ROOT = maps.ROOT
OUT, DBG = maps.OUT, maps.DBG

# ---- the camera, from the photo: a level horizon at row 373, the principal point at the centre,
# a phone's lens (a 49.6 deg horizontal field on the 1086 px width), and the height that makes the
# swimmer (~35 px, about 1.7 m) and the boat (~25 px, ~10 m) the right size at their distances.
F = 1170.0
CX, CY = 543.0, 600.0
HORIZON = maps.SHORE_Y
PITCH = np.arctan((CY - HORIZON) / F)
HEIGHT = 29.0                   # metres above the water
SWELL_DIR = np.array([-0.95, 0.3])  # where the swell travels on the water plane (x right, y away from the camera):
                                    # in from the mouth of the cove on the right, along the villas, onto the cliff


def ground(x, y):
    """Photo pixel -> point on the water plane (metres: x right, y away from the camera); nan above the horizon."""
    u, v = (x - CX) / F, (y - CY) / F
    down = v * np.cos(PITCH) + np.sin(PITCH)
    fwd = np.cos(PITCH) - v * np.sin(PITCH)
    t = np.where(down > 1e-4, HEIGHT / np.maximum(down, 1e-4), np.nan)
    return u * t, fwd * t


def norm_blur(img, mask, sigma):
    """Gaussian blur of img over mask only (normalised convolution): nothing bleeds in from outside."""
    m = mask.astype(np.float32)
    num = cv2.GaussianBlur(img * m[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(m, (0, 0), sigma)
    return num / np.maximum(den, 1e-4)[..., None], den


def main():
    M = maps.main()
    im, plate = M['im'].astype(np.float32), M['plate'].astype(np.float32)
    h, w = im.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    # ---- where the new water is drawn: open sea, the shallows, and the sea under the leaves
    W = M['deep'] | M['shallow'] | M['things'] | M['boom_wide'] & ~M['fg']
    under_leaves = M['hole'] & (M['right_zone'] | cv2.dilate(M['water'].astype(np.uint8), np.ones((61, 61), np.uint8)).astype(bool))
    W |= under_leaves & (yy > HORIZON + 4)
    # below the waterline the leaves along the bottom only ever hide sea
    W |= M['hole'] & (yy > 880)
    W = maps.fill_small_holes(W, 900)
    W &= yy > HORIZON
    W = cv2.morphologyEx(W.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    W = maps.largest_touching(W, [(600, 900), (1050, 420), (500, 1100), (950, 700)])
    grey = cv2.cvtColor(M['im'], cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    cover = maps.guided(grey, W.astype(np.float32), 2, 1e-3)
    cover = np.where(cv2.dilate(W.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool), cover, 0)

    # ---- the objects that float: cut out of the photo, and taken out of the sea under them
    objs = []
    hsv = cv2.cvtColor(M['im'], cv2.COLOR_BGR2HSV).astype(np.float32)
    Hh, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    sea_hue = (Hh >= 79) & (Hh <= 112) & (S > 40)
    obj_alpha = np.zeros((h, w), np.float32)
    for name, (cx, cy, rx, ry) in [('nuotatore', (243, 983, 26, 16)), ('barca', (1027, 442, 22, 9)), ('boa', (936, 486, 7, 7))]:
        e = np.zeros((h, w), np.uint8)
        cv2.ellipse(e, (cx, cy), (rx, ry), 0, 0, 360, 1, -1)
        e = e.astype(bool)
        # red (costume, buoy) or skin, or white and much brighter than the sea around (hull, splash)
        local = cv2.GaussianBlur(V, (0, 0), 6)
        warm = ((Hh < 25) | (Hh > 155)) & (S > 60) & (V > 60)
        white = (V > local * 1.25) & (S < 110)
        a = (e & (warm | white)).astype(np.float32)
        a = cv2.morphologyEx(a, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        a = cv2.GaussianBlur(a, (0, 0), 0.7) * e
        obj_alpha = np.maximum(obj_alpha, a)
        ys, xs = np.nonzero(a > 0.05)
        objs.append(dict(name=name, box=[int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
                         anchor=[float((xs * a[ys, xs]).sum() / a[ys, xs].sum()), float(ys.max())]))
    # the boom: its own strip, the part behind the leaves comes from the plate
    strip = (np.abs(M['across']) <= 4.5) & (M['along'] >= -2) & (M['along'] <= np.linalg.norm([1066 - 798, 683 - 623]))
    ph0 = cv2.cvtColor(np.clip(plate, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    yellow = (ph0[..., 0] >= 8) & (ph0[..., 0] <= 38) & (ph0[..., 1] > 70)
    boom_a = (strip & (yellow | (M["hole"] & (np.abs(M["across"]) <= 1.6)))).astype(np.float32)
    boom_a = cv2.morphologyEx(boom_a, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    boom_a = cv2.GaussianBlur(boom_a, (0, 0), 0.6) * strip
    # behind the leaves the photo never showed it: give it the colour of the part in plain view,
    # row by row across its width
    obj_rgb = plate.copy()
    seen = strip & yellow & ~M['hole']
    hid = strip & M["hole"] & (np.abs(M["across"]) <= 1.6)
    for k_ in range(-1, 2):
        rows = np.abs(M['across'] - k_) < 0.5
        if (seen & rows).any(): obj_rgb[hid & rows] = plate[seen & rows].mean(0)
    obj_alpha = np.maximum(obj_alpha, boom_a)
    ys, xs = np.nonzero(boom_a > 0.05)
    objs.append(dict(name='cima', box=[int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
                     a=[798.0, 623.0], b=[1066.0, 683.0]))

    # ---- the water body: the sea with its ripples, sparkles and objects taken out.
    # Sparkles first (a small median), then a blur as wide as the ripples look at that distance:
    # wide at the bottom, fine towards the horizon; narrower over the visible sea floor so the
    # rocks under the water keep their shape.
    gx, gy = ground(CX * np.ones(h, np.float32), np.arange(h, dtype=np.float32))
    dY = np.abs(np.gradient(gy))                       # metres of sea per photo row, along the middle
    period = 0.45 / np.maximum(dY, 1e-4)               # a ~45 cm ripple, in rows
    sig_row = np.clip(period * 0.6, 1.0, 4.0)
    sig_row = np.where(np.isfinite(sig_row), sig_row, 1.0)
    sig = np.repeat(sig_row[:, None], w, 1)
    sig = np.where(M['shallow'], np.minimum(sig, 1.8), sig)
    sig = cv2.GaussianBlur(sig.astype(np.float32), (0, 0), 8)

    src = cv2.medianBlur(np.clip(plate, 0, 255).astype(np.uint8), 5).astype(np.float32)
    clean = W & ~(obj_alpha > 0.02) & ~cv2.dilate((obj_alpha > 0.02).astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    # what is left of the old leaves in the water (faint edges, thin sprigs): green or yellow over
    # open water, where only the floor in the shallows may be that colour
    ph = cv2.cvtColor(np.clip(plate, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    leafy = W & ~M['shallow'] & (yy > 700) & ((ph[..., 0] < 76) | (ph[..., 1] < 35))
    leafy |= W & (M['leaf'] > 0.01)
    clean &= ~cv2.dilate(leafy.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
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
    # over the land: the nearest sea, smoothly, for refracted lookups that step over the edge
    seabed = np.where(W[..., None], seabed, maps.pull_push(seabed, W))
    cv2.imwrite(os.path.join(OUT, 'seabed.webp'), np.clip(seabed, 0, 255).astype(np.uint8), [cv2.IMWRITE_WEBP_QUALITY, 88])

    # ---- objects image: their own colours, transparent elsewhere
    oa = np.clip(obj_alpha, 0, 1)
    rgba = np.dstack([np.clip(obj_rgb, 0, 255), oa * 255]).astype(np.uint8)
    rgba[oa < 0.004] = 0
    cv2.imwrite(os.path.join(OUT, 'objects.webp'), rgba, [cv2.IMWRITE_WEBP_QUALITY, 90])

    # ---- shore: signed distance to the land, in photo pixels (water positive). The image edges,
    # the leaves and the far coast at the horizon are not shore.
    land = ~W & (yy > HORIZON + 30)
    d_out = cv2.distanceTransform((~land).astype(np.uint8), cv2.DIST_L2, 5)  # distance to the land, from anywhere
    # water side: distance to land; land side: minus the distance to the water
    d_to_water = cv2.distanceTransform((~W).astype(np.uint8), cv2.DIST_L2, 5)
    sd = np.where(W, d_out, -d_to_water)

    # ---- depth: shallow along the shore, deeper away from it (in metres on the water, so the
    # far shore does not look deep just because it is small), the visible floor kept shallow,
    # the open sea past the cove deep
    X, Y = ground(xx, yy)
    X = np.nan_to_num(X, nan=0.0); Y = np.nan_to_num(Y, nan=5000.0)
    # metres to the nearest land, approximated by pixels times the local metres per pixel
    mpp = np.sqrt(np.abs(np.gradient(X, axis=1)) * np.abs(np.gradient(Y, axis=0)))
    metres = d_out * mpp
    depth = 1 - np.exp(-metres / 18.0)
    depth = np.where(M['shallow'], np.minimum(depth, 0.18 + 0.5 * depth), depth)
    depth = np.maximum(depth, np.clip((Y - 160) / 300, 0, 1))
    depth = cv2.GaussianBlur(depth.astype(np.float32), (0, 0), 3) * W

    # ---- exposure: the shore faces the swell (its normal against the swell's travel), measured on
    # the water plane, carried a little way out into the water
    gxs = cv2.Sobel(cv2.GaussianBlur(sd.astype(np.float32), (0, 0), 3), cv2.CV_32F, 1, 0)
    gys = cv2.Sobel(cv2.GaussianBlur(sd.astype(np.float32), (0, 0), 3), cv2.CV_32F, 0, 1)
    # image gradient -> direction on the plane: through the local Jacobian of ground()
    dXdx, dXdy = np.gradient(X, axis=1), np.gradient(X, axis=0)
    dYdx, dYdy = np.gradient(Y, axis=1), np.gradient(Y, axis=0)
    nX = gxs * dXdx + gys * dXdy
    nY = gxs * dYdx + gys * dYdy
    nn = np.sqrt(nX ** 2 + nY ** 2) + 1e-6
    k = SWELL_DIR / np.linalg.norm(SWELL_DIR)
    face = np.clip(-(nX * k[0] + nY * k[1]) / nn, 0, 1)    # the normal points into the water
    band = (np.abs(sd) < 10) & (yy > HORIZON + 60)
    # every rock gets a little (the swell bends into the cove), the ones facing it the most
    exp_ = np.where(band, 0.35 + 0.65 * face, 0).astype(np.float32)
    exp_ = cv2.GaussianBlur(exp_, (0, 0), 4)
    exp_ = exp_ / max(np.percentile(exp_[band], 98), 1e-3)
    exp_ = np.clip(exp_, 0, 1) * (np.abs(sd) < 24)
    exp_ = cv2.GaussianBlur(exp_.astype(np.float32), (0, 0), 2)

    # RGB only: a browser may premultiply a PNG's alpha and lose the colour where alpha is 0
    bgr = np.dstack([np.clip(128 + 2 * sd, 0, 255), np.clip(depth, 0, 1) * 255, np.clip(cover, 0, 1) * 255])
    cv2.imwrite(os.path.join(OUT, 'sea.png'), np.round(bgr).astype(np.uint8), [cv2.IMWRITE_PNG_COMPRESSION, 9])
    # the exposure is smooth: it takes the drift's place in maps.png (half resolution, B)
    mp = cv2.imread(os.path.join(OUT, 'maps.png'))
    mp[..., 0] = np.clip(cv2.resize(exp_.astype(np.float32), (mp.shape[1], mp.shape[0]), interpolation=cv2.INTER_AREA) * 255 + 0.5, 0, 255).astype(np.uint8)
    cv2.imwrite(os.path.join(OUT, 'maps.png'), mp, [cv2.IMWRITE_PNG_COMPRESSION, 9])

    cam = dict(f=F, cx=CX, cy=CY, horizon=HORIZON, pitch=float(PITCH), height=HEIGHT, swell=[float(k[0]), float(k[1])],
               objects=objs)
    with open(os.path.join(DBG, 'sea-camera.json'), 'w') as fh:
        json.dump(cam, fh, indent=1)
    print('camera:', json.dumps({k_: v for k_, v in cam.items() if k_ != 'objects'}))
    print('objects:', json.dumps(objs))

    # ---- review images
    photo = M['im'].astype(np.float32)
    side = np.hstack([photo, np.where(W[..., None], seabed, photo * 0.35)])
    cv2.imwrite(os.path.join(DBG, 'sea-colore.jpg'), np.clip(side, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92])
    # depth (blue deep, yellow shallow), shore band, exposure (red), objects (magenta), a 5 m grid
    ov = photo * 0.45
    dep = depth[..., None]
    ov = np.where(W[..., None], ov + (np.array([255, 160, 40]) * dep + np.array([40, 220, 255]) * (1 - dep)) * 0.55, ov)
    ov = ov * (1 - 0.8 * exp_[..., None]) + np.array([40, 40, 255]) * 0.8 * exp_[..., None]
    ov = ov * (1 - oa[..., None]) + np.array([255, 0, 255]) * oa[..., None]
    gl = ((np.abs((X / 5.0) - np.round(X / 5.0)) < 0.02 * np.maximum(1, Y / 60)) |
          (np.abs((Y / 5.0) - np.round(Y / 5.0)) < 0.02 * np.maximum(1, Y / 60))) & W & (Y < 400)
    ov[gl] = (255, 255, 255)
    cv2.imwrite(os.path.join(DBG, 'sea-mappe.jpg'), np.clip(ov, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 90])
    for f in ['seabed.webp', 'sea.png', 'objects.webp']:
        print(f, os.path.getsize(os.path.join(OUT, f)) // 1024, 'KB')


if __name__ == '__main__':
    main()
