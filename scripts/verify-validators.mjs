// Vérifie xweb/static/validators.js pour de vrai, contre les RÉSULTATS
// RÉELS de xdsl/validators.py (source de vérité) sur les mêmes vecteurs —
// pas une comparaison de code lu, une comparaison de comportement mesuré.
// Même patron que verify-storage.mjs/verify-live-channel.mjs.
//
// Prérequis : uv run python scripts/validators_fixture.py (écrit
// .verify-validators.json depuis le VRAI xdsl/validators.py).
// Usage : npm run verify:validators

import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const HERE = new URL(".", import.meta.url);
const fixture = JSON.parse(readFileSync(new URL("../.verify-validators.json", HERE), "utf-8"));
const validatorsSrc = readFileSync(new URL("../xweb/static/validators.js", HERE), "utf-8");

let failures = 0;

async function check(name, fn) {
  try {
    await fn();
    console.log(`ok   — ${name}`);
  } catch (e) {
    failures++;
    console.error(`FAIL — ${name}\n      ${e.message}`);
  }
}

function newSandbox() {
  const fn = new Function("window", "console", validatorsSrc + "\n;return window;");
  return fn({}, console);
}

await check(`vecteurs règle-par-règle (${fixture.vectors.length}) identiques à xdsl/validators.py`, () => {
  const window = newSandbox();
  window.XWEB_SCHEMAS = { __vector__: null };
  for (const v of fixture.vectors) {
    window.XWEB_SCHEMAS.__vector__ = { field: [[v.rule, v.args]] };
    const result = window.XwebValidate("__vector__", { field: v.value });
    assert.equal(
      result.valid,
      v.valid,
      `${v.rule}(${JSON.stringify(v.args)}) sur ${JSON.stringify(v.value)} : attendu valid=${v.valid}, eu valid=${result.valid}`,
    );
    const gotErrors = result.errors.field || [];
    assert.equal(
      JSON.stringify(gotErrors),
      JSON.stringify(v.errors),
      `${v.rule}(${JSON.stringify(v.args)}) sur ${JSON.stringify(v.value)} : messages d'erreur différents`,
    );
  }
});

await check("validate_dict multi-champs identique à xdsl/validators.py::validate_dict", () => {
  const window = newSandbox();
  window.XWEB_SCHEMAS = { contact_form: fixture.schema };
  for (const c of fixture.dict_cases) {
    const result = window.XwebValidate("contact_form", c.data);
    assert.equal(result.valid, c.valid, `data=${JSON.stringify(c.data)}`);
    assert.equal(
      JSON.stringify(result.errors),
      JSON.stringify(c.errors),
      `data=${JSON.stringify(c.data)}`,
    );
  }
});

await check("schéma absent de window.XWEB_SCHEMAS -> valid:false explicite, jamais un silencieux true", () => {
  const window = newSandbox();
  window.XWEB_SCHEMAS = {};
  const result = window.XwebValidate("jamais_declare", { x: 1 });
  assert.equal(result.valid, false);
});

if (failures > 0) {
  console.error(`\n${failures} vérification(s) en échec`);
  process.exit(1);
}
console.log("\nToutes les vérifications validators.js passent (parité avec xdsl/validators.py).");
