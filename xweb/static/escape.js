/* Fonction d'échappement HTML centralisée — SEUL endroit où une valeur
de réponse (receive.schema) peut devenir du texte HTML côté navigateur.
Parité serveur : mêmes caractères que markupsafe (escape) —
& < > " '  ->  & < > " '
Cf. tests/test_xss_corpus.py pour le corpus de référence. 
*/
(function (global) {
    "use strict";

    var MAP = {
        "&": "\u0026\u0061\u006D\u0070\u003B",
        "<": "\u0026\u006C\u0074\u003B",
        ">": "\u0026\u0067\u0074\u003B",
        '"': "\u0026\u0071\u0075\u006F\u0074\u003B",
        "'": "\u0026\u0023\u0033\u0039\u003B"
    };

    function escapeHtml(value) {
        if (value == null) {
            return "";
        }
        return String(value).replace(/[&<>"']/g, function (ch) {
            return MAP[ch];
        });
    }

    global.XwebEscape = escapeHtml;
    global.XwebEscape.html = escapeHtml;
    global.escapeHtml = escapeHtml;
})(typeof window !== "undefined" ? window : globalThis);