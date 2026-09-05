// Fait tourner les extraits _hyperscript des docs (theming.md, shell.md)
// contre le vrai fichier vendorisé (xweb/static/_hyperscript.min.js) dans
// un vrai DOM (jsdom) — pas une lecture de la syntaxe, une exécution.
// Trouvé en écrivant ce script : #html n'est pas la balise <html>, c'est
// le sélecteur id="html" — document.documentElement est le bon idiome
// (voir docs/theming.md, corrigé suite à ce test).
//
// Usage : npm install && node scripts/verify-hyperscript.mjs
// Sort avec un code non-nul si un des assert échoue (utilisable en CI).

import { JSDOM } from "jsdom";
import { readFileSync } from "fs";
import assert from "node:assert/strict";

const HS_PATH = new URL("../xweb/static/_hyperscript.min.js", import.meta.url);
const hsSource = readFileSync(HS_PATH, "utf-8");

function newDom(html) {
  const dom = new JSDOM(html, { runScripts: "dangerously", url: "http://localhost/" });
  dom.window.eval(hsSource);
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

// ---------------------------------------------------------------------
// docs/theming.md — bascule de thème
// ---------------------------------------------------------------------
await check("theming.md — bascule light/dark + localStorage", async () => {
  const dom = newDom(
    `<!doctype html><html data-theme="light"><body><button id="toggle">x</button></body></html>`
  );
  const { document, localStorage } = dom.window;
  const html = document.documentElement;
  const btn = document.getElementById("toggle");

  btn.setAttribute(
    "_",
    `on click
       if document.documentElement.dataset.theme is 'dark' set document.documentElement.dataset.theme to 'light'
       else set document.documentElement.dataset.theme to 'dark'
     end
     then call localStorage.setItem('theme', document.documentElement.dataset.theme)`
  );
  dom.window._hyperscript.processNode(btn);

  assert.equal(html.getAttribute("data-theme"), "light");
  btn.click();
  await tick();
  assert.equal(html.getAttribute("data-theme"), "dark");
  assert.equal(localStorage.getItem("theme"), "dark");
  btn.click();
  await tick();
  assert.equal(html.getAttribute("data-theme"), "light");
  assert.equal(localStorage.getItem("theme"), "light");
});

// ---------------------------------------------------------------------
// docs/shell.md — palette de commandes : raccourci clavier
// ---------------------------------------------------------------------
await check("shell.md — ctrl+k ouvre la palette", async () => {
  const dom = newDom(`<!doctype html><html><body><div id="palette" class="modal"></div></body></html>`);
  const { document, window } = dom.window;
  const palette = document.getElementById("palette");
  palette.setAttribute("_", "on keydown[key=='k' and ctrlKey] from window toggle .modal-open on me");
  dom.window._hyperscript.processNode(palette);

  assert.equal(palette.className, "modal");
  window.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }));
  await tick();
  assert.equal(palette.className, "modal modal-open");
});

// ---------------------------------------------------------------------
// docs/shell.md — palette de commandes : filtrage local
// ---------------------------------------------------------------------
await check("shell.md — filtrage masque les commandes non matchées", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <input id="search" type="text"/>
    <ul id="cmd-list">
      <li>crm_app · nouveau contact</li>
      <li>stock · ajuster un stock</li>
    </ul>
  </body></html>`);
  const { document } = dom.window;
  const search = document.getElementById("search");
  search.setAttribute(
    "_",
    "on input show <li/> in #cmd-list when its textContent.toLowerCase() contains my value.toLowerCase()"
  );
  dom.window._hyperscript.processNode(search);

  search.value = "stock";
  search.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  await tick();

  const items = [...document.querySelectorAll("#cmd-list li")];
  assert.equal(items[0].style.display, "none", "crm_app doit être masqué");
  assert.notEqual(items[1].style.display, "none", "stock doit rester visible");
});

// ---------------------------------------------------------------------
// components/alert.xml — bouton de fermeture, "remove closest .alert"
// ---------------------------------------------------------------------
await check("alert.xml — le bouton de fermeture retire bien l'alerte du DOM", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <div class="alert" id="a1">
      <span>message</span>
      <button id="dismiss">x</button>
    </div>
  </body></html>`);
  const { document } = dom.window;
  const btn = document.getElementById("dismiss");
  btn.setAttribute("_", "on click remove closest .alert");
  dom.window._hyperscript.processNode(btn);

  assert.ok(document.getElementById("a1"), "l'alerte doit être présente avant le clic");
  btn.click();
  await tick();
  assert.equal(document.getElementById("a1"), null, "l'alerte doit être retirée du DOM après le clic");
});

if (failures > 0) {
  console.error(`\n${failures} vérification(s) échouée(s)`);
  process.exit(1);
}
console.log("\nToutes les vérifications _hyperscript passent.");

// ── Ajouts du shell reconstruit (components/shell.xml, layout.xml,
//    password.xml, toast.xml) — même principe : exécution réelle, pas lecture.

await check("shell.xml — le bouton de la topbar ouvre la palette et focus l'input", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <button id="open" _="on click add .modal-open to #command-palette then call #cmd-input.focus()">ouvrir</button>
    <div id="command-palette" class="modal"><input id="cmd-input" type="text"/></div>
  </body></html>`);
  const { document } = dom.window;
  dom.window._hyperscript.processNode(document.body);
  document.getElementById("open").click();
  await tick();
  assert.ok(document.getElementById("command-palette").classList.contains("modal-open"), "modal-open absent");
  assert.equal(document.activeElement, document.getElementById("cmd-input"), "l'input doit avoir le focus");
});

await check("shell.xml — Ctrl+K est intercepté (halt) et Escape referme", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <div id="command-palette" class="modal"
         _="on keydown[key=='k' and ctrlKey] from window halt the event then toggle .modal-open on me then call #cmd-input.focus()
            on keydown[key=='Escape'] from window remove .modal-open from me">
      <input id="cmd-input" type="text"/>
    </div>
  </body></html>`);
  const { document, KeyboardEvent } = dom.window;
  dom.window._hyperscript.processNode(document.body);
  const ev = new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true, cancelable: true });
  dom.window.dispatchEvent(ev);
  await tick();
  assert.ok(document.getElementById("command-palette").classList.contains("modal-open"), "Ctrl+K doit ouvrir");
  assert.ok(ev.defaultPrevented, "halt the event doit annuler le raccourci navigateur");
  dom.window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await tick();
  assert.ok(!document.getElementById("command-palette").classList.contains("modal-open"), "Escape doit fermer");
});

await check("password.xml — la bascule afficher/masquer change le type de l'input (possessif 's)", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <input type="password" id="pw" name="pw"/>
    <button id="t" _="on click if #pw's type is 'password' set #pw's type to 'text' else set #pw's type to 'password' end">œil</button>
  </body></html>`);
  const { document } = dom.window;
  dom.window._hyperscript.processNode(document.body);
  document.getElementById("t").click();
  await tick();
  assert.equal(document.getElementById("pw").type, "text");
  document.getElementById("t").click();
  await tick();
  assert.equal(document.getElementById("pw").type, "password");
});

await check("toast.xml — init wait Ns then remove me retire bien le toast", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <div id="toasts"><div id="t1" class="alert" _="init wait 50ms then remove me">ok</div></div>
  </body></html>`);
  const { document } = dom.window;
  dom.window._hyperscript.processNode(document.body);
  assert.ok(document.getElementById("t1"), "présent au départ");
  await tick(200);
  assert.equal(document.getElementById("t1"), null, "doit avoir disparu après le délai");
});

await check("shell.xml — un clic sur une commande referme la palette", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <div id="command-palette" class="modal modal-open"><ul><li><a id="c" href="#" _="on click remove .modal-open from #command-palette">Cmd</a></li></ul></div>
  </body></html>`);
  const { document } = dom.window;
  dom.window._hyperscript.processNode(document.body);
  document.getElementById("c").click();
  await tick();
  assert.ok(!document.getElementById("command-palette").classList.contains("modal-open"));
});

// plugins/account/templates/organization*.xml — confirmation native avant
// une action destructive (retirer un membre, supprimer un rôle). jsdom
// n'implémente pas window.confirm par défaut (jsdom/jsdom#1523) — posé ici
// comme le ferait un vrai navigateur, pour vérifier _hyperscript lui-même,
// pas jsdom.
// "halt the event" appelle preventDefault() (vérifié ci-dessous via l'objet
// Event lui-même — c'est ce que le navigateur consulte pour décider de
// vraiment soumettre le formulaire) mais PAS stopImmediatePropagation() :
// un test qui vérifie via un second listener sibling verrait ce listener
// tourner quand même, ce n'est pas ce qui compte en usage réel où
// _hyperscript est le seul gestionnaire sur cet évènement.
await check("organization.xml — confirm() refusé empêche la soumission réelle (preventDefault)", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <form id="f" _="on submit if not confirm('Retirer ce membre de cette organisation ?') halt the event">
      <input type="submit"/>
    </form>
  </body></html>`);
  const { document } = dom.window;
  dom.window.confirm = () => false;
  dom.window._hyperscript.processNode(document.body);
  const ev = new dom.window.Event("submit", { bubbles: true, cancelable: true });
  document.getElementById("f").dispatchEvent(ev);
  await tick();
  assert.equal(ev.defaultPrevented, true, "confirm() refusé doit empêcher la soumission réelle du formulaire");
});

await check("organization.xml — confirm() accepté laisse la soumission suivre son cours", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <form id="f" _="on submit if not confirm('Supprimer ce rôle ? Les membres concernés perdront les permissions associées.') halt the event">
      <input type="submit"/>
    </form>
  </body></html>`);
  const { document } = dom.window;
  dom.window.confirm = () => true;
  dom.window._hyperscript.processNode(document.body);
  const ev = new dom.window.Event("submit", { bubbles: true, cancelable: true });
  document.getElementById("f").dispatchEvent(ev);
  await tick();
  assert.equal(ev.defaultPrevented, false, "une confirmation acceptée ne doit jamais empêcher la soumission");
});

await check("organization_roles.xml — le filtre masque les permissions non matchées, tous types de balises mélangés", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <input id="search" type="text" _="on input show &lt;.perm-row/&gt; in #list when its textContent.toLowerCase() contains my value.toLowerCase()"/>
    <div id="list">
      <label class="perm-row">submissions:list</label>
      <div class="perm-row">user:read</div>
    </div>
  </body></html>`);
  const { document } = dom.window;
  dom.window._hyperscript.processNode(document.body);
  const search = document.getElementById("search");
  search.value = "user";
  search.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  await tick();
  const rows = [...document.querySelectorAll(".perm-row")];
  assert.equal(rows[0].style.display, "none", "submissions:list doit être masqué");
  assert.notEqual(rows[1].style.display, "none", "user:read doit rester visible");
});

// ---------------------------------------------------------------------
// xweb/components/kanban.xml — glisser-déposer natif HTML5, docs/components.md.
// jsdom 25 n'implémente ni DragEvent ni DataTransfer (probé en écrivant ce
// test : `new dom.window.DataTransfer()` lève "is not a constructor") — un
// Event générique + un objet dataTransfer minimal (setData/getData, même
// contrat que le vrai DataTransfer) suffit : _hyperscript n'appelle que ces
// deux méthodes. Piège réel trouvé en écrivant kanban.xml : `move X to end
// of Y` ne parse PAS avec cette version vendorisée de _hyperscript (erreur
// "Expected 'end' but found 'move'" — le mot "end" de "to end of" entre en
// conflit avec le "end" qui referme un bloc if/end) ; `put X at end of Y`
// est l'équivalent qui parse et déplace vraiment le nœud DOM (pas un
// clone — vérifié ci-dessous : la carte disparaît de sa colonne d'origine).
// ---------------------------------------------------------------------

function makeDataTransfer() {
  const store = new Map();
  return { setData: (t, v) => store.set(t, v), getData: (t) => store.get(t) ?? "" };
}

await check("kanban.xml — glisser une carte d'une colonne à l'autre la déplace vraiment (pas un clone)", async () => {
  const colScript = `on dragover halt the event then add .bg-base-300 to me
     on dragleave remove .bg-base-300 from me
     on drop halt the event then remove .bg-base-300 from me
        set draggedId to event.dataTransfer.getData('text/plain')
        set draggedCard to document.getElementById(draggedId)
        if draggedCard is not null
          put draggedCard at end of me
          send kanban:moved(card_id: draggedId, column_id: my.dataset.columnId) to draggedCard
        end`;
  const cardScript = `on dragstart call event.dataTransfer.setData('text/plain', my.id) then add .opacity-50 to me
     on dragend remove .opacity-50 from me`;

  const dom = newDom(`<!doctype html><html><body>
    <div id="col-todo" class="kanban-column" data-column-id="todo"></div>
    <div id="col-doing" class="kanban-column" data-column-id="doing"></div>
  </body></html>`);
  const { document } = dom.window;

  const colTodo = document.getElementById("col-todo");
  const colDoing = document.getElementById("col-doing");
  colTodo.setAttribute("_", colScript);
  colDoing.setAttribute("_", colScript);

  const card = document.createElement("div");
  card.id = "k-1";
  card.className = "kanban-card";
  card.setAttribute("draggable", "true");
  card.setAttribute("_", cardScript);
  card.textContent = "Carte 1";
  colTodo.appendChild(card);
  dom.window._hyperscript.processNode(document.body);

  const dt = makeDataTransfer();

  const dragstart = new dom.window.Event("dragstart", { bubbles: true, cancelable: true });
  dragstart.dataTransfer = dt;
  card.dispatchEvent(dragstart);
  await tick();
  assert.equal(dt.getData("text/plain"), "k-1", "dragstart doit poser l'id de la carte dans dataTransfer");
  assert.ok(card.classList.contains("opacity-50"), "dragstart doit griser la carte");

  const dragover = new dom.window.Event("dragover", { bubbles: true, cancelable: true });
  dragover.dataTransfer = dt;
  colDoing.dispatchEvent(dragover);
  await tick();
  assert.equal(dragover.defaultPrevented, true, "dragover doit halt (preventDefault) pour autoriser le drop");
  assert.ok(colDoing.classList.contains("bg-base-300"), "dragover doit surligner la colonne cible");

  let detail = null;
  card.addEventListener("kanban:moved", (e) => { detail = e.detail; });
  const drop = new dom.window.Event("drop", { bubbles: true, cancelable: true });
  drop.dataTransfer = dt;
  colDoing.dispatchEvent(drop);
  await tick();

  assert.equal(card.parentElement.id, "col-doing", "la carte doit avoir physiquement bougé vers la colonne cible");
  assert.equal(colTodo.contains(card), false, "la carte ne doit plus être dans son ancienne colonne (put déplace, ne clone pas)");
  assert.ok(!colDoing.classList.contains("bg-base-300"), "le surlignage doit disparaître après le drop");
  assert.ok(detail, "un événement kanban:moved doit avoir été envoyé à la carte");
  assert.equal(detail.card_id, "k-1");
  assert.equal(detail.column_id, "doing");
});

// ---------------------------------------------------------------------
// xweb/components/layout.xml — xweb.sidebar_toggle : repli/dépli desktop
// de la sidebar, même mécanique que xweb.theme_toggle (data-attribut sur
// <html> + localStorage), docs/shell.md.
// ---------------------------------------------------------------------
await check("layout.xml — xweb.sidebar_toggle bascule data-sidebar et le persiste en localStorage", async () => {
  const dom = newDom(`<!doctype html><html data-sidebar="expanded"><body><button id="toggle">t</button></body></html>`);
  const { document, localStorage } = dom.window;
  document.getElementById("toggle").setAttribute(
    "_",
    `on click
                 if document.documentElement.dataset.sidebar is 'collapsed' set document.documentElement.dataset.sidebar to 'expanded'
                 else set document.documentElement.dataset.sidebar to 'collapsed'
               end
               then call localStorage.setItem('sidebar', document.documentElement.dataset.sidebar)`
  );
  dom.window._hyperscript.processNode(document.body);

  document.getElementById("toggle").click();
  await tick();
  assert.equal(document.documentElement.dataset.sidebar, "collapsed");
  assert.equal(localStorage.getItem("sidebar"), "collapsed");

  document.getElementById("toggle").click();
  await tick();
  assert.equal(document.documentElement.dataset.sidebar, "expanded");
  assert.equal(localStorage.getItem("sidebar"), "expanded");
});

// ---------------------------------------------------------------------
// xweb/components/popover.xml — piège réel trouvé en l'écrivant : sans
// "then halt the event" sur le déclencheur, le MÊME clic qui ouvre le
// popover est vu comme "elsewhere" par le panneau (l'event bulle jusqu'au
// document juste après avoir ouvert le panneau) et le referme aussitôt.
// ---------------------------------------------------------------------
await check("popover.xml — ouvre au clic, ferme sur clic extérieur et sur Escape, jamais sur un clic à l'intérieur", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <button id="btn" _="on click toggle .popover-open on #panel then halt the event">open</button>
    <div id="panel" class="popover-panel"
         _="on click from elsewhere remove .popover-open from me
            on keyup[key=='Escape'] from the document remove .popover-open from me">content</div>
  </body></html>`);
  const { document } = dom.window;
  dom.window._hyperscript.processNode(document.body);
  const btn = document.getElementById("btn");
  const panel = document.getElementById("panel");

  btn.click();
  await tick();
  assert.ok(panel.classList.contains("popover-open"), "ouvert après clic sur le déclencheur");

  document.body.click();
  await tick();
  assert.ok(!panel.classList.contains("popover-open"), "fermé par un clic ailleurs");

  btn.click();
  await tick();
  document.dispatchEvent(new dom.window.KeyboardEvent("keyup", { key: "Escape", bubbles: true }));
  await tick();
  assert.ok(!panel.classList.contains("popover-open"), "fermé par Escape");

  btn.click();
  await tick();
  panel.click();
  await tick();
  assert.ok(panel.classList.contains("popover-open"), "un clic DANS le panneau ne doit pas le fermer");
});

// ---------------------------------------------------------------------
// xweb/components/popup.xml — menu contextuel positionné au curseur.
// Réutilise .popover-panel/.popover-open (xweb.popover) mais le
// déclencheur est `contextmenu` + `halt the event`, posé sur la ZONE
// elle-même — jamais sur `document` : un clic droit hors de la zone doit
// garder le menu natif du navigateur disponible (sinon toute la page
// perd son clic droit natif, un vrai régression de confort, pas juste
// un détail esthétique).
// ---------------------------------------------------------------------
await check("popup.xml — clic droit sur la zone positionne le panneau au curseur et l'ouvre", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <div id="zone" _="on contextmenu halt the event
                       then set #zone-panel's style.left to (event.clientX + 'px')
                       then set #zone-panel's style.top to (event.clientY + 'px')
                       then add .popover-open to #zone-panel">carte</div>
    <ul id="zone-panel" class="popover-panel fixed"
        _="on click from elsewhere remove .popover-open from me
           on keyup[key=='Escape'] from the document remove .popover-open from me">
      <li><a href="#">Action</a></li>
    </ul>
  </body></html>`);
  const { document, window } = dom.window;
  dom.window._hyperscript.processNode(document.body);
  const zone = document.getElementById("zone");
  const panel = document.getElementById("zone-panel");

  const ev = new window.MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 200, clientY: 80 });
  zone.dispatchEvent(ev);
  await tick();
  assert.equal(ev.defaultPrevented, true, "le menu natif du navigateur doit être supprimé sur la zone");
  assert.equal(panel.style.left, "200px");
  assert.equal(panel.style.top, "80px");
  assert.ok(panel.classList.contains("popover-open"));

  document.body.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await tick();
  assert.ok(!panel.classList.contains("popover-open"), "fermé par un clic ailleurs");
});

await check("popup.xml — un clic droit HORS de la zone garde le menu natif du navigateur", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <div id="zone" _="on contextmenu halt the event then add .popover-open to #zone-panel">carte</div>
    <div id="ailleurs">reste de la page</div>
    <ul id="zone-panel" class="popover-panel fixed"><li>x</li></ul>
  </body></html>`);
  const { document, window } = dom.window;
  dom.window._hyperscript.processNode(document.body);
  const ailleurs = document.getElementById("ailleurs");
  const ev = new window.MouseEvent("contextmenu", { bubbles: true, cancelable: true });
  ailleurs.dispatchEvent(ev);
  await tick();
  assert.equal(ev.defaultPrevented, false, "halt the event est scopé à la zone, jamais posé sur document");
});

// ---------------------------------------------------------------------
// xweb/components/combobox.xml — filtrage (même idiome que
// organization_roles.xml) + sélection : la valeur de l'option vient d'un
// attribut data- (my.dataset.value), jamais interpolée en dur dans le
// script _hyperscript (voir la docstring de combobox.xml).
// ---------------------------------------------------------------------
await check("combobox.xml — filtre les options et pose la valeur choisie dans le champ caché ET le champ visible", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <input type="hidden" id="combo-1" value=""/>
    <input type="text" id="combo-1-input" value=""
           _="on input show &lt;.combobox-option/&gt; in #combo-1-list when its textContent.toLowerCase() contains my value.toLowerCase()"/>
    <ul id="combo-1-list">
      <li class="combobox-option"><a data-value="fr" _="on click
          set document.getElementById('combo-1').value to my dataset.value
          set document.getElementById('combo-1-input').value to my textContent">France</a></li>
      <li class="combobox-option"><a data-value="de" _="on click
          set document.getElementById('combo-1').value to my dataset.value
          set document.getElementById('combo-1-input').value to my textContent">Allemagne</a></li>
    </ul>
  </body></html>`);
  const { document } = dom.window;
  dom.window._hyperscript.processNode(document.body);
  const input = document.getElementById("combo-1-input");
  const hidden = document.getElementById("combo-1");
  const [fr, de] = document.querySelectorAll(".combobox-option");

  input.value = "alle";
  input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  await tick();
  assert.equal(fr.style.display, "none", "France doit être masqué");
  assert.notEqual(de.style.display, "none", "Allemagne doit rester visible");

  de.querySelector("a").click();
  await tick();
  assert.equal(hidden.value, "de", "le champ caché doit recevoir la vraie valeur (data-value)");
  assert.equal(input.value, "Allemagne", "le champ visible doit afficher le libellé");
});

// ---------------------------------------------------------------------
// xweb/components/calendar.xml + datepicker.xml — un jour cliqué envoie
// calendar:select(iso:…) au calendrier (id), que le panneau du datepicker
// écoute via "from #id" pour se remplir et se refermer.
// ---------------------------------------------------------------------
await check("calendar.xml -> datepicker.xml — cliquer un jour pose la date choisie et referme le panneau", async () => {
  const dom = newDom(`<!doctype html><html><body>
    <div id="cal">
      <button id="day15" data-iso="2026-09-15" _="on click send calendar:select(iso: my.dataset.iso) to #cal">15</button>
    </div>
    <input type="hidden" id="dp-value"/>
    <input type="text" id="dp-input"/>
    <div id="dp-panel" class="popover-panel popover-open"
         _="on calendar:select from #cal
               set document.getElementById('dp-value').value to event.detail.iso
               set document.getElementById('dp-input').value to event.detail.iso
               remove .popover-open from me">panel</div>
  </body></html>`);
  const { document } = dom.window;
  dom.window._hyperscript.processNode(document.body);

  document.getElementById("day15").click();
  await tick();

  assert.equal(document.getElementById("dp-value").value, "2026-09-15");
  assert.equal(document.getElementById("dp-input").value, "2026-09-15");
  assert.ok(!document.getElementById("dp-panel").classList.contains("popover-open"), "le panneau doit se refermer après sélection");
});

// ---------------------------------------------------------------------
// xweb/components/shell.xml — #xweb-sidebar : hx-boost ne remplace QUE
// #xweb-content (docs/shell.md), la sidebar n'est jamais renvoyée par une
// réponse boostée — sans ce script, .menu-active reste figé sur la page
// du dernier chargement COMPLET. Trouvé sur une vraie capture d'écran
// (Démo restait allumé sur la page Kanban après un clic sidebar), pas en
// lisant le code. Script extrait du VRAI rendu de xweb.shell (échappement
// &lt;a/&gt; décodé par le navigateur avant que _hyperscript ne le lise).
// ---------------------------------------------------------------------
await check("shell.xml — #xweb-sidebar resynchronise .menu-active après chaque navigation boostée (htmx:afterSettle)", async () => {
  const SIDEBAR_SCRIPT = `on htmx:afterSettle from body
                    for a in <a/> in me
                      if a's @href is location.pathname
                        add .menu-active .bg-primary .text-primary-content to a
                      else
                        remove .menu-active .bg-primary .text-primary-content from a
                      end
                    end`;
  const dom = new JSDOM(`<!doctype html><html><body>
    <aside id="xweb-sidebar">
      <a href="/plugins/demo/" class="flex items-center gap-2 menu-active bg-primary text-primary-content">Démo</a>
      <a href="/plugins/demo/components" class="flex items-center gap-2">Composants</a>
      <a href="/plugins/demo/kanban" class="flex items-center gap-2">Kanban</a>
    </aside>
  </body></html>`, { runScripts: "dangerously", url: "http://localhost/plugins/demo/" });
  dom.window.eval(hsSource);
  const { document } = dom.window;
  document.getElementById("xweb-sidebar").setAttribute("_", SIDEBAR_SCRIPT);
  dom.window._hyperscript.processNode(document.body);

  const links = () => [...document.querySelectorAll("#xweb-sidebar a")];
  const activeHref = () => links().find((a) => a.classList.contains("menu-active"))?.getAttribute("href");

  assert.equal(activeHref(), "/plugins/demo/", "état initial (chargement complet) : Démo actif");

  // htmx met à jour l'historique AVANT que htmx:afterSettle ne bulle —
  // simulé ici avec pushState, comme htmx le fait réellement pour une
  // navigation boostée.
  dom.window.history.pushState({}, "", "/plugins/demo/components");
  document.body.dispatchEvent(new dom.window.Event("htmx:afterSettle", { bubbles: true }));
  await tick();
  assert.equal(activeHref(), "/plugins/demo/components", "après navigation boostée vers Composants : Démo ne doit plus rester allumé");

  dom.window.history.pushState({}, "", "/plugins/demo/kanban");
  document.body.dispatchEvent(new dom.window.Event("htmx:afterSettle", { bubbles: true }));
  await tick();
  assert.equal(activeHref(), "/plugins/demo/kanban", "après une deuxième navigation boostée : Kanban actif, un seul lien à la fois");
});

if (failures > 0) {
  console.error(`\n${failures} vérification(s) en échec`);
  process.exit(1);
}
console.log("\nToutes les vérifications _hyperscript (ajouts shell) passent.");
