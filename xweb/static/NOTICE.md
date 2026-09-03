# Assets vendorisés

Vendorisés plutôt que chargés depuis un CDN — la CSP portée depuis xui (`xweb/security.py`) est `default-src 'self'`, aucune exception cross-origin. Voir xweb Blueprint §2 pour la décision htmx/`_hyperscript` sur Alpine.js.

| Fichier | Origine | Version | Licence |
|---|---|---|---|
| `htmx.min.js` | https://unpkg.com/htmx.org | 2.0.10 | 0BSD |
| `_hyperscript.min.js` | https://unpkg.com/hyperscript.org | 0.9.93 | BSD-2-Clause |

Récupérés le 2 septembre 2026 (résolution unpkg au moment du téléchargement — la version "latest" à ce moment-là, pas volontairement choisie pour une raison précise). Aucune modification apportée aux fichiers.

Servis via `mount_builtin_assets()` (`xweb/mount.py`), montés sous `/xweb-static/` — voir `docs/plugins.md` pour le câblage complet.
