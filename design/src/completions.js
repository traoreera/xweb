"use strict";
const fs = require("fs");
const path = require("path");

/**
 * Logique pure de complétion pour xdsl — AUCUNE dépendance à `vscode` ici,
 * exprès : testable directement avec `node test/verify-completions.mjs`
 * (même discipline que le reste de ce dépôt — un module qui exigerait un
 * vrai VS Code pour être vérifié ne serait jamais vraiment testé). Le
 * wiring `vscode.CompletionItemProvider` vit dans extension.js, mince,
 * n'appelle que les fonctions d'ici.
 *
 * Heuristique de contexte : pas un vrai parseur xdsl (xdsl/parser.py en
 * a déjà un, dupliquer sa logique ici serait plus de code à maintenir en
 * double pour un gain marginal côté éditeur) — juste un comptage de
 * profondeur d'accolades en remontant depuis le curseur pour retrouver
 * l'en-tête du bloc englobant le plus proche (`channel foo {`, `onmessage {`,
 * `data foo {`...). Suffisant pour proposer les bonnes clés ; un texte
 * syntaxiquement invalide au moment de la frappe (normal, en cours
 * d'écriture) peut donner un contexte approximatif — ce n'est jamais
 * pire qu'une liste de complétion un peu trop large, jamais une erreur.
 */

// Miroir exact de xdsl/parser.py::KEYWORDS (xdsl/parser.py:413-442) — ne
// PAS ajouter un mot ici sans l'ajouter aussi là-bas, et vice versa.
const TOP_LEVEL_KEYWORDS = [
  { label: "component", detail: "component NOM { ... }" },
  { label: "import", detail: 'import { a, b } from "pkg"' },
  { label: "patch", detail: "patch CIBLE { xpath { ... } }" },
  { label: "copy", detail: "copy SOURCE as ALIAS { xpath { ... } }" },
  { label: "data", detail: "data NOM { champ: type @decorateurs }" },
  { label: "endpoint", detail: "endpoint NOM { method: ... url: ... }" },
  { label: "channel", detail: "channel NOM { url: ... onmessage { ... } }" },
  { label: "@include", detail: '@include "xweb.shell"' },
];

// xdsl/validators.py::BUILTIN_VALIDATORS — ensemble FERMÉ, un décorateur
// hors de cette liste lève CompileError à la compilation (pas une faute
// de frappe silencieuse). Garder synchronisé avec ce dict Python.
const DECORATORS = [
  { label: "required", insertText: "required", detail: "@required — champ obligatoire, non vide" },
  { label: "min_length", insertText: "min_length(${1:3})", detail: "@min_length(n) — longueur minimale (string)" },
  { label: "max_length", insertText: "max_length(${1:255})", detail: "@max_length(n) — longueur maximale (string)" },
  { label: "min", insertText: "min(${1:0})", detail: "@min(n) — valeur minimale (nombre)" },
  { label: "max", insertText: "max(${1:100})", detail: "@max(n) — valeur maximale (nombre)" },
  { label: "email", insertText: "email", detail: "@email — format email valide" },
  { label: "pattern", insertText: 'pattern("${1:regex}")', detail: "@pattern(regex) — expression régulière" },
  { label: "in", insertText: 'in([${1:"a", "b"}])', detail: "@in([...]) — valeur dans une liste autorisée" },
];

// xdsl/parser.py::_parse_endpoint (clés reconnues, ParseError sur le reste)
const ENDPOINT_FIELDS = [
  { label: "method", insertText: "method: ${1|POST,GET,PUT,PATCH,DELETE|}" },
  { label: "url", insertText: 'url: "${1:/api/...}"' },
  { label: "send", insertText: "send: ${1:schema_form}" },
  { label: "auth", insertText: "auth: ${1:cookie}" },
  { label: "headers", insertText: 'headers: { "${1:Content-Type}": "${2:application/json}" }' },
  { label: "receive", insertText: "receive {\n\ttype: json\n\ttarget: \"${1:#cible}\"\n\tevent: \"${2:nom}:changed\"\n}" },
  { label: "onloading", insertText: "onloading { ${1} }" },
  { label: "onsuccess", insertText: "onsuccess { ${1:toast { \"OK\" }} }" },
  { label: "onerror", insertText: "onerror { ${1:toast { \"Erreur\" }} }" },
];

// xdsl/parser.py::_parse_receive_spec
const RECEIVE_FIELDS = [
  { label: "type", insertText: "type: json" },
  { label: "schema", insertText: "schema: ${1:nom_schema}" },
  { label: "target", insertText: 'target: "${1:#cible}"' },
  { label: "event", insertText: 'event: "${1:nom}:changed"' },
];

// xdsl/parser.py::_parse_channel
const CHANNEL_FIELDS = [
  { label: "url", insertText: 'url: "${1:/stream}"' },
  { label: "channels", insertText: 'channels: ["${1:canal}"]' },
  { label: "transport", insertText: "transport: ${1|auto,sse,ws|}" },
  { label: "connect_timeout_ms", insertText: "connect_timeout_ms: ${1:5000}" },
  { label: "validate", insertText: 'validate: "${1:schema_form}"' },
  { label: "persist", insertText: 'persist: "${1:clé_stockage}"' },
  { label: "onmessage", insertText: "onmessage {\n\tbind: { \"${1:#cible}\": \"${2:champ}\" }\n}" },
];

// xdsl/parser.py::_parse_channel_onmessage — grammaire FERMÉE, rien d'autre
const ONMESSAGE_FIELDS = [
  { label: "bind", insertText: 'bind: { "${1:#cible}": "${2:champ}" }' },
  { label: "refresh", insertText: 'refresh: "${1:#zone}"' },
  { label: "dispatch", insertText: "dispatch: true" },
  { label: "event", insertText: 'event: "${1:nom}:changed"' },
];

// Attributs génériques d'élément — pas une liste fermée (n'importe quel
// composant xweb.* peut exposer ses propres props), juste les plus
// fréquents/structurels dans ce dépôt (hx-* = htmx, voir contacts_demo.dsl).
const COMMON_ELEMENT_ATTRS = [
  { label: "id", insertText: 'id: "${1}"' },
  { label: "class", insertText: 'class: ["${1}"]' },
  { label: "style", insertText: "style: { ${1:key}: \"${2:value}\" }" },
  { label: "use", insertText: "use: ${1:nom_endpoint}", detail: "attache un endpoint déclaré" },
  { label: "use_channel", insertText: "use_channel: ${1:nom_flux}", detail: "attache un channel déclaré" },
  { label: "hx-get", insertText: 'hx-get: "${1:/...}"' },
  { label: "hx-post", insertText: 'hx-post: "${1:/...}"' },
  { label: "hx-put", insertText: 'hx-put: "${1:/...}"' },
  { label: "hx-delete", insertText: 'hx-delete: "${1:/...}"' },
  { label: "hx-target", insertText: 'hx-target: "${1:#id}"' },
  { label: "hx-swap", insertText: "hx-swap: ${1|innerHTML,outerHTML,none,beforeend,afterbegin|}" },
  { label: "hx-trigger", insertText: 'hx-trigger: "${1:load}"' },
  { label: "hx-confirm", insertText: 'hx-confirm: "${1:Confirmer ?}"' },
];

const CONTROL_KEYWORDS = [
  { label: "if", insertText: "if (${1:condition}) {\n\t${2}\n}" },
  { label: "elif", insertText: "elif (${1:condition}) {\n\t${2}\n}" },
  { label: "else", insertText: "else {\n\t${1}\n}" },
  { label: "for", insertText: "for ${1:item} in ${2:items} {\n\t${3}\n}" },
];

const CONTENT_KEYWORDS = [
  { label: "slot", insertText: "slot" },
  { label: "raw", insertText: "raw ${1:expr}" },
  { label: "tr", insertText: 'tr "${1:texte}"' },
];

// ---------------------------------------------------------------------------
// Catalogue réel des composants xweb.* — généré par
// scripts/generate_components_catalog.py depuis xweb/components/*.xml (le
// même `<t t-set="prop" t-default="...">` que chaque composant déclare
// réellement, jamais une liste recopiée à la main qui dériverait au premier
// composant ajouté/modifié). Absent -> {} (dégrade en silence, pas une
// exception qui casserait toute la complétion pour un simple oubli de
// régénération).
// ---------------------------------------------------------------------------
let COMPONENTS_CATALOG = {};
try {
  COMPONENTS_CATALOG = JSON.parse(
    fs.readFileSync(path.join(__dirname, "components-catalog.json"), "utf-8"),
  );
} catch (_e) {
  COMPONENTS_CATALOG = {};
}

/** Traduit un `t-default` Python (ex. "'primary'", "None", "True", "''")
 * en placeholder de snippet xdsl plausible (ex. `"primary"`, ``, `true`). */
function defaultToPlaceholder(pyDefault) {
  if (pyDefault === undefined || pyDefault === "None") return "";
  if (pyDefault === "True") return "true";
  if (pyDefault === "False") return "false";
  const quoted = pyDefault.match(/^'(.*)'$|^"(.*)"$/);
  if (quoted) {
    const inner = quoted[1] !== undefined ? quoted[1] : quoted[2];
    return `"${inner}"`;
  }
  return pyDefault; // nombre, liste/dict littéral Python — affiché tel quel, best-effort
}

/** Une entrée de complétion par prop RÉELLEMENT déclarée par ce composant
 * (extraite de son XML) — jamais une liste générique. */
function propCompletionsFor(catalogKey) {
  const entry = COMPONENTS_CATALOG[catalogKey];
  if (!entry) return null;
  return entry.props.map((p, idx) => ({
    label: p.name,
    insertText: `${p.name}: \${${idx + 1}:${defaultToPlaceholder(p.default)}}`,
    detail: `${catalogKey} — défaut ${p.default}`,
  }));
}

/** Complétions de NOM de composant/balise — deux formes (le nom court
 * "popover", valable si importé via `import { popover } from "xweb"`, et
 * le nom qualifié "xweb.popover", valable sans import). Toujours proposées
 * en contexte "element" : nester un composant est valide n'importe où du
 * contenu peut apparaître. */
function componentNameCompletions() {
  const out = [];
  for (const key of Object.keys(COMPONENTS_CATALOG).sort()) {
    const short = key.startsWith("xweb.") ? key.slice("xweb.".length) : key;
    const propNames = COMPONENTS_CATALOG[key].props.map((p) => p.name).join(", ");
    const detail = propNames ? `props: ${propNames}` : "aucune prop déclarée";
    out.push({ label: short, insertText: `${short} {\n\t$0\n}`, detail });
    if (short !== key) {
      out.push({ label: key, insertText: `${key} {\n\t$0\n}`, detail });
    }
  }
  return out;
}

/** Le premier mot d'un en-tête de bloc ("popover", "xweb.button"...)
 * correspond-il à un composant catalogué ? Teste la forme telle quelle
 * ET préfixée de "xweb." (composant importé sous son nom court). */
function resolveComponentKey(firstWord) {
  if (COMPONENTS_CATALOG[firstWord]) return firstWord;
  const qualified = `xweb.${firstWord}`;
  if (COMPONENTS_CATALOG[qualified]) return qualified;
  return null;
}

/** Compte les accolades en remontant depuis `text` (déjà tronqué au
 * curseur) pour retrouver l'en-tête du bloc englobant le plus proche.
 * Retourne `null` au niveau racine du fichier. */
function findEnclosingBlockHeader(text) {
  let depth = 0;
  for (let i = text.length - 1; i >= 0; i--) {
    const ch = text[i];
    if (ch === "}") {
      depth++;
    } else if (ch === "{") {
      if (depth === 0) {
        // Trouvé l'accolade ouvrante du bloc englobant — remonte encore
        // pour capturer son "en-tête" (mot-clé + nom éventuel).
        const before = text.slice(0, i);
        // [ \t] (jamais \s) entre les deux mots de l'en-tête : "channel c {"
        // est un seul en-tête sur une ligne, mais "method: POST\n    receive {"
        // ne doit PAS coller "POST" et "receive" juste parce qu'un \s générique
        // franchit aussi le saut de ligne entre deux lignes sans rapport (bug
        // réel trouvé en écrivant test/verify-completions.mjs).
        const m = before.match(/([A-Za-z_][A-Za-z0-9_.]*(?:[ \t]+[A-Za-z_][A-Za-z0-9_.]*)?)[ \t]*$/);
        return m ? m[1].trim() : "";
      }
      depth--;
    }
  }
  return null; // aucune accolade non fermée -> racine du fichier
}

function classifyContext(header) {
  if (header === null) return "top-level";
  const firstWord = header.split(/\s+/)[0];
  if (firstWord === "onmessage") return "onmessage";
  if (firstWord === "receive") return "receive";
  if (firstWord === "endpoint") return "endpoint";
  if (firstWord === "channel") return "channel";
  if (firstWord === "data") return "data-schema";
  if (firstWord === "headers") return "dict-literal"; // pas de complétion utile
  return "element"; // component NOM / balise brute / appel de composant
}

/**
 * Point d'entrée principal. `textBeforeCursor` = tout le texte du document
 * du début jusqu'au curseur (VS Code fournit ça nativement via
 * `document.getText(new Range(new Position(0,0), position))`).
 * Retourne une liste de `{label, insertText, detail?}` — `insertText` est
 * un format de snippet VS Code (`${1:...}`), à passer tel quel à
 * `vscode.SnippetString`.
 */
function getCompletions(textBeforeCursor) {
  const lineStart = textBeforeCursor.lastIndexOf("\n") + 1;
  const currentLine = textBeforeCursor.slice(lineStart);

  // Juste après un `@` -> décorateur de validation, quel que soit le
  // contexte englobant (permissif plutôt que strictement limité à `data`
  // — voir la note de conception en tête de fichier).
  if (/@\w*$/.test(currentLine)) {
    return DECORATORS;
  }

  const header = findEnclosingBlockHeader(textBeforeCursor);
  const context = classifyContext(header);

  switch (context) {
    case "top-level":
      return TOP_LEVEL_KEYWORDS;
    case "endpoint":
      return ENDPOINT_FIELDS;
    case "receive":
      return RECEIVE_FIELDS;
    case "channel":
      return CHANNEL_FIELDS;
    case "onmessage":
      return ONMESSAGE_FIELDS;
    case "data-schema":
      return []; // les lignes `champ: type` n'ont pas de vocabulaire fermé à compléter
    case "dict-literal":
      return [];
    case "element": {
      // Le bloc englobant est-il l'appel d'un VRAI composant xweb.* (popover,
      // xweb.button...) ? Alors ses props RÉELLEMENT déclarées (extraites de
      // son XML — hx_get EN UNDERSCORE pour un t-call composant, jamais
      // hx-get, contrairement à une balise HTML brute juste en dessous),
      // jamais la liste générique. `component NOM {`/une balise HTML/un
      // composant inconnu retombent sur les attributs génériques.
      const firstWord = header ? header.split(/\s+/)[0] : null;
      const componentKey = firstWord ? resolveComponentKey(firstWord) : null;
      const attrs = componentKey ? propCompletionsFor(componentKey) : COMMON_ELEMENT_ATTRS;
      return [...attrs, ...componentNameCompletions(), ...CONTROL_KEYWORDS, ...CONTENT_KEYWORDS];
    }
    default:
      return [...COMMON_ELEMENT_ATTRS, ...componentNameCompletions(), ...CONTROL_KEYWORDS, ...CONTENT_KEYWORDS];
  }
}

module.exports = {
  getCompletions,
  findEnclosingBlockHeader,
  classifyContext,
  resolveComponentKey,
  propCompletionsFor,
  componentNameCompletions,
  defaultToPlaceholder,
  TOP_LEVEL_KEYWORDS,
  DECORATORS,
  ENDPOINT_FIELDS,
  RECEIVE_FIELDS,
  CHANNEL_FIELDS,
  ONMESSAGE_FIELDS,
  COMMON_ELEMENT_ATTRS,
  COMPONENTS_CATALOG,
};
