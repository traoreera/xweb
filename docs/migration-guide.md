# Guide de migration — checklist de parité et bascule

xweb supprime `ext.template_engine` au moment du basculement (*xweb Blueprint* §0, §6) — pas de filet en production. Cette checklist est ce qui sépare « xweb est prêt » de « xcore n'a plus de moteur de rendu qui marche ». Chaque ligne correspond à quelque chose que microframe+xui font déjà aujourd'hui, prouvé par le code source lu au moment de la conception — pas une aspiration.

## Migrer un plugin, étape par étape

1. **Composants avant pages** — vérifier que tous les composants dont le plugin dépend sont déjà migrés (`components.md`). Un plugin qui a besoin d'un composant non migré attend, il ne redéfinit pas une version locale en Jinja2 déguisée.
2. **Réécrire les templates** en `.xml`, classes DaisyUI (`components.md#conventions-de-migration`), attributs `hx-*`/`_` pour l'interactivité (`language.md`).
3. **Porter les routes de mutation** — les routes FastAPI existantes changent peu (`plugins.md` §2) : le corps de la route ne change pas, seul l'appel `engine.render(...)` cible `QwebRegistry` au lieu de `TemplateEngine`.
4. **Déclarer les contributions au shell** (`shell.md`) si le plugin a de la navigation, une entrée ribbon, ou des commandes.
5. **Porter les tests** — un test qui vérifiait une chaîne de sortie Jinja2 est réécrit contre la sortie QWeb, pas supprimé.
6. **Cocher la ligne du plugin** dans la checklist globale ci-dessous.

## Checklist de parité — condition d'entrée du basculement

- [ ] `billing` rendu par xweb, tests portés et verts
- [ ] `crm_app` rendu par xweb, tests portés et verts
- [ ] `dashboard` rendu par xweb, tests portés et verts
- [ ] `stock` rendu par xweb, tests portés et verts
- [ ] `tasks` rendu par xweb, tests portés et verts
- [ ] `ui_kit` rendu par xweb, tests portés et verts
- [ ] `docs_site` rendu par xweb, tests portés et verts
- [ ] `demo_auth` rendu par xweb, tests portés et verts
- [ ] CSRF validé de bout en bout sur un plugin avec formulaire (`demo_auth` ou `billing`)
- [ ] RBAC (`require_role`) validé — un utilisateur sans le bon rôle reçoit bien un refus, pas un rendu partiel
- [ ] `parse_form()` avec ré-affichage d'erreurs par champ validé, pas seulement le happy path
- [ ] Hot-reload testé — hook confirmé (`plugin.*.unloaded` sur l'event bus, `spec-v1.md` §3), reste à vérifier en pratique sur un vrai unload/reload
- [ ] Pas de régression de perf mesurée (temps de rendu, taux de cache hit) sur les pages migrées vs leur équivalent microframe

Les 8 premières lignes sont vérifiables indépendamment, en parallèle. Les 5 dernières sont transverses — à valider une fois qu'au moins un plugin avec formulaire et un plugin avec navigation sont migrés, pas seulement à la toute fin.

## Le jour du basculement

Un seul commit, pas un rollout progressif (*xweb Blueprint* §6) :

```diff
 # xcore.yaml
 services:
   extensions:
-    template_engine:
-      module: microframe.engine.integration.xcore:TemplateEngineExtension
-      config: { ... }
     xweb:
       module: xweb.engine.integration.xcore:XwebExtension
       config: { ... }
```

`microframe` et `xui` perdent leur statut de dépendance le même jour (Phase 7 de *xweb Blueprint* §7) — pas de période de grâce où les deux restent installés « au cas où ».

## Si la checklist échoue partiellement

**Question ouverte, non résolue** (*xweb Blueprint* §10) — si 7 plugins sur 8 passent et le 8ᵉ révèle un cas non couvert, il n'y a pas de ligne de config à rebasculer : revenir en arrière veut dire réinstaller microframe temporairement. Ce document ne prescrit pas de procédure de rollback tant que cette question n'est pas tranchée — la traiter avant, pas pendant, un vrai basculement.
