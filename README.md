# Mon Plan d'Entraînement

Application web (une seule page) pour planifier ses séances de course à pied et de vélo sur un calendrier hebdomadaire. Elle génère des semaines d'entraînement adaptées à ton profil et exporte les séances vers Intervals.icu, Zwift/TrainingPeaks (.ZWO) ou Garmin (.FIT).

Pas de build, pas de `npm install` : du HTML/JS natif, Tailwind via CDN, et Supabase comme backend (authentification + base de données).

## Fonctionnalités

- **Compte utilisateur** : inscription / connexion par e-mail et mot de passe (Supabase Auth).
- **Calendrier hebdomadaire** : navigation semaine par semaine, glisser-déposer pour déplacer une séance, case à cocher « réalisée », suppression d'une séance ou de tout le calendrier.
- **Séances structurées** : titre, date, type (Course à pied, Vélo / Gravel, Renforcement, Repos) et trois blocs (échauffement, bloc principal, retour au calme).
- **Profil athlète** : chronos et allures 5K / 10K, VO2 Max, allure et FC au seuil lactique. Ces valeurs servent à personnaliser les séances générées.
- **Générateur de plan (« coach »)** : selon l'objectif (vitesse / VO2max, seuil / rythme, endurance / fond, force / puissance, maintien), valable pour tous les sports, ton niveau d'énergie (en forme, normal, fatigué) et le nombre de séances voulues par sport en semaine et le week-end, il crée les séances de la semaine en tenant compte des deux dernières semaines. Pour chaque sport : une séance clé et une séance secondaire liées à l'objectif (via la colonne `category` de `training_bank`), le reste en endurance et une sortie longue le week-end. Un aperçu dans la fenêtre montre ce qui sera généré.
- **Export** :
  - texte au format Intervals.icu (à copier-coller) ;
  - fichier `.zwo` (Zwift / TrainingPeaks) ;
  - fichier `.fit` (Garmin Connect, écrit par [fitBuilder.js](fitBuilder.js)).
- Mode clair / sombre et mise en page adaptée au mobile.

## Structure du projet

| Fichier | Rôle |
| --- | --- |
| [index.html](index.html) | L'application complète : interface, logique, appels Supabase, générateur et exports. |
| [fitBuilder.js](fitBuilder.js) | Encodeur FIT minimal, sans dépendance, pour les fichiers d'entraînement Garmin. |
| [supabase.js](supabase.js) | Client Supabase en module ES (non utilisé par `index.html`, qui crée son propre client). |
| [test-import.js](test-import.js) | Petit test de chargement du SDK FIT officiel de Garmin depuis un CDN. |
| [garmin-export-app/](garmin-export-app/) | Prototype autonome : un bouton qui télécharge une séance de fractionné codée en dur au format `.fit`. |

## Lancer en local

`index.html` charge `fitBuilder.js` comme module ES. Les navigateurs bloquent les modules ouverts en `file://`, donc il faut passer par un petit serveur HTTP :

```bash
# au choix
npx serve .
python -m http.server 8000
```

Ouvre ensuite `http://localhost:8000` (ou l'adresse affichée), puis crée un compte.

L'extension VS Code **Live Server** fonctionne aussi.

## Configuration Supabase

L'URL du projet et la clé publique (*publishable*) sont écrites en dur au début du `<script type="module">` dans [index.html](index.html) (`SUPABASE_URL`, `SUPABASE_ANON_KEY`). Pour utiliser ton propre projet Supabase, remplace ces deux valeurs et crée les tables ci-dessous.

### Tables attendues

**`workouts`**

| Colonne | Type | Notes |
| --- | --- | --- |
| `id` | `uuid` / `bigint` | clé primaire |
| `user_id` | `uuid` | référence `auth.users.id` |
| `title` | `text` | |
| `date` | `date` | |
| `type` | `text` | `Course`, `Vélo`, `Renfo`, `Ski de fond classique`, `Ski de fond skate`, `Repos` |
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

1. Dans l'application, ouvre **Exporter** et télécharge le fichier `.fit`.
2. Va sur [Garmin Connect › Entraînements](https://connect.garmin.com/modern/workouts).
3. Clique sur **Importer** et choisis le fichier.
4. Envoie la séance vers ta montre.

## Limites connues

- Les blocs d'une séance sont du texte libre. Les exports (.zwo, .fit, Intervals.icu) les interprètent par motifs et approximations (par exemple, 400 m ≈ 90 s).
- `.env` est suivi par Git alors qu'il est aussi listé dans `.gitignore`. Il est vide aujourd'hui ; lance `git rm --cached .env` avant d'y mettre des secrets.
