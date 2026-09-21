#!/usr/bin/env node
/* Verification jsdom de XwebEscape (xweb/static/escape.js) contre le
   meme corpus de payloads que tests/test_xss_corpus.py.
   Doit passer SANS 'unsafe-eval' CSP -- escape.js n'utilise pas eval. */

import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";

// Charge escape.js
const escapeJsPath = path.resolve("xweb/static/escape.js");
const escapeJs = fs.readFileSync(escapeJsPath, "utf-8");

// Corpus identique a tests/test_xss_corpus.py
const PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    '"><script>alert(1)</script>',
    '" onmouseover="alert(1)',
    "' onclick='alert(1)'",
    "' onclick=alert(1)'",
    "{{1+1}}",
    "a&b",
    "<svg/onload=alert(1)>",
    "javascript:alert(1)",
];

// Resultats attendus - entites HTML construites par programme
// (on evite les entites dans le source JS qui cassent le parseur ES module)
function getExpected() {
    const A = String.fromCharCode(0x26); // &
    const lt = A + "lt;";
    const gt = A + "gt;";
    const amp = A + "amp;";
    const quot = A + "quot;";
    const apos = A + "#39;";
    
    return {
        "<script>alert(1)</script>": lt + "script" + gt + "alert(1)" + lt + "/script" + gt,
        "<img src=x onerror=alert(1)>": lt + "img src=x onerror=alert(1)" + gt,
        '"><script>alert(1)</script>': quot + gt + lt + "script" + gt + "alert(1)" + lt + "/script" + gt,
        '" onmouseover="alert(1)': quot + " onmouseover=" + quot + "alert(1)",
        "' onclick='alert(1)'": A + "#39; onclick=" + A + "#39;alert(1)" + A + "#39;",
        "' onclick=alert(1)'": A + "#39; onclick=alert(1)" + A + "#39;",
        "{{1+1}}": "{{1+1}}",
        "a&b": "a" + A + "amp;b",
        "<svg/onload=alert(1)>": lt + "svg/onload=alert(1)" + gt,
        "javascript:alert(1)": "javascript:alert(1)",
    };
}

function newDom(html) {
    const dom = new JSDOM(html, { runScripts: "dangerously", url: "http://localhost/" });
    dom.window.eval(escapeJs);
    return dom;
}

const dom = newDom("<!DOCTYPE html><html><body></body></html>");

const XwebEscape = dom.window.XwebEscape;
if (typeof XwebEscape !== "function") {
    console.error("ERREUR: XwebEscape n'est pas expose globalement");
    process.exit(1);
}

const EXPECTED = getExpected();

let failed = 0;
let passed = 0;

for (const payload of PAYLOADS) {
    const out = XwebEscape(payload);
    const expected = EXPECTED[payload];

    if (out !== expected) {
        console.error(`FAIL: payload=${JSON.stringify(payload)}`);
        console.error(`  attendu: ${JSON.stringify(expected)}`);
        console.error(`  obtenu:  ${JSON.stringify(out)}`);
        failed++;
        continue;
    }

    console.log(`OK: ${JSON.stringify(payload)} -> ${JSON.stringify(out)}`);
    passed++;
}

// Test bonus : chaine vide / null
const emptyTests = [null, undefined, ""];
for (const v of emptyTests) {
    const out = XwebEscape(v);
    if (out !== "") {
        console.error(`FAIL: empty input ${JSON.stringify(v)} -> ${JSON.stringify(out)}`);
        failed++;
    } else {
        passed++;
    }
}

console.log(`\nResultat: ${passed} passes, ${failed} echecs`);
if (failed > 0) {
    process.exit(1);
}