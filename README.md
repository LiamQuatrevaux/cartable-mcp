# Cartable

**Serveur MCP en lecture seule pour EcoleDirecte.** 61 outils, une session,
aucune écriture.

Cartable donne à un client MCP (Claude Desktop, Claude Code, Cursor, …) l'accès
aux données d'un compte **élève** EcoleDirecte : notes et bulletins, cahier de
textes, emploi du temps, vie scolaire, messagerie, documents, cantine, formulaires
et espaces de travail.

## Avertissement

Projet **non officiel**, sans aucune affiliation, partenariat ni approbation
d'Aplim ou d'EcoleDirecte, dont les noms et marques appartiennent à leurs
propriétaires respectifs. Il est destiné à l'usage personnel du titulaire du
compte, dans un cadre privé ou éducatif, et n'est ni redistribué, ni revendu, ni
mis à disposition de tiers.

L'utilisateur est seul responsable de son usage : il lui appartient de vérifier
que celui-ci respecte les conditions d'utilisation du service, les textes en
vigueur et les droits des tiers. Le logiciel est fourni « en l'état », sans
garantie d'aucune sorte.

Le client API embarqué (`ecoledirecte_api`) dérive de
[hacf-fr/ecoledirecte_api](https://github.com/hacf-fr/ecoledirecte_api) et reste
sous LGPL-3.0-or-later ; voir `NOTICE` et `COPYING.GPL-3.0`.

## Points clés

- **Lecture seule, garantie à la couche HTTP** : le client refuse toute méthode
  autre que `POST` et tout `verbe` autre que `get`/`list`, même si un outil était
  mal écrit. Aucun outil d'envoi, de commande ou de suppression n'est exposé.
- **61 outils** couvrant tout ce qu'un élève voit sur le site, plus
  `ed_get_catalog` (inventaire) et `ed_raw_query` (échappatoire `GET` contrôlée).
- **Une seule session HTTP** keep-alive, `X-Token` capturé à chaque réponse :
  aucun re-login inutile entre deux outils.
- **Cache TTL mémoire** et déduplication des lectures parallèles : deux outils qui
  demandent la même donnée ne déclenchent qu'une requête.
- **Compatible Raspberry Pi** (Python 3.11+), avec une unité systemd fournie.

## Couverture

| Domaine | Outils |
| --- | --- |
| Session | `ed_auth_status`, `ed_login`, `ed_submit_qcm`, `ed_logout`, `ed_select_account`, `ed_get_context`, `ed_health` |
| Élève | `ed_get_profile`, `ed_get_timeline`, `ed_get_school_timeline`, `ed_list_manuals`, `ed_list_visios`, `ed_list_qcms`, `ed_get_class_life`, `ed_list_class_students` |
| Notes | `ed_list_periods`, `ed_get_period_report`, `ed_list_subject_grades`, `ed_list_evaluations`, `ed_list_competences`, `ed_get_annual_summary` |
| Cahier de textes | `ed_list_homework`, `ed_get_homework_day`, `ed_list_homework_subjects`, `ed_get_homework_index` |
| Emploi du temps | `ed_get_timetable`, `ed_get_today`, `ed_get_week`, `ed_get_next_course`, `ed_list_timetable_changes` |
| Vie scolaire | `ed_get_vie_scolaire`, `ed_list_absences`, `ed_list_retards`, `ed_list_sanctions`, `ed_list_encouragements`, `ed_get_attendance_summary`, `ed_get_carnet_correspondance`, `ed_list_sessions_rdv` |
| Messagerie | `ed_list_messages`, `ed_get_message`, `ed_download_message_attachment` |
| Documents | `ed_list_documents`, `ed_list_pieces_a_verser`, `ed_get_wallet_balances`, `ed_download_document`, `ed_list_forms`, `ed_get_form`, `ed_list_surveys` |
| Cantine | `ed_get_menus`, `ed_list_canteen_points`, `ed_list_canteen_orders`, `ed_check_canteen_slot` |
| Espaces & cloud | `ed_list_workspaces`, `ed_get_workspace`, `ed_list_workspace_activities`, `ed_get_workspace_activity`, `ed_list_workspace_postits`, `ed_list_cloud`, `ed_download_cloud_file` |
| Méta | `ed_get_catalog`, `ed_raw_query` |

Les outils réellement exposés sont filtrés par les modules activés côté
établissement.

## Installation

Python 3.11 à 3.13 (3.13 recommandé) :

```console
$ git clone <url-de-ce-depot> cartable-mcp
$ cd cartable-mcp
$ python3 -m venv .venv && . .venv/bin/activate
$ pip install -e '.[mcp,fast]'   # 'fast' ajoute uvloop (optionnel, hors Windows)
```

Sur Raspberry Pi OS Bookworm, `sudo apt install python3 python3-venv` suffit
ensuite.

## Configuration

Les identifiants ne vont **jamais** dans le dépôt. Deux possibilités :

```console
$ mkdir -p ~/.config/ecoledirecte-mcp
$ cat > ~/.config/ecoledirecte-mcp/credentials.json <<'JSON'
{"username": "identifiant", "password": "motdepasse"}
JSON
$ chmod 600 ~/.config/ecoledirecte-mcp/credentials.json
```

ou les variables `ED_USERNAME` / `ED_PASSWORD` (prioritaires sur le fichier).

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `ED_CREDENTIALS_FILE` | `~/.config/ecoledirecte-mcp/credentials.json` | Fichier JSON `{"username", "password"}` |
| `ED_QCM_FILE` | `~/.config/ecoledirecte-mcp/qcm.json` | Réponses QCM mémorisées (écrites en `0600`) |
| `ED_DOWNLOAD_DIR` | `~/.config/ecoledirecte-mcp/downloads` | Dossier des pièces jointes |
| `ED_READ_ONLY` | `true` | Verrou lecture seule côté client HTTP |
| `ED_CACHE_TTL` | `60` | Durée du cache mémoire, en secondes |
| `ED_MIN_REQUEST_INTERVAL` | `0.2` | Espacement minimal entre deux appels |
| `ED_MAX_REQUESTS_PER_MINUTE` | `120` | Budget d'appels API par minute |
| `ED_REQUEST_TIMEOUT` | `45` | Timeout HTTP, en secondes |
| `ED_MAX_DOWNLOAD_MB` | `25` | Taille maximale d'un téléchargement |
| `ED_TIMEZONE` | `Europe/Paris` | Fuseau utilisé pour « aujourd'hui » |
| `ED_API_URL` / `ED_API_VERSION` | valeurs du client | Surcharge de l'endpoint ou de la version d'API |
| `ED_LOG_LEVEL` | `WARNING` | Niveau de log (sur stderr) |

## Brancher un client MCP

Transport stdio, par exemple :

```json
{
  "mcpServers": {
    "cartable": {
      "command": "/opt/ecoledirecte/.venv/bin/ecoledirecte-mcp",
      "env": {
        "ED_CREDENTIALS_FILE": "/etc/ecoledirecte-mcp/credentials.json",
        "ED_QCM_FILE": "/var/lib/ecoledirecte-mcp/qcm.json",
        "ED_DOWNLOAD_DIR": "/var/lib/ecoledirecte-mcp/downloads",
        "ED_READ_ONLY": "true",
        "ED_TIMEZONE": "Europe/Paris"
      }
    }
  }
}
```

Un exemple complet est fourni dans `deploy/claude-desktop.json`, et l'unité
systemd durcie dans `deploy/ecoledirecte-mcp.service`.

Le serveur démarre lui-même la session : appeler `ed_get_context`.
Si la réponse contient `status=qcm_required`, demander la réponse à l'utilisateur
puis appeler `ed_submit_qcm` ; elle est mémorisée pour les connexions suivantes.
Ce fichier n'est qu'un confort de connexion, stocké en `0600` : le supprimer (ou
repointer `ED_QCM_FILE`) à tout moment ramène à une saisie manuelle.

## Utiliser le client en Python

Le paquet embarque aussi le client asynchrone dont dépend le serveur :

```python
import asyncio

from ecoledirecte_api.client import EDClient

async def main():
    async with EDClient("username", "password", {}) as client:
        await client.login()
        print(await client.get_homeworks("student_id"))

asyncio.run(main())
```

Si le compte exige un QCM, fournir les réponses dans l'argument `qcm_json`.

## Transport HTTP (optionnel)

`ecoledirecte-mcp-http` expose le même serveur en Streamable HTTP sur
`http://127.0.0.1:8765/mcp`, protégé par une clé privée :

```console
$ export ED_HTTP_API_KEY_FILE=~/.config/ecoledirecte-mcp/api-key   # 0600, 32+ caractères
$ ecoledirecte-mcp-http
```

Chaque requête doit porter `Authorization: Bearer <clé>`.

`ED_HTTP_HOST` doit rester une adresse de bouclage et, par défaut, seuls les hôtes
de bouclage sont acceptés. Pour exposer le serveur derrière un tunnel TLS, lister
les hôtes publics dans `ED_HTTP_ALLOWED_HOSTS`, séparés par des virgules :
`host[:port]` autorise l'hôte et déduit ses origines `http`/`https`, alors qu'une
entrée `https://host` n'ajoute que cette origine. `ED_HTTP_PORT` change le port.

## Sécurité

- **Aucune écriture** : pas d'envoi de message, de commande ni de suppression.
  Seule l'ouverture d'un message peut le marquer comme lu côté EcoleDirecte,
  exactement comme sur le site.
- **Secrets** : identifiants et fichier QCM doivent être en `0600` (refus explicite
  sinon), les dossiers sont créés en `0700`, les mots de passe sont masqués dans
  les erreurs.
- **Entrées strictes** : dates, identifiants, années scolaires et bornes de
  pagination sont validés avant toute construction d'URL ; `ed_raw_query` refuse
  les routes d'authentification, d'upload et de téléchargement.
- **Téléchargements** : confinés dans `ED_DOWNLOAD_DIR`, permissions `0600`,
  taille plafonnée, streaming.
- **Réseau** : pas de proxy implicite (`.netrc` et `HTTP_PROXY` ignorés), TLS
  vérifié, budget de requêtes par minute.
- **Contenu non fiable** : les textes EcoleDirecte sont traités comme des
  données, jamais comme des instructions.
- **Disque** : aucun secret ni donnée scolaire persistés, hormis le fichier QCM
  et les pièces jointes demandées.

## Développement

```console
$ poetry install --with dev
$ poetry run ruff check src tests
$ poetry run mypy
$ poetry run pytest
```

Un DevContainer Python est fourni dans `.devcontainer/`. La CI GitHub Actions
exécute Ruff, mypy et la suite de tests.

## Licence et crédits

Distribué sous **LGPL-3.0-or-later** :

- `LICENSE` — texte de la GNU Lesser General Public License v3.0 ;
- `COPYING.GPL-3.0` — texte de la GNU GPL v3.0, dont la LGPL-3.0 reprend les
  termes et conditions ;
- `NOTICE` — attribution, périmètre du travail dérivé et liste des modifications.

Le client EcoleDirecte (`src/ecoledirecte_api`) est dérivé du projet
[hacf-fr/ecoledirecte_api](https://github.com/hacf-fr/ecoledirecte_api) de Giga77,
utilisé par l'intégration Home Assistant
[hass-ecoledirecte](https://github.com/hacf-fr/hass-ecoledirecte). Merci à eux.
La couche MCP (`src/ecoledirecte_mcp`) et les adaptations du client constituent
les modifications apportées à ce travail dérivé.
