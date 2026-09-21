/**
 * XwebValidate — port client (JS) du moteur de validation déclarative
 * xdsl/validators.py, pour du feedback instantané côté navigateur (avant
 * même d'envoyer une requête) sur des données reçues en live ou la RÉPONSE
 * JSON d'un `endpoint { receive { schema: ... } }` (voir
 * xdsl/compiler.py::_write_endpoint_scaffolding et ::_write_channel_bootstrap).
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
 * rafraîchissement DOM sur une donnée live malformée, bloquer onsuccess/
 * l'event de refresh d'un endpoint sur une réponse JSON invalide) — un
 * client hostile peut trivialement l'ignorer ou le contourner.
 *
 * Contrat :
 *   window.XWEB_SCHEMAS[name] = {
 *     champ: [[règle, [args...]], ...]   // ex: [["required", []], ["min_length", [3]]]
 *   }
 *   — écrit par le bootstrap généré (`channel { validate: "nom" }` ou
 *   `endpoint { receive { schema: "nom" } }`), jamais à la main.
 *   window.XwebValidate(name, data, opts) lit ce registre.
 *
 * COMPOSITION — un champ dont le type n'est pas un primitif (split par
 * xdsl/parser.py::split_value_type) porte une pseudo-règle qui n'est PAS
 * dans RULES, interprétée ici pour DESCENDRE :
 *   ["ref", ["address"]]   — value doit être un objet, validé contre le
 *                            schéma "address" (erreurs préfixées `address.street`).
 *   ["list", ["phone"]]    — value doit être un tableau, chaque item validé
 *                            contre le schéma "phone" (erreurs préfixées
 *                            `phones[0].number`), OU contre un PRIMITIF
 *                            (`["list", ["string"]]`, contrôle de type par item).
 *
 * window.XwebValidate(schemaName, data, opts) -> { valid: bool, errors: {champ: [msg...]} }
 *   - opts.list === true : data est un TABLEAU, chaque item validé contre le
 *     schéma, erreurs préfixées `0.name`, ... (`receive { list: true }`).
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

  // Miroir du wording de type de pydantic_bridge._TYPE_ERRORS (le serveur,
  // source de vérité — une liste reçoit `["list", [item]]` via la pseudo-
  // règle de _schema_to_json) — erreurs de STRUCTURE du type composé.
  const REF_TYPE_MESSAGE = (item) => `Type invalide — attendu : ${item}`;
  const LIST_TYPE_MESSAGE = "Doit être une liste valide.";

  // Primitifs acceptés comme item de `list[item]` — MÊME table que
  // parser.PRIMITIVE_TYPES moins `list` (un `list[list]` n'a pas de sens
  // à valider par item ici, et `list[dict]` reste un item objet possible).
  const PRIMITIVE_ITEMS = { string: true, int: true, float: true, bool: true, dict: true };

  function primitiveOk(value, item) {
    if (item === "string") return typeof value === "string";
    if (item === "bool") return typeof value === "boolean";
    if (item === "int") return typeof value === "number" && Number.isInteger(value);
    if (item === "float") return typeof value === "number" && Number.isFinite(value);
    if (item === "dict") return typeof value === "object" && value !== null && !Array.isArray(value);
    return true; // item inconnu -> passthrough (le serveur reste la vérité)
  }

  function resolveSchema(name) {
    const schema = window.XWEB_SCHEMAS && window.XWEB_SCHEMAS[name];
    if (!schema) {
      console.error(
        `[xweb] validators.js: schéma "${name}" absent de window.XWEB_SCHEMAS ` +
          `(un channel { validate: } ou endpoint { receive.schema: } doit l'exporter sur cette page)`,
      );
    }
    return schema;
  }

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

  // Valide UN objet contre un schéma, erreurs préfixées par *prefix* ("" au
  // niveau racine, "address." / "phones[0]." pour les champs composés).
  // Gère les pseudo-règles de composition `ref`/`list` en plus de RULES.
  function validateObject(schema, data, prefix, errors) {
    for (const field of Object.keys(schema)) {
      const rules = schema[field];
      const key = prefix + field;
      const value = data == null ? undefined : data[field];
      const fieldErrors = [];

      for (const [ruleName, args] of rules) {
        if (ruleName === "ref") {
          if (value === null || value === undefined) continue; // oblig. géré par required
          if (typeof value !== "object" || Array.isArray(value)) {
            fieldErrors.push(REF_TYPE_MESSAGE(args[0]));
          } else {
            const refSchema = resolveSchema(args[0]);
            if (refSchema) validateObject(refSchema, value, key + ".", errors);
            else fieldErrors.push(`Schéma imbriqué introuvable: ${args[0]}`);
          }
        } else if (ruleName === "list") {
          if (value === null || value === undefined) continue; // oblig. géré par required
          if (!Array.isArray(value)) {
            fieldErrors.push(LIST_TYPE_MESSAGE);
            continue;
          }
          const item = args[0];
          if (item in PRIMITIVE_ITEMS) {
            for (let i = 0; i < value.length; i++) {
              if (!primitiveOk(value[i], item)) {
                errors[key + "[" + i + "]"] = [REF_TYPE_MESSAGE(`list[${item}]`)];
              }
            }
          } else {
            const refSchema = resolveSchema(item);
            if (refSchema) {
              for (let i = 0; i < value.length; i++) {
                validateObject(refSchema, value[i], key + "[" + i + "].", errors);
              }
            } else {
              fieldErrors.push(`Schéma imbriqué introuvable: ${item}`);
            }
          }
        } else {
          fieldErrors.push(...validateField(value, [[ruleName, args]]));
        }
      }
      if (fieldErrors.length > 0) {
        errors[key] = (errors[key] || []).concat(fieldErrors);
      }
    }
  }

  function XwebValidate(schemaName, data, opts) {
    const schema = resolveSchema(schemaName);
    if (!schema) return { valid: false, errors: {} };
    const errors = {};
    if (opts && opts.list === true) {
      // `receive { list: true }` — la réponse JSON attendue est un tableau.
      if (!Array.isArray(data)) {
        return { valid: false, errors: { __root__: [LIST_TYPE_MESSAGE] } };
      }
      for (let i = 0; i < data.length; i++) {
        validateObject(schema, data[i], i + ".", errors);
      }
    } else {
      validateObject(schema, data, "", errors);
    }
    return { valid: Object.keys(errors).length === 0, errors };
  }

  window.XwebValidate = XwebValidate;
})();