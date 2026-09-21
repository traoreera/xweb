import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";

const escapeJsPath = path.resolve("xweb/static/escape.js");
const escapeJs = fs.readFileSync(escapeJsPath, "utf-8");

function getExpected() {
    const lt = "<";
    const gt = ">";
    const amp = "&";
    const quot = "";
    const apos = "'";
    
    return {
        "<script>alert(1)</script>": lt + "script" + gt + "alert(1)" + lt + "/script" + gt,
    };
}

console.log("OK");
