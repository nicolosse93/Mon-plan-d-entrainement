# Mon Plan d'Entraînement

Application web (une seule page) pour planifier ses séances de course à pied et de vélo sur un calendrier hebdomadaire. Elle génère des semaines d'entraînement adaptées à ton profil et exporte les séances vers Garmin (.FIT).

Pas de build, pas de `npm install` : du HTML/JS natif, Tailwind via CDN, et Supabase comme backend (authentification + base de données).

## Fonctionnalités

- **Compte utilisateur** : inscription / connexion par e-mail et mot de passe (Supabase Auth).
- **Mode démo** (bouton « Essayer la démo » sur la page de connexion) : visite complète sans compte, avec une semaine d'exemple et un profil fictif. Séances et profil restent en mémoire : rien n'est écrit en base, tout disparaît en quittant ou en rechargeant. Seule la banque d'entraînements (publique) est lue.
- **Calendrier hebdomadaire** : navigation semaine par semaine, glisser-déposer pour déplacer une séance, case à cocher « réalisée », suppression d'une séance ou de tout le calendrier.
- **Séances structurées** : titre, date, type (Course à pied, Vélo / Gravel, Musculation, ski de fond, Kayak de vitesse, Repos) et trois blocs (échauffement, bloc principal, retour au calme).
- **Ajouter une séance** (bouton « + » d'un jour), deux modes :
  - **Depuis la banque** : type de séance (clé, secondaire, endurance facile, sortie longue), énergie et objectif, avec les mêmes règles que le générateur ; évite les séances des 2 semaines précédentes ; bouton « Autre proposition ».
  - **Manuel** : un bloc par ligne (`20 min Z2`, `6x 3 min Z5, récup 2 min`, `10x 400m VMA / 1 min 15`). Un aperçu montre en direct les étapes que recevra la montre et signale ce qui n'est pas compris. Ces étapes servent aussi au détail de la séance et à l'export .FIT.
- **Import des activités de la montre** (bouton « Importer » de l'en-tête, ou glisser-déposer n'importe où) : fichiers `.fit` (montre en USB, dossier `GARMIN/Activity`) ou `.zip` de Garmin Connect (« Exporter le fichier d'origine »). Chaque activité coche la séance prévue le même jour pour le même sport, sinon une séance « libre » réalisée est ajoutée au calendrier. Le détail de la séance affiche « Réalisé : distance · durée · allure ou vitesse · FC · puissance » et les tours. Réimporter un fichier met à jour son activité, sans doublon.
  - **Prévu vs réalisé** : chaque effort comparé au tour correspondant (allure en course, zone de FC ailleurs ; durée ou distance), verdict « Tenu / Trop lent / Trop court… » et note de séance /10. Le détail par intervalle suppose d'avoir suivi la séance .FIT de l'app sur la montre (une étape = un tour).
  - **Charge & fatigue** : charge TRIMP (minutes × zone de FC ; estimée sans cardio) ; tuile « Charge 7 jours » du résumé avec le ratio sur la moyenne des 4 semaines et l'historique de 6 semaines ; le générateur propose « Fatigué » au-delà de 1,5×.
  - **Sortie réalisée** : temps par zone de FC (base FC seuil de la montre ou du profil, sinon FC max), Training Effect, courbes FC / allure ou vitesse / puissance / altitude / cadence avec survol, carte du parcours (Leaflet + OpenStreetMap).
- **Synchro de la montre en un clic** (bouton « Montre » de l'en-tête, montre branchée en USB sur un PC Windows avec le relais installé) : importe les nouvelles sorties, retire de la montre les séances de l'app datées d'avant aujourd'hui et y dépose celles des 14 prochains jours, dans l'ordre chronologique.
- **Profil athlète** : chronos et allures 5K / 10K, VO2 Max, allure et FC au seuil lactique. Ces valeurs servent à personnaliser les séances générées.
- **Générateur de plan (« coach »)** : selon l'objectif (vitesse / VO2max, seuil / rythme, endurance / fond, force / puissance, maintien), valable pour tous les sports, ton niveau d'énergie (en forme, normal, fatigué) et le nombre de séances voulues par sport en semaine et le week-end, il crée les séances de la semaine en tenant compte des deux dernières semaines. Pour chaque sport : une séance clé et une séance secondaire liées à l'objectif (via la colonne `category` de `training_bank`), le reste en endurance et une sortie longue le week-end. Un aperçu dans la fenêtre montre ce qui sera généré.
- **Export Garmin (.FIT)** : une séance (bouton « Garmin .FIT » de l'en-tête, ou détail d'une séance) ou **une semaine au choix** d'un coup (un fichier par séance, flèches pour changer de semaine). Le fichier, écrit par [fitBuilder.js](fitBuilder.js), contient :
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
| [outils/](outils/) | Relais montre (Windows) : `montre-relais.ps1` (petit serveur local qui lit la montre branchée en USB, même en MTP), `installer-relais.cmd` / `desinstaller-relais.cmd`. |
| [sql/activities.sql](sql/activities.sql) | Table `activities` (activités importées, rattachées aux séances : résumé, zones, charge, courbes, tracé) et ses règles d'accès. Relançable : ajoute les colonnes manquantes. |
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
| `updated_at` | `timestamptz` | |

> La clé publique est faite pour être visible côté navigateur. La sécurité repose sur la **Row Level Security** :
> - `workouts` et `user_profiles` : chacun ne lit et ne modifie que ses lignes (`user_id = auth.uid()`) ;
> - `training_bank` : lecture pour tous (mode démo compris), aucune écriture depuis le site. On la remplit depuis l'éditeur SQL de Supabase, qui n'est pas soumis à la RLS.
>
> Ne mets jamais la clé `service_role` (ou `sb_secret_…`) dans le code : elle contourne toutes ces règles.

## Importer ses activités Garmin

L'API officielle Garmin n'accepte pas de nouveaux développeurs (2026) et celle de Strava demande un abonnement : l'app lit donc directement les fichiers d'activité `.FIT`, gratuitement et sans mot de passe à confier.

1. Coller [sql/activities.sql](sql/activities.sql) dans l'éditeur SQL de Supabase (une seule fois).
2. Récupérer les fichiers : sur connect.garmin.com (ordinateur), ouvrir l'activité → engrenage → « Exporter le fichier d'origine » (un `.zip`, à glisser tel quel) ; ou montre en USB, dossier `GARMIN/Activity`.
3. Les glisser sur l'app (ou bouton « Importer »).

Seules les activités sont lues : VO2max, prédictions, sommeil, Body Battery et VFC restent saisis à la main dans le profil.

## Synchroniser la montre (Windows)

Une montre Garmin récente se branche en **MTP** (sans lettre de lecteur) : aucun navigateur ne peut la lire. Un petit relais PowerShell, sans logiciel à télécharger, le fait à sa place et ne répond qu'à l'app.

**Installation (une fois par PC)**
1. Double-cliquer sur [outils/installer-relais.cmd](outils/installer-relais.cmd), donner l'adresse du site (ex. `https://monsite.github.io`).
2. Le jeton affiché est copié dans le presse-papiers : le coller dans l'app, **Profil → Synchro de la montre**, puis « Tester ».
3. Au premier clic, le navigateur peut demander l'autorisation d'accéder aux appareils du réseau local : accepter.

**Utilisation** : brancher la montre, attendre qu'elle apparaisse dans l'Explorateur, cliquer sur **« Montre »**. Puis débrancher la montre : elle intègre les nouvelles séances.
- Sorties des 30 derniers jours pas encore récupérées → import habituel (rattachement aux séances, pas de doublon).
- Séances de l'app datées d'avant aujourd'hui (fichiers `AAAA-MM-JJ_….fit` de `GARMIN/Workouts` et `GARMIN/NewFiles`) → déplacées dans `%APPDATA%\MonPlan\retires` (pas effacées). Les autres entraînements de la montre ne sont jamais touchés.
- Séances des 14 prochains jours (non réalisées) → copiées dans `GARMIN/NewFiles` dans l'ordre chronologique, seulement si nouvelles ou modifiées. Le nom du fichier porte l'empreinte de son contenu (`AAAA-MM-JJ_jeu_titre_a3f9c1d2.fit`) : la synchro compare avec ce qui est sur la montre, sans rien garder dans le navigateur, et fonctionne donc depuis n'importe quel ordinateur. Toute modification (séance, allures du profil, étapes de la banque) est détectée ; l'ancienne version est retirée de la montre.

**Sécurité** : le relais n'écoute que `localhost:47812`, exige le jeton secret (gardé dans ce navigateur, jamais en base), n'accepte que l'adresse du site et `localhost`, refuse tout nom de fichier contenant un chemin et tout fichier qui n'est pas un `.FIT`. Journal : `%APPDATA%\MonPlan\relais.log`.

**Désinstallation** : double-cliquer sur [outils/desinstaller-relais.cmd](outils/desinstaller-relais.cmd).

## Importer une séance sur Garmin

Dans l'application, télécharge le fichier `.fit` : bouton **Garmin .FIT** de l'en-tête, ou **.FIT** dans le détail d'une séance. Ensuite, copie-le sur la montre par câble :

1. Branche la montre à l'ordinateur avec son câble USB.
2. Ouvre l'Explorateur › *Ce PC* › ta montre (selon le modèle : un lecteur, ou un appareil avec *Internal Storage*).
3. Copie le fichier dans le dossier `GARMIN/NewFiles`.
4. Débranche la montre : la séance apparaît dans le menu **Entraînements**.

Pour repartir à zéro chaque semaine : supprime les anciennes séances depuis le menu Entraînements de la montre, ou leurs fichiers dans `GARMIN/Workouts` en USB (selon le modèle), puis copie les fichiers de la nouvelle semaine.

> **Pas par Garmin Connect** : Garmin Connect n'a pas d'import manuel de fichiers d'entraînement. La page *Importer des données* n'accepte que des activités enregistrées et répond « Un de vos fichiers n'a pas été accepté par le système » ([forum Garmin](https://forums.garmin.com/developer/fit-sdk/f/discussion/426425/the-fit-workout-generated-by-a-tool-i-made-keeps-getting-rejected-by-the-garmin-connect-website/2005568)).

## Limites connues

- Les séances de la banque (`training_bank.garmin_steps`) sont exportées avec leur structure exacte. Une séance saisie à la main est du texte libre : l'export l'interprète par motifs et approximations (par exemple, 400 m ≈ 90 s).