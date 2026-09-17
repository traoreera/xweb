// Fait tourner syntaxes/xdsl.tmLanguage.json pour de vrai à travers le
// MÊME moteur de tokenisation TextMate que VS Code utilise en interne
// (vscode-textmate + vscode-oniguruma, le moteur de regex Oniguruma réel,
// pas une regex JS approximative) — sur du contenu .dsl RÉEL du dépôt
// (contacts_demo.dsl), pas des extraits inventés pour l'occasion. Même
// discipline que le reste de ce dépôt : un JSON de grammaire qui "a l'air
// bon" à la lecture peut très bien ne matcher aucun pattern en pratique
// (chevauchements de patterns, ancres oubliées, groupes mal nommés).
//
// Usage : node test/verify-grammar.mjs

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import assert from "node:assert/strict";

const require = createRequire(import.meta.url);
// CommonJS toutes les deux — require() direct plutôt que `import`, plus
// fiable que l'interop ESM/CJS de Node sur ces deux paquets précis (essayé
// d'abord, `import * as oniguruma` perd `loadWASM` au runtime malgré
// l'analyse statique qui le voit).
const oniguruma = require("vscode-oniguruma");
const { Registry, parseRawGrammar } = require("vscode-textmate");

const GRAMMAR_PATH = new URL("../syntaxes/xdsl.tmLanguage.json", import.meta.url);
const DEMO_DSL_PATH = new URL("../../contacts_demo.dsl", import.meta.url);

const wasmPath = require.resolve("vscode-oniguruma/release/onig.wasm");
const wasmBin = readFileSync(wasmPath).buffer;

await oniguruma.loadWASM(wasmBin);

const registry = new Registry({
  onigLib: Promise.resolve({
    createOnigScanner: (patterns) => new oniguruma.OnigScanner(patterns),
    createOnigString: (s) => new oniguruma.OnigString(s),
  }),
  loadGrammar: async (scopeName) => {
    if (scopeName !== "source.xdsl") return null;
    const content = readFileSync(GRAMMAR_PATH, "utf-8");
    return parseRawGrammar(content, GRAMMAR_PATH.pathname);
  },
});

const grammar = await registry.loadGrammar("source.xdsl");
if (!grammar) throw new Error("grammaire source.xdsl introuvable — chemin/scopeName incohérent");

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

/** Tokenise tout un texte multi-ligne, retourne les tokens de chaque ligne
 * avec leur texte source (plus pratique à asserter que des offsets bruts). */
function tokenizeAll(text) {
  let ruleStack = oniguruma.INITIAL ?? undefined;
  let state = null;
  const lines = text.split("\n");
  const out = [];
  for (const line of lines) {
    const res = grammar.tokenizeLine(line, state);
    state = res.ruleStack;
    out.push(
      res.tokens.map((t) => ({
        text: line.slice(t.startIndex, t.endIndex),
        scopes: t.scopes,
      })),
    );
  }
  return out;
}

function hasScopeContaining(tokens, text, scopeFragment) {
  return tokens.some((t) => t.text === text && t.scopes.some((s) => s.includes(scopeFragment)));
}

function flat(tokenLines) {
  return tokenLines.flat();
}

// --- Extraits synthétiques mais fidèles à la grammaire réelle -----------

check("mots-clés de déclaration : component/channel/endpoint/data/patch/copy", () => {
  const tokens = flat(
    tokenizeAll(
      "component test {\n" +
        "}\n" +
        "channel c {\n" +
        "}\n" +
        "endpoint e {\n" +
        "}\n" +
        "data d {\n" +
        "}\n" +
        "patch xweb.form {\n" +
        "}\n" +
        "copy xweb.form as x.y {\n" +
        "}\n",
    ),
  );
  for (const kw of ["component", "channel", "endpoint", "data", "patch", "copy"]) {
    assert.ok(
      hasScopeContaining(tokens, kw, "keyword.control.declaration.xdsl"),
      `"${kw}" devrait porter keyword.control.declaration.xdsl`,
    );
  }
});

check("commentaire // — toute la ligne scope comment.line", () => {
  const tokens = flat(tokenizeAll("// un commentaire\ncomponent c {}"));
  assert.ok(tokens.some((t) => t.scopes.some((s) => s.includes("comment.line.double-slash.xdsl"))));
});

check("décorateur connu (@required) vs inconnu (@bogus) — set fermé BUILTIN_VALIDATORS", () => {
  const tokens = flat(tokenizeAll('data d {\n    x: string @required @min_length(3) @bogus\n}'));
  assert.ok(
    hasScopeContaining(tokens, "required", "entity.name.function.decorator.xdsl"),
    "@required doit être reconnu comme décorateur valide",
  );
  assert.ok(
    hasScopeContaining(tokens, "min_length", "entity.name.function.decorator.xdsl"),
    "@min_length doit être reconnu comme décorateur valide",
  );
  assert.ok(
    hasScopeContaining(tokens, "bogus", "invalid.illegal.unknown-decorator.xdsl"),
    "@bogus (hors BUILTIN_VALIDATORS) doit être signalé invalid",
  );
});

check("chaîne avec interpolation ${...} — la chaîne ET l'interpolation sont scopées séparément", () => {
  const tokens = flat(tokenizeAll('hx-delete: "/api/contacts/${contact[\'id\']}"'));
  assert.ok(tokens.some((t) => t.scopes.some((s) => s.includes("string.quoted.double.xdsl"))));
  assert.ok(
    tokens.some((t) => t.scopes.some((s) => s.includes("punctuation.section.embedded.begin.xdsl"))),
    "${ doit ouvrir une interpolation scopée",
  );
});

check("nom de balise/composant (identifiant suivi de {) — entity.name.tag", () => {
  const tokens = flat(tokenizeAll("div {\n}\nxweb.button {\n}\n"));
  assert.ok(hasScopeContaining(tokens, "div", "entity.name.tag.xdsl"));
  assert.ok(hasScopeContaining(tokens, "xweb.button", "entity.name.tag.xdsl"));
});

check("attribut/champ (identifiant suivi de :) — entity.other.attribute-name, url/method/bind/refresh tous couverts", () => {
  const tokens = flat(tokenizeAll('url: "/x"\nmethod: POST\nbind: {}\nrefresh: "#x"\n'));
  for (const key of ["url", "method", "bind", "refresh"]) {
    assert.ok(
      hasScopeContaining(tokens, key, "entity.other.attribute-name.xdsl"),
      `"${key}:" devrait porter entity.other.attribute-name.xdsl`,
    );
  }
});

check("onmessage { ... } (ouvreur de bloc, PAS suivi de :) — entity.name.tag, pas attribute-name", () => {
  const tokens = flat(tokenizeAll("onmessage {\n}\n"));
  assert.ok(hasScopeContaining(tokens, "onmessage", "entity.name.tag.xdsl"));
});

check("hyperscript mode bloc _ { ... } — scope embarqué + mots-clés hyperscript reconnus", () => {
  const tokens = flat(tokenizeAll("_ {\n    on click\n        toggle .hidden on me\n}"));
  assert.ok(hasScopeContaining(tokens, "_", "entity.other.attribute-name.hyperscript.xdsl"));
  assert.ok(hasScopeContaining(tokens, "on", "keyword.control.hyperscript.xdsl"));
  assert.ok(hasScopeContaining(tokens, "toggle", "keyword.other.hyperscript.xdsl"));
  assert.ok(hasScopeContaining(tokens, "me", "variable.language.hyperscript.xdsl"));
});

check("hyperscript mode ligne _: ... s'arrête à la fin de ligne (ne mange pas la ligne suivante)", () => {
  const tokenLines = tokenizeAll('_ : on click log "x"\nspan { "après" }');
  const secondLineTokens = tokenLines[1];
  assert.ok(
    !secondLineTokens.some((t) => t.scopes.some((s) => s.includes("hyperscript"))),
    "la 2e ligne ne doit PAS être scopée hyperscript — le mode ligne s'arrête au \\n",
  );
});

check("@include \"xweb.shell\" — directive de fichier", () => {
  const tokens = flat(tokenizeAll('@include "xweb.shell"\n'));
  assert.ok(hasScopeContaining(tokens, "@include", "keyword.control.directive.xdsl"));
});

check("nombre entier/décimal et booléen", () => {
  const tokens = flat(tokenizeAll("min: 0\nmax: 3.14\nflag: true\n"));
  assert.ok(hasScopeContaining(tokens, "0", "constant.numeric.xdsl"));
  assert.ok(hasScopeContaining(tokens, "3.14", "constant.numeric.xdsl"));
  assert.ok(hasScopeContaining(tokens, "true", "constant.language.boolean.xdsl"));
});

// --- Le vrai fichier du dépôt : aucune ligne ne doit planter le tokenizer ---

check("contacts_demo.dsl (fichier réel du dépôt) se tokenise entièrement sans exception", () => {
  const real = readFileSync(DEMO_DSL_PATH, "utf-8");
  const lines = tokenizeAll(real); // lève si tokenizeLine plante sur une ligne
  assert.ok(lines.length > 50, "le fichier réel doit produire un nombre de lignes plausible");
  const flatTokens = flat(lines);
  assert.ok(hasScopeContaining(flatTokens, "channel", "keyword.control.declaration.xdsl"));
  assert.ok(hasScopeContaining(flatTokens, "dispatch", "entity.other.attribute-name.xdsl"));
});

if (failures > 0) {
  console.error(`\n${failures} vérification(s) en échec`);
  process.exit(1);
}
console.log("\nToutes les vérifications de grammaire xdsl passent (vrai moteur TextMate/Oniguruma).");
