# CLI

```bash
xweb inspect <t-name>      # chaîne d'héritage résolue pour un template
xweb render <t-name> --ctx '{"...": "..."}'   # rendu isolé, sans app xcore, pour debug/SSG
xweb list                  # tous les templates enregistrés, avec leur t-inherit s'il y en a un
xweb cache clear            # vide le cache de rendu (pas les fichiers .xml sur disque)
```

## `xweb inspect`

Le plus utile en pratique — répond à « pourquoi mon composant a un badge que je n'ai pas mis ».

```
$ xweb inspect xweb.button

xweb.button                                    (xweb/components/button.xml)
└── crm_app.button_badge   priority=10          (plugins/crm_app/templates/button_patch.xml)
    xpath: //button position=inside
```

Affiche la chaîne d'héritage complète dans l'ordre de résolution réel (`inheritance.md#résolution`) — pas juste la liste des fichiers qui existent, l'ordre dans lequel `PatchRegistry` les applique. Équivalent texte du debugger de vues d'Odoo, sans l'interface graphique.

## Statut d'implémentation

Non commencé — Phase 7 de *xweb Blueprint* §7. `microframe/cli.py` existe déjà comme squelette côté microframe (`FEATURES.md` v2.4, marqué « à implémenter ») ; `xweb inspect` est le premier usage réel prévu pour ce genre de commande, pas un portage direct puisque microframe n'a pas de notion d'héritage à inspecter.
