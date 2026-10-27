"""Export complet de mes données Garmin via la Personal API officielle.

Usage :  py outils/garmin-export.py [--jours 365] [--jours-detail 30] [--sans-fit]
La clé est lue dans .env (GARMIN_PERSONAL_API_KEY=...). Sortie : garmin-data/
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "garmin-data"

# Fenêtre max acceptée par Garmin pour chaque endpoint "plage de dates" (en jours)
PLAGES = {
    "daily-summaries": ("get_daily_summaries", 180),
    "hrv-summaries": ("get_daily_hrv_summaries", 180),
    "sleep-summaries": ("get_daily_sleep_summaries", 28),
    "body-battery": ("get_daily_body_battery", 28),
    "stress": ("get_daily_stress", 7),
    "steps": ("get_daily_steps", 7),
    "hydration": ("get_daily_hydration", 7),
    "weight": ("get_weight_measurements", 28),
    "weight-goals": ("get_effective_weight_goals", 28),
    "wellness-activities": ("get_wellness_activity_summaries", 28),
}

# Endpoints "un jour à la fois" (détail intra-journée)
PAR_JOUR = {
    "sleep": "get_daily_sleep",
    "hrv": "get_daily_hrv",
    "heart-rate": "get_daily_heart_rate",
    "spo2": "get_daily_spo2",
}


def lire_cle():
    if os.environ.get("GARMIN_PERSONAL_API_KEY"):
        return os.environ["GARMIN_PERSONAL_API_KEY"]
    for ligne in (RACINE / ".env").read_text(encoding="utf-8").splitlines():
        if ligne.startswith("GARMIN_PERSONAL_API_KEY="):
            return ligne.split("=", 1)[1].strip()
    sys.exit("Clé introuvable : ajoute GARMIN_PERSONAL_API_KEY=... dans .env")


def ecrire(chemin, donnees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")


def appel(nom, fn, *args, **kwargs):
    # Garmin limite à ~100 requêtes / minute : on attend et on réessaie sur HTTP 429
    for _ in range(5):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # on continue même si un endpoint échoue
            attente = re.search(r'HTTP 429.*"retryInSeconds":(\d+)', str(e))
            if not attente:
                print(f"  ! {nom} : {e}")
                return None
            pause = int(attente.group(1)) + 2
            print(f"  … limite atteinte, pause {pause}s")
            time.sleep(pause)
    print(f"  ! {nom} : abandon après 5 essais")
    return None


def morceaux(debut, fin, taille):
    d = debut
    while d <= fin:
        f = min(d + timedelta(days=taille - 1), fin)
        yield d, f
        d = f + timedelta(days=1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jours", type=int, default=365, help="historique des résumés quotidiens")
    p.add_argument("--jours-detail", type=int, default=30, help="historique du détail intra-journée")
    p.add_argument("--sans-fit", action="store_true", help="ne pas télécharger les fichiers FIT")
    args = p.parse_args()

    with PersonalApiAuthenticator() as auth:
        token = auth.obtain_token(lire_cle())
    print(f"Token obtenu (expire {token.expires_at})")

    aujourdhui = date.today()
    with GarminPersonalApiClient(token.access_token) as c:
        print("Profil…")
        ecrire(SORTIE / "profil.json", {
            "settings": appel("profil", c.get_user_profile_settings),
            "zones_fc": appel("zones FC", c.get_heart_rate_zones),
            "fitness_age": appel("fitness age", c.get_fitness_age, aujourdhui),
        })

        debut = aujourdhui - timedelta(days=args.jours - 1)
        for nom, (methode, taille) in PLAGES.items():
            print(f"{nom}…")
            resultats = []
            for d, f in morceaux(debut, aujourdhui, taille):
                r = appel(f"{nom} {d}", getattr(c, methode), d, f)
                if r is not None:
                    resultats.append({"debut": d.isoformat(), "fin": f.isoformat(), "data": r})
            ecrire(SORTIE / "quotidien" / f"{nom}.json", resultats)

        debut_detail = aujourdhui - timedelta(days=args.jours_detail - 1)
        for nom, methode in PAR_JOUR.items():
            print(f"{nom} (détail {args.jours_detail} j)…")
            for d, _ in morceaux(debut_detail, aujourdhui, 1):
                fichier = SORTIE / "detail" / nom / f"{d}.json"
                if fichier.exists() and d < aujourdhui:
                    continue
                r = appel(f"{nom} {d}", getattr(c, methode), d)
                if r is not None:
                    ecrire(fichier, r)

        print("Activités…")
        activites, start = [], 0
        while True:
            page = appel(f"activités {start}", c.search_activities, start=start, limit=50)
            if not page:
                break
            activites.extend(page)
            start += len(page)
            if len(page) < 50:
                break
        ecrire(SORTIE / "activites.json", activites)
        print(f"  {len(activites)} activités")

        for a in activites:
            aid = a.get("activityId")
            fichier = SORTIE / "activites" / f"{aid}.json"
            if not fichier.exists():
                detail = appel(f"activité {aid}", c.get_activity, aid)
                if detail is not None:
                    ecrire(fichier, {
                        "detail": detail,
                        "workouts": appel(f"workouts {aid}", c.get_activity_workouts, aid),
                    })
            zip_ = SORTIE / "fit" / f"{aid}.zip"
            if not args.sans_fit and not zip_.exists():
                contenu = appel(f"FIT {aid}", c.download_activity, aid)
                if contenu:
                    zip_.parent.mkdir(parents=True, exist_ok=True)
                    zip_.write_bytes(contenu)

    print(f"Terminé → {SORTIE}")


if __name__ == "__main__":
    main()
