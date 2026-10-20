# Mon Plan d'Entraînement

Application web (une seule page) pour planifier ses séances de course à pied et de vélo sur un calendrier hebdomadaire. Elle génère des semaines d'entraînement adaptées à ton profil et exporte les séances vers Garmin (.FIT).

Pas de build, pas de `npm install` : du HTML/JS natif, Tailwind via CDN, et Supabase comme backend (authentification + base de données).

## Fonctionnalités

- **Compte utilisateur** : inscription / connexion par e-mail et mot de passe (Supabase Auth).
- **Mode démo** (bouton « Essayer la démo » sur la page de connexion) : visite complète sans compte, avec une semaine d'exemple et un profil fictif. Séances et profil restent en mémoire : rien n'est écrit en base, tout disparaît en quittant ou en rechargeant. Seule la banque d'entraînements (publique) est lue.
- **Calendrier hebdomadaire** : navigation semaine par semaine, glisser-déposer pour déplacer une séance, case à cocher « réalisée », suppression d'une séance ou de tout le calendrier.
- **Séances structurées** : titre, date, type (Course à pied, Vélo / Gravel, Musculation, ski de fond, Repos) et trois blocs (échauffement, bloc principal, retour au calme).
- **Profil athlète** : chronos et allures 5K / 10K, VO2 Max, allure et FC au seuil lactique. Ces valeurs servent à personnaliser les séances générées.
- **Générateur de plan (« coach »)** : selon l'objectif (vitesse / VO2max, seuil / rythme, endurance / fond, force / puissance, maintien), valable pour tous les sports, ton niveau d'énergie (en forme, normal, fatigué) et le nombre de séances voulues par sport en semaine et le week-end, il crée les séances de la semaine en tenant compte des deux dernières semaines. Pour chaque sport : une séance clé et une séance secondaire liées à l'objectif (via la colonne `category` de `training_bank`), le reste en endurance et une sortie longue le week-end. Un aperçu dans la fenêtre montre ce qui sera généré.
- **Export Garmin (.FIT)** : une séance (bouton « Garmin .FIT » de l'en-tête, ou détail d'une séance) ou **une semaine au choix** d'un coup (un fichier par séance, flèches pour changer de semaine). Le fichier, écrit par [fitBuilder.js](fitBuilder.js), contient :
  - le nom « 2 Mar - Titre » : numéro du jour (1 = lundi … 7 = dimanche) et jour abrégé, pour garder l'ordre de la semaine sur la montre ;
  - les étapes et les répétitions, en **distance** quand le texte de la séance en donne une (« 5x 600m », pyramide « 200-400-600-400-200m ») ;
  - des **cibles d'allure** pour la course (calculées depuis les prédictions 5K / 10K du profil : allure de l'intervalle, endurance Z2 pour l'échauffement et le retour au calme, récup libre) ;
  - des zones cardio pour les autres sports.
- Thème clair / sombre qui suit automatiquement le réglage de l'appareil, et mise en page adaptée au mobile.

## Structure du projet

| Fichier | Rôle |
| --- | --- |
| [index.html](index.html) | L'application complète : interface, logique, appels Supabase, générateur et export. |
| [fitBuilder.js](fitBuilder.js) | Encodeur FIT minimal, sans dépendance, pour les fichiers d'entraînement Garmin (script classique qui expose `window.FitModule`). |
| [supabase.js](supabase.js) | Client Supabase en module ES (non utilisé par `index.html`, qui crée son propre client). |
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
| `type` | `text` | `Course`, `Vélo`, `Renfo` (affiché « Muscu »), `Ski de fond classique`, `Ski de fond skate`, `Repos` |
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

> La clé publique est faite pour être visible côté navigateur. La sécurité repose sur la **Row Level Security** : active-la sur les deux tables avec une politique du type `user_id = auth.uid()` pour que chacun ne voie que ses propres données.

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