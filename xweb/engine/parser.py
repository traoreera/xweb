"""Parses .xml QWeb template source into lxml element trees.

Phase 1 (docs/spec-v1.md, xweb Blueprint §7) — parsing only, no t-inherit
resolution. A single .xml file may define several <template t-name="...">
elements at the top level (same convention as Odoo's QWeb XML files: a
component and its variants can share one file).
"""

from __future__ import annotations

from lxml import etree


class TemplateSyntaxError(Exception):
    """Raised when a .xml template file is not well-formed XML, or a
    <template> is missing its required t-name attribute."""


def parse_templates(source: str, *, filename: str = "<string>") -> dict[str, etree._Element]:
    """Parse *source* and return every top-level <template t-name="...">
    it defines, keyed by t-name.

    Accepts either a single <template> as the document root, or several
    wrapped in a <templates> root — mirrors how a real .xml file on disk
    is free to define one component or a whole family of them.
    """
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

    out: dict[str, etree._Element] = {}
    for el in elements:
        if el.tag != "template":
            raise TemplateSyntaxError(f"{filename}: unexpected <{el.tag}> at the top level")
        t_name = el.get("t-name")
        if not t_name:
            raise TemplateSyntaxError(f"{filename}: <template> missing required t-name")
        out[t_name] = el
    return out
