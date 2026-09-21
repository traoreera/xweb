import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";

const escapeJsPath = path.resolve("xweb/static/escape.js");
const escapeJs = fs.readFileSync(escapeJsPath, "utf-8");

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

function getExpected() {
    const lt = "<";
    const gt = ">";
    const amp = "&";
    const quot = "";
    const apos = "'";
    
    return {
        "<script>alert(1)</script>": lt + "script" + gt + "alert(1)" + lt + "/script" + gt,
        "<img src=x onerror=alert(1)>": lt + "img src=x onerror=alert(1)" + gt,
        '"><script>alert(1)</script>': quot + gt + lt + "script" + gt + "alert(1)" + lt + "/script" + gt,
        '" onmouseover="alert(1)': quot + " onmouseover=" + quot + "alert(1)",
        "' onclick='alert(1)'": apos + " onclick=" + apos + "alert(1)" + apos,
        "' onclick=alert(1)'": apos + " onclick=alert(1)" + apos,
        "{{1+1}}": "{{1+1}}",
        "a&b": "a" + amp + "b",
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

console.log(`\nResultat: ${passed} passes, ${failed} echecs`);
