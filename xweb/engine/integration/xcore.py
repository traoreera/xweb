"""XwebExtension — le service xcore ext.xweb (docs/integration-xcore.md).

Contrat vérifié contre le vrai code source de xcore (`xcore/services/base.py`,
`xcore/services/extensions/loader.py`, `xcore/services/container.py:115`) :
BaseService exige init()/shutdown()/health_check()/status() en méthodes
abstraites, ExtensionLoader instancie via `cls(config=ext_config)`, et le
conteneur range le service sous la clé `f"ext.{name}"` — d'où
`xcore.services.get("ext.xweb")` dans les exemples de doc.

Import xcore optionnel avec repli local : ce module reste importable et
testable sans le paquet `xcore` réellement installé (celui-ci tire
FastAPI/SQLAlchemy/Redis/APScheduler — trop lourd pour ce que ce module a
besoin de prouver ici). Le repli reproduit EXACTEMENT le contrat lu dans
xcore/services/base.py ci-dessus ; si xcore est installé, c'est le vrai
`BaseService` qui est utilisé, pas le repli.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from ...contrib import ALL_REGISTRIES
from ...i18n import Catalog
from ..registry import QwebRegistry

try:
    from xcore.services.base import BaseService, ServiceStatus
except ImportError:
    from abc import ABC, abstractmethod
    from enum import Enum

    class ServiceStatus(str, Enum):  # type: ignore[no-redef]
        UNINITIALIZED = "uninitialized"
        INITIALIZING = "initializing"
        READY = "ready"
        DEGRADED = "degraded"
        FAILED = "failed"
        STOPPED = "stopped"

    class BaseService(ABC):  # type: ignore[no-redef]
        """Repli local — mêmes méthodes abstraites que xcore.services.base.BaseService
        (voir docstring du module). Utilisé seulement quand xcore n'est pas installé."""

        name: str = "service"

        def __init__(self) -> None:
            self._status = ServiceStatus.UNINITIALIZED

        @abstractmethod
        async def init(self) -> None: ...

        @abstractmethod
        async def shutdown(self) -> None: ...

        @abstractmethod
        async def health_check(self) -> tuple[bool, str]: ...

        @abstractmethod
        def status(self) -> dict[str, Any]: ...

        @property
        def is_ready(self) -> bool:
            return self._status == ServiceStatus.READY


class XwebExtension(BaseService):
    """Déclaré dans xcore.yaml sous services.extensions.xweb (docs/integration-xcore.md) :

        xweb:
          module: xweb.engine.integration.xcore:XwebExtension
          config:
            namespaces:
              billing: plugins/billing/templates

    `xweb/components/` (les ~30 `xweb.*` DaisyUI — `xweb.button`, `xweb.card`,
    `xweb.shell`, `xweb.pdf_document`…) est chargé automatiquement, à CHAQUE
    `init()`, sans configuration — c'est le catalogue de composants intégré
    au paquet xweb lui-même (`source_plugin="xweb-core"`), pas un dossier de
    ce projet particulier. Vécu comme un vrai écart docs/code jusqu'ici :
    `docs/integration-xcore.md` documentait déjà "vivent dans xweb/components/"
    mais le code réel les chargeait via un `directory:` pointant sur un dossier
    `components/` à la racine du projet — donc absent du paquet distribué
    (`pyproject.toml`: `packages = ["xweb"]`, rien en dehors de `xweb/` n'est
    embarqué dans le wheel). Un projet qui installe `xweb` obtient maintenant
    `xweb.shell`/`xweb.button`/etc. sans rien configurer — c'est tout le sens
    d'un SDK.

    `directory` (optionnel — ce projet ne l'utilise plus) reste disponible
    pour un dossier de templates PARTAGÉS propre à un projet donné (au-delà
    des composants xweb intégrés), scanné avec source_plugin="core" — jamais
    pour les composants xweb eux-mêmes, ils ne dépendent d'aucune config.
    Chaque entrée de `namespaces` est scannée avec source_plugin=<clé> —
    utilisé dans les messages de conflit xpath (docs/inheritance.md#conflits),
    pas pour préfixer les t-name : contrairement au Loader Jinja2 de
    microframe, QwebRegistry indexe par t-name auto-qualifié dans le fichier
    lui-même (docs/language.md#t-name), pas par chemin de fichier —
    `namespaces` ici ne fait que dire QUELS dossiers scanner, pas comment
    nommer.

    `enable_cache`/`cache_ttl` sont acceptés mais pas encore consommés —
    aucune couche de cache au-delà du cache de résolution intégré à
    QwebRegistry (docs/inheritance.md) n'existe avant que le CacheService
    de xcore soit branché (docs/integration-xcore.md#cache, pas fait).

    `locales`/`locales_dir` (docs/i18n.md) — codes supplémentaires à
    charger en plus du français source ("fr", jamais listé lui-même) et
    dossier contenant un `<code>.json` par locale. Absents → `self.i18n`
    ne connaît que le français ; `_()` devient l'identité partout, aucun
    template `t-tr` ne casse pour autant (xweb/i18n.py::Catalog dégrade
    déjà en douceur pour un fichier manquant, même sans cette section).
    """

    name = "xweb"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._config = config or {}
        self.engine: QwebRegistry | None = None
        self.i18n: Catalog | None = None
        # Secret de process, comme microframe.TemplateEngine.csrf_token
        # (docs/csrf.py) — généré ici plutôt qu'à l'appel pour qu'il soit
        # stable sur toute la durée de vie du process, pas régénéré à
        # chaque requête (ce qui invaliderait tout formulaire déjà affiché).
        self.csrf_token = secrets.token_urlsafe(32)

    async def init(self) -> None:
        self._status = ServiceStatus.INITIALIZING
        self.engine = QwebRegistry()

        # xweb/components/ — le catalogue de composants intégré au paquet
        # (voir docstring de la classe) ; toujours chargé, jamais derrière
        # une clé de config — c'est ce qui fait de xweb un SDK auto-suffisant
        # plutôt qu'un moteur nu qu'il faudrait pointer soi-même vers une
        # copie de ces fichiers.
        builtin_components = Path(__file__).resolve().parent.parent.parent / "components"
        self.engine.register_dir(builtin_components, source_plugin="xweb-core")

        directory = self._config.get("directory")
        if directory:
            self.engine.register_dir(Path(directory), source_plugin="core")

        for plugin_name, path in self._config.get("namespaces", {}).items():
            self.engine.register_dir(Path(path), source_plugin=plugin_name)

        self.i18n = Catalog(
            self._config.get("locales_dir"), list(self._config.get("locales", [])),
            source_locale=self._config.get("source_locale", "fr"),
        )

        # Résout tout maintenant — les conflits xpath (docs/inheritance.md#conflits)
        # atterrissent dans le log de boot, pas seulement sur la première page
        # qui déclenche le template concerné par hasard (registry.py::check_all).
        self.engine.check_all()

        self._status = ServiceStatus.READY if len(self.engine) > 0 else ServiceStatus.DEGRADED

    async def shutdown(self) -> None:
        self._status = ServiceStatus.STOPPED

    async def health_check(self) -> tuple[bool, str]:
        if self.engine is None:
            return False, "not initialized"
        return self.is_ready, f"{len(self.engine)} templates" if self.is_ready else str(self._status)

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self._status.value,
            "templates": len(self.engine) if self.engine is not None else 0,
        }


def bind_hot_reload(xcore: Any, extension: "XwebExtension") -> None:
    """S'abonne une fois à plugin.*.unloaded (docs/spec-v1.md §3,
    xcore/kernel/runtime/supervisor.py:323-327 + EventBus wildcards via
    fnmatch) pour nettoyer QwebRegistry et les 4 registres de
    contribution quand un plugin est déchargé/rechargé.

    Correction par rapport à ce que spec-v1.md affirmait avant ce test :
    ext.xweb ne peut PAS faire ça lui-même dans son propre init() —
    ExtensionLoader._load() instancie une extension avec seulement
    `config`, jamais le KernelContext/EventBus (xcore/services/extensions/
    loader.py:75, vérifié). Point de câblage réel : après xcore.boot(app),
    côté app — même endroit que bind_engine()/register_action_routes()
    pour microframe (docs/integration-xcore.md).

        await xcore.boot(app)
        bind_hot_reload(xcore, xcore.services.get("ext.xweb"))
    """

    async def _on_unloaded(event: Any) -> None:
        # supervisor.py émet plugin.{name}.unloaded avec un payload
        # TOUJOURS vide (xcore/kernel/runtime/supervisor.py:327,
        # `await self._events.emit(f"plugin.{plugin_name}.unloaded", {})`)
        # — le nom du plugin ne peut venir que d'event.name, jamais
        # d'event.data (vérifié dans EventBus.emit(), pas supposé).
        parts = (getattr(event, "name", "") or "").split(".")
        if len(parts) != 3:
            return
        plugin_name = parts[1]
        if extension.engine is not None:
            extension.engine.unregister_plugin(plugin_name)
        for registry in ALL_REGISTRIES:
            registry.unregister_plugin(plugin_name)

    xcore.events.subscribe("plugin.*.unloaded", _on_unloaded)
