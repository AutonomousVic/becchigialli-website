# becchigialli-website

Il sito di Becchigialli Holding Immobiliare, sul modello di vittoriodini.it: una caletta di Paraggi che segue l'ora di chi visita, un pannello di vetro con la password e, dietro, il menu.

**Stato: anteprima.** Scena, luce dell'ora, "Cambia il meteo" (ora, vento, movimento), sblocco e menu con contenuti di riempimento.

| File | A cosa serve |
| :-- | :-- |
| `index.html` | La pagina: sblocco, ora, alba e tramonto, meteo, menu e card |
| `scene.html` | Lo sfondo in WebGL2, caricato come iframe dietro la pagina |
| `astro.js` | Sole e luna per il luogo di chi visita |
| `content.json` | I testi del menu e delle card |
| `img/` | La foto e le sue mappe (vedi sotto) |
| `fonts/` | Cormorant Garamond e Inter Tight, ospitati sul sito (licenza OFL) |
| `_headers` | Per Cloudflare Pages: font e immagini restano in cache nel browser |
| `source/` | La foto originale, da cui `tools/maps.py` ricava `img/` |
| `tools/` | Mappe della foto, file unico, impronta della password, screenshot e video di prova |

Le immagini in `img/`:

| File | Cosa contiene |
| :-- | :-- |
| `plate.webp` | La foto, con i rami in primo piano tolti e il mare ricostruito dietro |
| `leafrgb.webp`, `leaf.png` | I rami in primo piano: colore e trasparenza |
| `maps.png` | A metà risoluzione: profondità (R), quanto si muovono i rami (G), quanto ogni scoglio prende l'onda (B) |
| `sky.png`, `skyfill.png` | Dove c'è cielo, e il cielo da mettere dietro le colline |
| `poster.webp` | Una copia leggera della foto, mostrata finché la scena non è pronta |
| `seabed.webp` | Il colore del mare senza increspature: fondale, zone, profondità. Sopra si disegna la superficie |
| `sea.png` | Dove c'è acqua (R), profondità (G), distanza dalla riva (B) |
| `objects.webp` | Nuotatore, barca, boa e cima gialla, ritagliati per galleggiare |

## Anteprima in locale

```bash
python3 -m http.server 4173
```

Poi apri <http://localhost:4173>. Con `?hour=20.5` si vede un'ora a scelta. Su `scene.html` si possono usare anche `?wind=8` (m/s) e `?motion=0.5` (quanto si muove la scena, 1 = normale).

## Il movimento

La camera è ferma e la costa resta la foto. Il mare è ricostruito: il colore è quello della foto senza increspature (`seabed.webp`), e sopra c'è una superficie simulata a ogni fotogramma. Due piccole texture d'onde sommano ciascuna 24 onde con la loro velocità fisica, quindi il disegno non si ripete mai; più un'onda lunga di risacca. La superficie riflette il cielo dell'ora, il sole e la luna (la scia si forma da sola), sposta il fondale dove l'acqua è bassa e ci posa le reti di luce. La prospettiva viene da una camera ricavata dalla foto (`tools/sea.py`): circa 29 m sopra l'acqua. Il vento regola quanto il mare è mosso, "Movimento" quanto in fretta va. I rami oscillano interi. La scena usa i pixel della foto, mai più di quelli dello schermo, e gira a 30 fotogrammi al secondo sul telefono e a 60 altrove. Con "riduci movimento" attivo nel sistema, la scena sta ferma.

## Rifare le mappe della foto

```bash
pip install numpy opencv-python-headless
python3 tools/sea.py       # rifà anche le mappe di tools/maps.py; legge source/caletta.jpg, scrive img/ e i controlli in tools/out/
```

## Il file unico

```bash
node tools/bundle.mjs                 # dist/becchigialli-single.html, si apre ovunque
node tools/bundle.mjs --fragment      # senza doctype/head/body, per chi incornicia la pagina (es. un artifact)
```

Font e immagini diventano dati dentro la pagina. La scena va in fondo al file e parte quando il pannello è già disegnato: la password funziona subito, anche su una rete lenta.

## Pubblicare su Cloudflare Pages

Carica la cartella con `index.html`, `scene.html`, `astro.js`, `content.json`, `img/`, `fonts/` e `_headers`. Il file `_headers` deve stare nella radice, accanto a `index.html`.

## Cambiare la password

```bash
node tools/set-password.mjs 'nuova password'
```

Nella pagina resta solo un'impronta SHA-256 con sale. La protezione è scenografica: non usare una password che usi altrove.
