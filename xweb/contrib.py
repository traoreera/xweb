"""Registres de contribution au shell (docs/shell.md) — généralisation de
NavRegistry, seul de ce type qui existait avant (xui/nav.py).

Toujours des singletons de module (même limite assumée que xui/nav.py :
pas de slot kernel dédié tant qu'une vraie extension n'y est montée) —
mais le nettoyage au hot-reload N'EST PLUS à la charge de chaque plugin :
XwebExtension s'abonne une fois à plugin.*.unloaded sur l'event bus xcore
et appelle unregister_plugin() sur les quatre registres ci-dessous
automatiquement (docs/spec-v1.md §3, engine/integration/xcore.py).

Quatre régions, quatre registres (docs/shell.md) :

    nav         sidebar — arbre (parent_id/children), rendu par xweb.nav_items
    ribbon      colonne d'icônes à gauche — une icône + tooltip par entrée
    commands    palette Ctrl+K — label + action_url (+ hotkey indicatif)
    status_bar  barre du bas — texte court, `side` gauche/droite

Un seul dataclass `Contribution` pour les quatre : les champs qui ne
concernent pas une région sont simplement ignorés par elle (documenté
champ par champ ci-dessous) — plus simple pour un auteur de plugin qu'un
type par registre, et c'est déjà ce que xui/nav.py faisait.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Pseudo-permission injectée par xweb/mount.py::_base_render_context() dans
# user_roles pour TOUT utilisateur connecté (n'importe quel rôle, même
# aucun) — jamais un vrai nom de rôle/permission qu'un plugin utiliserait
# lui-même (entourée d'astérisques précisément pour ça). Poser
# `permission=AUTHENTICATED` sur une Contribution (docs/shell.md) la cache
# pour un visiteur anonyme, sans avoir besoin d'un champ à part — le
# mécanisme de filtrage (ContributionRegistry.list(), plus bas) reste
# identique à celui déjà utilisé pour "audit:read"/"tenants:read"/etc.
AUTHENTICATED = "*authenticated*"


@dataclass
class Contribution:
    id: str
    plugin: str
    label: str = ""
    # Nom d'icône xweb.icon (xweb/components/icon.xml — "home", "users", "cog"…).
    # Vide = pas d'icône (nav) ou initiale du label (ribbon).
    icon: str = ""
    order: int = 100
    # Rôle OU permission requis pour voir l'entrée (docs/plugins.md — seulement
    # de l'affichage, jamais une protection : la route derrière fait son
    # propre require_role).
    permission: str | None = None
    # Nav + ribbon + commands — cible du clic. Nav uniquement : parent_id.
    path: str | None = None
    parent_id: str | None = None
    # Commands uniquement — alias historique de `path` (xui). Si les deux sont
    # donnés, action_url gagne.
    action_url: str | None = None
    # Commands uniquement — raccourci affiché dans la palette ("Ctrl+K"),
    # purement indicatif : xweb ne câble aucun raccourci global lui-même.
    hotkey: str | None = None
    # Ribbon + status bar — texte au survol (title=). Vide = label.
    tooltip: str = ""
    # Status bar uniquement — "left" | "right".
    side: str = "left"
    # Nav uniquement — petit badge à côté du label (xweb.nav_items,
    # components/shell.xml), même idée que la prop `badge` de xweb.menu
    # (démo : plugins/demo/templates/components.xml). STATIQUE, posé une
    # fois à nav.register() (docs/shell.md) — ce registre est un singleton
    # de module partagé par TOUTE requête/utilisateur, jamais reconstruit
    # par visiteur. Ne PAS s'en servir pour un compteur par utilisateur
    # (notifications non lues, par ex.) : tous les visiteurs verraient la
    # valeur du DERNIER qui l'aurait mise à jour, pas la leur — ça exigerait
    # un mécanisme de résolution par requête qui n'existe pas ici. Bon pour
    # un tag fixe ("Bêta", une version, un nombre de plugins installés…).
    badge: str | None = None

    @property
    def href(self) -> str | None:
        """Cible effective d'un clic — action_url (commands) sinon path."""
        return self.action_url or self.path

    @property
    def title(self) -> str:
        return self.tooltip or self.label

    def to_dict(self) -> dict:
        d = asdict(self)
        d["href"] = self.href
        d["title"] = self.title
        return d


class ContributionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Contribution] = {}

    def register(self, item: Contribution) -> None:
        if item.id in self._items:
            raise ValueError(
                f"Contribution id en collision : '{item.id}' "
                f"(déjà déclarée par '{self._items[item.id].plugin}')"
            )
        self._items[item.id] = item

    def unregister_plugin(self, plugin_name: str) -> None:
        self._items = {k: v for k, v in self._items.items() if v.plugin != plugin_name}

    def list(self, user_roles: set[str] | None = None) -> list[Contribution]:
        items = [
            c for c in self._items.values()
            if c.permission is None or user_roles is None or c.permission in user_roles
        ]
        return sorted(items, key=lambda c: (c.order, c.label))

    def __len__(self) -> int:
        return len(self._items)


class NavRegistry(ContributionRegistry):
    """Seule différence avec la base : tree() au lieu de list() — même
    algorithme que xui/nav.py, porté tel quel (id/parent_id/children)."""

    def tree(self, user_roles: set[str] | None = None) -> list[dict]:
        visible = self.list(user_roles)
        visible_ids = {c.id for c in visible}
        by_parent: dict[str | None, list[Contribution]] = {}
        for c in visible:
            parent = c.parent_id if c.parent_id in visible_ids else None
            by_parent.setdefault(parent, []).append(c)

        def build(pid: str | None) -> list[dict]:
            children = sorted(by_parent.get(pid, []), key=lambda c: (c.order, c.label))
            return [
                {"id": c.id, "label": c.label, "path": c.path, "icon": c.icon, "badge": c.badge, "children": build(c.id)}
                for c in children
            ]

        return build(None)


class RibbonRegistry(ContributionRegistry):
    pass


class CommandRegistry(ContributionRegistry):
    pass


class StatusBarRegistry(ContributionRegistry):
    def sides(self, user_roles: set[str] | None = None) -> tuple[list[Contribution], list[Contribution]]:
        """(gauche, droite) — tout ce qui n'est pas explicitement "right"
        va à gauche, jamais perdu sur une faute de frappe."""
        items = self.list(user_roles)
        right = [c for c in items if c.side == "right"]
        left = [c for c in items if c.side != "right"]
        return left, right


# Singletons de module — voir docstring pour la limite assumée.
nav = NavRegistry()
ribbon = RibbonRegistry()
commands = CommandRegistry()
status_bar = StatusBarRegistry()

ALL_REGISTRIES: tuple[ContributionRegistry, ...] = (nav, ribbon, commands, status_bar)
