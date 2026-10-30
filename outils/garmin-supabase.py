"""Envoie les données exportées par garmin-export.py dans Supabase (tables de sql/garmin.sql).

Usage :  py outils/garmin-supabase.py
Connexion avec ton compte de l'app : SUPABASE_EMAIL et SUPABASE_PASSWORD dans .env.
Relançable : rien n'est dupliqué, une activité déjà en base (même heure de départ) garde sa séance liée.
"""
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "garmin-data"

# Mêmes valeurs publiques que index.html
SUPABASE_URL = "https://dopgoecbdssvxexanavs.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_5GrtRyqg1LV-wDZpFUxEnw_FHTDWbux"

# Type Garmin -> types de séance de l'app, par ordre de préférence (comme appTypes de fitParser.js)
TYPES_APP = {
    "running": ["Course"], "treadmill_running": ["Course"], "trail_running": ["Course"],
    "track_running": ["Course"], "indoor_running": ["Course"],
    "cycling": ["Vélo"], "road_biking": ["Vélo"], "mountain_biking": ["Vélo"], "gravel_cycling": ["Vélo"],
    "virtual_ride": ["Vélo"], "indoor_cycling": ["Vélo"],
    "strength_training": ["Renfo"],
    "cross_country_skiing_ws": ["Ski de fond classique", "Ski de fond skate"],
    "skate_skiing_ws": ["Ski de fond skate", "Ski de fond classique"],
    "e_bike_mountain": ["Vélo"], "e_bike_fitness": ["Vélo"],
    "paddling_v2": ["Kayak"], "kayaking_v2": ["Kayak"],
    "rowing_v2": ["Aviron"], "indoor_rowing": ["Aviron"],
    "walking": ["Marche"], "casual_walking": ["Marche"], "speed_walking": ["Marche"],
    "hiking": ["Randonnée"],
}
# Tout type Garmin absent de TYPES_APP devient « Autre »
types_app = lambda type_key: TYPES_APP.get(type_key, ["Autre"])
SPORT_FIT = {"Course": 1, "Vélo": 2, "Renfo": 10, "Ski de fond classique": 12, "Ski de fond skate": 12, "Kayak": 19,
             "Aviron": 15, "Marche": 11, "Randonnée": 17}


def env():
    valeurs = {}
    for ligne in (RACINE / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in ligne and not ligne.lstrip().startswith("#"):
            k, v = ligne.split("=", 1)
            valeurs[k.strip()] = v.strip()
    return valeurs


class Supabase:
    def __init__(self, email, mot_de_passe):
        r = self._http("POST", "/auth/v1/token?grant_type=password", {"email": email, "password": mot_de_passe}, auth=False)
        self.token, self.user_id = r["access_token"], r["user"]["id"]

    def _http(self, methode, chemin, corps=None, auth=True, entetes=None):
        h = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
        if auth:
            h["Authorization"] = f"Bearer {self.token}"
        h.update(entetes or {})
        donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8") if corps is not None else None
        req = urllib.request.Request(SUPABASE_URL + chemin, data=donnees, method=methode, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as rep:
                texte = rep.read().decode("utf-8")
                return json.loads(texte) if texte else None
        except urllib.error.HTTPError as e:
            sys.exit(f"Supabase {methode} {chemin.split('?')[0]} : HTTP {e.code} {e.read().decode('utf-8')[:500]}")

    def tout_lire(self, table, colonnes):
        lignes, debut = [], 0
        while True:
            page = self._http("GET", f"/rest/v1/{table}?select={colonnes}", entetes={"Range": f"{debut}-{debut + 999}"})
            lignes.extend(page)
            if len(page) < 1000:
                return lignes
            debut += 1000

    def upsert(self, table, lignes, conflit, taille=100):
        for i in range(0, len(lignes), taille):
            self._http("POST", f"/rest/v1/{table}?on_conflict={conflit}", lignes[i:i + taille],
                       entetes={"Prefer": "resolution=merge-duplicates,return=minimal"})

    def inserer(self, table, lignes, taille=100):
        for i in range(0, len(lignes), taille):
            self._http("POST", f"/rest/v1/{table}", lignes[i:i + taille], entetes={"Prefer": "return=minimal"})

    def modifier(self, table, filtre, valeurs):
        self._http("PATCH", f"/rest/v1/{table}?{filtre}", valeurs, entetes={"Prefer": "return=minimal"})


def lire(nom):
    return json.loads((DONNEES / nom).read_text(encoding="utf-8"))


def plat(nom, cle=None):
    out = []
    for morceau in lire(f"quotidien/{nom}.json"):
        d = morceau["data"]
        if cle and isinstance(d, dict):
            d = d.get(cle) or []
        if isinstance(d, list):
            out.extend(d)
    return out


def positif(v):
    return v if isinstance(v, (int, float)) and v >= 0 else None


def entier(v):
    return round(v) if isinstance(v, (int, float)) else None


def profil(sb):
    p = lire("profil.json")
    sb.upsert("garmin_profile", [{
        "user_id": sb.user_id, "settings": p.get("settings"), "hr_zones": p.get("zones_fc"),
        "fitness_age": p.get("fitness_age"), "updated_at": datetime.now(timezone.utc).isoformat(),
    }], "user_id")
    print("Profil envoyé")


def quotidien(sb):
    raw = {}

    def brut(date, cle, valeur):
        if date:  # Garmin renvoie parfois une entrée vide sans date
            raw.setdefault(date, {})[cle] = valeur

    for s in plat("daily-summaries", "data"):
        brut(s["calendarDate"], "summary", s)
    for s in plat("sleep-summaries"):
        brut(s["calendarDate"], "sleep", s)
    for s in plat("hrv-summaries", "hrvSummaries"):
        brut(s["calendarDate"], "hrv", s)
    for s in plat("body-battery"):
        brut(s["date"], "body_battery", s)
    for s in plat("stress"):
        brut(s["calendarDate"], "stress", s)
    for s in plat("steps"):
        brut(s["calendarDate"], "steps", s)

    maintenant = datetime.now(timezone.utc).isoformat()
    lignes = []
    for date, r in sorted(raw.items()):
        s, sl, hv, st = r.get("summary") or {}, r.get("sleep") or {}, r.get("hrv") or {}, r.get("steps") or {}
        hr, bb, stress = s.get("heartRate") or {}, s.get("bodyBattery") or {}, s.get("stress") or {}
        mv, cal, im, resp = s.get("movement") or {}, s.get("calories") or {}, s.get("intensityMinutes") or {}, s.get("respiration") or {}
        base = hv.get("baseline") or {}
        lignes.append({
            "user_id": sb.user_id, "date": date,
            "resting_hr": positif(hr.get("restingValue")), "min_hr": positif(hr.get("minValue")), "max_hr": positif(hr.get("maxValue")),
            "hrv_last_night": hv.get("lastNightAvg"), "hrv_weekly_avg": hv.get("weeklyAvg"),
            "hrv_baseline_low": base.get("balancedLow"), "hrv_baseline_high": base.get("balancedUpper"), "hrv_status": hv.get("status"),
            "sleep_seconds": sl.get("sleepTimeSeconds"), "sleep_deep_seconds": sl.get("deepSleepSeconds"),
            "sleep_light_seconds": sl.get("lightSleepSeconds"), "sleep_rem_seconds": sl.get("remSleepSeconds"),
            "sleep_awake_seconds": sl.get("awakeSleepSeconds"), "sleep_avg_hr": sl.get("avgHeartRate"),
            "sleep_avg_stress": sl.get("avgSleepStress"), "sleep_avg_respiration": sl.get("averageRespirationValue"),
            "body_battery_min": positif(bb.get("minValue")), "body_battery_max": positif(bb.get("maxValue")),
            "body_battery_charged": positif(bb.get("chargedValue")), "body_battery_drained": positif(bb.get("drainedValue")),
            "stress_avg": positif(stress.get("avgLevel")), "stress_max": positif(stress.get("maxLevel")),
            "steps": positif(st.get("totalSteps") if st else mv.get("steps")), "step_goal": st.get("stepGoal"),
            "distance_m": positif(st.get("totalDistance")), "floors_ascended": positif(mv.get("floorsAscended")),
            "calories_total": entier(positif(cal.get("burnedTotal"))), "calories_active": entier(positif(cal.get("burnedActive"))),
            "intensity_minutes_moderate": positif(im.get("moderate")), "intensity_minutes_vigorous": positif(im.get("vigorous")),
            "respiration_avg": positif(resp.get("avgValue")),
            "raw": r, "updated_at": maintenant,
        })
    sb.upsert("garmin_daily", lignes, "user_id,date")
    print(f"Santé quotidienne : {len(lignes)} jours envoyés")

    detail = []
    for dossier in sorted((DONNEES / "detail").iterdir()):
        for f in sorted(dossier.glob("*.json")):
            detail.append({"user_id": sb.user_id, "date": f.stem, "kind": dossier.name.replace("-", "_"),
                           "data": json.loads(f.read_text(encoding="utf-8")), "updated_at": maintenant})
    sb.upsert("garmin_daily_detail", detail, "user_id,date,kind", taille=20)
    print(f"Détail intra-journée : {len(detail)} courbes envoyées")


def cle_titre(titre):
    """Titre comparable : sans accents, casse, espaces ni ponctuation."""
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", titre or "").lower())


def seance_suivie(nom):
    """Séance de l'app suivie sur la montre : la sortie en garde le nom « 10-29 Jeu - Titre » (tronqué à 47 car.).
    Renvoie (clé du titre, tronqué ?) ou None."""
    m = re.match(r"^(?:\d{2}-)?\d{2}-\d{2} \S+ - (.+)$", nom or "")
    cle = cle_titre(m.group(1)) if m else ""
    return (cle, len(nom) >= 47) if cle else None


def activites(sb):
    zones = (lire("profil.json").get("zones_fc") or [{}])[0]
    base_zones = {"type": "max", "hr": zones["maxHeartRateUsed"]} if zones.get("maxHeartRateUsed") else None
    en_base = sb.tout_lire("activities", "id,start_time,workout_id")
    par_heure = {datetime.fromisoformat(a["start_time"]).timestamp(): a for a in en_base}
    seances = sb.tout_lire("workouts", "id,date,type,completed,title")
    prises = {str(a["workout_id"]) for a in en_base if a.get("workout_id")}

    nouvelles, existantes, a_cocher, vues = [], [], [], set()
    for a in sorted(lire("activites.json"), key=lambda x: x["startTimeGMT"]):
        aid = a["activityId"]
        debut = datetime.fromisoformat(a["startTimeGMT"].replace(" ", "T")).replace(tzinfo=timezone.utc)
        # Multisport : le parent et sa première étape partagent l'heure de départ, une seule ligne par heure
        if debut.timestamp() in vues:
            continue
        vues.add(debut.timestamp())
        fiche = DONNEES / "activites" / f"{aid}.json"
        garmin = {
            "user_id": sb.user_id,
            "start_time": debut.isoformat(),
            "start_date_local": a["startTimeLocal"][:10],
            "garmin_activity_id": aid,
            "name": a.get("activityName"),
            "garmin_type": a["activityType"]["typeKey"],
            "garmin_summary": a,
            "garmin_detail": json.loads(fiche.read_text(encoding="utf-8"))["detail"] if fiche.exists() else None,
        }
        deja = par_heure.get(debut.timestamp())
        if deja:
            # Déjà importée depuis la montre : on ajoute seulement les infos Garmin, courbes et séance liée intactes
            existantes.append({"id": deja["id"], **garmin})
            continue

        types = types_app(a["activityType"]["typeKey"])
        tiz = [entier(a.get(f"hrTimeInZone_{i}")) or 0 for i in range(1, 6)]
        timer = entier(a.get("duration"))
        charge = round(sum(sec / 60 * (i + 1) for i, sec in enumerate(tiz))) if any(tiz) else None
        cadence = a.get("averageBikingCadenceInRevPerMinute") or (
            a.get("averageRunningCadenceInStepsPerMinute") and a["averageRunningCadenceInStepsPerMinute"] / 2)

        # Même rattachement que l'import FIT de l'app : séance suivie sur la montre, retrouvée par son titre à 14 jours
        # au plus (la plus proche) ; sinon première séance libre du jour et du sport, non réalisée d'abord
        jour = date.fromisoformat(garmin["start_date_local"])
        libres = [w for w in seances if w["type"] in types and str(w["id"]) not in prises]
        ecart = lambda w: abs((date.fromisoformat(w["date"]) - jour).days)
        suivie = seance_suivie(a.get("activityName"))
        nommees = [w for w in libres if ecart(w) <= 14 and suivie and (
            cle_titre(w.get("title")).startswith(suivie[0]) if suivie[1] else cle_titre(w.get("title")) == suivie[0])]
        nommees.sort(key=lambda w: (ecart(w), bool(w["completed"])))
        candidates = [w for w in libres if w["date"] == garmin["start_date_local"]]
        candidates.sort(key=lambda w: (bool(w["completed"]), types.index(w["type"])))
        seance = (nommees or candidates or [None])[0]
        if seance:
            prises.add(str(seance["id"]))
            if not seance["completed"]:
                a_cocher.append(seance["id"])

        nouvelles.append({
            **garmin,
            "workout_id": str(seance["id"]) if seance else None,
            "sport": types[0] if types else None,
            "fit_sport": SPORT_FIT.get(types[0]) if types else None,
            "fit_sub_sport": None,
            "elapsed_time": entier(a.get("elapsedDuration")),
            "timer_time": timer,
            "distance": a.get("distance") or None,
            "total_ascent": a.get("elevationGain"),
            "avg_heart_rate": entier(a.get("averageHR")),
            "max_heart_rate": entier(a.get("maxHR")),
            "avg_speed": a.get("averageSpeed"),
            "max_speed": a.get("maxSpeed"),
            "avg_cadence": entier(cadence),
            "avg_power": entier(a.get("avgPower")),
            "calories": entier(a.get("calories")),
            "training_effect": a.get("aerobicTrainingEffect"),
            "anaerobic_effect": a.get("anaerobicTrainingEffect"),
            "time_in_zones": tiz if any(tiz) else None,
            "zone_basis": base_zones if any(tiz) else None,
            # Sans FC : même estimation que l'app (2 points par minute)
            "load": charge if charge is not None else round((timer or 0) / 60 * 2),
            "load_estimated": charge is None,
        })

    sb.upsert("activities", existantes, "id", taille=50)
    sb.inserer("activities", nouvelles, taille=50)

    # Activités enregistrées sans sport (type Garmin alors inconnu de l'app) : sport attribué après coup
    sans_sport = {a["garmin_type"] for a in sb.tout_lire("activities", "garmin_type,sport") if not a["sport"] and a["garmin_type"]}
    for type_key in sorted(sans_sport):
        sport = types_app(type_key)[0]
        sb.modifier("activities", f"sport=is.null&garmin_type=eq.{type_key}", {"sport": sport, "fit_sport": SPORT_FIT.get(sport)})
    if sans_sport:
        print(f"Sport attribué aux activités sans sport : {', '.join(sorted(sans_sport))}")
    for i in range(0, len(a_cocher), 100):
        sb.modifier("workouts", f"id=in.({','.join(str(x) for x in a_cocher[i:i + 100])})", {"completed": True})
    print(f"Activités : {len(nouvelles)} ajoutées, {len(existantes)} déjà en base complétées, "
          f"{sum(1 for n in nouvelles if n['workout_id'])} rattachées à une séance ({len(a_cocher)} cochées)")


def main():
    e = env()
    if not e.get("SUPABASE_EMAIL") or not e.get("SUPABASE_PASSWORD"):
        sys.exit("Ajoute SUPABASE_EMAIL=... et SUPABASE_PASSWORD=... (ton compte de l'app) dans .env")
    sb = Supabase(e["SUPABASE_EMAIL"], e["SUPABASE_PASSWORD"])
    print(f"Connecté à Supabase ({e['SUPABASE_EMAIL']})")
    profil(sb)
    quotidien(sb)
    activites(sb)


if __name__ == "__main__":
    main()
