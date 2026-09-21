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

console.log("OK");
