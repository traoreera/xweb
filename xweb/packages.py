"""XwebPackageRegistry — partage de composants entre plugins.

Porté depuis xui/packages.py, même limite assumée : sans hook kernel sur
l'ordre de chargement des plugins, aucune vérification "explicite au
boot" des dépendances déclarées (`packages:` dans plugin.yaml,
docs/spec-v1.md §2.1) n'est faite ici — get() échoue avec un message
clair au premier accès manquant plutôt qu'au boot.

À ne pas confondre avec les registres de shell.md (NavRegistry,
RibbonRegistry…) : ceci partage des *composants* (t-name qualifiés) par
package_id, pas des contributions à une région de shell.
"""

from __future__ import annotations

from typing import Any


class XwebPackageRegistry:
    def __init__(self) -> None:
        self._packages: dict[str, dict[str, Any]] = {}

    def register(self, package_id: str, plugin_name: str, exports: dict[str, Any]) -> None:
        if package_id in self._packages:
            raise ValueError(f"UI package '{package_id}' déjà déclaré")
        self._packages[package_id] = {"plugin": plugin_name, "exports": exports}

    def get(self, package_id: str, export_name: str) -> Any:
        pkg = self._packages.get(package_id)
        if pkg is None:
            raise KeyError(
                f"UI package '{package_id}' non trouvé. "
                "Vérifiez que le plugin exportateur est bien chargé "
                "(et chargé avant le consommateur)."
            )
        if export_name not in pkg["exports"]:
            raise KeyError(f"'{package_id}' n'exporte pas '{export_name}'")
        return pkg["exports"][export_name]

    def unregister_plugin(self, plugin_name: str) -> None:
        self._packages = {k: v for k, v in self._packages.items() if v["plugin"] != plugin_name}


registry = XwebPackageRegistry()
