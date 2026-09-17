"""Compiler xdsl — convertit l'AST en XML QWeb.

Respecte le mapping complet défini dans `docs/dsl-design.md`.
"""

from __future__ import annotations

import xml.sax.saxutils as saxutils
from typing import Any

from .parser import (
    AST,
    Assignment,
    Attribute,
    AttributeValue,
    ChannelDef,
    ComponentDef,
    CopyDef,
    DataSchemaDef,
    Element,
    EndpointDef,
    ForLoop,
    IfBlock,
    Import,
    PatchDef,
    Props,
    SlotNode,
    Style,
    TextNode,
    XpathPatch,
)

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


def build_import_scope(imports: list[Import], package_id: str) -> dict[str, str]:
    """Construit la table nom → nom qualifié pour les imports."""
    scope: dict[str, str] = {}
    for imp in imports:
        for name in imp.names:
            if imp.relative:
                clean = imp.source.rstrip("/")
                if clean in ("", "."):
                    scope[name] = f"{package_id}.{name}"
                else:
                    # "../auth" → auth, "../xweb" → xweb
                    suffix = clean.split("/")[-1]
                    scope[name] = f"{suffix}.{name}"
            else:
                scope[name] = f"{imp.source}.{name}"
    return scope


def _esc(value: str) -> str:
    """Échappe une valeur d'attribut XML (quotes et entities)."""
    return saxutils.escape(value, {"'": "&apos;", '"': "&quot;"})


def _esc_expr(value: str) -> str:
    """Échappe une EXPRESSION Python destinée à un attribut XML délimité par
    des guillemets doubles (t-att-x="'texte'").

    Comme `_esc` mais laisse les apostrophes intactes : ce sont les
    délimiteurs du littéral Python lui-même et elles sont parfaitement
    valides dans un attribut délimité par `"`. Les échapper en `&apos;`
    marcherait aussi (lxml les redécode) mais rendrait toute la sortie
    compilée illisible, pour rien.

    Régression réelle sans ceci (trouvée en écrivant site/templates/) : une
    prop littérale de t-call contenant `<` — `card { title: "un <template>" }`
    — produisait `t-att-title="'un <template>'"`, un XML INVALIDE. L'erreur
    remontait de lxml au moment d'enregistrer le template ("Unescaped '<' not
    allowed in attributes values"), en pointant la ligne du XML COMPILÉ, pas
    celle du .dsl source. C'était le seul chemin d'émission d'attribut du
    compilateur qui n'échappait rien."""
    return saxutils.escape(value, {'"': "&quot;"})


# Attributs où la valeur est reparsée comme du CODE par le navigateur une
# fois l'attribut HTML décodé (hyperscript pour `_`, JSON/expr JS pour
# `hx-vals`) — une interpolation ${...} qui y atterrit est protégée par un
# filtre QWeb supplémentaire (`hs`/`js`, xweb/engine/filters.py) en plus de
# l'échappement HTML normal de l'attribut. L'échappement HTML seul protège
# la frontière HTML (impossible de fermer l'attribut ou d'injecter une
# balise) mais PAS cette grammaire imbriquée : une valeur contenant un
# guillemet redevient un guillemet réel une fois décodée par le navigateur,
# et peut interrompre prématurément la chaîne hyperscript/l'objet JS pour
# faire exécuter du code injecté — trouvé en auditant `_ : ... ${x} ...` et
# `hx-vals: "js:{id: ${x}}"`, les deux exemples donnés par docs/dsl-design.md.
_CODE_ATTR_FILTERS: dict[str, str] = {"_": "hs", "hx-vals": "js"}


def _to_qweb_interp(value: str, filter_name: str | None = None) -> str:
    """Convertit la syntaxe `${ expr }` du DSL en `{{ expr }}` attendue
    par t-attf-* dans xweb (compute_attr _eval_formatted). Sans cette
    conversion, le moteur laisse `${...}` littéral — l'interpolation
    serveur ne se produit jamais. Les accolades sont comptées par profondeur,
    donc `${JSON.stringify({a: 1})}` reste un seul groupe. Toute séquence
    `${` non fermée est laissée telle quelle (attribut construit, pas une
    erreur).

    `filter_name` (voir `_CODE_ATTR_FILTERS`) chaîne un filtre QWeb
    (`(expr) | hs`) sur chaque expression interpolée — défense en
    profondeur pour les attributs reparsés comme code côté navigateur."""
    out: list[str] = []
    i, n = 0, len(value)
    while i < n:
        if i + 2 <= n and value[i] == "$" and value[i + 1] == "{":
            depth = 1
            j = i + 2
            while j < n and depth > 0:
                if value[j] == "{":
                    depth += 1
                elif value[j] == "}":
                    depth -= 1
                j += 1
            if depth == 0:
                expr = value[i + 2 : j - 1].strip()
                if filter_name:
                    expr = f"({expr}) | {filter_name}"
                out.append("{{" + expr + "}}")
                i = j
                continue
        out.append(value[i])
        i += 1
    return "".join(out)


def _build_python_concat(value: str) -> str:
    """Convertit une valeur (avec d'éventuels ${expr}) en expression Python
    qui produit la chaîne : 'pre' + (expr) + 'post'. Sans ${...}, retourne
    repr(value) — une seule chaîne littérale. L'expression contenue dans
    `${...}` doit être du Python valide (les ternaires JS `? :` ne le sont
    pas — utiliser `x if c else y`, comme partout ailleurs dans le DSL)."""
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(value)
    while i < n:
        if i + 2 <= n and value[i] == "$" and value[i + 1] == "{":
            depth = 1
            j = i + 2
            while j < n and depth > 0:
                if value[j] == "{":
                    depth += 1
                elif value[j] == "}":
                    depth -= 1
                j += 1
            if depth == 0:
                lit = "".join(buf).strip()
                if lit:
                    out.append(repr(lit))
                buf = []
                out.append("(" + value[i + 2 : j - 1].strip() + ")")
                i = j
                continue
        buf.append(value[i])
        i += 1
    if buf:
        out.append(repr("".join(buf).strip()))
    if not out:
        out.append(repr(value.strip()))
    return " + ".join(out)


class CompileError(Exception):
    """Erreur de compilation xdsl — ex. `use: nom` référence un endpoint
    jamais déclaré. Jamais un silence : un typo dans `use:` doit planter
    à la compilation, pas produire un bouton inerte (même posture que
    QwebRegistry.register_source pour un t-call xweb: vers une cible
    absente du registre — voir tests/test_xweb_shorthand.py)."""


def _schema_to_json(schema: DataSchemaDef) -> dict[str, list[list[Any]]]:
    """Convertit un `data` schema en descripteur JSON-safe pour
    `window.XWEB_SCHEMAS` — même forme que `DataField.decorators`
    (`[("required", []), ("min_length", [3])]`) mais en listes (JSON n'a
    pas de tuple), lu ensuite par xweb/static/validators.js::XwebValidate.
    Ne couvre QUE les règles de xdsl/validators.py::BUILTIN_VALIDATORS —
    la même liste fermée des deux côtés (serveur ET client), voir
    validators.js pour le miroir exact de chaque règle."""
    return {f.name: [[rule, list(args)] for rule, args in f.decorators] for f in schema.fields}


class Compiler:
    """Compile l'AST xdsl en XML QWeb."""

    def __init__(self, ast: AST, package_id: str = "__plugin__"):
        self.ast = ast
        self.package_id = package_id
        self.indent = 0
        self.lines: list[str] = []
        self._local_template_names = {
            comp.name for comp in self.ast.components
        } | {copy.alias for copy in self.ast.copies}
        self._data_schemas = {schema.name: schema for schema in self.ast.data_schemas}
        self._endpoints = {ep.name: ep for ep in self.ast.endpoints}
        self._channels = {ch.name: ch for ch in self.ast.channels}
        self._use_counter = 0
        self._patch_counter = 0
        self._global_scope: dict[str, str] = {}

    # -------------------------------------------------------------------------
    # Attributs structurés (liste de classes, dict de style)
    # -------------------------------------------------------------------------

    def _class_tokens(self, items: list[AttributeValue]) -> str:
        """Construit le contenu t-attf-* d'une liste ``class: [...]``.

        Items littéraux → texte brut, expressions → {{expr}}, chaînes
        avec ${...} → {{expr}} (via _to_qweb_interp).
        """
        out: list[str] = []
        for av in items:
            if av.quoted:
                if "${" in av.value:
                    out.append(_to_qweb_interp(av.value))
                else:
                    out.append(av.value)
            else:
                out.append("{{" + av.value + "}}")
        return " ".join(t for t in out if t)

    def _style_dict_to_xml_attr(self, props: dict[str, AttributeValue]) -> str:
        """Expansion d'un dict ``style: { p: v }``.

        - Tous les items statiques → ``style="p: v; p: v;"``.
        - Sinon → ``t-att-style="'p: ' + ... + ';'"`` (concaténation Python,
          évaluée par le moteur xweb).
        """
        static = all(av.quoted and "${" not in av.value for av in props.values())
        if static:
            clauses = [
                f"{key}: {av.value.strip()}"
                for key, av in props.items()
                if av.value.strip()
            ]
            body = "; ".join(clauses)
            return f'style="{_esc(body + ";" if body else body)}"'

        pieces: list[str] = []
        for key, av in props.items():
            if pieces:
                pieces.append("'; '")
            pieces.append(f"'{key}: '")
            if av.quoted:
                pieces.append(_build_python_concat(av.value))
            else:
                pieces.append("(" + av.value + ")")
        pieces.append("';'")
        return f't-att-style="{_esc(" + ".join(pieces))}"'

    def compile(self) -> str:
        global_scope = build_import_scope(self.ast.imports, self.package_id)
        self._global_scope = global_scope

        if self.ast.layout:
            self._write(f'<!-- layout: {_esc(self.ast.layout)} -->')

        for component in self.ast.components:
            self._compile_component(component, global_scope)

        for patch in self.ast.patches:
            self._compile_patch(patch, global_scope)

        for copy in self.ast.copies:
            self._compile_copy(copy, global_scope)

        for child in self.ast.children:
            self._compile_node(child, global_scope)

        return "\n".join(self.lines)

    def _indent(self) -> str:
        return "    " * self.indent

    def _write(self, line: str) -> None:
        self.lines.append(f"{self._indent()}{line}")

    def _compile_component(self, comp: ComponentDef, outer_scope: dict[str, str]) -> None:
        scope = build_import_scope(comp.imports, self.package_id)
        scope.update(outer_scope)

        attrs = f't-name="{comp.name}"'
        if comp.inherits:
            attrs += f' t-inherit="{comp.inherits}"'
        if comp.inherit_mode:
            attrs += f' t-inherit-mode="{comp.inherit_mode}"'
        if comp.priority:
            attrs += f' priority="{comp.priority}"'

        self._write(f"<template {attrs}>")
        self.indent += 1

        if comp.style:
            self._compile_style(comp.style)
        if comp.props:
            self._compile_props(comp.props)

        for child in comp.children:
            self._compile_node(child, scope)

        self.indent -= 1
        self._write("</template>")
        self._write("")

    def _compile_style(self, style: Style) -> None:
        self._write("<style>")
        for line in style.css.strip().split("\n"):
            self._write(line)
        self._write("</style>")

    def _compile_props(self, props: Props) -> None:
        for name, default in props.defaults.items():
            if isinstance(default, bool):
                val = "true" if default else "false"
            elif isinstance(default, (int, float)):
                val = str(default)
            else:
                val = f"'{default}'"
            self._write(f'<t t-set="{name}" t-default="{val}"/>')

    def _compile_patch(self, patch: PatchDef, scope: dict[str, str]) -> None:
        # t-name OBLIGATOIRE même pour un patch extension — jamais utilisé
        # pour un t-call (une patch ne se résout pas par nom, elle modifie
        # l'arbre de sa cible en place), mais xweb/engine/parser.py rejette
        # tout <template> sans t-name ("<template> missing required
        # t-name"). Bug réel trouvé en enregistrant une vraie patch xdsl
        # pour la première fois — les tests existants ne comparaient que du
        # texte compilé, jamais un vrai enregistrement/rendu (même trou que
        # ReceiveSpec.type avant lui). Synthétique et unique : deux `patch`
        # sur LA MÊME cible dans un même fichier (priorités différentes,
        # docs/inheritance.md) ne doivent jamais collisionner.
        self._patch_counter += 1
        attrs = (
            f't-name="{self.package_id}.__patch{self._patch_counter}__" '
            f't-inherit="{patch.target}" t-inherit-mode="extension"'
        )
        if patch.priority:
            attrs += f' priority="{patch.priority}"'

        self._write(f"<template {attrs}>")
        self.indent += 1
        for xpath in patch.xpath_patches:
            self._compile_xpath(xpath, scope)
        self.indent -= 1
        self._write("</template>")
        self._write("")

    def _compile_copy(self, copy: CopyDef, scope: dict[str, str]) -> None:
        self._write(
            f'<template t-name="{copy.alias}" t-inherit="{copy.source}" t-inherit-mode="primary">'
        )
        self.indent += 1
        for xpath in copy.xpath_patches:
            self._compile_xpath(xpath, scope)
        self.indent -= 1
        self._write("</template>")
        self._write("")

    def _compile_xpath(self, xpath: XpathPatch, scope: dict[str, str]) -> None:
        self._write(f'<xpath expr="{_esc(xpath.expr)}" position="{xpath.position.value}">')
        self.indent += 1
        if xpath.position.value == "attributes":
            self._compile_xpath_attributes(xpath.children)
        else:
            for child in xpath.children:
                self._compile_node(child, scope)
        self.indent -= 1
        self._write("</xpath>")

    def _compile_xpath_attributes(self, children: list[Any]) -> None:
        """position="attributes" : le moteur QWeb (xweb/engine/inherit.py::
        extract_patch) lit exclusivement des <attribute name="X">Y</attribute>
        — jamais un élément <a X="Y"/>. Bug réel trouvé en enregistrant une
        vraie patch xdsl pour la première fois : l'ancienne sortie
        s'enregistrait sans la moindre erreur mais l'opération ne posait
        aucun attribut, silencieusement (extract_patch ne cherche QUE des
        enfants <attribute>, xp.findall("attribute") — un <a .../> lui est
        invisible)."""
        for child in children:
            if not isinstance(child, Element):
                raise CompileError(
                    'xpath { attributes: ... } attend un élément dont les attributs '
                    'deviennent ceux posés — ex. attributes: a { disabled: "true" }'
                )
            for attr in child.attributes:
                value = attr.value if isinstance(attr.value, str) else str(attr.value)
                self._write(f'<attribute name="{_esc(attr.name)}">{_esc(value)}</attribute>')

    def _compile_node(self, node: Any, scope: dict[str, str]) -> None:
        if isinstance(node, IfBlock):
            self._compile_if(node, scope)
        elif isinstance(node, ForLoop):
            self._compile_for(node, scope)
        elif isinstance(node, Assignment):
            self._compile_assignment(node)
        elif isinstance(node, TextNode):
            self._compile_text(node)
        elif isinstance(node, SlotNode):
            self._write('<t t-out="slot"/>')
        elif isinstance(node, Element):
            self._compile_element(node, scope)
        elif isinstance(node, str):
            self._write(_esc(node))

    def _compile_if(self, node: IfBlock, scope: dict[str, str]) -> None:
        # Forme fratrie : <t t-if>…</t> <t t-elif>…</t> <t t-else>…</t>,
        # la chaîne est résolue par balayage des siblings (xweb/engine/compiler.py).
        self._write(f'<t t-if="{_esc(node.condition)}">')
        self.indent += 1
        for child in node.children:
            self._compile_node(child, scope)
        self.indent -= 1
        self._write("</t>")

        for condition, children in node.elif_blocks:
            self._write(f'<t t-elif="{_esc(condition)}">')
            self.indent += 1
            for child in children:
                self._compile_node(child, scope)
            self.indent -= 1
            self._write("</t>")

        if node.else_children:
            self._write('<t t-else="1">')
            self.indent += 1
            for child in node.else_children:
                self._compile_node(child, scope)
            self.indent -= 1
            self._write("</t>")

    def _compile_for(self, node: ForLoop, scope: dict[str, str]) -> None:
        self._write(f'<t t-foreach="{_esc(node.iterable)}" t-as="{node.variable}">')
        self.indent += 1
        for child in node.children:
            self._compile_node(child, scope)
        self.indent -= 1
        self._write("</t>")

    def _compile_assignment(self, node: Assignment) -> None:
        directive = "t-default" if node.default else "t-value"
        self._write(f'<t t-set="{node.name}" {directive}="{_esc(node.value)}"/>')

    def _compile_text(self, node: TextNode) -> None:
        if node.translate:
            if node.literal:
                self._write(f'<t t-tr="1">{_esc(node.content)}</t>')
            else:
                self._write(f'<t t-out="tr({node.content})"/>')
        elif node.raw:
            self._write(f'<t t-out="{_esc(node.content)}"/>')
        elif node.literal:
            self._write(_esc(node.content))
        else:
            self._write(f'<t t-esc="{_esc(node.content)}"/>')

    def _compile_element(self, node: Element, scope: dict[str, str]) -> None:
        qualified = scope.get(node.tag)
        if qualified is not None:
            self._compile_component_call(node, qualified, scope)
            return

        # Composant défini dans le même fichier (t-name local dotted) — appel
        # direct par son nom complet, ex. xweb.card { } (doc "Slots").
        if node.tag in self._local_template_names:
            self._compile_component_call(node, node.tag, scope)
            return

        self._compile_raw_element(node, scope)

    def _compile_component_call(
        self, node: Element, qualified: str, scope: dict[str, str]
    ) -> None:
        attrs, channel = self._resolve_use_channel(node.attributes)
        attrs, ep, use_id = self._resolve_use(attrs)
        extra_attrs: list[Attribute] = []
        if ep is not None:
            extra_attrs = self._endpoint_attrs(ep, use_id)
            if qualified == "xweb.form" and ep.method in ("POST", "PUT", "PATCH", "DELETE"):
                # xweb.form pose déjà son propre csrf_token en interne
                # (xweb/components/form.xml) — juste lui transmettre le
                # vrai jeton de la page, jamais un enfant en plus.
                extra_attrs.append(Attribute(name="token", value="csrf_token", dynamic=True))

        props = self._build_component_props(attrs + extra_attrs)
        suffix = (" " + props) if props else ""

        if not node.children:
            self._write(f'<t t-call="{qualified}"{suffix}/>')
        else:
            self._write(f'<t t-call="{qualified}"{suffix}>')
            self.indent += 1
            for child in node.children:
                self._compile_node(child, scope)
            self.indent -= 1
            self._write("</t>")

        if ep is not None:
            self._write_endpoint_scaffolding(ep, use_id)
        if channel is not None:
            self._write_channel_bootstrap(channel)

    def _compile_raw_element(self, node: Element, scope: dict[str, str]) -> None:
        attrs, channel = self._resolve_use_channel(node.attributes)
        attrs, ep, use_id = self._resolve_use(attrs)
        extra_attrs: list[Attribute] = []
        inject_csrf = False
        if ep is not None:
            extra_attrs = self._endpoint_attrs(ep, use_id)
            inject_csrf = node.tag == "form" and ep.method in ("POST", "PUT", "PATCH", "DELETE")

        html_attrs = self._build_html_attrs(attrs + extra_attrs)
        void = node.void or node.tag in VOID_ELEMENTS

        if void or (not node.children and not inject_csrf):
            self._write(f"<{node.tag}{html_attrs}/>")
        else:
            self._write(f"<{node.tag}{html_attrs}>")
            self.indent += 1
            if inject_csrf:
                self._write('<t t-call="xweb.csrf" t-att-token="csrf_token"/>')
            for child in node.children:
                self._compile_node(child, scope)
            self.indent -= 1
            self._write(f"</{node.tag}>")

        if ep is not None:
            self._write_endpoint_scaffolding(ep, use_id)
        if channel is not None:
            self._write_channel_bootstrap(channel)

    # -------------------------------------------------------------------------
    # `use: nom` — expansion d'un endpoint en attributs hx-*/_hyperscript
    # -------------------------------------------------------------------------

    def _resolve_use(
        self, attrs: list[Attribute]
    ) -> tuple[list[Attribute], EndpointDef | None, str]:
        """Sépare un éventuel attribut `use: nom` du reste, résout
        l'endpoint (CompileError si le nom n'a jamais été déclaré — jamais
        un bouton inerte silencieux) et alloue un identifiant unique pour
        cet usage (`{nom}-{compteur}` — le même endpoint peut être utilisé
        par plusieurs éléments dans un même fichier, chacun a besoin de
        ses propres ids DOM pour l'indicateur/les blocs onsuccess-onerror)."""
        remaining: list[Attribute] = []
        use_name: str | None = None
        for attr in attrs:
            if attr.name == "use" and isinstance(attr.value, str):
                use_name = attr.value
                continue
            remaining.append(attr)
        if use_name is None:
            return attrs, None, ""
        ep = self._endpoints.get(use_name)
        if ep is None:
            raise CompileError(
                f"use: {use_name!r} référence un endpoint jamais déclaré "
                f"(endpoints connus : {sorted(self._endpoints) or 'aucun'})"
            )
        self._use_counter += 1
        use_id = f"{ep.name}-{self._use_counter}"
        return remaining, ep, use_id

    def _endpoint_attrs(self, ep: EndpointDef, use_id: str) -> list[Attribute]:
        """Construit les attributs hx-*/_hyperscript que `use: {ep.name}`
        ajoute à l'élément porteur."""
        attrs: list[Attribute] = []
        method = ep.method.lower()
        attrs.append(
            Attribute(name=f"hx-{method}", value=ep.url, interpolated="${" in ep.url)
        )
        if ep.headers:
            import json as _json

            # ATTENTION (piège réel, pas théorique) : `headers` ne fait que
            # poser des en-têtes HTTP — ça ne change PAS la sérialisation du
            # corps de la requête. htmx encode toujours les champs d'un
            # <form> en application/x-www-form-urlencoded par défaut ; poser
            # `"Content-Type": "application/json"` ici étiquette donc un
            # corps form-encodé comme JSON sans le convertir, et une route
            # qui appelle request.json() échoue. Convertir en JSON réel
            # demande l'extension htmx `json-enc` (non vendorisée dans ce
            # projet, xweb/static/ ne l'a pas) — sans elle, laisser la route
            # lire des données de formulaire normales (request.form()),
            # comme partout ailleurs dans ce repo.
            attrs.append(Attribute(name="hx-headers", value=_json.dumps(ep.headers)))
        if ep.onloading:
            attrs.append(Attribute(name="hx-indicator", value=f"#{use_id}-indicator"))
        if ep.receive.kind == "json":
            # Une réponse JSON n'est JAMAIS du HTML à injecter dans le DOM —
            # sans ce hx-swap="none", htmx applique son comportement par
            # défaut (remplacer l'innerHTML de l'élément DÉCLENCHEUR par le
            # corps brut de la réponse) et le texte JSON écraserait le
            # formulaire/bouton lui-même. Le vrai rendu passe par
            # onsuccess/onerror (précompilés) + receive.target (aller-retour
            # serveur), jamais par un swap direct de la réponse JSON.
            attrs.append(Attribute(name="hx-swap", value="none"))

        script = self._endpoint_hyperscript(ep, use_id)
        if script:
            attrs.append(Attribute(name="_", value=script))
        return attrs

    def _endpoint_hyperscript(self, ep: EndpointDef, use_id: str) -> str:
        """Écoute htmx:afterRequest sur l'élément porteur et révèle le bon
        bloc pré-compilé (onsuccess/onerror, cachés par défaut — voir
        _write_endpoint_scaffolding) selon `event.detail.successful`. Au
        succès, diffuse aussi l'événement `receive.event` (par défaut
        `{nom}:done`) vers `receive.target` — c'est à CET élément
        d'écouter avec un vrai `hx-trigger` pour se re-rendre depuis le
        serveur (même idiome que calendar:select -> datepicker.xml,
        jamais de rendu JSON côté client, QWeb est server-only)."""
        if not (ep.onsuccess or ep.onerror or ep.receive.target):
            return ""
        success_actions: list[str] = []
        error_actions: list[str] = []
        if ep.onsuccess:
            success_actions.append(f"remove @hidden from #{use_id}-onsuccess")
        if ep.onerror:
            success_actions.append(f"add @hidden to #{use_id}-onerror")
            error_actions.append(f"remove @hidden from #{use_id}-onerror")
        if ep.onsuccess:
            error_actions.append(f"add @hidden to #{use_id}-onsuccess")
        if ep.receive.target:
            event_name = ep.receive.event or f"{ep.name}:done"
            success_actions.append(f"send {event_name} to {ep.receive.target}")
        if not success_actions and not error_actions:
            return ""
        lines = ["on htmx:afterRequest", "  if event.detail.successful"]
        lines += [f"    {a}" for a in success_actions] or ["    nop"]
        lines.append("  else")
        lines += [f"    {a}" for a in error_actions] or ["    nop"]
        lines.append("  end")
        return "\n".join(lines)

    def _write_endpoint_scaffolding(self, ep: EndpointDef, use_id: str) -> None:
        """Émet, juste après l'élément porteur, les blocs statiques
        pré-compilés pour onloading (classe htmx-indicator native — htmx
        gère lui-même l'opacité pendant la requête, aucun CSS à ajouter
        dans ce projet, vérifié dans xweb/static/htmx.min.js) et onsuccess/
        onerror (cachés par défaut via l'attribut `hidden`, révélés par le
        hyperscript de _endpoint_hyperscript). Contenu STATIQUE, compilé
        une fois pour toutes — pas de liaison aux champs de la réponse
        JSON dans ce v1 (voir docstring d'EndpointDef.onsuccess)."""
        if ep.onloading:
            self._write(f'<div id="{use_id}-indicator" class="htmx-indicator">')
            self.indent += 1
            for child in ep.onloading:
                self._compile_node(child, self._global_scope)
            self.indent -= 1
            self._write("</div>")
        if ep.onsuccess:
            self._write(f'<div id="{use_id}-onsuccess" hidden="hidden">')
            self.indent += 1
            for child in ep.onsuccess:
                self._compile_node(child, self._global_scope)
            self.indent -= 1
            self._write("</div>")
        if ep.onerror:
            self._write(f'<div id="{use_id}-onerror" hidden="hidden">')
            self.indent += 1
            for child in ep.onerror:
                self._compile_node(child, self._global_scope)
            self.indent -= 1
            self._write("</div>")

    # -------------------------------------------------------------------------
    # `use_channel: nom` — expansion d'un channel en <script> de bootstrap
    # xweb/static/live_channel.js
    # -------------------------------------------------------------------------

    def _resolve_use_channel(self, attrs: list[Attribute]) -> tuple[list[Attribute], ChannelDef | None]:
        """Sépare un éventuel attribut `use_channel: nom` du reste, résout
        le channel (CompileError si jamais déclaré — même posture que
        `use:`/l'endpoint correspondant, jamais un abonnement silencieusement
        absent)."""
        remaining: list[Attribute] = []
        channel_name: str | None = None
        for attr in attrs:
            if attr.name == "use_channel" and isinstance(attr.value, str):
                channel_name = attr.value
                continue
            remaining.append(attr)
        if channel_name is None:
            return attrs, None
        ch = self._channels.get(channel_name)
        if ch is None:
            raise CompileError(
                f"use_channel: {channel_name!r} référence un channel jamais déclaré "
                f"(channels connus : {sorted(self._channels) or 'aucun'})"
            )
        return remaining, ch

    def _write_channel_bootstrap(self, ch: ChannelDef) -> None:
        """Émet, juste après l'élément porteur de `use_channel:`, un
        <script> qui instancie xweb/static/live_channel.js::XwebLiveChannel
        — ce fichier DOIT être chargé par la page (même contrat que
        htmx.min.js/_hyperscript.min.js, jamais injecté ici). `<script>`
        brut plutôt que hyperscript : EventSource/WebSocket + dispatch est
        au-delà de ce qui est idiomatique en _hyperscript (même exception
        déjà faite dans live_channel.js/notifications.xml).

        Contenu 100% déterminé à la compilation (aucune donnée de requête/
        utilisateur — un channel est une déclaration statique comme
        `endpoint`), donc json.dumps() suffit à produire des littéraux JS
        sûrs : ce n'est PAS le même risque que l'interpolation ${...}
        RUNTIME dans un attribut `_`/`hx-vals` que les filtres `hs`/`js`
        protègent (_CODE_ATTR_FILTERS) — rien ici ne vient d'un utilisateur
        final ni d'une réponse serveur au moment de la compilation.

        onMessage, dans l'ordre : (1) valide `data` si `validate:` est posé
        (ignore le reste du handler si invalide — jamais une exception JS),
        (2) applique chaque `bind:` en textContent (jamais innerHTML, XSS —
        voir live_channel.js §Sécurité), (3) déclenche `refresh:` via
        `htmx.trigger()` (jamais un rendu de composant xweb côté client,
        même limite que `endpoint`/`receive` — QWeb n'a pas de runtime
        navigateur), (4) diffuse un vrai `CustomEvent` DOM sur `document`
        si `dispatch: true` est posé — la porte de sortie vers du
        hyperscript/JS arbitraire, DÉJÀ supporté ailleurs dans le DSL
        (attribut `_` sur n'importe quel élément) : `onmessage {}` reste
        une grammaire fermée, mais un `_: on {event} from document ...`
        sur n'importe quel élément récupère `event.detail.{channel,data}`
        et fait ce qu'il veut du DOM — jamais besoin d'ouvrir `onmessage {}`
        lui-même à du code arbitraire pour ça, (5) met en cache dans
        xweb/static/storage.js si `persist:` est posé."""
        import json as _json

        opts: dict[str, Any] = {"url": ch.url, "channels": ch.channels, "transport": ch.transport}
        if ch.connect_timeout_ms is not None:
            opts["connectTimeoutMs"] = ch.connect_timeout_ms

        lines = ["(function () {"]
        if ch.validate:
            schema = self._data_schemas.get(ch.validate)
            if schema is None:
                raise CompileError(
                    f"channel {ch.name!r} : validate: {ch.validate!r} référence un schéma "
                    f"`data` jamais déclaré (schémas connus : {sorted(self._data_schemas) or 'aucun'})"
                )
            # Colocalisé avec le bootstrap qui le consomme plutôt qu'un
            # passage global séparé : garantit que window.XWEB_SCHEMAS[nom]
            # existe avant que onMessage ne puisse jamais être invoqué (même
            # fonction synchrone, exécutée avant `new XwebLiveChannel`) —
            # xweb/static/validators.js ne lit jamais un schéma qu'un
            # `channel` n'a pas explicitement importé ici.
            lines.append("  window.XWEB_SCHEMAS = window.XWEB_SCHEMAS || {};")
            lines.append(f"  window.XWEB_SCHEMAS[{_json.dumps(ch.validate)}] = {_json.dumps(_schema_to_json(schema))};")
        lines += [
            f"  var _xwebChannelOpts = {_json.dumps(opts)};",
            "  _xwebChannelOpts.onMessage = function (channel, data) {",
        ]
        if ch.validate:
            lines.append(
                f"    if (window.XwebValidate && !window.XwebValidate({_json.dumps(ch.validate)}, data).valid) return;"
            )
        for selector, field_name in ch.onmessage.bindings:
            lines.append(
                f"    (function () {{ var el = document.querySelector({_json.dumps(selector)}); "
                f"if (el && data) el.textContent = data[{_json.dumps(field_name)}]; }})();"
            )
        event_name = ch.onmessage.event or f"{ch.name}:message"
        if ch.onmessage.refresh:
            lines.append(
                f"    (function () {{ var t = document.querySelector({_json.dumps(ch.onmessage.refresh)}); "
                f"if (t && window.htmx) window.htmx.trigger(t, {_json.dumps(event_name)}, data); }})();"
            )
        if ch.onmessage.dispatch:
            lines.append(
                f"    document.dispatchEvent(new CustomEvent({_json.dumps(event_name)}, "
                f"{{ detail: {{ channel: channel, data: data }} }}));"
            )
        if ch.persist:
            lines.append(f"    if (window.XwebStorage) window.XwebStorage.set({_json.dumps(ch.persist)}, data);")
        lines += [
            "  };",
            "  if (window.XwebLiveChannel) { new window.XwebLiveChannel(_xwebChannelOpts); }",
            "  else { console.error('[xdsl] XwebLiveChannel introuvable — xweb/static/live_channel.js doit être chargé par la page'); }",
            "})();",
        ]

        self._write("<script>")
        self.indent += 1
        for line in lines:
            self._write(_esc(line))
        self.indent -= 1
        self._write("</script>")

    def _build_component_props(self, attrs: list[Attribute]) -> str:
        """Construit les attributs d'un <t t-call>.

        Règles (design spec) :
        - hx-* / _ : attribut statique sur le t-call
        - class : t-attf-extra_class (interpolation) — jamais t-attf-class :
          `class` est un mot-clé réservé Python, {{class}} dans la cible est
          une SyntaxError (xweb/engine/compiler._eval). La convention xweb
          (box/button/container) est la prop extra_class.
        - autres : t-att-* pour expr/bare, t-attf-* pour ${},
                   t-att-name="'val'" pour littéral string,
                   t-att-name="True"/"False" pour booléens.
        """
        parts: list[str] = []
        for attr in attrs:
            if isinstance(attr.value, list):
                # class: ["flex", expr] → t-attf-extra_class / t-attf-class
                name = "extra_class" if attr.name == "class" else attr.name
                parts.append(f't-attf-{name}="{_esc(self._class_tokens(attr.value))}"')
                continue
            if isinstance(attr.value, dict):
                parts.append(self._style_dict_to_xml_attr(attr.value))
                continue
            if attr.name.startswith("hx-") or attr.name == "_":
                if attr.interpolated:
                    filt = _CODE_ATTR_FILTERS.get(attr.name)
                    parts.append(f't-attf-{attr.name}="{_esc(_to_qweb_interp(attr.value, filt))}"')
                else:
                    parts.append(f'{attr.name}="{_esc(attr.value)}"')
            elif attr.name == "class":
                if attr.dynamic:
                    parts.append(f't-att-extra_class="{_esc(attr.value)}"')
                else:
                    parts.append(f't-attf-extra_class="{_esc(_to_qweb_interp(attr.value))}"')
            elif attr.interpolated:
                parts.append(f't-attf-{attr.name}="{_esc(_to_qweb_interp(attr.value))}"')
            elif attr.dynamic:
                parts.append(f't-att-{attr.name}="{_esc(attr.value)}"')
            else:
                # Valeur statique : string → Python-quoted, bool → True/False, number → raw
                val = attr.value
                if val in ("true", "false"):
                    python_bool = "True" if val == "true" else "False"
                    parts.append(f't-att-{attr.name}="{python_bool}"')
                elif val.replace(".", "").replace("-", "").isdigit():
                    parts.append(f't-att-{attr.name}="{_esc(val)}"')
                else:
                    inner = val.replace("'", "\\'")
                    parts.append(f't-att-{attr.name}="{_esc_expr(chr(39) + inner + chr(39))}"')
        return " ".join(parts)

    def _build_html_attrs(self, attrs: list[Attribute]) -> str:
        """Construit les attributs HTML littéraux d'un élément."""
        if not attrs:
            return ""

        parts: list[str] = []
        for attr in attrs:
            if isinstance(attr.value, list):
                parts.append(f't-attf-class="{_esc(self._class_tokens(attr.value))}"')
                continue
            if isinstance(attr.value, dict):
                parts.append(self._style_dict_to_xml_attr(attr.value))
                continue
            if attr.interpolated:
                filt = _CODE_ATTR_FILTERS.get(attr.name)
                parts.append(f't-attf-{attr.name}="{_esc(_to_qweb_interp(attr.value, filt))}"')
            elif attr.dynamic:
                parts.append(f't-att-{attr.name}="{_esc(attr.value)}"')
            else:
                # Valeur statique → attribut HTML brut
                parts.append(f'{attr.name}="{_esc(attr.value)}"')
        return " " + " ".join(parts)