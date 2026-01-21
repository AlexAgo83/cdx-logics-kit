# cdx-logics-kit

Kit réutilisable de “Logics skills” (guides + scripts) à importer dans tes projets sous `logics/skills/`.

Objectif : standardiser un workflow léger basé sur Markdown (`logics/request` → `logics/backlog` → `logics/tasks` → `logics/specs`) et fournir des commandes pour créer/promouvoir/linter/indexer/reviewer.

## Prérequis

- `python3` (scripts sans dépendances externes)
- `git`

## Installation (recommandé : submodule)

Dans un nouveau repo projet :

```bash
mkdir -p logics
git submodule add -b main git@github.com:AlexAgo83/cdx-logics-kit.git logics/skills
git submodule update --init --recursive
```

Puis bootstrap de l’arborescence Logics (crée les dossiers manquants + `.gitkeep`, et un `logics/instructions.md` par défaut si absent) :

```bash
python3 logics/skills/logics-bootstrapper/scripts/logics_bootstrap.py
```

## Usage (dans le repo projet)

Créer une request/backlog/task avec IDs auto :

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new request --title "My first need"
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new backlog --title "My first need"
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py new task --title "Implement my first need"
```

Promouvoir entre étapes :

```bash
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote request-to-backlog logics/request/req_001_my_first_need.md
python3 logics/skills/logics-flow-manager/scripts/logics_flow.py promote backlog-to-task logics/backlog/item_002_my_first_need.md
```

Vérifier les conventions Logics :

```bash
python3 logics/skills/logics-doc-linter/scripts/logics_lint.py
```

## Mise à jour du kit (dans un projet existant)

Mettre à jour le submodule vers la dernière version de `main` :

```bash
git submodule update --remote --merge
git add logics/skills
git commit -m "Update Logics kit"
```

Pinner sur un tag (recommandé si tu veux des upgrades contrôlés) :

```bash
cd logics/skills
git fetch --tags
git checkout v0.1.0
cd -
git add logics/skills
git commit -m "Pin Logics kit to v0.1.0"
```

## Notes

- Ce repo est fait pour être exécuté depuis le **repo projet** (où `logics/skills` pointe vers ce kit).
- Les docs `req_*`, `item_*`, `task_*`, `spec_*` restent dans le repo projet : pas de “pollution” entre projets.

