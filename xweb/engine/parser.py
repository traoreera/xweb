"""Parses .xml QWeb template source into lxml element trees.

Phase 1 (docs/spec-v1.md, xweb Blueprint §7) — parsing only, no t-inherit
resolution. A single .xml file may define several <template t-name="...">
elements at the top level (same convention as Odoo's QWeb XML files: a
component and its variants can share one file).

Raccourci <xweb:...> (sucre syntaxique) : un élément namespacé
<xweb:button variant="primary">…</xweb:button> est désucé au parse en
<t t-call="xweb.button" variant="primary">…</t> — le compilateur, le
registre, l'héritage et l'export du Studio ne voient jamais que la forme
canonique. Les deux syntaxes coexistent dans un même fichier. Le nom est
un chemin : sans point → la composante vit sous le préfixe xweb
(<xweb:button> ⇒ xweb.button) ; avec point → c'est le t-call complet tel
quel, n'importe quelle cible du registre (<xweb:auth.login_page> ⇒
auth.login_page). Règles :
  - toute prop autre que t-* est passée telle quelle (chaîne littérale) ;
  - `attr="=expr"` devient t-att-attr (expression Python évaluée) ;
  - `attr="pro{{x}}"` devient t-attf-attr (chaîne interpolée) ;
  - le contenu (texte + enfants) devient le slot, comme sur un t-call ;
  - les directives (t-if, t-foreach, t-set-slot, …) passent inchangées ;
  - `slot` et `t-call` sont des erreurs ; un nom de composant invalide
    aussi — jamais de silence, contrairement aux t-* inconnus du rendu.
Le préfixe `xweb` est réservé à l'espace de noms urn:xweb : son déclaration
est injectée automatiquement au parse quand le source l'utilise sans la
déclarer. La résolution des cibles inconnues (l'équivalence de la sémantique
« pas de t-call muet ») a lieu à l'enregistrement — voir
QwebRegistry.register_source, qui échoue sur un <xweb:?> non enregistré.
"""

from __future__ import annotations

import re

from lxml import etree


class TemplateSyntaxError(Exception):
    """Raised when a .xml template file is not well-formed XML, a
    <template> is missing its required t-name attribute, or the
    <xweb:...> shorthand is misused (invalid component name, reserved
    attribute, …)."""


# ---------------------------------------------------------------------------
# <xweb:...> raccourci — désucage vers <t t-call="xweb.<nom>">
# ---------------------------------------------------------------------------

_XWEB_NS = "urn:xweb"                       # espace réservé au raccourci
_XWEB_PREFIX = "xweb"
_XWEB_TAG_PREFIX = f"{{{_XWEB_NS}}}"        # forme Clark des balises lxml
# segments dot-séparés (le point est un NameChar XML valide) : sans point
# ⇒ xweb.<nom>, avec point ⇒ cible complète passée telle quelle.
_XWEB_NAME_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*")


class _ParsedTemplates(dict):
    """Dict[str, etree._Element] — un dict ordinaire (`parse_templates`
    reste transparent pour l'API existante) qui porte en plus la liste des
    cibles de raccourci <xweb:...> rencontrées, pour la validation à
    l'enregistrement (un <xweb:?> vers un t-name inconnu doit échouer là,
    pas au premier rendu — l'inverse des t-* muets)."""

    def __init__(self) -> None:
        super().__init__()
        self.shorthand_targets: list[str] = []


def _ensure_xweb_namespace(source: str) -> str:
    """Injecte xmlns:xweb="urn:xweb" sur la racine quand le source utilise
    <xweb:...> sans la déclarer — le XML interdit un préfixe non déclaré,
    et taper la déclaration à la main irait contre l'objectif du raccourci.
    Un source qui la déclare déjà (peu importe où) n'est pas touché."""
    if "<xweb:" not in source or "xmlns:xweb" in source:
        return source
    return re.sub(r"<(templates?)(?=[\s>])", r'<\1 xmlns:xweb="urn:xweb"', source, count=1)


def _desugar_xweb_shorthand(template: "etree._Element", *, filename: str) -> list[str]:
    """Réécrit en place chaque élément <xweb:...> de *template* en
    <t t-call="xweb.<nom>" ...> — la forme exacte que le compilateur gère
    déjà (compiler.py::_render_call), jamais une variante. Retourne chaque
    cible désucée, pour la validation du registre."""
    targets: list[str] = []
    for el in template.iter():
        tag = el.tag
        if not isinstance(tag, str) or not tag.startswith(_XWEB_TAG_PREFIX):
            continue
        local = etree.QName(el).localname
        if not _XWEB_NAME_RE.fullmatch(local):
            raise TemplateSyntaxError(
                f"{filename}: <{_XWEB_PREFIX}:{local}> — nom de composant invalide "
                f"({local!r}, attendu [a-zA-Z_][a-zA-Z0-9_]* avec point libre)"
            )
        for attr_name, attr_value in list(el.attrib.items()):
            if attr_name == "t-call":
                raise TemplateSyntaxError(
                    f"{filename}: <{_XWEB_PREFIX}:{local}> — t-call est interdit, "
                    f"le raccourci désigne déjà la cible"
                )
            if attr_name == "slot":
                raise TemplateSyntaxError(
                    f"{filename}: <{_XWEB_PREFIX}:{local}> — slot est réservé au "
                    f"contenu (les enfants du raccourci), jamais une prop"
                )
            if not attr_name.startswith("t-"):
                if attr_value.startswith("=") and len(attr_value) > 1:
                    el.attrib.pop(attr_name)
                    el.set(f"t-att-{attr_name}", attr_value[1:])
                elif "{{" in attr_value:
                    el.attrib.pop(attr_name)
                    el.set(f"t-attf-{attr_name}", attr_value)
        target = local if "." in local else f"{_XWEB_PREFIX}.{local}"
        el.tag = "t"
        el.set("t-call", target)
        targets.append(target)
    return targets


def parse_templates(source: str, *, filename: str = "<string>") -> dict[str, etree._Element]:
    """Parse *source* and return every top-level <template t-name="...">
    it defines, keyed by t-name.

    Accepts either a single <template> as the document root, or several
    wrapped in a <templates> root — mirrors how a real .xml file on disk
    is free to define one component or a whole family of them.

    <xweb:...> shorthand elements are desugared into their canonical
    <t t-call="xweb.<name>"> form as part of the parse (see module doc,
    *_ensure_xweb_namespace*, *_desugar_xweb_shorthand*).
    """
    source = _ensure_xweb_namespace(source)
    try:
        root = etree.fromstring(source.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise TemplateSyntaxError(f"{filename}: {exc}") from exc

    if root.tag == "template":
        elements = [root]
    elif root.tag == "templates":
        # Un commentaire XML (ou une PI) entre deux <template> est du bruit
        # légitime — l'en-tête de xweb/components/shell.xml en est un — jamais
        # une erreur de syntaxe : lxml expose ces nœuds avec un .tag qui
        # n'est pas une chaîne, on les saute comme le compilateur le fait.
        elements = [el for el in root if isinstance(el.tag, str)]
    else:
        raise TemplateSyntaxError(
            f"{filename}: expected <template> or <templates> at the root, got <{root.tag}>"
        )

    out: _ParsedTemplates = _ParsedTemplates()
    for el in elements:
        if el.tag != "template":
            raise TemplateSyntaxError(f"{filename}: unexpected <{el.tag}> at the top level")
        t_name = el.get("t-name")
        if not t_name:
            raise TemplateSyntaxError(f"{filename}: <template> missing required t-name")
        out.shorthand_targets.extend(_desugar_xweb_shorthand(el, filename=filename))
        out[t_name] = el
    return out
