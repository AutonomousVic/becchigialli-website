# becchigialli-website

Il sito di Becchigialli Holding Immobiliare, sul modello di vittoriodini.it: una caletta di Paraggi che segue l'ora di chi visita, un pannello di vetro con la password e, dietro, il menu.

**Stato: anteprima (tappa 1).** Scena, luce dell'ora e schermata di sblocco. Card, meteo completo e pannello "Cambia il meteo" arrivano nella tappa 2.

| File | A cosa serve |
| :-- | :-- |
| `index.html` | La pagina: sblocco, ora, alba e tramonto, meteo, orologi delle sedi, menu |
| `scene.html` | Lo sfondo in WebGL2, caricato come iframe dietro la pagina |
| `astro.js` | Sole e luna per il luogo di chi visita |
| `img/` | La foto e le sue mappe (cielo, mare, rami, profondità) |
| `fonts/` | Cormorant Garamond e Inter Tight, ospitati sul sito (licenza OFL) |
| `tools/` | Mappe della foto, impronta della password, screenshot e video di prova |

## Anteprima in locale

```bash
python3 -m http.server 4173
```

Poi apri <http://localhost:4173>. Con `?hour=20.5` si vede un'ora a scelta.

## Rifare le mappe della foto

```bash
pip install numpy opencv-python-headless
python3 tools/maps.py      # scrive img/sky.png, img/skyfill.png, img/maps.png e i controlli in tools/out/
```

## Cambiare la password

```bash
node tools/set-password.mjs 'nuova password'
```

Nella pagina resta solo un'impronta SHA-256 con sale. La protezione è scenografica: non usare una password che usi altrove.
