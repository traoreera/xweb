/**
 * XwebValidate — port client (JS) du moteur de validation déclarative
 * xdsl/validators.py, pour du feedback instantané côté navigateur (avant
 * même d'envoyer une requête) sur des données reçues en live (voir
 * xdsl/compiler.py::_write_channel_bootstrap, `channel { validate: ... }`).
 *
 * Écrit à la main, comme le reste du JS non-vendorisé de ce dépôt
 * (storage.js, live_channel.js, script anti-flash de thème) : même
 * ensemble FERMÉ de règles des deux côtés, pas une lib de validation
 * générique — voir BUILTIN_VALIDATORS dans xdsl/validators.py, la seule
 * source de vérité sur les règles qui existent.
 *
 * NE REMPLACE JAMAIS la validation SERVEUR (xdsl/validators.py::validate_dict,
 * appelée par le compilateur DSL sur tout `endpoint`/`receive`) — c'est la
 * seule qui compte pour la sécurité (docs/dsl-design.md#requêtes-réseau,
 * CLAUDE.md "server est la seule source de vérité pour la sécurité"). Ce
 * fichier n'existe QUE pour de l'UX (surligner un champ, bloquer un
 * rafraîchissement DOM sur une donnée live malformée) — un client hostile
 * peut trivialement l'ignorer ou le contourner.
 *
 * Contrat :
 *   window.XWEB_SCHEMAS[name] = {
 *     champ: [[règle, [args...]], ...]   // ex: [["required", []], ["min_length", [3]]]
 *   }
 *   — écrit par le bootstrap généré (`channel { validate: "nom" }`), jamais
 *   à la main. window.XwebValidate(name, data) lit ce registre.
 *
 * window.XwebValidate(schemaName, data) -> { valid: bool, errors: {champ: [msg...]} }
 *   - schéma introuvable dans window.XWEB_SCHEMAS -> échoue de façon
 *     VISIBLE (console.error + valid:false), jamais un silencieux
 *     valid:true qui masquerait un nom de schéma mal tapé.
 *   - règle inconnue dans le descripteur -> pareil, console.error +
 *     valid:false (ne devrait jamais arriver : le compilateur xdsl ne
 *     génère que des règles qu'il connaît lui-même).
 */
(function () {
  "use strict";

  // Miroir exact de xdsl/validators.py::BUILTIN_VALIDATORS — même noms,
  // mêmes messages (français), mêmes règles de passthrough (une règle
  // typée string/nombre qui reçoit une valeur du mauvais type LAISSE
  // PASSER, elle ne s'applique juste pas — voir MinLength.check/MinValue.check
  // côté Python, ce n'est pas un oubli ici).
  const RULES = {
    required(value) {
      if (value === null || value === undefined) return false;
      if (typeof value === "string" && value.trim() === "") return false;
      return true;
    },
    min_length(value, [minLen]) {
      if (typeof value !== "string") return true;
      return value.length >= minLen;
    },
    max_length(value, [maxLen]) {
      if (typeof value !== "string") return true;
      return value.length <= maxLen;
    },
    min(value, [minVal]) {
      const n = Number(value);
      if (value === null || value === undefined || value === "" || Number.isNaN(n)) return true;
      return n >= minVal;
    },
    max(value, [maxVal]) {
      const n = Number(value);
      if (value === null || value === undefined || value === "" || Number.isNaN(n)) return true;
      return n <= maxVal;
    },
    email(value) {
      if (typeof value !== "string") return true;
      return /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(value);
    },
    pattern(value, [regex]) {
      if (typeof value !== "string") return true;
      return new RegExp("^(?:" + regex + ")").test(value);
    },
    in(value, [allowed]) {
      return allowed.map(String).includes(String(value));
    },
  };

  const MESSAGES = {
    required: () => "Ce champ est obligatoire",
    min_length: ([n]) => `Minimum ${n} caractère${n > 1 ? "s" : ""}`,
    max_length: ([n]) => `Maximum ${n} caractère${n > 1 ? "s" : ""}`,
    min: ([n]) => `La valeur minimale est ${n}`,
    max: ([n]) => `La valeur maximale est ${n}`,
    email: () => "Adresse email invalide",
    pattern: () => "La valeur ne correspond pas au format attendu",
    in: ([allowed]) => `Valeur invalide — autorisées : ${allowed.join(", ")}`,
  };

  function validateField(value, rules) {
    const errors = [];
    for (const [ruleName, args] of rules) {
      const check = RULES[ruleName];
      if (!check) {
        console.error(`[xweb] validators.js: règle de validation inconnue côté client: "${ruleName}"`);
        errors.push(`Règle de validation inconnue: ${ruleName}`);
        continue;
      }
      if (!check(value, args)) {
        errors.push(MESSAGES[ruleName](args));
      }
    }
    return errors;
  }

  function XwebValidate(schemaName, data) {
    const schema = window.XWEB_SCHEMAS && window.XWEB_SCHEMAS[schemaName];
    if (!schema) {
      console.error(
        `[xweb] validators.js: schéma "${schemaName}" absent de window.XWEB_SCHEMAS ` +
          `(un channel { validate: "${schemaName}" } doit être compilé sur cette page pour l'exporter)`,
      );
      return { valid: false, errors: {} };
    }
    const errors = {};
    for (const field of Object.keys(schema)) {
      const fieldErrors = validateField(data ? data[field] : undefined, schema[field]);
      if (fieldErrors.length > 0) errors[field] = fieldErrors;
    }
    return { valid: Object.keys(errors).length === 0, errors };
  }

  window.XwebValidate = XwebValidate;
})();
