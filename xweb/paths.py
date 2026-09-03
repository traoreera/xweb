"""Préfixe de montage des plugins — source de vérité UNIQUE : `app.plugin_prefix`
dans [integration.yaml](../integration.yaml). xcore ne donne à un plugin (ni à
xweb) aucun moyen public de connaître son propre préfixe de montage à
l'exécution — `main.py` en a déjà fait les frais une fois pour `app.name`
(voir son commentaire sur `APP_NAME` : `Xcore` n'expose que `_config`, privé,
donc la valeur y est dupliquée à la main plutôt que de dépendre d'un
attribut qui pourrait disparaître sans avertissement).

`ConfigLoader` (`xcore.configurations.loader`) est en revanche une classe
PUBLIQUE — la même que `Xcore.boot()` utilise en interne pour lire
`integration.yaml` (`xcore/__init__.py`, vérifié) — on la réutilise donc ici
plutôt que dupliquer le défaut "/plugins" à la main : si xcore change un
jour sa propre résolution (variable d'env, second fichier de config...),
cette fonction suit automatiquement au lieu de diverger silencieusement.

Résultat mis en cache (`lru_cache`) : `integration.yaml` ne change jamais
sans un redémarrage complet du process — `xcli manager start --reload` ne
recharge que les `*.py` (CLAUDE.md "i18n" documente déjà ce même piège pour
un autre fichier YAML) — donc pas de raison de relire le fichier à chaque
appel.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def plugin_prefix() -> str:
    """`/app`, `/plugins`, ou tout ce que `integration.yaml` déclare sous
    `app.plugin_prefix` — jamais un littéral codé en dur ailleurs dans le
    projet. `xcore/configurations/sections.py` défaut à `/plugin` (singulier)
    si la clé est absente ; ce module ne redéfinit PAS ce défaut, il relaie
    tel quel ce que `ConfigLoader` résout réellement, y compris ce cas."""
    from xcore.configurations.loader import ConfigLoader

    cfg = ConfigLoader.load()
    return cfg.app.plugin_prefix or "/plugins"
