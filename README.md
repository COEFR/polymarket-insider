# polymarket-insider

Detector liviano de **dinero informado** en Polymarket para GitHub Actions.

- Mira los trades públicos (`data-api.polymarket.com`) y, cuando ve una apuesta ≥ \$500,
  revisa la wallet: antigüedad, cantidad de operaciones y valor en juego.
- Avisa a **#🕵️-polymarket-insider** si la wallet es nueva o tiene poco historial
  (puntaje ≥ 3/6). Las wallets con cientos de operaciones se descartan como profesionales.
- No opera nada y no usa claves privadas.

Estado: `vistos.json` (el workflow lo commitea para no repetir avisos).
