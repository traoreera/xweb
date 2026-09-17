// Vérifie src/completions.js pour de vrai — pas de mock du contexte, du
// texte xdsl réaliste tronqué à un point de curseur précis, comme VS Code
// le ferait réellement (document.getText jusqu'à la position). Aucune
// dépendance à `vscode` (le module testé n'en a pas), donc exécutable en
// Node pur, sans lancer un Extension Development Host.
//
// Usage : node test/verify-completions.mjs

import { createRequire } from "node:module";
import assert from "node:assert/strict";

const require = createRequire(import.meta.url);
const { getCompletions, findEnclosingBlockHeader, classifyContext } = require("../src/completions.js");

let failures = 0;
function check(name, fn) {
  try {
    fn();
    console.log(`ok   — ${name}`);
  } catch (e) {
    failures++;
    console.error(`FAIL — ${name}\n      ${e.message}`);
  }
}

const labels = (list) => list.map((c) => c.label);

check("racine du fichier -> mots-clés de haut niveau", () => {
  const src = "component test { div { \"x\" } }\n\n";
  const got = labels(getCompletions(src));
  assert.ok(got.includes("channel"));
  assert.ok(got.includes("endpoint"));
  assert.ok(got.includes("@include"));
  assert.ok(!got.includes("bind"), "bind: n'a pas de sens à la racine");
});

check("dans channel { } -> les clés de channel, pas celles d'endpoint", () => {
  const src = 'channel contacts_feed {\n    url: "/stream"\n    ';
  const got = labels(getCompletions(src));
  assert.ok(got.includes("transport"));
  assert.ok(got.includes("onmessage"));
  assert.ok(!got.includes("method"), "method appartient à endpoint, pas à channel");
});

check("dans endpoint { } -> les clés d'endpoint, pas celles de channel", () => {
  const src = "endpoint save_contact {\n    method: POST\n    ";
  const got = labels(getCompletions(src));
  assert.ok(got.includes("url"));
  assert.ok(got.includes("receive"));
  assert.ok(!got.includes("transport"), "transport appartient à channel, pas à endpoint");
});

check("dans channel { onmessage { } } -> les clés de onmessage (bind/refresh/dispatch/event), rien d'autre", () => {
  const src = 'channel c {\n    url: "/x"\n    onmessage {\n        bind: { "#x": "y" }\n        ';
  const got = labels(getCompletions(src));
  assert.deepEqual(got.sort(), ["bind", "dispatch", "event", "refresh"].sort());
});

check("dans endpoint { receive { } } -> les clés de receive, pas celles d'endpoint", () => {
  const src = "endpoint e {\n    method: POST\n    receive {\n        type: json\n        ";
  const got = labels(getCompletions(src));
  assert.deepEqual(got.sort(), ["event", "schema", "target", "type"].sort());
});

check("après @ -> les décorateurs BUILTIN_VALIDATORS, ensemble fermé exact", () => {
  const src = "data d {\n    name: string @";
  const got = labels(getCompletions(src));
  assert.deepEqual(
    got.sort(),
    ["email", "in", "max", "max_length", "min", "min_length", "pattern", "required"].sort(),
  );
});

check("après @req (décorateur partiellement tapé) -> toujours la liste des décorateurs (VS Code filtre lui-même par préfixe)", () => {
  const src = "data d {\n    name: string @req";
  const got = labels(getCompletions(src));
  assert.ok(got.includes("required"));
});

check("dans component { } au niveau élément -> attributs génériques + structures de contrôle", () => {
  const src = 'component p {\n    div {\n        ';
  const got = labels(getCompletions(src));
  assert.ok(got.includes("id"));
  assert.ok(got.includes("hx-get"));
  assert.ok(got.includes("if"));
  assert.ok(got.includes("use_channel"));
});

check("findEnclosingBlockHeader retrouve bien le bloc le plus proche, pas le plus englobant", () => {
  const src = "channel c {\n    onmessage {\n        ";
  assert.equal(findEnclosingBlockHeader(src), "onmessage");
});

check("findEnclosingBlockHeader ignore un bloc déjà refermé (headers: {...} clos avant le curseur)", () => {
  const src = 'endpoint e {\n    headers: { "a": "b" }\n    ';
  const header = findEnclosingBlockHeader(src);
  assert.equal(classifyContext(header), "endpoint");
});

check("racine sans aucune accolade ouverte -> null / top-level", () => {
  assert.equal(findEnclosingBlockHeader("component "), null);
  assert.equal(classifyContext(null), "top-level");
});

check("dans data { } -> aucun vocabulaire fermé (noms de champs arbitraires), liste vide", () => {
  const src = "data contact_form {\n    ";
  assert.deepEqual(getCompletions(src), []);
});

// ---------------------------------------------------------------------------
// Catalogue réel des composants (design/src/components-catalog.json, généré
// par scripts/generate_components_catalog.py depuis xweb/components/*.xml)
// ---------------------------------------------------------------------------

check("le catalogue de composants est chargé et non vide (généré depuis xweb/components/*.xml)", () => {
  const { COMPONENTS_CATALOG } = require("../src/completions.js");
  assert.ok(Object.keys(COMPONENTS_CATALOG).length > 50, "catalogue vide ou trop petit — as-tu lancé generate_components_catalog.py ?");
  assert.ok(COMPONENTS_CATALOG["xweb.popover"], "xweb.popover devrait être dans le catalogue");
});

check("dans component { } au niveau élément -> les vrais noms de composants sont proposés (popover, xweb.popover)", () => {
  const src = 'component p {\n    div {\n        ';
  const got = labels(getCompletions(src));
  assert.ok(got.includes("popover"), "forme courte (import { popover } from \"xweb\")");
  assert.ok(got.includes("xweb.popover"), "forme qualifiée (sans import)");
  assert.ok(got.includes("table"));
  assert.ok(got.includes("button"));
});

check("dans popover { } -> les VRAIES props déclarées par xweb.popover (trigger_label, position...), pas les attributs génériques", () => {
  const src = "component p {\n    popover {\n        ";
  const got = labels(getCompletions(src));
  assert.ok(got.includes("trigger_label"));
  assert.ok(got.includes("trigger_class"));
  assert.ok(got.includes("position"));
  assert.ok(!got.includes("hx-get"), "hx-get (tiret) est la forme d'une balise HTML brute, pas d'un composant");
});

check("dans xweb.button { } (forme qualifiée) -> mêmes props que via le nom court", () => {
  const src = "component p {\n    xweb.button {\n        ";
  const got = labels(getCompletions(src));
  assert.ok(got.includes("variant"));
  assert.ok(got.includes("hx_get"), "props htmx d'un composant en UNDERSCORE (hx_get), jamais hx-get");
});

check("dans div { } (balise HTML brute, PAS un composant) -> attributs génériques hx-* en TIRET, pas les props d'un composant", () => {
  const src = "component p {\n    div {\n        ";
  const got = labels(getCompletions(src));
  assert.ok(got.includes("hx-get"), "balise brute -> tiret, comme dans contacts_demo.dsl (hx-delete, hx-target...)");
  assert.ok(!got.includes("hx_get"), "hx_get (underscore) est une prop de composant, pas un attribut de balise brute");
});

check("defaultToPlaceholder — None -> vide, True/False -> true/false (xdsl), chaîne Python -> chaîne xdsl", () => {
  const { defaultToPlaceholder } = require("../src/completions.js");
  assert.equal(defaultToPlaceholder("None"), "");
  assert.equal(defaultToPlaceholder("True"), "true");
  assert.equal(defaultToPlaceholder("False"), "false");
  assert.equal(defaultToPlaceholder("'primary'"), '"primary"');
  assert.equal(defaultToPlaceholder("''"), '""');
});

if (failures > 0) {
  console.error(`\n${failures} vérification(s) en échec`);
  process.exit(1);
}
console.log("\nToutes les vérifications de complétion xdsl passent.");
