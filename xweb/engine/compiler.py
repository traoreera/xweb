"""Compiles a parsed <template> element into rendered HTML.

Phase 1 (docs/spec-v1.md, xweb Blueprint §7): a tree-walking interpreter,
not codegen to a cached Python function — that optimization (matching
what Odoo's real QWeb does, see xweb Blueprint §5's three-tier diagram)
is deferred until the directive semantics implemented here are proven
against real components. This module is that proof.

Directive precedence on one element, in order: t-if/t-elif/t-else (decided
by the PARENT's child-iteration, before this element's own render is even
called) → t-foreach (loops everything below) → t-set (mutates scope, never
emits) → t-call (replaces the node with an included template's output) →
t-esc/t-out (replaces children with computed text) → plain children.

Scope rule: a dict copy happens once per new nesting level (entering an
element's children, one loop iteration, one t-call). Within that copy,
all direct siblings share the same dict reference, so t-set on one
sibling is visible to the ones that follow — but never leaks back up to
the enclosing level. `hx-*` and `_` (htmx / _hyperscript) attributes are
not directives at all: `_render_attrs` copies them through verbatim,
which is the whole point of choosing them over Alpine.js (xweb Blueprint
§2) — nothing here treats them specially.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from markupsafe import Markup, escape

from .filters import apply_filters, split_filters

if TYPE_CHECKING:
    from lxml import etree

    from .registry import QwebRegistry

_INTERP = re.compile(r"\{\{(.*?)\}\}")
_WS_RUN = re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    """Un texte source XML multi-lignes (indentation de mise en forme
    incluse) collapse en une seule ligne à espaces simples — exactement
    ce qu'un navigateur affiche de toute façon pour du texte HTML normal
    (les retours à la ligne/l'indentation du fichier .xml n'ont jamais été
    significatifs). Sans ça, la clé de traduction de t-tr dépendrait de
    l'indentation exacte du gabarit — fragile à écrire dans un catalogue
    JSON et cassé au moindre reformatage du fichier source."""
    return _WS_RUN.sub(" ", text).strip()

_VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})

# HTML5 "raw text elements" — un navigateur ne décode JAMAIS les entités à
# l'intérieur, contrairement à tout le reste du document. Trouvé en calculant
# le hash CSP du script anti-flash de shell.xml (docs/theming.md#build) :
# escape() y transformait ' en &#39;, un navigateur exécute ça littéralement
# -> SyntaxError. Le texte littéral de ces deux tags ne doit jamais passer
# par escape() — voir _render_element_body.
_RAW_TEXT_TAGS = frozenset({"script", "style"})

_DIRECTIVE_ATTRS = frozenset({
    "t-if", "t-elif", "t-else", "t-foreach", "t-as", "t-esc", "t-out", "t-tr",
    "t-set", "t-value", "t-call", "t-name", "t-inherit", "t-inherit-mode",
})


class TemplateError(Exception):
    """Raised at render time — bad expression, unknown t-call target, etc."""


def _eval(expr: str, ctx: dict) -> Any:
    """Evaluate a Python expression against the render context.

    Undefined names evaluate to None (falsy, renders as empty text/omits
    the attribute) rather than raising — a template that expects a prop
    with a default must set one explicitly with t-set; there is no
    props-with-defaults mechanism in Phase 1 (see docs/components.md,
    tests/test_compiler.py::test_no_default_props_yet for what that
    means in practice).

    Supports a CLOSED set of value filters via `| name:args` chaining
    (xweb/engine/filters.py — no plugin can register a filter). The whole
    filtered result still goes through escape() at the t-esc call site, so
    a filter can never emit raw HTML.
    """
    # Une expression avec un filtre connu ("price | money") évalue la partie
    # valeur, puis chaîne les filtres ; sinon eval normal (a | b = bitwise OR
    # reste valide car split_filters ne découpe que sur des NOMS connus).
    parts = split_filters(expr)
    value_expr = parts[0]
    has_filters = len(parts) > 1 and parts[1].lstrip().startswith("|")
    try:
        base = eval(value_expr, {"__builtins__": {}}, ctx)  # noqa: S307 — template authors are trusted plugin code (docs/spec-v1.md principe 2), not end users
    except NameError:
        # Un nom non défini reste falsy (None), MAIS ne doit pas court-
        # circuiter une chaîne de filtres — sinon "missing | default:'N/A'"
        # rendait vide au lieu de "N/A" : le seul cas d'usage réel de
        # default/default_if_empty/yesno (gérer une valeur absente) était
        # justement celui que ce retour anticipé empêchait. Trouvé en
        # testant le nouveau module filters.py pour de vrai.
        base = None
    except Exception as exc:
        raise TemplateError(f"expression failed: {expr!r} — {exc}") from exc
    if not has_filters:
        return base
    return apply_filters(expr, ctx, base)[0]


def _eval_formatted(text: str, ctx: dict) -> str:
    """t-attf-* interpolation: {{ expr }} inside a literal string."""

    def repl(match: re.Match) -> str:
        value = _eval(match.group(1).strip(), ctx)
        return "" if value is None else str(value)

    return _INTERP.sub(repl, text)


class Compiler:
    """Renders <template> element trees against a QwebRegistry, used to
    resolve t-call targets."""

    def __init__(self, registry: "QwebRegistry") -> None:
        self.registry = registry

    def render(self, template_el: "etree._Element", ctx: dict) -> Markup:
        buf: list[str] = []
        self._render_children(template_el, dict(ctx), buf)
        return Markup("".join(buf))

    # ------------------------------------------------------------------
    # Sibling iteration — where t-if/t-elif/t-else chains are resolved.
    # ------------------------------------------------------------------

    def _render_children(self, parent_el: "etree._Element", ctx: dict, buf: list[str]) -> None:
        children = list(parent_el)
        i, n = 0, len(children)
        while i < n:
            el = children[i]
            if not isinstance(el.tag, str):  # comments, PIs
                i += 1
                continue

            if el.get("t-if") is not None:
                chain = [el]
                j = i + 1
                while j < n and (
                    children[j].get("t-elif") is not None or children[j].get("t-else") is not None
                ):
                    chain.append(children[j])
                    j += 1
                for branch in chain:
                    cond = branch.get("t-if", branch.get("t-elif"))
                    if cond is None or _eval(cond, ctx):
                        self._render_element(branch, ctx, buf)
                        break
                if chain[-1].tail:  # text after whichever branch was last in the chain
                    buf.append(str(escape(chain[-1].tail)))
                i = j
                continue

            if el.get("t-elif") is not None or el.get("t-else") is not None:
                i += 1  # orphaned elif/else, no preceding t-if — skipped, not an error, in Phase 1
                continue

            self._render_element(el, ctx, buf)
            if el.tail:  # text between this element and its next sibling
                buf.append(str(escape(el.tail)))
            i += 1

    # ------------------------------------------------------------------
    # One element, t-if already resolved by the caller above.
    # ------------------------------------------------------------------

    def _render_element(self, el: "etree._Element", ctx: dict, buf: list[str]) -> None:
        if el.get("t-foreach") is not None:
            self._render_foreach(el, ctx, buf)
            return
        self._render_element_body(el, ctx, buf)

    def _render_foreach(self, el: "etree._Element", ctx: dict, buf: list[str]) -> None:
        items = list(_eval(el.get("t-foreach"), ctx) or [])
        var = el.get("t-as")
        if not var:
            raise TemplateError(f"t-foreach without t-as on <{el.tag}>")
        n = len(items)
        for i, item in enumerate(items):
            loop_ctx = dict(ctx)
            loop_ctx[var] = item
            loop_ctx[f"{var}_index"] = i
            loop_ctx[f"{var}_size"] = n
            loop_ctx[f"{var}_first"] = i == 0
            loop_ctx[f"{var}_last"] = i == n - 1
            self._render_element_body(el, loop_ctx, buf)

    def _render_element_body(self, el: "etree._Element", ctx: dict, buf: list[str]) -> None:
        t_set = el.get("t-set")
        if t_set is not None:
            t_default = el.get("t-default")
            if t_default is not None:
                # Props-with-defaults (docs/components.md — the Phase 1 gap
                # tests/test_compiler.py::test_no_default_props_yet_documents_the_real_gap
                # pinned down): only fills in the value if the caller
                # genuinely didn't pass this prop at all. `t-set="x"
                # t-value="expr"` (no t-default) still always overwrites —
                # this is additive, not a replacement for that.
                if t_set not in ctx:
                    ctx[t_set] = _eval(t_default, ctx)
            else:
                ctx[t_set] = _eval(el.get("t-value", "None"), ctx)
            return  # a t-set node never emits output

        if el.get("t-call") is not None:
            self._render_call(el, ctx, buf)
            return

        tag = el.tag
        is_t = tag == "t"  # <t> is logic-only, never emits its own HTML tag
        void = tag in _VOID_ELEMENTS

        if not is_t:
            buf.append(f"<{tag}")
            self._render_attrs(el, ctx, buf)
            buf.append(" />" if void else ">")
        if void:
            return

        t_esc = el.get("t-esc")
        t_out = el.get("t-out")
        t_tr = el.get("t-tr")
        if t_esc is not None:
            value = _eval(t_esc, ctx)
            if value is not None:
                buf.append(str(escape(value)))
        elif t_out is not None:
            value = _eval(t_out, ctx)
            if value is not None:
                buf.append(value if isinstance(value, Markup) else str(escape(value)))
        elif t_tr is not None:
            # docs/i18n.md — traduit le texte statique du nœud. Contrairement
            # à t-esc/t-out, PAS une expression Python : la clé de traduction
            # EST le texte source français lui-même (convention gettext),
            # pour rester aussi mécanique à poser qu'un attribut de plus sur
            # un élément déjà écrit — <h1 t-tr="1">Organisation</h1>, jamais
            # <h1 t-esc="_('Organisation')"/>. `_` (le traducteur lié à la
            # locale résolue pour CETTE requête) vit dans ctx, jamais importé
            # ici — xweb/mount.py::_base_render_context est le seul endroit
            # qui sait ce qu'est une locale. Absent de ctx (rendu hors
            # mount_xweb_page — tests, CLI xweb) → texte source inchangé,
            # jamais une exception.
            source = _normalize_ws(el.text or "")
            translate = ctx.get("_")
            text = translate(source) if source and callable(translate) else source
            buf.append(str(escape(text)))
        else:
            if el.text:
                if tag in _RAW_TEXT_TAGS:
                    buf.append(el.text)  # jamais escape() — voir _RAW_TEXT_TAGS
                else:
                    buf.append(str(escape(el.text)))
            self._render_children(el, dict(ctx), buf)

        if not is_t:
            buf.append(f"</{tag}>")

    # ------------------------------------------------------------------

    def _render_attrs(self, el: "etree._Element", ctx: dict, buf: list[str]) -> None:
        for name, value in el.attrib.items():
            if name in _DIRECTIVE_ATTRS:
                continue
            if name.startswith("t-att-"):
                attr_name, attr_value = name[len("t-att-"):], _eval(value, ctx)
            elif name.startswith("t-attf-"):
                attr_name, attr_value = name[len("t-attf-"):], _eval_formatted(value, ctx)
            elif name.startswith("t-"):
                continue  # unknown/future directive — ignored, not an error, in Phase 1
            else:
                # plain attribute: class="btn", hx-post="/...", _="on click …" —
                # htmx and _hyperscript need no special handling here at all
                # (xweb Blueprint §2) — that IS the point of choosing them.
                attr_name, attr_value = name, value

            if attr_value is None or attr_value is False:
                continue
            text = attr_name if attr_value is True else str(attr_value)
            buf.append(f' {attr_name}="{escape(text)}"')

    def _render_call(self, el: "etree._Element", ctx: dict, buf: list[str]) -> None:
        target = el.get("t-call")

        # The calling node's body is rendered with the CALLER's context
        # and handed to the callee as `slot` — the callee's own context
        # is otherwise isolated (only explicit props below + slot), same
        # boundary django-cotton-ui's {% uivars %} components already
        # drew for the components xui ported (docs/language.md#t-call).
        slot_buf: list[str] = []
        if el.text:
            slot_buf.append(str(escape(el.text)))
        self._render_children(el, dict(ctx), slot_buf)

        call_ctx: dict = {}
        for name, value in el.attrib.items():
            if name.startswith("t-att-"):
                call_ctx[name[len("t-att-"):].replace("-", "_")] = _eval(value, ctx)
            elif not name.startswith("t-"):
                call_ctx[name.replace("-", "_")] = value
        call_ctx["slot"] = Markup("".join(slot_buf))

        target_el = self.registry.get(target)
        if target_el is None:
            raise TemplateError(f"t-call: unknown template {target!r}")
        buf.append(self.render(target_el, call_ctx))
