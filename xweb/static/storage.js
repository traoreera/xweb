/**
 * XwebStorage — wrapper minimal et défensif autour de localStorage.
 *
 * Écrit à la main, comme le reste du JS non-vendorisé de ce dépôt (script
 * anti-flash de thème, flux SSE de notifications — xweb/components/layout.xml,
 * docs/theming.md) : un besoin trop petit pour justifier une dépendance npm.
 *
 * Pourquoi une classe plutôt que localStorage direct :
 *  - namespace ("xweb:" par défaut) — un futur plugin qui stocke ses
 *    propres préférences ne risque pas d'écraser silencieusement une clé
 *    de xweb (ou d'un autre plugin) juste parce qu'ils ont choisi le même
 *    nom de clé ; `new XwebStorage('mon_plugin')` prend son propre espace.
 *  - JSON automatique — get()/set() (dé)sérialisent, l'appelant manipule
 *    des valeurs JS normales (objets, tableaux, booléens), jamais des
 *    chaînes brutes à parser lui-même.
 *  - défensif — localStorage peut lever (navigation privée sur certains
 *    navigateurs, storage désactivé par une politique/extension) ; chaque
 *    méthode intercepte et dégrade (get -> fallback, set/remove/has ->
 *    échec silencieux signalé par une valeur de retour, jamais une
 *    exception qui remonterait casser le script appelant).
 *
 * Ne JAMAIS y stocker un secret (jeton, mot de passe, identifiant de
 * session) — localStorage est lisible par n'importe quel JS de la page
 * (un XSS y a un accès direct), contrairement à un cookie HttpOnly
 * (xweb/cookies.py, côté serveur, jamais accessible en JS). Ce n'est PAS
 * l'équivalent client d'xweb/cookies.py — seulement un espace pour des
 * préférences d'affichage (thème, colonnes repliées, filtres récents…),
 * rien qui donnerait un pouvoir à quiconque le lirait.
 *
 * N'EST PAS branché sur le thème/sidebar existants (xweb.shell_head) :
 * leur script anti-flash est épinglé par hash dans la CSP
 * (XWEB_THEME_SCRIPT_HASH, xweb/security.py) et lit du localStorage EN
 * CHAÎNE BRUTE ('dark'/'light', pas de JSON) — le faire passer par
 * get()/set() ici changerait le format stocké (JSON-encodé) sans changer
 * l'autre moitié de la paire lecture/écriture, un vrai bug silencieux au
 * chargement suivant. Cette classe est pour du code NEUF, pas une
 * migration automatique de l'existant.
 *
 * Clé de stockage réelle : `encodeURIComponent(namespace):encodeURIComponent(key)`
 * — jamais une simple concaténation. Bug réel trouvé en la construisant :
 * `namespace:key` brut fait collisionner deux paires (namespace, clé)
 * DIFFÉRENTES sur la MÊME entrée localStorage dès que l'une des deux
 * contient elle-même ':' — `("a", "b:c")` et `("a:b", "c")` donnaient
 * toutes les deux `"a:b:c"`. `encodeURIComponent` échappe ':' (device
 * `%3A`), donc les deux ne peuvent plus jamais se rencontrer. Rétro-
 * incompatible avec des clés déjà posées par une version antérieure de ce
 * fichier SI namespace/clé contenaient ':' — improbable en pratique (rien
 * de ce dépôt n'utilise ':' dans un nom de namespace/clé), et de toute
 * façon rien de plus grave qu'une préférence perdue une fois (voir
 * l'avertissement "jamais un secret" ci-dessus).
 */
class XwebStorage {
  constructor(namespace = "xweb") {
    this.namespace = namespace;
  }

  _key(key) {
    return `${encodeURIComponent(this.namespace)}:${encodeURIComponent(key)}`;
  }

  get(key, fallback = null) {
    let raw;
    try {
      raw = window.localStorage.getItem(this._key(key));
    } catch (_e) {
      return fallback;
    }
    if (raw === null) return fallback;
    try {
      return JSON.parse(raw);
    } catch (_e) {
      return raw; // valeur préexistante non posée par cette classe (chaîne brute)
    }
  }

  set(key, value) {
    try {
      window.localStorage.setItem(this._key(key), JSON.stringify(value));
      return true;
    } catch (_e) {
      return false;
    }
  }

  remove(key) {
    try {
      window.localStorage.removeItem(this._key(key));
      return true;
    } catch (_e) {
      return false;
    }
  }

  has(key) {
    try {
      return window.localStorage.getItem(this._key(key)) !== null;
    } catch (_e) {
      return false;
    }
  }

  /** Clés de CE namespace, sans le préfixe — jamais les clés d'un autre
   * namespace/plugin (localStorage est un espace global unique par
   * origine, `keys()` doit rester scopé comme le reste de cette classe). */
  keys() {
    const prefix = `${encodeURIComponent(this.namespace)}:`;
    const result = [];
    try {
      for (let i = 0; i < window.localStorage.length; i++) {
        const raw = window.localStorage.key(i);
        if (raw !== null && raw.startsWith(prefix)) {
          result.push(decodeURIComponent(raw.slice(prefix.length)));
        }
      }
    } catch (_e) {
      return [];
    }
    return result;
  }

  /** Efface TOUTES les clés de ce namespace — jamais tout localStorage (ça
   * effacerait aussi les autres plugins/le thème). Collecte d'abord la
   * liste complète via keys() PUIS supprime — égrener removeItem() pendant
   * qu'on itère localStorage.key(i) directement décale les index au fur
   * et à mesure et saute des entrées, piège classique de ce genre de
   * boucle. */
  clear() {
    let ok = true;
    for (const key of this.keys()) {
      if (!this.remove(key)) ok = false;
    }
    return ok;
  }
}

// Instance par défaut (namespace "xweb") pour un usage direct depuis un
// <script>/_hyperscript ("call XwebStorage.set('key', valeur)"), plus la
// classe elle-même pour un plugin qui veut son propre namespace.
window.XwebStorage = new XwebStorage();
window.XwebStorageClass = XwebStorage;
