# Mon Plan d'Entraînement

Application web (une seule page) pour planifier ses séances de course à pied et de vélo sur un calendrier hebdomadaire. Elle génère des semaines d'entraînement adaptées à ton profil et exporte les séances vers Garmin (.FIT).

Pas de build, pas de `npm install` : du HTML/JS natif, Tailwind via CDN, et Supabase comme backend (authentification + base de données).

## Fonctionnalités

- **Compte utilisateur** : inscription / connexion par e-mail et mot de passe (Supabase Auth).
- **Mode démo** (bouton « Essayer la démo » sur la page de connexion) : visite complète sans compte, avec une semaine d'exemple et un profil fictif. Séances et profil restent en mémoire : rien n'est écrit en base, tout disparaît en quittant ou en rechargeant. Seule la banque d'entraînements (publique) est lue.
- **Calendrier hebdomadaire** : navigation semaine par semaine, glisser-déposer pour déplacer une séance, case à cocher « réalisée », suppression d'une séance.
- **Séances structurées** : titre, date, type (Course à pied, Vélo / Gravel, Musculation, ski de fond, Kayak de vitesse, Repos) et trois blocs (échauffement, bloc principal, retour au calme).
- **Ajouter une séance** (bouton « + » d'un jour), deux modes :
  - **Depuis la banque** : type de séance (clé, secondaire, endurance facile, sortie longue), énergie et objectif, avec les mêmes règles que le générateur ; évite les séances des 2 semaines précédentes ; bouton « Autre proposition ».
  - **Manuel** : un bloc par ligne (`20 min Z2`, `6x 3 min Z5, récup 2 min`, `10x 400m VMA / 1 min 15`). Un aperçu montre en direct les étapes que recevra la montre et signale ce qui n'est pas compris. Ces étapes servent aussi au détail de la séance et à l'export .FIT.
- **Import des activités de la montre** (par la synchro, bouton « Montre » de l'en-tête) : chaque activité coche la séance prévue le même jour pour le même sport, sinon une séance « libre » réalisée est ajoutée au calendrier. Le détail de la séance affiche « Réalisé : distance · durée · allure ou vitesse · FC · puissance » et les tours. Une activité déjà importée est reconnue, sans doublon.
  - **Prévu vs réalisé** : chaque effort comparé au tour correspondant (allure en course, zone de FC ailleurs ; durée ou distance), verdict « Tenu / Trop lent / Trop court… » et note de séance /10. Le détail par intervalle suppose d'avoir suivi la séance .FIT de l'app sur la montre (une étape = un tour).
  - **Charge & fatigue** : charge TRIMP (minutes × zone de FC ; estimée sans cardio) ; tuile « Charge 7 jours » du résumé avec le ratio sur la moyenne des 4 semaines et l'historique de 6 semaines ; le générateur s'en sert avec la VFC, le sommeil et la FC au repos pour proposer le niveau d'énergie.
  - **Sortie réalisée** : temps par zone de FC (base FC seuil de la montre ou du profil, sinon FC max), Training Effect, courbes FC / allure ou vitesse / puissance / altitude / cadence avec survol, carte du parcours (Leaflet + OpenStreetMap).
  - **Tours dans les courbes** : une bande par tour (teintée selon la zone de l'étape quand la séance .FIT de l'app a été suivie), séparateurs et numéros, palier de la moyenne du tour (FC, allure ou vitesse, puissance, cadence), tour indiqué dans la bulle. Tableau des tours dessous (durée, distance, allure ou vitesse, FC, puissance) : toucher une ligne surligne le tour dans la courbe, toucher la courbe surligne la ligne.
- **Synchro de la montre en un clic** (bouton « Montre » de l'en-tête, montre branchée en USB sur un PC Windows ou un Mac avec le relais installé) : importe les nouvelles sorties, retire de la montre les séances de l'app datées d'avant aujourd'hui et y dépose celles des 14 prochains jours, dans l'ordre chronologique.
- **Profil athlète** (« Mon profil ») : ce que Garmin ne partage pas avec l'app, saisi à la main : prédictions 5K / 10K, VO2 Max, allure au seuil lactique. Ces valeurs servent à personnaliser les séances générées. La FC au seuil, la FC max, la FC de repos et les meilleurs 5 / 10 km des 6 dernières semaines viennent de Garmin (« Données Garmin › Repères course », avec un bouton pour reporter ces temps dans le profil).
- **Générateur de plan (« coach »)** : selon l'objectif (vitesse / VO2max, seuil / rythme, endurance / fond, force / puissance, maintien), valable pour tous les sports, ton niveau d'énergie (en forme, normal, fatigué) et le nombre de séances voulues par sport en semaine et le week-end, il crée les séances de la semaine en tenant compte des deux dernières semaines. Pour chaque sport : une séance clé et une séance secondaire liées à l'objectif (via la colonne `category` de `training_bank`), le reste en endurance et une sortie longue le week-end. Un aperçu dans la fenêtre montre la semaine jour par jour ; le bouton **Info** explique le moteur.
  - **Forme** : à l'ouverture, VFC (statut Garmin), sommeil (score moyen des 3 dernières nuits), FC au repos (vs moyenne) et charge 7 jours proposent le niveau d'énergie (« Fatigué » sur un signal de fatigue ou deux de vigilance, « Pêche d'enfer » retirée sur un seul) ; les signaux s'affichent sous le choix.
  - **Cycle** : type de semaine automatique, semaine de récup après 3 semaines chargées d'affilée (≥ 80 % de la moyenne des 8 précédentes) : séances plus courtes, clé à effort ≤ 7, secondaire en endurance. Forçable en charge ou récup.
  - **Objectif de course** (Mon profil : date, distance, allure visée, temps calculé ; colonnes ajoutées par [sql/objectif.sql](sql/objectif.sql)) : bloc spécifique les 4 semaines avant l'affûtage (clés de course selon la distance, pas de semaine de récup), affûtage 1 semaine (2 dès 30 km), semaine de course (séances courtes, veille très facile, récup après) et la course ajoutée au calendrier le jour J (« Objectif 10 km - 49:10 »).
  - **Placement** : toutes les répartitions sur les jours cochés sont essayées ; celle retenue évite deux séances dures d'affilée (tous sports), puis le même sport deux jours de suite. L'aperçu prévient si c'est impossible avec les jours choisis.
- **Export Garmin (.FIT)** : les séances des 14 prochains jours partent sur la montre avec la synchro (bouton « Montre ») ; une séance seule se télécharge aussi depuis sa fiche (bouton « .FIT »). Le fichier, écrit par [fitBuilder.js](fitBuilder.js), contient :
  - le nom « 10-22 Jeu - Titre » : mois-jour et jour abrégé, pour garder l'ordre chronologique sur la montre (fin décembre, quand les 14 jours de la synchro débordent sur janvier, l'année est ajoutée : « 26-12-29 Mar », « 27-01-03 Sam ») ;
  - les étapes et les répétitions, en **distance** quand le texte de la séance en donne une (« 5x 600m », pyramide « 200-400-600-400-200m ») ;
  - des **cibles d'allure** pour la course (calculées depuis les prédictions 5K / 10K du profil : allure de l'intervalle, endurance Z2 pour l'échauffement et le retour au calme, récup libre) ;
  - des zones cardio pour les autres sports.
- Thème clair / sombre qui suit automatiquement le réglage de l'appareil, et mise en page adaptée au mobile.

## Structure du projet

| Fichier | Rôle |
| --- | --- |
| [index.html](index.html) | L'application complète : interface, logique, appels Supabase, générateur et export. |
| [fitBuilder.js](fitBuilder.js) | Encodeur FIT minimal, sans dépendance, pour les fichiers d'entraînement Garmin (script classique qui expose `window.FitModule`). |
| [fitParser.js](fitParser.js) | Lecteur FIT minimal, sans dépendance, pour les activités de la montre (résumé, tours, mesures seconde par seconde, zones, heure locale) et les .zip de Garmin Connect ; calcule temps par zone, charge, courbes réduites et tracé GPS (`window.FitParser`). |
| [outils/](outils/) | Relais montre, petit serveur local qui lit la montre branchée en USB, même en MTP. Windows : `montre-relais.ps1`, `installer-relais.cmd` / `desinstaller-relais.cmd`. Mac : `montre-relais-mac.py` (libmtp), `installer-relais-mac.command` / `desinstaller-relais-mac.command`. Mêmes routes, l'app ne voit pas la différence. |
| [sql/activities.sql](sql/activities.sql) | Table `activities` (activités importées, rattachées aux séances : résumé, zones, charge, courbes, tracé) et ses règles d'accès. Relançable : ajoute les colonnes manquantes. |
| [sql/objectif.sql](sql/objectif.sql) | Colonnes de l'objectif de course dans `user_profiles` (date, distance, allure visée). Relançable. |
| [sql/garmin.sql](sql/garmin.sql) | Données Garmin Connect : colonnes Garmin de `activities`, tables `garmin_profile`, `garmin_daily`, `garmin_daily_detail`, `garmin_credentials` et leurs règles d'accès. Relançable. |
| [supabase/functions/garmin-sync/](supabase/functions/garmin-sync/) | Fonction Supabase du bouton « Mettre à jour » de Mes données Garmin (Personal API de Garmin Connect). |
| [sql/seed_training_bank.sql](sql/seed_training_bank.sql) | Requête à coller dans l'éditeur SQL de Supabase : ~35 séances par sport dans `training_bank` (relançable sans doublons). |
| [test-import.js](test-import.js) | Petit test de chargement du SDK FIT officiel de Garmin depuis un CDN. |
| [garmin-export-app/](garmin-export-app/) | Prototype autonome : un bouton qui télécharge une séance de fractionné codée en dur au format `.fit`. |

## Lancer en local

Tu peux ouvrir `index.html` directement dans le navigateur. Un petit serveur HTTP reste conseillé :

```bash
# au choix
npx serve .
python -m http.server 8000
```

Ouvre ensuite `http://localhost:8000` (ou l'adresse affichée), puis crée un compte.

L'extension VS Code **Live Server** fonctionne aussi.

## Installer en web app

Le site est installable comme une application ([manifest.webmanifest](manifest.webmanifest), icônes dans [icons/](icons/), service worker [sw.js](sw.js)). Il faut le site en ligne (HTTPS, ex. GitHub Pages) ou `localhost` ; pas en ouvrant le fichier.

- **Brave / Chrome / Edge (ordinateur)** : icône « Installer » au bout de la barre d'adresse, ou menu ☰ › *Enregistrer et partager* › *Installer la page en tant qu'application*. L'app s'ouvre dans sa propre fenêtre.
- **Brave / Chrome (Android)** : menu › *Installer l'application* (ou *Ajouter à l'écran d'accueil*).
- **iPhone / iPad** : Safari › Partager › *Sur l'écran d'accueil*.

Le service worker passe toujours par le réseau d'abord : chaque mise à jour du site est prise au prochain chargement. Hors connexion, l'app s'ouvre sur la dernière version chargée (sans données, Supabase demande le réseau).

## Configuration Supabase

L'URL du projet et la clé publique (*publishable*) sont écrites en dur au début du script principal de [index.html](index.html) (`SUPABASE_URL`, `SUPABASE_ANON_KEY`). Pour utiliser ton propre projet Supabase, remplace ces deux valeurs et crée les tables ci-dessous.

### Tables attendues

**`workouts`**

| Colonne | Type | Notes |
| --- | --- | --- |
| `id` | `uuid` / `bigint` | clé primaire |
| `user_id` | `uuid` | référence `auth.users.id` |
| `title` | `text` | |
| `date` | `date` | |
| `type` | `text` | `Course`, `Vélo`, `Renfo` (affiché « Muscu »), `Ski de fond classique`, `Ski de fond skate`, `Kayak` (affiché « Kayak de vitesse »), `Repos` |
| `warmup` | `text` | |
| `main_block` | `text` | |
| `cooldown` | `text` | |
| `completed` | `boolean` | `false` par défaut |

**`user_profiles`**

| Colonne | Type | Notes |
| --- | --- | --- |
| `user_id` | `uuid` | unique (sert pour l'`upsert`) |
| `p5k_time`, `p5k_pace` | `text` | ex. `22:30`, `4:30 /km` |
| `p10k_time`, `p10k_pace` | `text` | |
| `vo2max` | `numeric` | |
| `threshold_pace` | `text` | ex. `4:15 /km` |
| `threshold_hr` | `text` | ex. `178 bpm` |
| `race_date`, `race_distance`, `race_pace` | `date`, `numeric`, `text` | objectif de course : ex. `2026-11-14`, `10`, `4:55 /km` ([sql/objectif.sql](sql/objectif.sql)) |
| `updated_at` | `timestamptz` | |

> La clé publique est faite pour être visible côté navigateur. La sécurité repose sur la **Row Level Security** :
> - `workouts` et `user_profiles` : chacun ne lit et ne modifie que ses lignes (`user_id = auth.uid()`) ;
> - `training_bank` : lecture pour tous (mode démo compris), aucune écriture depuis le site. On la remplit depuis l'éditeur SQL de Supabase, qui n'est pas soumis à la RLS.
>
> Ne mets jamais la clé `service_role` (ou `sb_secret_…`) dans le code : elle contourne toutes ces règles.

## Importer ses activités Garmin

L'app lit directement les fichiers d'activité `.FIT` de la montre : courbes seconde par seconde, tours et tracé GPS, gratuitement et sans mot de passe à confier.

1. Coller [sql/activities.sql](sql/activities.sql) dans l'éditeur SQL de Supabase (une seule fois).
2. Installer le relais de la montre (voir [Synchroniser la montre](#synchroniser-la-montre-windows-et-mac)) : la synchro importe les nouvelles sorties du dossier `GARMIN/Activity`.

La montre ne donne que les activités. La santé (sommeil, Body Battery, VFC…) vient de Garmin Connect : voir [Mes données Garmin](#mes-données-garmin).

## Mes données Garmin

Bouton **« Données »** de l'en-tête, inspiré de Garmin Connect : indicateurs du jour en haut (score de sommeil, Body Battery, VFC, FC au repos, stress, pas, minutes intensives, âge physique), puis **Sommeil** (nuit détaillée : score, coucher → lever, phases, FC, respiration ; toucher une nuit du graphique pour l'afficher), **Body Battery** (plus haut / plus bas, rechargé / dépensé, même principe), volume d'entraînement par sport, temps par zone FC, VFC et sa plage normale, FC au repos, stress, pas, records, repères course et liste filtrable des activités, sur 7 jours (par défaut), 30 jours, 90 jours ou 1 an. Lu dans Supabase (tables `garmin_*` et `activities`).

Depuis octobre 2026, Garmin Connect donne à chacun une **Personal API Key** pour lire ses propres données (lecture seule ; ~100 requêtes / minute).

**Installation (une fois)**
1. Coller [sql/garmin.sql](sql/garmin.sql) dans l'éditeur SQL de Supabase (relançable).
2. Déployer la fonction [supabase/functions/garmin-sync/index.ts](supabase/functions/garmin-sync/index.ts) sous le nom `garmin-sync` : tableau de bord Supabase › Edge Functions › *Deploy a new function* › *Via Editor*, coller le fichier, déployer (ou `supabase functions deploy garmin-sync`).
3. Créer la clé sur le site Garmin Connect (Paramètres › Personal API Key) et la coller dans l'app : bouton « Données » › « Clé Personal API Garmin ».

**« Mettre à jour »** appelle `garmin-sync`, avec la session de l'utilisateur (ses règles d'accès s'appliquent) : profil et zones, santé depuis le dernier jour en base (28 jours au plus), détail intra-journée d'hier et d'aujourd'hui, nouvelles activités (rattachées aux séances comme l'import de la montre ; une sortie déjà importée par la montre reçoit seulement les infos Garmin). Si Garmin limite les requêtes, la synchro s'arrête proprement : relancer une minute plus tard.

**Mise à jour automatique** : connecté, l'app lance elle-même cette synchro si la dernière ne date pas d'aujourd'hui (vérifié à l'ouverture, au retour sur l'app et toutes les heures si elle reste ouverte). Au moins une par jour, donc, dès que l'app est ouverte ; les nouvelles activités sont signalées par une notification.

**Historique complet** (première fois, ou pour tout recharger) : [outils/garmin-export.py](outils/garmin-export.py) télécharge tout dans `garmin-data/` (non versionné : données de santé), [outils/garmin-supabase.py](outils/garmin-supabase.py) l'envoie dans Supabase (`SUPABASE_EMAIL` / `SUPABASE_PASSWORD` du compte de l'app et `GARMIN_PERSONAL_API_KEY` dans `.env`), [outils/garmin-page.py](outils/garmin-page.py) génère une page locale `garmin-data/tableau.html`. Python 3.12+ et `pip install garmin-connect-personal-api-python`.

## Synchroniser la montre (Windows et Mac)

Une montre Garmin récente se branche en **MTP** (sans lettre de lecteur) : aucun navigateur ne peut la lire. Un petit relais local le fait à sa place et ne répond qu'à l'app : PowerShell sur Windows (sans logiciel à télécharger), Python + libmtp sur Mac. Les deux répondent de la même façon : un ordinateur ou l'autre, le bouton « Montre » fait la même chose. Chaque ordinateur a son propre jeton, à coller dans le navigateur de cet ordinateur. Pas de synchro sur iPad : iPadOS ne lit pas les montres en MTP.

**Installation sur Windows (une fois par PC)**
1. Double-cliquer sur [outils/installer-relais.cmd](outils/installer-relais.cmd), donner l'adresse du site (ex. `https://monsite.github.io`).
2. Le jeton affiché est copié dans le presse-papiers : le coller dans l'app : bouton **« Montre »** de l'en-tête, puis **« Réglages du relais »** en bas de la fenêtre, et « Tester ».
3. Au premier clic, le navigateur peut demander l'autorisation d'accéder aux appareils du réseau local : accepter.

**Installation sur Mac (une fois par Mac)**
1. Installer [Homebrew](https://brew.sh) s'il n'y est pas.
2. Double-cliquer sur [outils/installer-relais-mac.command](outils/installer-relais-mac.command) (si macOS le bloque : clic droit → Ouvrir, ou `bash outils/installer-relais-mac.command` dans le Terminal). Il installe libmtp (et Python 3 si besoin), demande l'adresse du site et lance le relais à chaque ouverture de session (LaunchAgent `com.monplan.relais`).
3. Coller le jeton affiché (déjà dans le presse-papiers) dans l'app : bouton **« Montre »** de l'en-tête, puis **« Réglages du relais »** en bas de la fenêtre, et « Tester ».
4. Navigateur conseillé : Chrome ou Edge. Safari peut refuser qu'un site en ligne appelle `localhost`.

**Utilisation** : brancher la montre (sur Windows, attendre qu'elle apparaisse dans l'Explorateur ; sur Mac, **fermer Garmin Express**, qui bloque l'accès à la montre), cliquer sur **« Montre »**. Puis débrancher la montre : elle intègre les nouvelles séances.
- Sorties des 30 derniers jours pas encore récupérées → import habituel (rattachement aux séances, pas de doublon).
- Séances de l'app datées d'avant aujourd'hui → déplacées dans `%APPDATA%\MonPlan\retires` (Mac : `~/Library/Application Support/MonPlan/retires`), pas effacées. Le relais les reconnaît dans `GARMIN/NewFiles` (`AAAA-MM-JJ_….fit`) et dans `GARMIN/Workouts`, où la montre les range au débranchement sous un nom tiré du nom affiché (`10-23_Ven_-_Seuil_Lactique_-_2x_workout.fit`, contenu identique). Les autres entraînements de la montre ne sont jamais touchés.
- Séances des 14 prochains jours (non réalisées) → copiées dans `GARMIN/NewFiles` dans l'ordre chronologique, seulement si nouvelles ou modifiées. Le nom du fichier porte l'empreinte de son contenu (`AAAA-MM-JJ_jeu_titre_a3f9c1d2.fit`), que le relais recalcule pour les séances renommées par la montre : la synchro compare les empreintes avec ce qui est sur la montre, sans rien garder dans le navigateur, et fonctionne donc depuis n'importe quel ordinateur. Toute modification (séance, allures du profil, étapes de la banque) est détectée ; l'ancienne version est retirée de la montre.

**Sécurité** : le relais n'écoute que `localhost:47812`, exige le jeton secret (gardé dans ce navigateur, jamais en base), n'accepte que l'adresse du site et `localhost`, refuse tout nom de fichier contenant un chemin et tout fichier qui n'est pas un `.FIT`. Journal : `%APPDATA%\MonPlan\relais.log` (Mac : `~/Library/Application Support/MonPlan/relais.log`).

**Désinstallation** : double-cliquer sur [outils/desinstaller-relais.cmd](outils/desinstaller-relais.cmd) (Windows) ou [outils/desinstaller-relais-mac.command](outils/desinstaller-relais-mac.command) (Mac).

## Importer une séance sur Garmin

La synchro de la montre (bouton **« Montre »**) le fait toute seule. Sans le relais : télécharge le fichier `.fit` avec le bouton **.FIT** du détail de la séance, puis copie-le sur la montre par câble :

1. Branche la montre à l'ordinateur avec son câble USB.
2. Ouvre l'Explorateur › *Ce PC* › ta montre (selon le modèle : un lecteur, ou un appareil avec *Internal Storage*).
3. Copie le fichier dans le dossier `GARMIN/NewFiles`.
4. Débranche la montre : la séance apparaît dans le menu **Entraînements**.

Pour repartir à zéro chaque semaine : supprime les anciennes séances depuis le menu Entraînements de la montre, ou leurs fichiers dans `GARMIN/Workouts` en USB (selon le modèle), puis copie les fichiers de la nouvelle semaine.

> **Pas par Garmin Connect** : Garmin Connect n'a pas d'import manuel de fichiers d'entraînement. La page *Importer des données* n'accepte que des activités enregistrées et répond « Un de vos fichiers n'a pas été accepté par le système » ([forum Garmin](https://forums.garmin.com/developer/fit-sdk/f/discussion/426425/the-fit-workout-generated-by-a-tool-i-made-keeps-getting-rejected-by-the-garmin-connect-website/2005568)).

## Limites connues

- Les séances de la banque (`training_bank.garmin_steps`) sont exportées avec leur structure exacte. Une séance saisie à la main est du texte libre : l'export l'interprète par motifs et approximations (par exemple, 400 m ≈ 90 s).