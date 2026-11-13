"""Builds the foreground branches and leaves the scene draws from scratch (step 4 of the new scene).

Nothing of the photo's leaves is moved any more: the scene draws every leaf itself, as an object,
on a skeleton that follows the photo's own branches. This script finds that skeleton and lays out
the leaves; their colour is taken from the photo where each one sits, so the light (sun, shade,
backlight) stays where the photo has it.

  skeleton  the foliage mask (tools/maps.py), measured from where each plant enters the frame
            (geodesic distance, inside the mask); every 22 px of that distance a band, every piece
            of a band a node, hung on the piece of the band before it. A node turns about its pivot
            (where it meets its parent) and carries everything beyond it: the branch bends at its
            joints, the tips move most.
  leaves    laid on a jittered grid inside the mask, two layers for the depth of a real canopy,
            each attached to its node; oak leaves (lobed) on the branch on the right, plain ones on
            the bushes along the bottom, softer where the photo is out of focus there.
  twigs     on the branch on the right, the segments of the skeleton, thin and dark.

Output: img/rig.json and img/leaftex.webp (the photo's leaves, carried over the bushes' soft rim). Review image: tools/out/foliage.jpg (the leaves drawn still, over the plate).
"""
import os, json, base64
from collections import deque
import cv2
import numpy as np
import maps

OUT, DBG = maps.OUT, maps.DBG
BAND = 22


def geodesic(mask, roots):
    """Distance inside mask from the root pixels, in px (breadth first; diagonal steps cost 1.414)."""
    h, w = mask.shape
    D = np.full(h * w, np.inf, np.float32)
    m = mask.ravel()
    q = deque()
    for i in np.flatnonzero(roots.ravel()):
        D[i] = 0; q.append(i)
    steps = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0), (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
    while q:                                   # a label-correcting search: good enough for bands of 22 px
        i = q.popleft(); y, x = divmod(i, w); d = D[i]
        for dy, dx, c in steps:
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w:
                j = yy * w + xx
                if m[j] and d + c < D[j] - 1e-3:
                    D[j] = d + c; q.append(j)
    return D.reshape(h, w)


def main():
    # maps.py's masks only: its images in img/ are left as they are (sea.py has rewritten maps.png)
    real = cv2.imwrite
    cv2.imwrite = lambda path, *a, **k: True if os.path.dirname(os.path.abspath(path)) == os.path.abspath(OUT) else real(path, *a, **k)
    try:
        M = maps.main()
    finally:
        cv2.imwrite = real
    im, plate, leafA = M['im'], M['plate'], M['leaf']
    h, w = leafA.shape
    yy, xx = np.mgrid[0:h, 0:w]
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV).astype(np.float32)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    # the leaves only: the matte, without the water and the rock it took in along its edges
    waterish = (H >= 72) & (H <= 115) & (S > 30)
    # only where the photo shows plant: green-yellow, or dark (shade, twigs); never the sea the
    # old matte took in along the bushes
    plant = ((H < 70) & (S > 40)) | (V < 55)
    branch = (xx > 790) & (yy < 1010)          # the branch on the right: its matte is right as it is
    mask = (leafA > 0.45) & np.where(branch, ~((H >= 79) & (H <= 112) & (S > 45) & (V > 70)), plant & ~waterish)
    opened = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)).astype(bool)
    mask = np.where(branch, mask, opened)
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)).astype(bool)
    F = cv2.imread(os.path.join(OUT, 'leafrgb.webp')).astype(np.float32)
    build(im, plate, F, mask, branch, OUT, os.path.join(DBG, 'foliage.jpg'))


def build(im, plate, F, mask, branch, out_dir, review):
    """Skeleton, leaves and rig for one photo. im/plate: the photo and the photo without its foliage;
    F: the foliage's own colour; mask: where the foliage is; branch: where it is a hanging branch
    (oak leaves, twigs) rather than a bush; writes rig.json and leaftex.webp to out_dir."""
    h, w = mask.shape
    yy, xx = np.mgrid[0:h, 0:w]
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    edge = np.zeros_like(mask)
    edge[:, :2] = edge[:, -2:] = edge[-2:, :] = True
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] > 80 and (edge & (lab == i)).any(): keep[i] = True
    mask = keep[lab]
    roots = mask & edge
    D = geodesic(mask, roots)
    D[~mask] = np.inf
    print('foliage px', int(mask.sum()), 'max distance', float(D[np.isfinite(D)].max()))

    # ---- skeleton: bands of distance, pieces of bands, each hung on the piece before it
    band = np.where(mask, np.floor(D / BAND), -1).astype(np.int32)
    node_lab = np.full((h, w), -1, np.int32)
    nodes = []
    for b in range(int(band.max()) + 1):
        nb, lb = cv2.connectedComponents((band == b).astype(np.uint8), connectivity=8)
        for j in range(1, nb):
            sel = lb == j
            if sel.sum() < 6 and b > 0:
                continue
            idx = len(nodes)
            node_lab[sel] = idx
            ys, xs = np.nonzero(sel)
            d = D[ys, xs]
            entry = d <= d.min() + 3
            parent = -1
            if b > 0:
                ring = cv2.dilate(sel.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & (band == b - 1)
                cand = node_lab[ring]
                cand = cand[cand >= 0]
                if len(cand): parent = int(np.bincount(cand).argmax())
            nodes.append(dict(px=float(xs[entry].mean()), py=float(ys[entry].mean()), parent=parent, band=b,
                              area=int(sel.sum()), cx=float(xs.mean()), cy=float(ys.mean())))
    # small pieces left out of a band join the node next to them
    miss = mask & (node_lab < 0)
    if miss.any():
        k = np.ones((5, 5), np.uint8)
        for _ in range(6):
            grown = cv2.dilate((node_lab + 1).astype(np.float32), k) - 1
            node_lab = np.where(miss & (node_lab < 0), grown.astype(np.int32), node_lab)
    # orphans (a piece whose parent band was too small) hang on the nearest earlier node
    P = np.array([[nd['px'], nd['py']] for nd in nodes])
    for i, nd in enumerate(nodes):
        if nd['parent'] < 0 and nd['band'] > 0:
            earlier = [j for j, o in enumerate(nodes) if o['band'] < nd['band']]
            dd = np.hypot(P[earlier, 0] - nd['px'], P[earlier, 1] - nd['py'])
            nd['parent'] = earlier[int(dd.argmin())]
    # how much each node carries (its whole subtree): big limbs are slow and stiff, twigs quick
    mass = np.array([nd['area'] for nd in nodes], np.float64)
    for i in sorted(range(len(nodes)), key=lambda i: -nodes[i]['band']):
        p = nodes[i]['parent']
        if p >= 0: mass[p] += mass[i]
    rng = np.random.default_rng(5)
    total = mass.max()
    for i, nd in enumerate(nodes):
        f = np.sqrt(mass[i] / total)
        nd['freq'] = float(0.32 + 1.3 * (1 - f) ** 1.5 + 0.08 * rng.random())       # Hz
        nd['amp'] = float(0.0022 + 0.010 * (1 - f) ** 2)                           # rad at the reference wind
        nd['phase'] = float(rng.random() * 6.2832)
    print('nodes', len(nodes))

    # ---- leaves. Their colour: the photo's leaves where they are surely leaves, carried outwards
    # over the soft, out-of-focus rim (where the photo shows as much sea as leaf), so a leaf at the
    # edge of a bush is green, not the colour of the water behind it
    # the bushes, as the branch: each leaf carries the photo's leaves where it sits. Around the bushes
    # the photo is out of focus and half sea: there the texture holds the plant's colour, carried out
    # from the plant, so a leaf at the rim never shows the water
    T = F.copy()
    bush = ~branch
    T = np.where((bush & ~mask)[..., None], maps.pull_push(F, mask), T)
    cv2.imwrite(os.path.join(out_dir, 'leaftex.webp'), np.clip(T, 0, 255).astype(np.uint8), [cv2.IMWRITE_WEBP_QUALITY, 85])
    F = T
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
    sharp = np.sqrt(cv2.GaussianBlur(cv2.Laplacian(g, cv2.CV_32F) ** 2, (0, 0), 10))
    right = mask & branch
    leaves = []
    for layer, (cell, jit) in enumerate([(7.0, 0.9), (8.5, 0.9), (9.5, 1.0)]):
        for cy in np.arange(cell / 2, h, cell):
            for cx in np.arange(cell / 2, w, cell):
                x = cx + (rng.random() - 0.5) * cell * jit + layer * 3.1
                y = cy + (rng.random() - 0.5) * cell * jit + layer * 2.3
                xi, yi = int(round(x)), int(round(y))
                if not (0 <= xi < w and 0 <= yi < h) or not mask[yi, xi]: continue
                oak = bool(right[yi, xi])
                if layer == 2 and oak: continue              # the third layer only thickens the bushes
                L = (13.0 if oak else 21.0) * (0.75 + 0.5 * rng.random()) * (1.0 if layer == 0 else 0.85)
                nd_i = int(node_lab[yi, xi])
                if nd_i < 0: continue
                nd = nodes[nd_i]
                # pointing away from where the branch comes from, drooping a little, varied
                ang = np.arctan2(y - nd['py'], x - nd['px']) + rng.normal(0, 0.9)
                ang = ang + 0.25 * np.sin(ang) * (1 if oak else 0)
                r = max(1, int(L * 0.35))
                y0, y1, x0, x1 = max(0, yi - r), min(h, yi + r + 1), max(0, xi - r), min(w, xi + r + 1)
                sub = mask[y0:y1, x0:x1]
                col = F[y0:y1, x0:x1][sub].mean(0) if sub.any() else F[yi, xi]
                col = col * (0.94 + 0.12 * rng.random()) * (0.92 if layer == 0 else 1.0)   # the lower layer a touch darker
                s_loc = sharp[yi, xi]
                soft = float(np.clip(2.0 - s_loc / 50.0, 0.6, 1.7))
                leaves.append((nd_i, x - nd['px'], y - nd['py'], L, ang, col[2], col[1], col[0], soft,
                               1 if oak else 0, rng.random()))
    print('leaves', len(leaves))

    # ---- twigs: the skeleton of the branch on the right, thin and dark
    twigs = []
    for i, nd in enumerate(nodes):
        p = nd['parent']
        if p < 0 or not branch[min(h - 1, int(nd['py'])), min(w - 1, int(nd['px']))]: continue
        width = float(np.clip(0.6 + 2.2 * np.sqrt(mass[i] / total) ** 0.7, 0.6, 3.0))
        twigs.append((i, p, width))
    print('twigs', len(twigs))

    # ---- pack: nodes as plain numbers, leaves as one base64 block of uint16/uint8
    order = sorted(range(len(nodes)), key=lambda i: nodes[i]['band'])
    assert all(nodes[i]['parent'] < 0 or order.index(nodes[i]['parent']) < order.index(i) for i in order[:50])
    lv = bytearray()
    for (nd_i, dx, dy, L, ang, r, gch, b, soft, kind, seed) in leaves:
        lv += np.array([nd_i, int(round((dx + 512) * 32)), int(round((dy + 512) * 32))], np.uint16).tobytes()
        lv += np.array([int(round(L * 8)), int(round((ang % (2 * np.pi)) / (2 * np.pi) * 255)), int(np.clip(r, 0, 255)),
                        int(np.clip(gch, 0, 255)), int(np.clip(b, 0, 255)), int(round(soft * 50)), kind * 128 + int(seed * 127)],
                       np.uint8).tobytes()
    rig = dict(
        note='nodes: [pivot x, pivot y (photo px), parent (-1 root), freq Hz, amp rad, phase]; leaves: base64, 13 bytes each: '
             'node u16, (dx+512)*32 u16, (dy+512)*32 u16, length*8 u8, angle/2pi*255 u8, r g b (sRGB) u8, softness*50 u8, '
             'oak*128+seed*127 u8; twigs: [node, parent, width px]',
        nodes=[[round(nd['px'], 2), round(nd['py'], 2), nd['parent'], round(nd['freq'], 3), round(nd['amp'], 5), round(nd['phase'], 3)] for nd in nodes],
        leaves=base64.b64encode(bytes(lv)).decode(), count=len(leaves),
        twigs=[[a, b, round(c, 2)] for (a, b, c) in twigs])
    with open(os.path.join(out_dir, 'rig.json'), 'w') as fh:
        json.dump(rig, fh, separators=(',', ':'))
    print('rig.json', os.path.getsize(os.path.join(out_dir, 'rig.json')) // 1024, 'KB')

    # ---- review: the leaves drawn still over the plate (ellipses, their colour)
    rev = plate.astype(np.uint8).copy()
    for i, p, wd in twigs:
        a, b = nodes[i], nodes[p]
        cv2.line(rev, (int(a['px']), int(a['py'])), (int(b['px']), int(b['py'])), (30, 35, 40), max(1, int(round(wd))), cv2.LINE_AA)
    for (nd_i, dx, dy, L, ang, r, gch, b, soft, kind, seed) in leaves:
        nd = nodes[nd_i]
        c = (int(nd['px'] + dx), int(nd['py'] + dy))
        cv2.ellipse(rev, c, (max(1, int(L / 2)), max(1, int(L * 0.3))), float(np.degrees(ang)), 0, 360,
                    (int(b), int(gch), int(r)), -1, cv2.LINE_AA)
    cv2.imwrite(review, np.hstack([im, rev]), [cv2.IMWRITE_JPEG_QUALITY, 90])


if __name__ == '__main__':
    main()
