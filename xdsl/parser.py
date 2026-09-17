"""Parser xdsl — Lexer + Parser récursif descendant.

Le lexer tokenise le source en tokens.
Le parser consomme les tokens et construit l'AST.

Usage:
    parser = Parser(source)
    ast = parser.parse()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# =============================================================================
# AST Nodes
# =============================================================================

class Position(Enum):
    """Positions XPath pour le patching."""

    INSIDE = "inside"
    REPLACE = "replace"
    BEFORE = "before"
    AFTER = "after"
    ATTRIBUTES = "attributes"


@dataclass
class Import:
    """Import d'un composant."""

    names: list[str]
    source: str
    relative: bool = False


@dataclass
class Props:
    """Définition de props d'un composant."""

    defaults: dict[str, Any] = field(default_factory=dict)


@dataclass
class Style:
    """Bloc CSS natif."""

    css: str


@dataclass
class AttributeValue:
    """Valeur d'attribut : chaîne littérale ou expression.

    - `quoted=True` : un token STRING (littéral). S'il contient `${...}`,
      il est interpolé côté serveur.
    - `quoted=False` : une expression Python à évaluer.
    """

    value: str
    quoted: bool = False


@dataclass
class Attribute:
    """Attribut d'un élément (statique ou dynamique).

    `value` peut être :
    - `str` : forme historique (drapeaux `dynamic`/`interpolated`).
    - `list[AttributeValue]` : liste ``class: ["a", expr]``.
    - `dict[str, AttributeValue]` : dict ``style: { p: v }``.
    """

    name: str
    value: str | list[AttributeValue] | dict[str, AttributeValue]
    dynamic: bool = False  # True = t-att-*, False = attribut statique
    interpolated: bool = False  # True = t-attf-* (contient ${...})


@dataclass
class XpathPatch:
    """Patch XPath sur un nœud."""

    expr: str
    position: Position
    children: list[Any] = field(default_factory=list)


@dataclass
class ComponentDef:
    """Définition d'un composant."""

    name: str
    inherits: str | None = None
    inherit_mode: str | None = None  # "extension" ou "primary"
    priority: int = 0
    imports: list[Import] = field(default_factory=list)
    props: Props | None = None
    style: Style | None = None
    children: list[Any] = field(default_factory=list)


@dataclass
class PatchDef:
    """Définition d'un patch (extension)."""

    target: str
    priority: int = 0
    xpath_patches: list[XpathPatch] = field(default_factory=list)


@dataclass
class CopyDef:
    """Définition d'une copie (primary) — `copy source as alias { xpath "..." { ... } }`.

    UNIQUEMENT des blocs `xpath`, jamais des éléments littéraux : le moteur
    QWeb (xweb/engine/inherit.py::_resolve_primary/extract_patch) ne lit
    QUE les enfants <xpath> d'un <template t-inherit-mode="primary"> — tout
    le reste du corps serait silencieusement ignoré (bug réel trouvé en
    enregistrant une vraie copie pour la première fois : le corps
    "personnalisé" ne changeait RIEN au rendu, la cible ressortait telle
    quelle). `_parse_copy` refuse donc explicitement tout enfant qui n'est
    pas un `xpath` plutôt que de compiler quelque chose de mort."""

    source: str
    alias: str
    xpath_patches: list[XpathPatch] = field(default_factory=list)


@dataclass
class IfBlock:
    """Bloc conditionnel."""

    condition: str
    children: list[Any] = field(default_factory=list)
    elif_blocks: list[tuple[str, list[Any]]] = field(default_factory=list)
    else_children: list[Any] = field(default_factory=list)


@dataclass
class ForLoop:
    """Boucle for."""

    variable: str
    iterable: str
    children: list[Any] = field(default_factory=list)


@dataclass
class Assignment:
    """Affectation de variable."""

    name: str
    value: str
    default: bool = False  # True = t-default, False = t-value


@dataclass
class TextNode:
    """Nœud texte (échappé par défaut)."""

    content: str
    raw: bool = False  # True = t-out, False = t-esc
    translate: bool = False  # True = t-tr
    literal: bool = False  # True = texte brut entre guillemets (pas d'évaluation Python)


@dataclass
class SlotNode:
    """Slot (contenu passé par le parent)."""
    pass


@dataclass
class Element:
    """Élément HTML."""

    tag: str
    attributes: list[Attribute] = field(default_factory=list)
    children: list[Any] = field(default_factory=list)
    void: bool = False  # True = auto-fermant


@dataclass
class DataField:
    """Un champ d'un schéma `data` — type + règles de validation (@decorators,
    xweb/engine — pardon, xdsl/validators.py::BUILTIN_VALIDATORS). Un champ
    sans décorateur `@required` est optionnel (Required est juste une règle
    de validation parmi d'autres, jamais un flag séparé — cohérent avec
    xdsl/validators.py où "required" est déjà une entrée de BUILTIN_VALIDATORS,
    pas un cas à part)."""

    name: str
    # string|int|float|bool|list|dict — voir validators.OneOf.type_map.
    # PAS nommé `type` : le sérialiseur JSON (xdsl/serialize.py) réserve
    # cette clé comme discriminant de nœud — trouvé en cassant le round-
    # trip .xdsl.json pour de vrai (`ReceiveSpec.type` a fait la même
    # erreur, voir juste plus bas).
    value_type: str = "string"
    decorators: list[tuple[str, list[Any]]] = field(default_factory=list)  # [("required", []), ("min_length", [3])]


@dataclass
class DataSchemaDef:
    """Définition `data nom { champ: type @decorateurs... }` — schéma de
    validation réutilisable, référencé par son nom depuis `endpoint.send`."""

    name: str
    fields: list[DataField] = field(default_factory=list)


@dataclass
class ReceiveSpec:
    """Bloc `receive { ... }` d'un endpoint — décrit la réponse attendue.

    `target`/`event` ne pilotent JAMAIS un rendu côté client (QWeb n'a pas
    de runtime navigateur, xweb/engine/ est server-only) : au succès, le
    compilateur ajoute `send {event} to {target}` à la suite du hyperscript
    onsuccess — c'est à l'élément CIBLE d'écouter cet événement avec un vrai
    `hx-trigger="{event} from:body"` (même idiome que calendar:select ->
    datepicker.xml, ou xpulse) pour se re-rendre depuis le SERVEUR. `schema`
    documente juste la forme JSON attendue (nom d'un `data`/futur schéma de
    réponse) — pas encore utilisé pour piloter quoi que ce soit.

    `kind`, PAS `type` : même piège que DataField.value_type, la clé
    `"type"` est réservée par le sérialiseur JSON comme discriminant de
    nœud (xdsl/serialize.py) — un champ dataclass qui s'appelle aussi
    `type` écrase silencieusement le discriminant à la sérialisation,
    cassant la désérialisation (`AttributeError: 'dict' object has no
    attribute 'target'`), trouvé en testant le round-trip .xdsl.json pour
    de vrai."""

    kind: str = "json"
    schema: str | None = None
    target: str | None = None
    event: str | None = None


@dataclass
class EndpointDef:
    """Définition `endpoint nom { ... }` — requête réseau déclarative,
    consommée via la prop `use: nom` sur un `form`/`button`/tout élément
    (xdsl/compiler.py — expansion en hx-*/_hyperscript à la compilation,
    jamais un t-call : un endpoint n'émet aucun XML par lui-même)."""

    name: str
    method: str = "GET"
    url: str = ""
    # nom d'un `data` — documente la forme envoyée, exploitable côté serveur
    # via xdsl.api.extract_schemas(). PAS ENCORE désucré en attributs HTML5
    # natifs (required/type=email/…) sur les <input> correspondants — v1,
    # voir docs/dsl-design.md#limites-connues-v1.
    send: str | None = None
    headers: dict[str, Any] = field(default_factory=dict)
    # "cookie" est un no-op délibéré au compilateur : l'auth de ce projet
    # est 100% cookies HttpOnly (access_token/refresh_token, CLAUDE.md#auth)
    # envoyés automatiquement par le navigateur en same-origin, rien à
    # ajouter. Toute AUTRE valeur (ex. "bearer") est acceptée par le parser
    # mais n'a AUCUN effet à la compilation aujourd'hui — pas encore câblé.
    auth: str | None = None
    receive: ReceiveSpec = field(default_factory=ReceiveSpec)
    onloading: list[Any] = field(default_factory=list)  # nœuds DSL — rendu pré-compilé, révélé via hx-indicator
    onsuccess: list[Any] = field(default_factory=list)  # nœuds DSL — rendu pré-compilé, révélé sur htmx:afterRequest
    onerror: list[Any] = field(default_factory=list)


@dataclass
class ChannelOnMessage:
    """Ce qui se passe à la réception d'un message — voir ChannelDef.
    AUCUN rendu de composant xweb ici, jamais : QWeb n'a pas de runtime
    navigateur (même décision qu'EndpointDef.onsuccess/receive). Trois
    actions, toutes faisables sans moteur de rendu côté client : déclencher
    un aller-retour serveur (refresh, comme receive.target/event des
    endpoints), écrire un champ brut en textContent (bind — jamais
    innerHTML, voir live_channel.js §Sécurité), ou diffuser un vrai
    CustomEvent DOM (dispatch) — la porte de sortie vers du hyperscript/JS
    arbitraire DÉJÀ supporté ailleurs dans le DSL (attribut `_` sur
    n'importe quel élément), sans faire de `onmessage {}` lui-même une
    grammaire ouverte à du code arbitraire."""

    refresh: str | None = None  # sélecteur CSS à rafraîchir via htmx.trigger(el, event)
    event: str | None = None  # nom d'event partagé par refresh/dispatch — défaut "{channel}:message"
    dispatch: bool = False  # document.dispatchEvent(CustomEvent(event, {detail:{channel,data}}))
    bindings: list[tuple[str, str]] = field(default_factory=list)  # [(sélecteur, nom de champ), ...]


@dataclass
class ChannelDef:
    """Définition `channel nom { ... }` — abonnement SSE/WS déclaratif,
    consommé via la prop `use_channel: nom` sur n'importe quel élément
    (xdsl/compiler.py — expansion en <script> de bootstrap
    xweb/static/live_channel.js, jamais un t-call : un channel n'émet pas
    de XML de composant par lui-même, comme `endpoint`)."""

    name: str
    url: str = ""
    channels: list[str] = field(default_factory=list)
    transport: str = "auto"  # "auto" | "sse" | "ws" — voir live_channel.js
    connect_timeout_ms: int | None = None
    # Nom d'un `data` — valide `data` reçu AVANT d'appliquer les bindings
    # (jamais avant `refresh`, qui ne lit aucun champ individuel). Un
    # message qui ne valide pas est ignoré pour les bindings, jamais une
    # exception JS — même posture "jamais un crash silencieux côté
    # rendu, mais jamais un crash bruyant non plus" que le reste du projet.
    validate: str | None = None
    # Clé xweb/static/storage.js (namespace "xweb") sous laquelle le
    # DERNIER `data` reçu est mis en cache à chaque message — relu au
    # prochain chargement de page, avant même que le channel ait eu le
    # temps de se reconnecter. None = pas de cache (défaut).
    persist: str | None = None
    onmessage: ChannelOnMessage = field(default_factory=ChannelOnMessage)


@dataclass
class AST:
    """Racine de l'AST."""

    components: list[ComponentDef] = field(default_factory=list)
    patches: list[PatchDef] = field(default_factory=list)
    copies: list[CopyDef] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    data_schemas: list[DataSchemaDef] = field(default_factory=list)
    endpoints: list[EndpointDef] = field(default_factory=list)
    channels: list[ChannelDef] = field(default_factory=list)
    children: list[Any] = field(default_factory=list)
    layout: str | None = None  # @include "xweb.shell"


# =============================================================================
# Tokens
# =============================================================================

class TokenKind(Enum):
    """Types de tokens."""

    # Mots-clés
    COMPONENT = auto()
    IMPORT = auto()
    FROM = auto()
    IF = auto()
    ELIF = auto()
    ELSE = auto()
    FOR = auto()
    IN = auto()
    PATCH = auto()
    COPY = auto()
    AS = auto()
    PRIORITY = auto()
    SLOT = auto()
    RAW = auto()
    TR = auto()
    STYLE = auto()
    PROPS = auto()
    XPATH = auto()
    INSIDE = auto()
    REPLACE = auto()
    BEFORE = auto()
    AFTER = auto()
    ATTRIBUTES = auto()
    EXTENSION = auto()
    PRIMARY = auto()
    INCLUDE = auto()  # @include
    DATA = auto()  # data nom { champ: type @decorateurs }
    ENDPOINT = auto()  # endpoint nom { ... } — requête réseau déclarative
    CHANNEL = auto()  # channel nom { ... } — abonnement SSE/WS déclaratif
    AT = auto()  # @ — préfixe d'un décorateur de validation (@required, @min_length(3))

    # Identifiants et littéraux
    IDENT = auto()  # nom de variable, de composant, de tag
    STRING = auto()  # "texte" ou 'texte'
    NUMBER = auto()  # 42, 3.14
    INTERPOLATION = auto()  # ${expr}
    RAW_TEXT = auto()  # texte brut entre accolades
    HYPERSCRIPT_SCRIPT = auto()  # attribut _ : script hyperscript brut

    # Opérateurs et séparateurs
    LBRACE = auto()  # {
    RBRACE = auto()  # }
    LPAREN = auto()  # (
    RPAREN = auto()  # )
    LBRACKET = auto()  # [
    RBRACKET = auto()  # ]
    COLON = auto()  # :
    COMMA = auto()  # ,
    ASSIGN = auto()  # =
    ASSIGN_DEFAULT = auto()  # ?=
    DOT = auto()  # .
    SLASH = auto()  # /
    ARROW = auto()  # ->
    PLUS = auto()  # +
    MINUS = auto()  # -
    STAR = auto()  # *
    PERCENT = auto()  # %
    PIPE = auto()  # | — chaînage de filtre QWeb (xweb/engine/filters.py)
    QUESTION = auto()  # ? — ternaire (cond ? si_vrai : si_faux)
    EQ = auto()  # ==
    NE = auto()  # !=
    LE = auto()  # <=
    GE = auto()  # >=
    LT = auto()  # <
    GT = auto()  # >

    # Spéciaux
    NEWLINE = auto()
    EOF = auto()


# Mots-clés réservés
KEYWORDS: dict[str, TokenKind] = {
    "component": TokenKind.COMPONENT,
    "import": TokenKind.IMPORT,
    "from": TokenKind.FROM,
    "if": TokenKind.IF,
    "elif": TokenKind.ELIF,
    "else": TokenKind.ELSE,
    "for": TokenKind.FOR,
    "in": TokenKind.IN,
    "patch": TokenKind.PATCH,
    "copy": TokenKind.COPY,
    "as": TokenKind.AS,
    "priority": TokenKind.PRIORITY,
    "slot": TokenKind.SLOT,
    "raw": TokenKind.RAW,
    "tr": TokenKind.TR,
    "style": TokenKind.STYLE,
    "props": TokenKind.PROPS,
    "xpath": TokenKind.XPATH,
    "inside": TokenKind.INSIDE,
    "replace": TokenKind.REPLACE,
    "before": TokenKind.BEFORE,
    "after": TokenKind.AFTER,
    "attributes": TokenKind.ATTRIBUTES,
    "extension": TokenKind.EXTENSION,
    "primary": TokenKind.PRIMARY,
    "data": TokenKind.DATA,
    "endpoint": TokenKind.ENDPOINT,
    "channel": TokenKind.CHANNEL,
}

# Tailles des espaces d'indentation
TAB_SIZE = 4


@dataclass
class Token:
    """Un token du lexer."""

    kind: TokenKind
    value: str
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.kind.name}, {self.value!r}, L{self.line}:{self.col})"


class LexerError(Exception):
    """Erreur de lexing."""

    def __init__(self, message: str, line: int, col: int):
        super().__init__(f"L{line}:{col}: {message}")
        self.line = line
        self.col = col


class Lexer:
    """Tokenise le source xdsl en tokens.

    Usage:
        lexer = Lexer(source)
        tokens = lexer.tokenize()
    """

    def __init__(self, source: str, filename: str = "<stdin>"):
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """Tokenise le source et retourne la liste des tokens."""
        while self.pos < len(self.source):
            self._skip_whitespace_except_newline()

            if self.pos >= len(self.source):
                break

            char = self.source[self.pos]

            # Nouvelle ligne
            if char == "\n":
                self._emit(TokenKind.NEWLINE, "\n")
                self.pos += 1
                self.line += 1
                self.col = 1
                continue

            # Commentaires
            if char == "/" and self._peek(1) == "/":
                self._skip_line_comment()
                continue
            if char == "/" and self._peek(1) == "*":
                self._skip_block_comment()
                continue

            # Chaines de caractères
            if char == '"' or char == "'":
                self._read_string(char)
                continue

            # Interpolation ${...}
            if char == "$" and self._peek(1) == "{":
                self._read_interpolation()
                continue

            # Nombres
            if char.isdigit() or (char == "-" and self._peek(1).isdigit()):
                self._read_number()
                continue

            # Hyperscript brut : "_ : ..." (ligne) ou "_ { ... }" (bloc).
            # Capturé avant l'analyse des identifiants pour qu'aucun mot-clé
            # hyperscript (on, click, wait…) ne soit tokenisé comme du DSL.
            if char == "_" and self._peek_next_non_space() in (":", "{"):
                self._read_hyperscript()
                continue

            # Identifiants et mots-clés
            if char.isalpha() or char == "_":
                self._read_ident()
                continue

            # Opérateurs et séparateurs
            if char == "{":
                self._emit(TokenKind.LBRACE, "{")
                self.pos += 1
                self.col += 1
                continue
            if char == "}":
                self._emit(TokenKind.RBRACE, "}")
                self.pos += 1
                self.col += 1
                continue
            if char == "(":
                self._emit(TokenKind.LPAREN, "(")
                self.pos += 1
                self.col += 1
                continue
            if char == ")":
                self._emit(TokenKind.RPAREN, ")")
                self.pos += 1
                self.col += 1
                continue
            if char == "[":
                self._emit(TokenKind.LBRACKET, "[")
                self.pos += 1
                self.col += 1
                continue
            if char == "]":
                self._emit(TokenKind.RBRACKET, "]")
                self.pos += 1
                self.col += 1
                continue
            if char == ":":
                self._emit(TokenKind.COLON, ":")
                self.pos += 1
                self.col += 1
                continue
            if char == ",":
                self._emit(TokenKind.COMMA, ",")
                self.pos += 1
                self.col += 1
                continue
            if char == ".":
                self._emit(TokenKind.DOT, ".")
                self.pos += 1
                self.col += 1
                continue
            if char == "/":
                self._emit(TokenKind.SLASH, "/")
                self.pos += 1
                self.col += 1
                continue
            if char == "?" and self._peek(1) == "=":
                self._emit(TokenKind.ASSIGN_DEFAULT, "?=")
                self.pos += 2
                self.col += 2
                continue
            if char == "-" and self._peek(1) == ">":
                self._emit(TokenKind.ARROW, "->")
                self.pos += 2
                self.col += 2
                continue

            # Opérateurs de comparaison — 2 caractères AVANT les 1 caractère,
            # sinon "==" deviendrait "=" + "=" et "&lt;=" un "&lt;" puis "="
            # (chaque caractère inconnu était avalé silencieusement).
            if char == "=" and self._peek(1) == "=":
                self._emit(TokenKind.EQ, "==")
                self.pos += 2
                self.col += 2
                continue
            if char == "!" and self._peek(1) == "=":
                self._emit(TokenKind.NE, "!=")
                self.pos += 2
                self.col += 2
                continue
            if char == "<" and self._peek(1) == "=":
                self._emit(TokenKind.LE, "<=")
                self.pos += 2
                self.col += 2
                continue
            if char == ">" and self._peek(1) == "=":
                self._emit(TokenKind.GE, ">=")
                self.pos += 2
                self.col += 2
                continue
            if char == "<":
                self._emit(TokenKind.LT, "<")
                self.pos += 1
                self.col += 1
                continue
            if char == ">":
                self._emit(TokenKind.GT, ">")
                self.pos += 1
                self.col += 1
                continue
            if char == "?":
                self._emit(TokenKind.QUESTION, "?")
                self.pos += 1
                self.col += 1
                continue
            if char == "=":
                self._emit(TokenKind.ASSIGN, "=")
                self.pos += 1
                self.col += 1
                continue

            # Opérateurs arithmétiques (préservés dans les expressions)
            if char == "+":
                self._emit(TokenKind.PLUS, "+")
                self.pos += 1
                self.col += 1
                continue
            if char == "-" and not (self._peek(1).isdigit()):
                self._emit(TokenKind.MINUS, "-")
                self.pos += 1
                self.col += 1
                continue
            if char == "*":
                self._emit(TokenKind.STAR, "*")
                self.pos += 1
                self.col += 1
                continue
            if char == "%":
                self._emit(TokenKind.PERCENT, "%")
                self.pos += 1
                self.col += 1
                continue
            if char == "|":
                self._emit(TokenKind.PIPE, "|")
                self.pos += 1
                self.col += 1
                continue

            # Directive @include
            if char == "@":
                if self._peek(1) == "i" and self._peek(2) == "n":
                    # Lit le mot entier après @ (jusqu'à non-alphanum)
                    start = self.pos + 1
                    end = start
                    while end < len(self.source) and (
                        self.source[end].isalnum() or self.source[end] in ("_", "-")
                    ):
                        end += 1
                    word = self.source[start:end]
                    if word == "include":
                        self._emit(TokenKind.INCLUDE, "@include")
                        self.pos = end
                        self.col += end - start + 1
                        continue
                # @ non suivi d'"include" : décorateur de validation
                # (@required, @min_length(3)…) — voir _parse_decorators.
                # Piège déjà trouvé une fois avec `|` (xdsl/parser.py, voir
                # TokenKind.PIPE) : un caractère "ignoré silencieusement"
                # ici mangle toute syntaxe qui l'utilise plus tard sans la
                # moindre erreur — jamais recommencer ce pattern.
                self._emit(TokenKind.AT, "@")
                self.pos += 1
                self.col += 1
                continue

            # Caractère inconnu — on l'ignore
            self.pos += 1
            self.col += 1

        self._emit(TokenKind.EOF, "")
        return self.tokens

    def _peek(self, offset: int = 0) -> str:
        """Regarde le caractère à offset positionns devant."""
        idx = self.pos + offset
        if idx < len(self.source):
            return self.source[idx]
        return "\0"

    def _emit(self, kind: TokenKind, value: str) -> None:
        """Émet un token."""
        self.tokens.append(Token(kind, value, self.line, self.col))

    def _skip_whitespace_except_newline(self) -> None:
        """Ignore les espaces (sauf nouvelles lignes)."""
        while self.pos < len(self.source) and self.source[self.pos] in (" ", "\t", "\r"):
            self.pos += 1
            self.col += 1

    def _skip_line_comment(self) -> None:
        """Ignore un commentaire sur une ligne (// ...)."""
        while self.pos < len(self.source) and self.source[self.pos] != "\n":
            self.pos += 1
            self.col += 1

    def _skip_block_comment(self) -> None:
        """Ignore un commentaire multi-lignes (/* ... */)."""
        self.pos += 2  # saute /*
        self.col += 2
        while self.pos < len(self.source):
            if self.source[self.pos] == "*" and self._peek(1) == "/":
                self.pos += 2
                self.col += 2
                return
            if self.source[self.pos] == "\n":
                self.line += 1
                self.col = 1
            self.pos += 1
            self.col += 1

    def _read_string(self, quote: str) -> None:
        """Lit une chaine de caractères (simple ou double guillemet), multiligne possible."""
        start_line, start_col = self.line, self.col
        self.pos += 1  # saute le guillemet ouvrant
        self.col += 1
        value: list[str] = []

        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char == quote:
                self.pos += 1
                self.col += 1
                self._emit(TokenKind.STRING, "".join(value))
                return
            if char == "\\":
                # Gère les séquences d'échappement
                self.pos += 1
                self.col += 1
                escaped = self.source[self.pos] if self.pos < len(self.source) else ""
                escape_map = {"n": "\n", "t": "\t", "\\": "\\", "'": "'", '"': '"'}
                value.append(escape_map.get(escaped, escaped))
                self.pos += 1
                self.col += 1
            elif char == "\n":
                value.append(char)
                self.pos += 1
                self.line += 1
                self.col = 1
            else:
                value.append(char)
                self.pos += 1
                self.col += 1

        raise LexerError("Chaine non fermée", start_line, start_col)

    def _read_interpolation(self) -> None:
        """Lit une interpolation ${expr}."""
        start_line, start_col = self.line, self.col
        self.pos += 2  # saute ${
        self.col += 2
        depth = 1
        value: list[str] = []

        while self.pos < len(self.source) and depth > 0:
            char = self.source[self.pos]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    self.pos += 1
                    self.col += 1
                    self._emit(TokenKind.INTERPOLATION, "".join(value))
                    return
            value.append(char)
            self.pos += 1
            self.col += 1

        raise LexerError("Interpolation non fermée", start_line, start_col)

    def _peek_next_non_space(self) -> str:
        """Regarde le caractère suivant en ignorant les espaces (pas les \n)."""
        idx = self.pos + 1
        while idx < len(self.source) and self.source[idx] in (" ", "\t"):
            idx += 1
        return self.source[idx] if idx < len(self.source) else "\0"

    def _read_hyperscript(self) -> None:
        """Capture un script hyperscript brut en un unique token.

        Deux modes (sélectionnés par le caractère après `_` + espaces :
        - ``_ : on click toggle .hidden``  → capture jusqu'à la fin de ligne.
        - ``_ { ... }``  → capture jusqu'à l'accolade fermante, en comptant
          la profondeur des accolades (un bloc js() qui contient { } reste
          équilibré). Les nouvelles lignes sont conservées : hyperscript
          sépare ses déclarations par des sauts de ligne (ex. deux handlers
          `on ...`), les écraser par des espaces casserait le script.
        """
        start_line, start_col = self.line, self.col
        # Saute `_` et les espaces
        self.pos += 1
        self.col += 1
        while self.pos < len(self.source) and self.source[self.pos] in (" ", "\t"):
            self.pos += 1
            self.col += 1

        if self.pos >= len(self.source):
            raise LexerError("Attribut hyperscript inattendu (fin de fichier)", start_line, start_col)

        if self.source[self.pos] == ":":
            # Mode ligne : jusqu'au premier \n ou } non inclus. L'accolade
            # d'un élément sur la même ligne (div { _ : ... }) ne doit pas
            # être avalée dans le script — hyperscript ne ferme pas ses
            # déclarations avec } (sauf dans un js(...), cas du mode bloc).
            self.pos += 1
            self.col += 1
            value: list[str] = []
            while self.pos < len(self.source):
                char = self.source[self.pos]
                if char in ("\n", "}"):
                    break
                if char == "$" and self.pos + 1 < len(self.source) and self.source[self.pos + 1] == "{":
                    # Groupe ${ expr } : le } appartient à l'interpolation,
                    # pas à la fermeture de l'élément — on le consomme avec
                    # ses éventuelles accolades imbriquées (${...{a:1}...}).
                    value.append(char)
                    self.pos += 1
                    self.col += 1
                    value.append(self.source[self.pos])
                    self.pos += 1
                    self.col += 1
                    depth = 1
                    while self.pos < len(self.source) and depth > 0:
                        c = self.source[self.pos]
                        if c == "{":
                            depth += 1
                        elif c == "}":
                            depth -= 1
                        value.append(c)
                        self.pos += 1
                        self.col += 1
                    continue
                value.append(char)
                self.pos += 1
                self.col += 1
            script = "".join(value).strip()
            self._emit(TokenKind.HYPERSCRIPT_SCRIPT, script)
            return

        # Mode bloc : { ... } avec profondeur d'accolades
        if self.source[self.pos] == "{":
            self.pos += 1
            self.col += 1
            depth = 1
            value = []
            while self.pos < len(self.source) and depth > 0:
                char = self.source[self.pos]
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        self.pos += 1
                        self.col += 1
                        self._emit(TokenKind.HYPERSCRIPT_SCRIPT, "".join(value).strip())
                        return
                elif char == "\n":
                    self.line += 1
                    self.col = 1
                    value.append("\n")
                    self.pos += 1
                    continue
                value.append(char)
                self.pos += 1
                self.col += 1

            raise LexerError("Bloc hyperscript non fermé", start_line, start_col)

        # `_` suivi de n'importe quoi d'autre : token ident normal
        self._emit(TokenKind.IDENT, "_")

    def _read_number(self) -> None:
        """Lit un nombre (entier ou décimal)."""
        start = self.pos
        if self.source[self.pos] == "-":
            self.pos += 1
            self.col += 1

        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            self.pos += 1
            self.col += 1

        if self.pos < len(self.source) and self.source[self.pos] == ".":
            self.pos += 1
            self.col += 1
            while self.pos < len(self.source) and self.source[self.pos].isdigit():
                self.pos += 1
                self.col += 1

        value = self.source[start : self.pos]
        self._emit(TokenKind.NUMBER, value)

    def _read_ident(self) -> None:
        """Lit un identifiant ou un mot-clé."""
        start = self.pos
        while self.pos < len(self.source) and (
            self.source[self.pos].isalnum() or self.source[self.pos] in ("_", "-")
        ):
            self.pos += 1
            self.col += 1

        value = self.source[start : self.pos]

        # Vérifie si c'est un mot-clé
        kind = KEYWORDS.get(value, TokenKind.IDENT)
        self._emit(kind, value)


# =============================================================================
# Parser
# =============================================================================

class ParseError(Exception):
    """Erreur de parsing."""

    def __init__(self, message: str, token: Token | None = None):
        if token:
            super().__init__(f"L{token.line}:{token.col}: {message}")
        else:
            super().__init__(message)
        self.token = token


class Parser:
    """Parser xdsl — convertit les tokens en AST.

    Parser récursif descendant :
    - Chaque production grammaticale = une méthode
    - Consume les tokens via self._advance() / self._expect()
    - Récursion pour les blocs imbriqués

    Usage:
        parser = Parser(source)
        ast = parser.parse()
    """

    def __init__(self, source: str, filename: str = "<stdin>"):
        self.source = source
        self.filename = filename
        self.tokens = Lexer(source, filename).tokenize()
        self.pos = 0
        self.current = self.tokens[0] if self.tokens else None

    def parse(self) -> AST:
        """Parse le source et retourne l'AST racine."""
        ast = AST()

        self._skip_newlines()

        while not self._at_end():
            token = self.current

            if token.kind == TokenKind.COMPONENT:
                ast.components.append(self._parse_component())
            elif token.kind == TokenKind.PATCH:
                ast.patches.append(self._parse_patch())
            elif token.kind == TokenKind.COPY:
                ast.copies.append(self._parse_copy())
            elif token.kind == TokenKind.IMPORT:
                ast.imports.append(self._parse_import())
            elif token.kind == TokenKind.DATA:
                ast.data_schemas.append(self._parse_data_schema())
            elif token.kind == TokenKind.ENDPOINT:
                ast.endpoints.append(self._parse_endpoint())
            elif token.kind == TokenKind.CHANNEL:
                ast.channels.append(self._parse_channel())
            elif token.kind == TokenKind.INCLUDE:
                ast.layout = self._parse_include()
            elif token.kind == TokenKind.NEWLINE:
                self._advance()
            else:
                # Nœud enfant au niveau racine (pour les fichiers sans component)
                ast.children.append(self._parse_node())

            self._skip_newlines()

        return ast

    # -------------------------------------------------------------------------
    # Navigation dans les tokens
    # -------------------------------------------------------------------------

    def _advance(self) -> Token:
        """Avance au token suivant et retourne le token précédent."""
        token = self.current
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current = self.tokens[self.pos]
        return token

    def _expect(self, kind: TokenKind) -> Token:
        """Attend un token du type donné et l'avance."""
        if self.current.kind != kind:
            raise ParseError(
                f"Attendu {kind.name}, trouvé {self.current.kind.name} ({self.current.value!r})",
                self.current,
            )
        return self._advance()

    def _expect_ident(self) -> str:
        """Attend un identifiant et le retourne."""
        token = self._expect(TokenKind.IDENT)
        return token.value

    def _match(self, *kinds: TokenKind) -> Token | None:
        """Si le token courant est l'un des kinds donnés, l'avance et le retourne."""
        if self.current.kind in kinds:
            return self._advance()
        return None

    def _at_end(self) -> bool:
        """Vérifie si on est à la fin des tokens."""
        return self.current.kind == TokenKind.EOF

    def _skip_newlines(self) -> None:
        """Ignore les tokens NEWLINE consécutifs."""
        while self.current.kind == TokenKind.NEWLINE:
            self._advance()

    # -------------------------------------------------------------------------
    # Parsing des structures principales
    # -------------------------------------------------------------------------

    def _parse_component(self) -> ComponentDef:
        """Parse: component name { ... }"""
        self._expect(TokenKind.COMPONENT)
        name = self._parse_dotted_name()
        self._expect(TokenKind.LBRACE)

        comp = ComponentDef(name=name)
        self._skip_newlines()

        while self.current.kind != TokenKind.RBRACE:
            if self.current.kind == TokenKind.IMPORT:
                comp.imports.append(self._parse_import())
            elif self.current.kind == TokenKind.PROPS:
                comp.props = self._parse_props()
            elif self.current.kind == TokenKind.STYLE:
                comp.style = self._parse_style()
            elif self.current.kind == TokenKind.COMPONENT:
                # Composant imbriqué
                comp.children.append(self._parse_component())
            else:
                comp.children.append(self._parse_node())
            self._skip_newlines()

        self._expect(TokenKind.RBRACE)
        return comp

    def _parse_patch(self) -> PatchDef:
        """Parse: patch target { xpath "//expr" { position: ... } }"""
        self._expect(TokenKind.PATCH)
        target = self._parse_dotted_name()

        patch = PatchDef(target=target)

        # Optionnel: priority: N
        if self._match(TokenKind.PRIORITY):
            self._expect(TokenKind.COLON)
            patch.priority = int(self._expect(TokenKind.NUMBER).value)

        self._expect(TokenKind.LBRACE)
        self._skip_newlines()

        while self.current.kind != TokenKind.RBRACE:
            if self.current.kind == TokenKind.XPATH:
                patch.xpath_patches.append(self._parse_xpath_patch())
            else:
                # On pourrait avoir d'autres instructions dans un patch
                break
            self._skip_newlines()

        self._expect(TokenKind.RBRACE)
        return patch

    def _parse_xpath_patch(self) -> XpathPatch:
        """Parse: xpath "//expr" { inside: ... }"""
        self._expect(TokenKind.XPATH)
        expr_token = self._expect(TokenKind.STRING)
        expr = expr_token.value

        self._expect(TokenKind.LBRACE)
        self._skip_newlines()

        # Parse la position
        position = Position.INSIDE  # défaut
        children: list[Any] = []

        # Les mots-clés de position sont des tokens réservés
        position_tokens = {
            TokenKind.INSIDE: Position.INSIDE,
            TokenKind.REPLACE: Position.REPLACE,
            TokenKind.BEFORE: Position.BEFORE,
            TokenKind.AFTER: Position.AFTER,
            TokenKind.ATTRIBUTES: Position.ATTRIBUTES,
        }

        if self.current.kind in position_tokens:
            position = position_tokens[self.current.kind]
            self._advance()
            self._expect(TokenKind.COLON)

            # Les enfants du patch
            self._skip_newlines()
            if self.current.kind == TokenKind.LBRACE:
                self._advance()
                self._skip_newlines()
                while self.current.kind != TokenKind.RBRACE:
                    children.append(self._parse_node())
                    self._skip_newlines()
                self._expect(TokenKind.RBRACE)
            else:
                children.append(self._parse_node())

        self._skip_newlines()
        self._expect(TokenKind.RBRACE)

        return XpathPatch(expr=expr, position=position, children=children)

    def _parse_copy(self) -> CopyDef:
        """Parse: copy source as alias { xpath "..." { ... } ... }

        Voir CopyDef : uniquement des blocs `xpath`, comme `patch` — le
        moteur QWeb n'applique jamais rien d'autre en mode primary."""
        self._expect(TokenKind.COPY)
        source = self._parse_dotted_name()
        self._expect(TokenKind.AS)
        alias = self._parse_dotted_name()

        copy = CopyDef(source=source, alias=alias)

        self._expect(TokenKind.LBRACE)
        self._skip_newlines()

        while self.current.kind != TokenKind.RBRACE:
            if self.current.kind == TokenKind.XPATH:
                copy.xpath_patches.append(self._parse_xpath_patch())
            else:
                raise ParseError(
                    "copy ... as ... { } (t-inherit-mode=\"primary\") n'accepte que "
                    "des blocs xpath — le moteur QWeb n'applique jamais un contenu "
                    "littéral en mode primary, seulement les <xpath> de la copie "
                    "(docs/inheritance.md#primary). Écrivez : "
                    'xpath "//..." { replace: ... } (ou inside/before/after/attributes)',
                    self.current,
                )
            self._skip_newlines()

        self._expect(TokenKind.RBRACE)
        return copy

    def _parse_import(self) -> Import:
        """Parse: import { name1, name2 } from "source" """
        self._expect(TokenKind.IMPORT)
        self._expect(TokenKind.LBRACE)

        names: list[str] = []
        while self.current.kind != TokenKind.RBRACE:
            names.append(self._expect_ident())
            if self._match(TokenKind.COMMA) is None:
                break

        self._expect(TokenKind.RBRACE)
        self._expect(TokenKind.FROM)

        source_token = self._expect(TokenKind.STRING)
        source = source_token.value

        # Détermine si c'est un import relatif
        relative = source.startswith(".") or source.startswith("..")

        return Import(names=names, source=source, relative=relative)

    def _parse_include(self) -> str:
        """Parse: @include "layout_name" — directive de layout au niveau fichier."""
        self._expect(TokenKind.INCLUDE)
        token = self._expect(TokenKind.STRING)
        return token.value

    def _parse_props(self) -> Props:
        """Parse: props: { name: default, ... }"""
        self._expect(TokenKind.PROPS)
        self._expect(TokenKind.COLON)
        self._expect(TokenKind.LBRACE)
        self._skip_newlines()

        props = Props()

        while self.current.kind != TokenKind.RBRACE:
            name = self._expect_ident()
            self._expect(TokenKind.COLON)

            # Parse la valeur par défaut
            default = self._parse_default_value()
            props.defaults[name] = default

            self._match(TokenKind.COMMA)
            self._skip_newlines()

        self._expect(TokenKind.RBRACE)
        return props

    def _parse_default_value(self) -> Any:
        """Parse une valeur par défaut (string, number, bool, ident)."""
        token = self.current

        if token.kind == TokenKind.STRING:
            self._advance()
            return token.value
        elif token.kind == TokenKind.NUMBER:
            self._advance()
            try:
                return int(token.value)
            except ValueError:
                return float(token.value)
        elif token.kind == TokenKind.IDENT:
            self._advance()
            if token.value == "true":
                return True
            elif token.value == "false":
                return False
            return token.value
        else:
            raise ParseError(f"Valeur par défaut inattendue: {token.kind.name}", token)

    def _parse_style(self) -> Style:
        """Parse: style: "css content" """
        self._expect(TokenKind.STYLE)
        self._expect(TokenKind.COLON)
        css_token = self._expect(TokenKind.STRING)
        return Style(css=css_token.value)

    # -------------------------------------------------------------------------
    # Parsing des schémas `data` et des requêtes `endpoint`
    # -------------------------------------------------------------------------

    def _parse_data_schema(self) -> DataSchemaDef:
        """Parse: data nom { champ: type @decorateur... }"""
        self._expect(TokenKind.DATA)
        name = self._expect_ident()
        self._expect(TokenKind.LBRACE)
        self._skip_newlines()

        schema = DataSchemaDef(name=name)
        while self.current.kind != TokenKind.RBRACE:
            schema.fields.append(self._parse_data_field())
            self._match(TokenKind.COMMA)
            self._skip_newlines()

        self._expect(TokenKind.RBRACE)
        return schema

    def _parse_data_field(self) -> DataField:
        """Parse: nom: type @decorateur @decorateur(args)..."""
        name = self._expect_ident()
        self._expect(TokenKind.COLON)
        type_name = self._expect_ident()
        decorators = self._parse_decorators()
        return DataField(name=name, value_type=type_name, decorators=decorators)

    def _parse_decorators(self) -> list[tuple[str, list[Any]]]:
        """Parse une suite de @nom[(args, ...)] — validators.py::BUILTIN_VALIDATORS
        pour les noms reconnus, mais le parser ne valide pas ici (même
        posture que apply_filters() côté QWeb : un nom inconnu n'est pas
        une TemplateSyntaxError au parse, l'échec de résolution vient plus
        tard, côté compiler/export, avec un message qui pointe le nom)."""
        decorators: list[tuple[str, list[Any]]] = []
        while self.current.kind == TokenKind.AT:
            self._advance()
            # `in` (@in(["a","b"])) est un mot-clé réservé (for x IN list),
            # pas un IDENT — sans ce cas, un nom de décorateur qui coïncide
            # avec un mot-clé DSL serait un ParseError, même piège que
            # `truncate`/`last` etc. le seraient pour BUILTIN_VALIDATORS si
            # un futur nom de règle recoupait un mot-clé.
            if self.current.kind == TokenKind.IN:
                name = self._advance().value
            else:
                name = self._expect_ident()
            args: list[Any] = []
            if self.current.kind == TokenKind.LPAREN:
                self._advance()
                while self.current.kind != TokenKind.RPAREN:
                    args.append(self._parse_decorator_arg())
                    if not self._match(TokenKind.COMMA):
                        break
                self._expect(TokenKind.RPAREN)
            decorators.append((name, args))
        return decorators

    def _parse_decorator_arg(self) -> Any:
        """Argument d'un décorateur : littéral simple, ou liste littérale
        (@in(["admin", "editor"])) — _parse_default_value ne connaît pas
        les listes, seul cas où un décorateur en a besoin."""
        if self.current.kind == TokenKind.LBRACKET:
            self._advance()
            self._skip_newlines()
            items: list[Any] = []
            while self.current.kind != TokenKind.RBRACKET:
                items.append(self._parse_decorator_arg())
                if not self._match(TokenKind.COMMA):
                    break
                self._skip_newlines()
            self._expect(TokenKind.RBRACKET)
            return items
        return self._parse_default_value()

    def _parse_endpoint(self) -> EndpointDef:
        """Parse: endpoint nom { method: POST  url: "..."  send: schema
        headers: {...}  auth: cookie  receive { ... }  onloading { ... }
        onsuccess { ... }  onerror { ... } }"""
        self._expect(TokenKind.ENDPOINT)
        name = self._expect_ident()
        self._expect(TokenKind.LBRACE)
        self._skip_newlines()

        ep = EndpointDef(name=name)
        while self.current.kind != TokenKind.RBRACE:
            key_token = self._expect(TokenKind.IDENT)
            key = key_token.value
            if key == "method":
                self._expect(TokenKind.COLON)
                ep.method = str(self._parse_default_value()).upper()
            elif key == "url":
                self._expect(TokenKind.COLON)
                ep.url = str(self._parse_default_value())
            elif key == "send":
                self._expect(TokenKind.COLON)
                ep.send = str(self._parse_default_value())
            elif key == "auth":
                self._expect(TokenKind.COLON)
                ep.auth = str(self._parse_default_value())
            elif key == "headers":
                self._expect(TokenKind.COLON)
                ep.headers = self._parse_simple_dict()
            elif key == "receive":
                ep.receive = self._parse_receive_spec()
            elif key == "onloading":
                ep.onloading = self._parse_hook_body()
            elif key == "onsuccess":
                ep.onsuccess = self._parse_hook_body()
            elif key == "onerror":
                ep.onerror = self._parse_hook_body()
            else:
                raise ParseError(f"Clé d'endpoint inconnue: {key!r}", key_token)
            self._skip_newlines()

        self._expect(TokenKind.RBRACE)
        return ep

    def _parse_receive_spec(self) -> ReceiveSpec:
        """Parse: receive { type: json  schema: nom  target: "#id"  event: "nom" }"""
        self._expect(TokenKind.LBRACE)
        self._skip_newlines()

        spec = ReceiveSpec()
        while self.current.kind != TokenKind.RBRACE:
            key_token = self._expect(TokenKind.IDENT)
            key = key_token.value
            self._expect(TokenKind.COLON)
            value = self._parse_default_value()
            if key == "type":
                spec.kind = str(value)
            elif key == "schema":
                spec.schema = str(value)
            elif key == "target":
                spec.target = str(value)
            elif key == "event":
                spec.event = str(value)
            else:
                raise ParseError(f"Clé de receive inconnue: {key!r}", key_token)
            self._match(TokenKind.COMMA)
            self._skip_newlines()

        self._expect(TokenKind.RBRACE)
        return spec

    def _parse_hook_body(self) -> list[Any]:
        """Parse le corps d'un onloading/onsuccess/onerror : une liste de
        nœuds DSL normaux (mêmes règles qu'un corps de composant) — du
        contenu STATIQUE, précompilé une fois pour toutes (pas de liaison
        aux données de la réponse JSON dans ce v1, voir docs/dsl-design.md)."""
        self._expect(TokenKind.LBRACE)
        self._skip_newlines()
        nodes: list[Any] = []
        while self.current.kind != TokenKind.RBRACE:
            nodes.append(self._parse_node())
            self._skip_newlines()
        self._expect(TokenKind.RBRACE)
        return nodes

    def _parse_simple_dict(self) -> dict[str, Any]:
        """Parse: { "clé littérale": valeur, autre_clé: valeur }"""
        self._expect(TokenKind.LBRACE)
        self._skip_newlines()
        result: dict[str, Any] = {}
        while self.current.kind != TokenKind.RBRACE:
            if self.current.kind == TokenKind.STRING:
                key = self._advance().value
            else:
                key = self._expect_ident()
            self._expect(TokenKind.COLON)
            result[key] = self._parse_default_value()
            self._match(TokenKind.COMMA)
            self._skip_newlines()
        self._expect(TokenKind.RBRACE)
        return result

    def _parse_string_list(self) -> list[str]:
        """Parse: [ "a", "b", "c" ] — liste de chaînes littérales simples
        (channels: [...] d'un `channel`, jamais des expressions)."""
        self._expect(TokenKind.LBRACKET)
        items: list[str] = []
        while self.current.kind != TokenKind.RBRACKET:
            self._skip_newlines()
            if self.current.kind == TokenKind.RBRACKET:
                break
            if self.current.kind in (TokenKind.NEWLINE, TokenKind.COMMA):
                self._advance()
                continue
            items.append(self._expect(TokenKind.STRING).value)
        self._expect(TokenKind.RBRACKET)
        return items

    def _parse_channel(self) -> ChannelDef:
        """Parse: channel nom { url: "..."  channels: [...]  transport: ...
        connect_timeout_ms: ...  validate: nom  persist: "clé"
        onmessage { refresh: "#sel"  event: "nom"  bind: { "#sel": champ } } }"""
        self._expect(TokenKind.CHANNEL)
        name = self._expect_ident()
        self._expect(TokenKind.LBRACE)
        self._skip_newlines()

        ch = ChannelDef(name=name)
        while self.current.kind != TokenKind.RBRACE:
            key_token = self._expect(TokenKind.IDENT)
            key = key_token.value
            if key == "url":
                self._expect(TokenKind.COLON)
                ch.url = str(self._parse_default_value())
            elif key == "channels":
                self._expect(TokenKind.COLON)
                ch.channels = self._parse_string_list()
            elif key == "transport":
                self._expect(TokenKind.COLON)
                ch.transport = str(self._parse_default_value())
            elif key == "connect_timeout_ms":
                self._expect(TokenKind.COLON)
                ch.connect_timeout_ms = int(self._parse_default_value())
            elif key == "validate":
                self._expect(TokenKind.COLON)
                ch.validate = str(self._parse_default_value())
            elif key == "persist":
                self._expect(TokenKind.COLON)
                ch.persist = str(self._parse_default_value())
            elif key == "onmessage":
                ch.onmessage = self._parse_channel_onmessage()
            else:
                raise ParseError(f"Clé de channel inconnue: {key!r}", key_token)
            self._skip_newlines()

        self._expect(TokenKind.RBRACE)
        return ch

    def _parse_channel_onmessage(self) -> ChannelOnMessage:
        """Parse: onmessage { refresh: "#sel"  event: "nom"  bind: { "#sel": champ } }"""
        self._expect(TokenKind.LBRACE)
        self._skip_newlines()
        om = ChannelOnMessage()
        while self.current.kind != TokenKind.RBRACE:
            key_token = self._expect(TokenKind.IDENT)
            key = key_token.value
            self._expect(TokenKind.COLON)
            if key == "refresh":
                om.refresh = str(self._parse_default_value())
            elif key == "event":
                om.event = str(self._parse_default_value())
            elif key == "dispatch":
                om.dispatch = bool(self._parse_default_value())
            elif key == "bind":
                bindings = self._parse_simple_dict()
                om.bindings = [(sel, str(field_name)) for sel, field_name in bindings.items()]
            else:
                raise ParseError(f"Clé de onmessage inconnue: {key!r}", key_token)
            self._match(TokenKind.COMMA)
            self._skip_newlines()
        self._expect(TokenKind.RBRACE)
        return om

    # -------------------------------------------------------------------------
    # Parsing des nœuds (if, for, affectation, élément, texte)
    # -------------------------------------------------------------------------

    def _parse_node(self) -> Any:
        """Parse un nœud générique."""
        token = self.current

        if token.kind == TokenKind.IF:
            return self._parse_if()
        elif token.kind == TokenKind.FOR:
            return self._parse_for()
        elif token.kind == TokenKind.RAW:
            return self._parse_raw()
        elif token.kind == TokenKind.TR:
            # `tr { ... }` (accolade juste après) est la balise HTML <tr> —
            # `tr "texte"`/`tr expr` (tout le reste) est la directive de
            # traduction. Trouvé en écrivant un <table> à la main dans le
            # DSL (contacts_demo.dsl) : sans cette désambiguïsation, <tr>
            # est tout simplement injoignable en xdsl.
            if self._next_significant_kind() == TokenKind.LBRACE:
                self._advance()
                return self._parse_element_body("tr")
            return self._parse_translate()
        elif token.kind == TokenKind.SLOT:
            self._advance()
            return SlotNode()
        elif token.kind == TokenKind.IDENT:
            # Soit une affectation (x = expr), soit un élément (div { ... }),
            # soit une expression texte (item.name)
            if self._peek_is_assign():
                return self._parse_assignment()
            elif self._peek_is_element():
                return self._parse_element()
            else:
                return TextNode(content=self._read_expression())
        elif token.kind == TokenKind.STRING:
            # Texte brut entre guillemets — pas d'évaluation Python
            self._advance()
            return TextNode(content=token.value, literal=True)
        else:
            raise ParseError(f"Nœud inattendu: {token.kind.name} ({token.value!r})", token)

    def _peek_is_assign(self) -> bool:
        """Vérifie si on a une affectation (x = expr ou x ?= expr)."""
        if self.current.kind != TokenKind.IDENT:
            return False

        # Regarde le token suivant (en ignorant les newlines)
        idx = self.pos + 1
        while idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.NEWLINE:
            idx += 1

        if idx >= len(self.tokens):
            return False

        return self.tokens[idx].kind in (TokenKind.ASSIGN, TokenKind.ASSIGN_DEFAULT)

    def _peek_is_element(self) -> bool:
        """Vérifie si le token courant est le début d'un élément.

        Accepte un nom dotted : ``auth.login {`` (appel d'un composant
        défini dans le même fichier, doc "Slots"/"Scope des variables"),
        pas seulement un ident simple suivi de LBRACE.
        """
        if self.current.kind != TokenKind.IDENT:
            return False

        # Regarde le token suivant (en ignorant les newlines)
        idx = self.pos + 1
        while idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.NEWLINE:
            idx += 1

        # Nom dotted : IDENT (. IDENT)*
        while (
            idx + 1 < len(self.tokens)
            and self.tokens[idx].kind == TokenKind.DOT
            and self.tokens[idx + 1].kind == TokenKind.IDENT
        ):
            idx += 2

        # Ignore les newlines après le nom (div\n{ … }) aussi pour le dotted
        while idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.NEWLINE:
            idx += 1

        return idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.LBRACE

    def _parse_if(self) -> IfBlock:
        """Parse: if (condition) { ... } elif (...) { ... } else { ... }"""
        self._expect(TokenKind.IF)
        self._expect(TokenKind.LPAREN)
        condition = self._read_expression()
        self._expect(TokenKind.RPAREN)

        block = IfBlock(condition=condition)
        self._expect(TokenKind.LBRACE)
        self._skip_newlines()

        while self.current.kind != TokenKind.RBRACE:
            block.children.append(self._parse_node())
            self._skip_newlines()

        self._expect(TokenKind.RBRACE)
        self._skip_newlines()

        # elif
        while self._match(TokenKind.ELIF) is not None:
            self._expect(TokenKind.LPAREN)
            elif_cond = self._read_expression()
            self._expect(TokenKind.RPAREN)
            self._expect(TokenKind.LBRACE)
            self._skip_newlines()
            elif_children: list[Any] = []
            while self.current.kind != TokenKind.RBRACE:
                elif_children.append(self._parse_node())
                self._skip_newlines()
            self._expect(TokenKind.RBRACE)
            block.elif_blocks.append((elif_cond, elif_children))
            self._skip_newlines()

        # else
        if self._match(TokenKind.ELSE) is not None:
            self._expect(TokenKind.LBRACE)
            self._skip_newlines()
            while self.current.kind != TokenKind.RBRACE:
                block.else_children.append(self._parse_node())
                self._skip_newlines()
            self._expect(TokenKind.RBRACE)

        return block

    def _parse_for(self) -> ForLoop:
        """Parse: for item in list { ... }"""
        self._expect(TokenKind.FOR)
        variable = self._expect_ident()
        self._expect(TokenKind.IN)
        iterable = self._read_expression()

        loop = ForLoop(variable=variable, iterable=iterable)

        self._skip_newlines()
        self._expect(TokenKind.LBRACE)
        self._skip_newlines()

        while self.current.kind != TokenKind.RBRACE:
            loop.children.append(self._parse_node())
            self._skip_newlines()

        self._expect(TokenKind.RBRACE)
        return loop

    def _parse_assignment(self) -> Assignment:
        """Parse: x = expr ou x ?= expr"""
        name = self._expect_ident()

        if self._match(TokenKind.ASSIGN_DEFAULT):
            default = True
        else:
            self._expect(TokenKind.ASSIGN)
            default = False

        value = self._read_expression()
        return Assignment(name=name, value=value, default=default)

    def _parse_raw(self) -> TextNode:
        """Parse: raw expr"""
        self._expect(TokenKind.RAW)
        expr = self._read_expression()
        return TextNode(content=expr, raw=True)

    def _parse_translate(self) -> TextNode:
        """Parse: tr "texte" ou tr expr"""
        self._expect(TokenKind.TR)

        if self.current.kind == TokenKind.STRING:
            content = self._advance().value
            return TextNode(content=content, translate=True, literal=True)
        else:
            content = self._read_expression()
            return TextNode(content=content, translate=True)

    def _parse_element(self) -> Element:
        """Parse: tag { attr: value; ... children ... } — tag peut être dotted (auth.login)."""
        tag = self._parse_dotted_name()
        return self._parse_element_body(tag)

    def _parse_element_body(self, tag: str) -> Element:
        """Corps d'un élément une fois son tag déjà connu — factorisé pour
        <tr> : `tr` est par ailleurs le mot-clé de traduction (`tr "texte"`),
        donc `_parse_node` bascule ici directement (après avoir consommé le
        token TR lui-même) sans repasser par _parse_dotted_name/_expect_ident,
        qui n'acceptent qu'un IDENT. Même disambiguïsation que `style:` déjà
        acceptée comme NOM D'ATTRIBUT malgré son propre mot-clé réservé
        (_parse_attribute) — un mot-clé DSL peut toujours doubler comme nom
        HTML légitime selon la position où il apparaît."""
        elem = Element(tag=tag)

        # Vérifie si on a des attributs et/ou des enfants
        if self.current.kind == TokenKind.LBRACE:
            self._advance()
            self._skip_newlines()

            while self.current.kind != TokenKind.RBRACE:
                # Vérifie si c'est un attribut (name: value) ou un enfant
                if self._peek_is_attribute():
                    attr = self._parse_attribute()
                    if any(a.name == attr.name for a in elem.attributes):
                        raise ParseError(
                            f"Attribut en double '{attr.name}' dans <{tag}> — "
                            f"chaque attribut n'apparaît qu'une fois",
                            self.current,
                        )
                    elem.attributes.append(attr)
                    self._skip_newlines()
                elif self.current.kind == TokenKind.NEWLINE:
                    self._advance()
                else:
                    elem.children.append(self._parse_node())
                    self._skip_newlines()

            self._expect(TokenKind.RBRACE)

        return elem

    def _peek_is_attribute(self) -> bool:
        """Vérifie si le token courant est le début d'un attribut."""
        if self.current.kind == TokenKind.HYPERSCRIPT_SCRIPT:
            return True

        if self.current.kind != TokenKind.IDENT and self.current.kind != TokenKind.STYLE:
            return False

        # Les mots-clés ne sont pas des attributs
        if self.current.kind in (
            TokenKind.IF,
            TokenKind.FOR,
            TokenKind.ELSE,
            TokenKind.ELIF,
            TokenKind.COMPONENT,
            TokenKind.PATCH,
            TokenKind.COPY,
            TokenKind.SLOT,
            TokenKind.RAW,
            TokenKind.TR,
        ):
            return False

        # Regarde si le prochain token non-newline est COLON
        idx = self.pos + 1
        while idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.NEWLINE:
            idx += 1

        if idx >= len(self.tokens):
            return False

        return self.tokens[idx].kind == TokenKind.COLON

    def _parse_attribute(self) -> Attribute:
        """Parse: name: value ou name: expr"""
        # Attribut hyperscript brut : le token porte déjà "_" + le script.
        # ${...} présent → interpolation serveur via t-attf-_.
        if self.current.kind == TokenKind.HYPERSCRIPT_SCRIPT:
            token = self._advance()
            return Attribute(
                name="_",
                value=token.value,
                dynamic=False,
                interpolated="${" in token.value,
            )

        # Le nom peut être un IDENT ou un mot-clé utilisable comme attribut (style:)
        if self.current.kind == TokenKind.STYLE:
            name = self._advance().value
        else:
            name = self._expect_ident()
        self._expect(TokenKind.COLON)

        # Liste de tokens de classes (class: ["flex", expr]) et dict de style
        # (style: { prop: value }) — forme structurée du moteur No-Code.
        if self.current.kind == TokenKind.LBRACKET:
            return Attribute(name=name, value=self._parse_list())
        if self.current.kind == TokenKind.LBRACE:
            return Attribute(name=name, value=self._parse_style_dict())

        # Détermine le type d'attribut selon le premier token
        if self.current.kind == TokenKind.STRING:
            # Littéral string : valeur non dynamique
            value = self._advance().value
            interpolated = "${" in value
            return Attribute(name=name, value=value, dynamic=False, interpolated=interpolated)

        if self.current.kind == TokenKind.NUMBER:
            # Littéral numérique
            value = self._advance().value
            return Attribute(name=name, value=value, dynamic=False, interpolated=False)

        if self.current.kind == TokenKind.IDENT and self.current.value in ("true", "false"):
            # Littéral booléen
            value = self._advance().value
            return Attribute(name=name, value=value, dynamic=False, interpolated=False)

        # Expression (variable, dotted name, ternaire, etc.)
        value = self._read_expression()
        interpolated = "${" in value
        return Attribute(name=name, value=value, dynamic=True, interpolated=interpolated)

    def _parse_list(self) -> list[AttributeValue]:
        """Parse: [ "a", expr, "b" ] — liste de jetons de classes, ou liste de
        littéraux dict ([{"label": ..., "path": ...}, ...] — items d'un
        xweb.breadcrumbs/xweb.table/xweb.tabs déclarés inline dans un fichier
        .dsl, pas seulement passés depuis le contexte Python).

        Séparateurs : virgules et/ou nouvelles lignes. Un item peut être une
        chaîne littérale (eventuellement avec ${...}), un littéral dict
        (`{...}`, régression réelle : sans `allow_top_level_brace=True` ici,
        `_read_expression` s'arrête immédiatement sur ce `{` sans avancer,
        boucle infinie dans CETTE fonction — trouvé en écrivant docs_site.dsl),
        ou une expression ordinaire.
        """
        self._expect(TokenKind.LBRACKET)
        items: list[AttributeValue] = []
        while self.current.kind != TokenKind.RBRACKET:
            self._skip_newlines()
            if self.current.kind == TokenKind.RBRACKET:
                break
            if self.current.kind in (TokenKind.NEWLINE, TokenKind.COMMA):
                self._advance()
                continue
            if self.current.kind == TokenKind.STRING:
                items.append(AttributeValue(value=self._advance().value, quoted=True))
            else:
                items.append(AttributeValue(value=self._read_expression(allow_top_level_brace=True), quoted=False))
        self._expect(TokenKind.RBRACKET)
        return items

    def _parse_style_dict(self) -> dict[str, AttributeValue]:
        """Parse: { color: "red", padding: expr } — dict de style inline.

        Les clés sont des identifiants ou des chaînes (pour les noms
        kebab-case comme "background-color"). Séparateurs : virgules et/ou
        nouvelles lignes.
        """
        self._expect(TokenKind.LBRACE)
        props: dict[str, AttributeValue] = {}
        while self.current.kind != TokenKind.RBRACE:
            self._skip_newlines()
            if self.current.kind == TokenKind.RBRACE:
                break
            if self.current.kind in (TokenKind.NEWLINE, TokenKind.COMMA):
                self._advance()
                continue
            if self.current.kind == TokenKind.STRING:
                key = self._advance().value
            else:
                key = self._expect_ident()
            self._expect(TokenKind.COLON)
            if self.current.kind == TokenKind.STRING:
                props[key] = AttributeValue(value=self._advance().value, quoted=True)
            else:
                props[key] = AttributeValue(value=self._read_expression(), quoted=False)
        self._expect(TokenKind.RBRACE)
        return props

    # -------------------------------------------------------------------------
    # Utilitaires
    # -------------------------------------------------------------------------

    def _parse_dotted_name(self) -> str:
        """Parse un nom avec points: xweb.button, auth.login, etc."""
        parts = [self._expect_ident()]

        while self.current.kind == TokenKind.DOT:
            self._advance()
            parts.append(self._expect_ident())

        return ".".join(parts)

    def _read_expression(self, *, ternary_branch: bool = False, allow_top_level_brace: bool = False) -> str:
        """Lit une expression jusqu'au prochain token structurel.

        Reconnaît aussi le chaînage de filtre QWeb `expr | nom[:arg]`
        (xweb/engine/filters.py, docs/language.md#filtres) — même syntaxe
        qu'à l'intérieur d'un `${...}` (_to_qweb_interp), mais ici le `:`
        est structurel : il sépare normalement un nom d'attribut de sa
        valeur (`_parse_attribute`), donc un `:` à profondeur 0 termine
        l'expression PARTOUT SAUF juste après un nom de filtre (celui qui
        suit immédiatement un `|`) — là il introduit l'unique argument du
        filtre plutôt que l'attribut suivant. Un IDENT immédiatement après
        un `|` échappe aussi à l'heuristique "ident suivi de `:` = probable
        nom d'attribut suivant" (`_ident_followed_by_colon`), pour la même
        raison : c'est un nom de filtre, pas un nouvel attribut.

        Un seul argument positionnel par filtre est supporté ici (`x |
        truncate:5`, `x | default:'N/A'`) — un filtre multi-arguments
        (`x | join:', ',name`) a besoin d'une virgule de premier niveau,
        ambiguë avec un séparateur d'item de `class: [...]`/`style: {...}`
        dans une expression nue ; écrire ce cas dans un `${...}` à la
        place, où la syntaxe complète est déjà supportée (texte brut,
        aucune ambiguïté structurelle — voir `_to_qweb_interp`).

        Ternaire `cond ? si_vrai : si_faux` : converti en Python `si_vrai
        if (cond) else si_faux` (le moteur évalue les t-value/t-if en eval
        Python — AGENTS.md). Supporté au niveau racine de l'expression
        (depth 0) uniquement : dans des parenthèses `(a ? b : c)` ou en
        imbrication directe sans parens, une ParseError claire est levée —
        la corruption silencieuse (`x < 5` → `x 5`) est un bug, pas une
        syntaxe. C'est cohérent avec la contrainte du design doc (le
        ternaire vit dans la valeur d'un attribut ou d'une assignation)."""
        parts: list[str] = []
        depth = 0
        last_kind: TokenKind | None = None
        last_was_dot = False
        filter_name_pending_colon = False

        while not self._at_end():
            token = self.current

            if token.kind in (TokenKind.LBRACE, TokenKind.LPAREN, TokenKind.LBRACKET):
                if (
                    depth == 0
                    and token.kind == TokenKind.LBRACE
                    and not (allow_top_level_brace and not parts)
                ):
                    # `{` à profondeur 0 marque normalement la fin de l'expression
                    # (début du corps d'un élément, `div { ... }`) — SAUF si
                    # `allow_top_level_brace` autorise un littéral dict comme
                    # PREMIER token de l'expression (`_parse_list`, un item
                    # `{"label": ..., "path": ...}` dans `items: [...]`).
                    # Une fois ce premier `{...}` consommé (`parts` non vide),
                    # un `{` suivant referme normalement l'expression — pas de
                    # bypass permanent, seulement pour ce tout premier token.
                    break
                depth += 1
                parts.append(token.value)
                self._advance()
                last_kind = token.kind
                last_was_dot = False
                filter_name_pending_colon = False
            elif token.kind in (TokenKind.RBRACE, TokenKind.RPAREN, TokenKind.RBRACKET):
                if depth > 0:
                    depth -= 1
                    parts.append(token.value)
                    self._advance()
                    last_kind = token.kind
                    last_was_dot = False
                    filter_name_pending_colon = False
                else:
                    break
            elif token.kind == TokenKind.NEWLINE and depth == 0:
                break
            elif token.kind == TokenKind.COMMA and depth == 0:
                break
            elif token.kind == TokenKind.COLON and depth == 0:
                if filter_name_pending_colon:
                    # `| nom` puis ':' — introduit l'argument du filtre,
                    # ne termine pas l'expression.
                    filter_name_pending_colon = False
                    parts.append(":")
                    last_kind = TokenKind.COLON
                    last_was_dot = False
                    self._advance()
                    continue
                break
            elif token.kind == TokenKind.EOF:
                break
            elif token.kind == TokenKind.QUESTION and depth == 0 and ternary_branch:
                raise ParseError(
                    "Ternaires ? : imbriqués sans parenthèses non supportés — "
                    "séparez-les (`a ? (b ? c : d) : e`) ou mettez le ternaire "
                    "au niveau racine (AGENTS.md)",
                    token,
                )
            elif token.kind == TokenKind.QUESTION and depth == 0:
                # Ternaire `cond ? si_vrai : si_faux` → Python `si_vrai if
                # (cond) else si_faux`. Le `?` clôt la condition (tout ce
                # qui précède), la "branche vraie" est relue par la même
                # mécanique d'expression — elle s'arrête naturellement au
                # `:` à depth 0 (branche COLON ci-dessus) — puis le COLON est
                # consommé, et la branche fausse s'arrête au terminateur
                # structurel normal (NEWLINE, COMMA, EOF, …).
                cond = "".join(parts).strip()
                self._advance()  # consomme le '?'
                true_part = self._read_expression(ternary_branch=True)
                self._expect(TokenKind.COLON)
                false_part = self._read_expression(ternary_branch=True)
                if not cond:
                    raise ParseError("Ternaire sans condition avant '?'", token)
                return f"{true_part} if ({cond}) else {false_part}"
            elif token.kind == TokenKind.QUESTION:
                raise ParseError(
                    "Ternaire ? : hors de portée (dans des parenthèses/crochets) — "
                    "le ternaire doit être au niveau racine de l'expression "
                    "(AGENTS.md)",
                    token,
                )
            elif (
                not ternary_branch
                and token.kind == TokenKind.IDENT
                and last_kind != TokenKind.PIPE
                and self._ident_followed_by_colon()
            ):
                break
            else:
                is_word = token.kind in (TokenKind.IDENT, TokenKind.NUMBER, TokenKind.STRING)
                is_dot = token.kind == TokenKind.DOT
                prev_is_word = last_kind in (TokenKind.IDENT, TokenKind.NUMBER, TokenKind.STRING)

                # Insère un espace sauf autour d'un DOT
                if parts and not is_dot and not last_was_dot:
                    if is_word and prev_is_word:
                        parts.append(" ")
                    elif is_word and last_kind is not None and not prev_is_word and last_kind not in (
                        TokenKind.LPAREN, TokenKind.LBRACKET,
                    ):
                        parts.append(" ")
                    elif not is_word and prev_is_word:
                        parts.append(" ")

                parts.append(self._expr_token_value(token))
                # Nom de filtre = un IDENT qui suit directement un '|' —
                # son ':' éventuel (juste après) n'est pas un séparateur
                # d'attribut, voir la branche COLON ci-dessus.
                filter_name_pending_colon = (
                    token.kind == TokenKind.IDENT and last_kind == TokenKind.PIPE
                )
                last_kind = token.kind
                last_was_dot = is_dot
                self._advance()

        result = "".join(parts)
        while result and result[0] in (" ", "\t"):
            result = result[1:]
        while result and result[-1] in (" ", "\t"):
            result = result[:-1]
        return result

    @staticmethod
    def _expr_token_value(token: Token) -> str:
        """Normalise la valeur d'un token dans une expression compilée.

        Le lexer rend un STRING déquoté (ex. ``"texte"`` → ``texte``) ; en
        contexte expression (assignation, condition, iterable, t-value…), le
        moteur QWeb évalue l'expression en Python, il faut donc reconstituer
        un littéral valide : `"texte"`, `True`, `False`. Les booléens DSL
        `true`/`false` sont des IDENT à traduire en `True`/`False`.
        """
        value = token.value
        if token.kind == TokenKind.STRING:
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if token.kind == TokenKind.IDENT and value in ("true", "false"):
            return "True" if value == "true" else "False"
        return value

    def _ident_followed_by_colon(self) -> bool:
        """Vérifie si le token courant (IDENT) est suivi d'un COLON (au prochain token non-newline)."""
        idx = self.pos + 1
        while idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.NEWLINE:
            idx += 1
        return idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.COLON

    def _next_significant_kind(self) -> TokenKind | None:
        """Type du prochain token après le courant, en sautant les NEWLINE."""
        idx = self.pos + 1
        while idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.NEWLINE:
            idx += 1
        return self.tokens[idx].kind if idx < len(self.tokens) else None


# =============================================================================
# API publique
# =============================================================================

def parse(source: str, filename: str = "<stdin>") -> AST:
    """Parse le source xdsl et retourne l'AST.

    Args:
        source: Code source xdsl.
        filename: Nom du fichier (pour les messages d'erreur).

    Returns:
        AST racine.
    """
    return Parser(source, filename).parse()
