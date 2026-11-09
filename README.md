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
| `maps.png` | A metà risoluzione: profondità (R), quanto si muovono i rami (G), quanto scorre il mare (B) |
| `sky.png`, `skyfill.png` | Dove c'è cielo, e il cielo da mettere dietro le colline |
| `poster.webp` | Una copia leggera della foto, mostrata finché la scena non è pronta |

## Anteprima in locale

```bash
python3 -m http.server 4173
```

Poi apri <http://localhost:4173>. Con `?hour=20.5` si vede un'ora a scelta. Su `scene.html` si possono usare anche `?wind=8` (m/s) e `?motion=0.5` (quanto si muove la scena, 1 = normale).

## Il movimento

La camera è ferma. Si muovono solo le increspature del mare e i rami in primo piano, piano, con il vento. Il mare scorre usando le increspature della foto stessa e non ripete mai lo stesso ciclo, quindi non pulsa. I rami oscillano interi. Le luci della notte sono disegnate una volta e restano ferme. La scena usa i pixel della foto, mai più di quelli dello schermo, e gira a 30 fotogrammi al secondo sul telefono e a 60 altrove. Se il dispositivo fatica, scende da sola. Con "riduci movimento" attivo nel sistema, la scena sta ferma.

## Rifare le mappe della foto

```bash
pip install numpy opencv-python-headless
python3 tools/maps.py      # legge source/caletta.jpg, scrive img/ e i controlli in tools/out/
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
