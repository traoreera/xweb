"""t-inherit / XPath — non-destructive template extension.

Phase 2 (docs/inheritance.md, xweb Blueprint §7). A <template t-inherit="…">
never registers itself as a renderable template directly — it registers a
Patch, applied by QwebRegistry (see registry.py) whenever a template is
looked up. Two modes, both driven by the same Patch/XPathOp machinery
below — only WHERE the result lands differs:

    t-inherit-mode="extension" (default) — the patch's OWN t-name is
        never renderable on its own ; it live-patches the TARGET's shared
        tree in place, resolved by QwebRegistry._resolve(). Every plugin
        that renders the target sees the patched version.

    t-inherit-mode="primary" — full structural duplication (real
        QWeb/Odoo has this). The patch's OWN t-name becomes a genuinely
        new, independent template : a deep copy of the target's fully
        resolved tree (parent patches included), with this patch's own
        <xpath> ops applied on top — then registered under the PATCH's
        name, not the target's. Resolved by QwebRegistry._resolve_primary().
        A one-time snapshot, not a live link : if the target changes later
        without this primary template being re-registered itself, the
        snapshot does not follow — deliberate, matches "duplication", not
        "another patch". See docs/inheritance.md#primary.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from lxml import etree

from .compiler import TemplateError

_XPATH_POSITIONS = frozenset({"before", "after", "inside", "replace", "attributes"})


@dataclass
class XPathOp:
    expr: str
    position: str
    nodes: list[etree._Element] = field(default_factory=list)   # element content, for position != "attributes"
    attributes: dict[str, str] = field(default_factory=dict)     # for position == "attributes"


_INHERIT_MODES = frozenset({"extension", "primary"})


@dataclass
class Patch:
    t_name: str            # the patch's own t-name — shown in conflict warnings and xweb inspect (docs/cli.md)
    inherit: str            # target t-name being extended
    priority: int
    source_plugin: str
    xpath_ops: list[XPathOp]
    mode: str = "extension"  # "extension" (live-patches inherit's shared tree) or "primary" (duplicates it under t_name)


def extract_patch(template_el: etree._Element, *, source_plugin: str = "") -> Patch | None:
    """Returns a Patch if *template_el* has t-inherit, None for a plain
    (base) template — the caller (QwebRegistry) uses that to decide
    which dict a parsed <template> belongs in."""
    inherit = template_el.get("t-inherit")
    if inherit is None:
        return None

    mode = template_el.get("t-inherit-mode", "extension")
    if mode not in _INHERIT_MODES:
        raise TemplateError(
            f"{template_el.get('t-name')}: t-inherit-mode={mode!r} unknown "
            f"(only 'extension'/'primary' — docs/inheritance.md)"
        )

    priority = int(template_el.get("priority", "0"))
    ops: list[XPathOp] = []
    for xp in template_el.findall("xpath"):
        expr, position = xp.get("expr"), xp.get("position")
        if not expr or not position:
            raise TemplateError(f"{template_el.get('t-name')}: <xpath> requires expr and position")
        if position not in _XPATH_POSITIONS:
            raise TemplateError(f"{template_el.get('t-name')}: unknown xpath position {position!r}")

        if position == "attributes":
            attrs = {a.get("name"): (a.text or "") for a in xp.findall("attribute")}
            ops.append(XPathOp(expr=expr, position=position, attributes=attrs))
        else:
            ops.append(XPathOp(expr=expr, position=position, nodes=list(xp)))

    return Patch(
        t_name=template_el.get("t-name", "<anonymous>"),
        inherit=inherit,
        priority=priority,
        source_plugin=source_plugin,
        xpath_ops=ops,
        mode=mode,
    )


def apply_patch_ops(tree: etree._Element, ops: list[XPathOp], *, patch_name: str) -> etree._Element:
    """Applies *ops* to a COPY of tree, in order, and returns the copy —
    the caller's tree is never mutated in place (needed so re-resolving
    after a new patch registers, docs/inheritance.md#résolution, always
    starts fresh from the base template rather than compounding drift)."""
    tree = copy.deepcopy(tree)
    for op in ops:
        matches = tree.xpath(op.expr)
        if not matches:
            raise TemplateError(f"{patch_name}: xpath {op.expr!r} matched no node")
        for node in matches:
            _apply_op(node, op)
    return tree


def _apply_op(node: etree._Element, op: XPathOp) -> None:
    if op.position == "attributes":
        for name, value in op.attributes.items():
            node.set(name, value)
        return

    new_nodes = [copy.deepcopy(n) for n in op.nodes]  # fresh copies per match — an lxml element has one parent

    if op.position == "before":
        for n in new_nodes:
            node.addprevious(n)
    elif op.position == "after":
        # addnext() always lands immediately after `node` — inserting in
        # source order left-to-right would reverse the result, so insert
        # in reverse to end up in the order the <xpath> block wrote them.
        for n in reversed(new_nodes):
            node.addnext(n)
    elif op.position == "inside":
        for n in new_nodes:
            node.append(n)
    elif op.position == "replace":
        parent = node.getparent()
        if parent is None:
            raise TemplateError('position="replace" cannot target the template root')
        idx = list(parent).index(node)
        parent.remove(node)
        for offset, n in enumerate(new_nodes):
            parent.insert(idx + offset, n)
