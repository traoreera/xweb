"""QwebRegistry — the single template registry for xweb.

Phase 2 (docs/spec-v1.md, xweb Blueprint §7) adds t-inherit resolution on
top of Phase 1's register/get/render. Unlike microframe's ComponentRegistry
+ separate page Loader, this is one registry for both pages and components
(docs/spec-v1.md principe 6) — and now also the one place t-inherit patches
resolve against, rather than a separate PatchRegistry (that split existed
in the *Patch Points* design, before the pivot to real QWeb — see xweb
Blueprint §0).
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .compiler import Compiler, TemplateError
from .inherit import Patch, apply_patch_ops, extract_patch
from .parser import TemplateSyntaxError, parse_templates

if TYPE_CHECKING:
    from lxml import etree

logger = logging.getLogger(__name__)


class QwebRegistry:
    """Process-global by convention (one instance per process, same
    posture as microframe's ComponentRegistry), but not enforced as a
    singleton here — tests instantiate their own to stay isolated."""

    def __init__(self) -> None:
        self._templates: dict[str, "etree._Element"] = {}   # base (non-inheriting) templates only — a resolved primary-mode template also lands here, from its first get() onward
        self._template_plugin: dict[str, str] = {}             # t-name -> source_plugin, for unregister_plugin()
        self._patches: dict[str, list[Patch]] = {}            # target t-name -> extension-mode patches extending it
        self._primary: dict[str, Patch] = {}                    # the primary-mode patch's OWN t-name -> not-yet-resolved duplication recipe (docs/inheritance.md#primary)
        self._resolved: dict[str, "etree._Element"] = {}       # target t-name -> fully patched tree, cached
        self.version = 0                                        # bumped on every registration — cache key material (docs/inheritance.md)
        self._compiler = Compiler(self)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_source(self, source: str, *, filename: str = "<string>", source_plugin: str = "") -> list[str]:
        """Parse *source* and register every <template> it defines —
        either as a base template, or (if it has t-inherit) as a patch
        against one. Returns every t-name found, patches included, for
        logging/tests."""
        templates = parse_templates(source, filename=filename)
        for name, el in templates.items():
            patch = extract_patch(el, source_plugin=source_plugin)
            if patch is not None and patch.mode == "primary":
                # docs/inheritance.md#primary — sa PROPRE t-name devient un
                # template à part entière (pas un patch anonyme sur la
                # cible) : même conflit "re-registered" qu'un vrai template
                # de base si ce nom est déjà pris.
                if patch.t_name in self._templates or patch.t_name in self._primary:
                    logger.warning(
                        "template '%s' re-registered (%s) — shadows the previous definition", patch.t_name, filename,
                    )
                self._primary[patch.t_name] = patch
                self._template_plugin[patch.t_name] = source_plugin
                self._templates.pop(patch.t_name, None)  # une résolution précédente peut l'avoir matérialisé ici
                self._resolved.pop(patch.t_name, None)
            elif patch is not None:
                self._patches.setdefault(patch.inherit, []).append(patch)
                self._resolved.pop(patch.inherit, None)
            else:
                if name in self._templates:
                    logger.warning(
                        "template '%s' re-registered (%s) — shadows the previous definition", name, filename,
                    )
                self._templates[name] = el
                self._template_plugin[name] = source_plugin
                self._resolved.pop(name, None)
            self.version += 1
        self._validate_shorthand_targets(templates, filename=filename)
        return list(templates)

    def _validate_shorthand_targets(self, templates: "dict", *, filename: str) -> None:
        """Un <xweb:...> au parse n'a jamais le droit de viser un t-name
        absent du registre — l'envers exact des t-* muets du rendu. La
        vérification a lieu ici (après l'enregistrement des templates de
        ce source), pas au premier rendu, pour que l'erreur d'auteur
        tombe au chargement, avec le fichier en cause."""
        if not getattr(templates, "shorthand_targets", None):
            return
        unknown = [t for t in templates.shorthand_targets if self.get(t) is None]
        if unknown:
            raise TemplateSyntaxError(
                f"{filename}: <xweb:...> -> cible(s) absente(s) du registre : "
                f"{', '.join(sorted(set(unknown)))}"
            )

    def register_file(self, path: str | Path, *, source_plugin: str = "") -> list[str]:
        path = Path(path)
        return self.register_source(path.read_text(encoding="utf-8"), filename=str(path), source_plugin=source_plugin)

    def register_dir(self, directory: str | Path, *, source_plugin: str = "") -> list[str]:
        """Silent no-op if *directory* doesn't exist yet — same defensive
        posture as xui's mount_template_static (a plugin without its own
        templates directory isn't an error)."""
        directory = Path(directory)
        if not directory.is_dir():
            return []
        names: list[str] = []
        for file in sorted(directory.glob("*.xml")):
            names.extend(self.register_file(file, source_plugin=source_plugin))
        return names

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def get(self, name: str) -> "etree._Element | None":
        """Returns the fully resolved (patched) tree for *name* — this
        is what render() and t-call use; callers never see the
        unpatched base. Cached per t-name, invalidated by any
        registration that touches this template or a patch against it
        (see register_source)."""
        if name in self._resolved:
            return self._resolved[name]
        base = self._templates.get(name)
        if base is not None:
            resolved = self._resolve(name, base)
            self._resolved[name] = resolved
            return resolved
        primary = self._primary.get(name)
        if primary is not None:
            # Matérialise la duplication comme une nouvelle base, PUIS
            # applique tout patch extension-mode qui viserait ce même nom
            # (réutilise _resolve() tel quel — un template primary-mode
            # matérialisé n'est plus distingué d'un vrai template de base
            # à partir d'ici, docs/inheritance.md#primary).
            base = self._resolve_primary(name, primary)
            self._templates[name] = base
            resolved = self._resolve(name, base)
            self._resolved[name] = resolved
            return resolved
        return None

    def _resolve_primary(self, name: str, patch: Patch) -> "etree._Element":
        """t-inherit-mode="primary" — copie intégrale de l'arbre RÉSOLU de
        la cible (patches déjà appliqués sur elle comprise, via l'appel
        récursif à self.get() : une cible elle-même primary-mode ou
        déjà étendue fonctionne sans distinction), puis les <xpath> de ce
        patch appliqués sur cette copie — jamais sur l'arbre partagé de la
        cible (apply_patch_ops() copie déjà en interne, mais le point de
        départ ici est déjà une copie dédiée : deux niveaux de deepcopy
        n'est pas un bug, juste redondant et sans conséquence)."""
        parent = self.get(patch.inherit)
        if parent is None:
            raise TemplateError(
                f"{name}: t-inherit-mode=\"primary\" cible {patch.inherit!r}, introuvable "
                f"(docs/inheritance.md#primary)"
            )
        tree = copy.deepcopy(parent)
        if patch.xpath_ops:
            tree = apply_patch_ops(tree, patch.xpath_ops, patch_name=patch.t_name)
        return tree

    def _resolve(self, name: str, base: "etree._Element") -> "etree._Element":
        patches = sorted(self._patches.get(name, []), key=lambda p: p.priority)
        tree = base
        claimed_replace: dict[str, Patch] = {}  # expr -> the patch that already won position="replace" on it
        for patch in patches:
            ops = []
            for op in patch.xpath_ops:
                if op.position == "replace":
                    winner = claimed_replace.get(op.expr)
                    if winner is not None:
                        logger.warning(
                            "%s: xpath %r position=replace conflict — '%s' (%s, priority=%d) already "
                            "applied, '%s' (%s, priority=%d) ignored for this node",
                            name, op.expr,
                            winner.t_name, winner.source_plugin, winner.priority,
                            patch.t_name, patch.source_plugin, patch.priority,
                        )
                        continue
                    claimed_replace[op.expr] = patch
                ops.append(op)
            if ops:
                tree = apply_patch_ops(tree, ops, patch_name=patch.t_name)
        return tree

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, name: str, ctx: dict | None = None) -> str:
        el = self.get(name)
        if el is None:
            raise KeyError(f"QwebRegistry: no template named {name!r}")
        return self._compiler.render(el, dict(ctx or {}))

    def __len__(self) -> int:
        """Base templates registered — not counting patches, which live
        in a separate dict keyed by target, not by their own t-name."""
        return len(self._templates)

    def unregister_plugin(self, plugin_name: str) -> None:
        """Removes both a plugin's own base templates AND any patches it
        registered against someone else's — called from
        engine/integration/xcore.py's plugin.*.unloaded subscription
        (docs/spec-v1.md §3), not by individual plugins themselves."""
        for name in [n for n, owner in self._template_plugin.items() if owner == plugin_name]:
            # .pop(name, None), pas del self._templates[name] : un template
            # primary-mode (docs/inheritance.md#primary) peut n'avoir
            # jamais été résolu — encore seulement dans self._primary,
            # jamais matérialisé dans self._templates.
            self._templates.pop(name, None)
            self._primary.pop(name, None)
            del self._template_plugin[name]
            self._resolved.pop(name, None)

        for target, patches in list(self._patches.items()):
            remaining = [p for p in patches if p.source_plugin != plugin_name]
            if len(remaining) != len(patches):
                self._patches[target] = remaining
                self._resolved.pop(target, None)

        self.version += 1

    def check_all(self) -> None:
        """Resolves every base template now, instead of waiting for the
        first render() to hit each one lazily.

        Decided (docs/inheritance.md#conflits) — a position="replace"
        conflict on a widely shared template (xweb.button, used by every
        page) never raises: that would 500 every page using it over a
        disagreement between two unrelated plugins, wildly
        disproportionate to what a shared component crossing two other
        plugins' patches actually warrants. It only ever logs. The
        tradeoff that leaves is *when* the warning surfaces — get()'s
        laziness means it only fires the first time some request happens
        to touch that exact template. Called from
        engine/integration/xcore.py::XwebExtension.init() so conflicts
        land in the boot log next to everything else, not hours later on
        whichever page a visitor happens to open first."""
        for name in list(self._templates):
            self.get(name)
        for name in list(self._primary):
            self.get(name)
