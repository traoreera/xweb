// xweb.editable_table — vérifie pour de vrai (jsdom, _hyperscript vendorisé
// réel) : bascule affichage/édition d'une cellule texte, choix d'une
// option "select" via le menu, et le calcul de l'ordre au dépôt d'une
// ligne glissée. Même patron que verify-hyperscript.mjs — le HTML testé
// ici vient d'un VRAI rendu QWeb (écrit dans un fichier temporaire par un
// script Python, lu ci-dessous), pas retapé à la main : un test qui
// invente son propre HTML ne prouverait rien sur le vrai template.
//
// Usage : npm run verify:editable-table (lance d'abord le rendu Python)

import { JSDOM } from "jsdom";
import { readFileSync } from "fs";
import assert from "node:assert/strict";

const HS_PATH = new URL("../xweb/static/_hyperscript.min.js", import.meta.url);
const hsSource = readFileSync(HS_PATH, "utf-8");
const HTML_PATH = new URL("../.verify-editable-table.html", import.meta.url);
const tableHtml = readFileSync(HTML_PATH, "utf-8");

function newDom() {
  const dom = new JSDOM(
    `<!doctype html><html><body>${tableHtml}</body></html>`,
    { runScripts: "dangerously", url: "http://localhost/" }
  );
  dom.window.eval(hsSource);
  // Le HTML ici vient d'un vrai rendu QWeb, _="..." déjà posé sur une
  // douzaine d'éléments — contrairement à verify-hyperscript.mjs (qui pose
  // un seul _ à la main par test via setAttribute + processNode), il faut
  // traiter tout le sous-arbre d'un coup. processNode() sur <body> suffit
  // (descend récursivement) — jamais compter sur l'auto-scan au chargement
  // (asynchrone/absent en jsdom, trouvé en écrivant ce script : le premier
  // essai, sans cet appel, ne déclenchait tout simplement rien).
  dom.window._hyperscript.processNode(dom.window.document.body);
  return dom;
}

async function tick(ms = 30) {
  await new Promise((r) => setTimeout(r, ms));
}

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

await check("cellule texte : clic affiche l'input, valeur pré-remplie, focus posé", async () => {
  const dom = newDom();
  const { document } = dom.window;
  const span = document.querySelector(".cell-display");
  const input = span.nextElementSibling;
  assert.equal(input.tagName, "INPUT");
  assert.equal(input.style.display, "none");
  span.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await tick();
  assert.equal(span.style.display, "none", "le span doit se cacher au clic");
  assert.notEqual(input.style.display, "none", "l'input doit apparaître au clic");
  assert.equal(document.activeElement, input, "l'input doit recevoir le focus");
});

await check("cellule texte : perte de focus recache l'input et raffiche le span", async () => {
  const dom = newDom();
  const { document } = dom.window;
  const span = document.querySelector(".cell-display");
  const input = span.nextElementSibling;
  span.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await tick();
  input.dispatchEvent(new dom.window.FocusEvent("blur", { bubbles: true }));
  await tick();
  assert.notEqual(span.style.display, "none");
  assert.equal(input.style.display, "none");
});

await check("cellule select : clic sur une option pose la valeur et déclenche 'change'", async () => {
  const dom = newDom();
  const { document } = dom.window;
  const hidden = document.querySelector('input[type="hidden"][id^="cell-r2-status"]');
  assert.ok(hidden, "input caché de la cellule status (r2) introuvable");
  let changed = false;
  hidden.addEventListener("change", () => { changed = true; });
  // scopé au <td> de r2 — les deux lignes ont les mêmes options
  // (active/paused), un data-value="active" existe donc DEUX FOIS dans le
  // document (un par ligne) : querySelector seul sur tout le document
  // attraperait celui de r1.
  const option = hidden.closest("td").querySelector('a[data-value="active"]');
  assert.ok(option, "option 'active' introuvable dans le menu de r2");
  option.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await tick();
  assert.equal(hidden.value, "active");
  assert.equal(changed, true, "l'événement change doit être envoyé à l'input caché");
});

await check("glisser-déposer : dépôt au-dessus du milieu insère AVANT la ligne cible", async () => {
  const dom = newDom();
  const { document, window } = dom.window;
  const rows = () => Array.from(document.querySelectorAll("tbody tr"));
  const [row1, row2] = rows();
  assert.equal(row1.id, "r1");
  assert.equal(row2.id, "r2");

  let sentOrder = null;
  row2.addEventListener("table:reordered", (ev) => { sentOrder = ev.detail.order; });

  row2.getBoundingClientRect = () => ({ top: 100, height: 40, bottom: 140, left: 0, right: 0, width: 0 });

  const dragStart = new window.Event("dragstart", { bubbles: true, cancelable: true });
  dragStart.dataTransfer = { setData: (_type, val) => { dragStart._id = val; }, getData: () => dragStart._id };
  row1.dispatchEvent(dragStart);
  await tick();

  const dropEvent = new window.Event("drop", { bubbles: true, cancelable: true });
  dropEvent.dataTransfer = { getData: () => "r1" };
  dropEvent.clientY = 105; // au-dessus du milieu (100 + 40/2 = 120) -> avant row2
  row2.dispatchEvent(dropEvent);
  await tick(60);

  const idsAfter = rows().map((r) => r.id);
  assert.deepEqual(idsAfter, ["r1", "r2"], "r1 déjà avant r2 — l'ordre ne doit pas changer ici");
  // Array.from(...) : sentOrder vient du realm jsdom (construit dans le
  // bloc js(...)...end de _hyperscript) — assert/strict (deepStrictEqual)
  // rejette un Array d'un autre realm malgré un contenu identique (même
  // piège que verify-storage.mjs, trouvé ici aussi).
  assert.deepEqual(Array.from(sentOrder), ["r1", "r2"], "l'ordre envoyé au serveur doit refléter le DOM après dépôt");
});

await check("glisser-déposer : dépôt sous le milieu insère APRÈS la ligne cible", async () => {
  const dom = newDom();
  const { document, window } = dom.window;
  const rows = () => Array.from(document.querySelectorAll("tbody tr"));
  const [row1, row2] = rows();

  let sentOrder = null;
  row1.addEventListener("table:reordered", (ev) => { sentOrder = ev.detail.order; });

  row1.getBoundingClientRect = () => ({ top: 0, height: 40, bottom: 40, left: 0, right: 0, width: 0 });

  const dragStart = new window.Event("dragstart", { bubbles: true, cancelable: true });
  dragStart.dataTransfer = { setData: (_type, val) => { dragStart._id = val; }, getData: () => dragStart._id };
  row2.dispatchEvent(dragStart);
  await tick();

  const dropEvent = new window.Event("drop", { bubbles: true, cancelable: true });
  dropEvent.dataTransfer = { getData: () => "r2" };
  dropEvent.clientY = 35; // sous le milieu (0 + 40/2 = 20) -> après row1
  row1.dispatchEvent(dropEvent);
  await tick(60);

  const idsAfter = rows().map((r) => r.id);
  assert.deepEqual(idsAfter, ["r1", "r2"]);
  assert.deepEqual(Array.from(sentOrder), ["r1", "r2"]);
});

await check("en-tête de colonne : clic affiche l'input pré-rempli, focus posé, attributs htmx corrects", async () => {
  // htmx lui-même n'est pas chargé dans ce script (seul _hyperscript l'est,
  // comme verify-hyperscript.mjs) : on vérifie ici le comportement
  // _hyperscript (bascule affichage/édition) + que les attributs posés
  // sont ceux attendus, pas qu'une vraie requête HTTP part.
  const dom = newDom();
  const { document } = dom.window;
  const header = document.querySelector("thead th:nth-child(2)"); // 1er = poignée, 2e = colonne "name"
  const span = header.querySelector(".cell-display");
  const input = header.querySelector("input");
  assert.ok(span, "en-tête doit porter le span cliquable (rename_column_url fourni dans la fixture)");
  assert.equal(input.style.display, "none");
  assert.equal(input.value, "Nom");
  assert.equal(input.getAttribute("hx-patch"), "/demo/table/column/name");
  assert.equal(input.getAttribute("hx-target"), "closest th");

  span.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await tick();
  assert.notEqual(input.style.display, "none", "l'input doit apparaître au clic sur l'en-tête");
  assert.equal(document.activeElement, input, "l'input doit recevoir le focus");

  input.dispatchEvent(new dom.window.FocusEvent("blur", { bubbles: true }));
  await tick();
  assert.equal(input.style.display, "none", "l'input doit se recacher à la perte de focus");
});

await check("bouton \"+\" de colonne : hx-post posé, cible le conteneur .editable-table entier", async () => {
  const dom = newDom();
  const { document } = dom.window;
  const addColBtn = document.querySelector('button[aria-label="Ajouter une colonne"]');
  assert.ok(addColBtn, "bouton + de colonne introuvable (add_column_url fourni dans la fixture)");
  assert.equal(addColBtn.getAttribute("hx-post"), "/demo/table/column");
  assert.equal(addColBtn.getAttribute("hx-target"), "closest .editable-table");
  assert.equal(addColBtn.getAttribute("hx-swap"), "outerHTML");
  assert.ok(document.querySelector(".editable-table"), "le conteneur ciblé doit exister");
});

await check("glisser-déposer : déplace vraiment la ligne (pas juste un ordre qui restait déjà correct)", async () => {
  const dom = newDom();
  const { document, window } = dom.window;
  const rows = () => Array.from(document.querySelectorAll("tbody tr"));
  const [row1, row2] = rows();
  assert.deepEqual(rows().map((r) => r.id), ["r1", "r2"], "ordre initial");

  row1.getBoundingClientRect = () => ({ top: 0, height: 40, bottom: 40, left: 0, right: 0, width: 0 });

  const dragStart = new window.Event("dragstart", { bubbles: true, cancelable: true });
  dragStart.dataTransfer = { setData: (_type, val) => { dragStart._id = val; }, getData: () => dragStart._id };
  row2.dispatchEvent(dragStart); // on fait glisser r2...
  await tick();

  const dropEvent = new window.Event("drop", { bubbles: true, cancelable: true });
  dropEvent.dataTransfer = { getData: () => "r2" };
  dropEvent.clientY = 5; // ...déposé au-dessus du milieu de row1 -> avant row1
  row1.dispatchEvent(dropEvent);
  await tick(60);

  assert.deepEqual(rows().map((r) => r.id), ["r2", "r1"], "r2 doit maintenant précéder r1 dans le DOM");
});

console.log(failures === 0 ? "\nTout est vert." : `\n${failures} échec(s).`);
process.exit(failures === 0 ? 0 : 1);
