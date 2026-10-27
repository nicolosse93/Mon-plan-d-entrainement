"""Génère garmin-data/tableau.html à partir des JSON exportés par garmin-export.py.

Usage :  py outils/garmin-page.py   (puis ouvrir garmin-data/tableau.html)
"""
import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "garmin-data"


def lire(nom):
    return json.loads((DONNEES / nom).read_text(encoding="utf-8"))


def plat(nom, cle=None):
    """Aplatit les morceaux d'un fichier quotidien/<nom>.json en une seule liste."""
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


def sport(type_key):
    if "running" in type_key:
        return "Course"
    if "cycling" in type_key or "ride" in type_key or "biking" in type_key:
        return "Vélo"
    if "skiing" in type_key:
        return "Ski de fond"
    return "Autre"


def construire():
    jours = {}

    def jour(date):
        return jours.setdefault(date, {"d": date})

    for s in plat("daily-summaries", "data"):
        hr, bb = s.get("heartRate") or {}, s.get("bodyBattery") or {}
        jour(s["calendarDate"]).update(
            rhr=positif(hr.get("restingValue")),
            bbMin=positif(bb.get("minValue")),
            bbMax=positif(bb.get("maxValue")),
            stress=positif((s.get("stress") or {}).get("avgLevel")),
            cal=positif((s.get("calories") or {}).get("burnedTotal")),
        )
    for s in plat("steps"):
        jour(s["calendarDate"]).update(steps=positif(s.get("totalSteps")), stepGoal=s.get("stepGoal"))
    for h in plat("hrv-summaries", "hrvSummaries"):
        base = h.get("baseline") or {}
        jour(h["calendarDate"]).update(
            hrv=h.get("lastNightAvg"), hrvWeek=h.get("weeklyAvg"),
            hrvLo=base.get("balancedLow"), hrvHi=base.get("balancedUpper"), hrvStatus=h.get("status"),
        )
    for s in plat("sleep-summaries"):
        if not s.get("sleepTimeSeconds"):
            continue
        h = lambda k: round((s.get(k) or 0) / 3600, 2)
        jour(s["calendarDate"]).update(
            sDeep=h("deepSleepSeconds"), sRem=h("remSleepSeconds"),
            sLight=h("lightSleepSeconds"), sAwake=h("awakeSleepSeconds"),
            sStress=s.get("avgSleepStress"), sHr=s.get("avgHeartRate"),
        )

    activites = []
    for a in lire("activites.json"):
        activites.append({
            "id": a["activityId"],
            "d": a["startTimeLocal"][:16],
            "n": a.get("activityName") or "",
            "t": a["activityType"]["typeKey"],
            "s": sport(a["activityType"]["typeKey"]),
            "km": round((a.get("distance") or 0) / 1000, 2),
            "min": round((a.get("movingDuration") or a.get("duration") or 0) / 60, 1),
            "v": a.get("averageSpeed"),
            "hr": a.get("averageHR"),
            "te": a.get("aerobicTrainingEffect"),
            "load": a.get("activityTrainingLoad"),
            "dplus": a.get("elevationGain"),
            "f5k": a.get("fastestSplit_5000"),
            "z": [a.get(f"hrTimeInZone_{i}") or 0 for i in range(1, 6)],
        })

    profil = lire("profil.json")
    fa = profil.get("fitness_age") or {}
    zones = (profil.get("zones_fc") or [{}])[0]
    nom = next((a.get("ownerFullName") for a in lire("activites.json") if a.get("ownerFullName")), "")
    return {
        "nom": nom,
        "age": fa.get("chronologicalAge"),
        "fitnessAge": fa.get("fitnessAge"),
        "fitnessAgeCible": fa.get("achievableFitnessAge"),
        "zones": zones,
        "jours": sorted(jours.values(), key=lambda j: j["d"]),
        "activites": activites,
    }


def main():
    data = json.dumps(construire(), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    gabarit = (Path(__file__).parent / "garmin-page.html").read_text(encoding="utf-8")
    sortie = DONNEES / "tableau.html"
    sortie.write_text(gabarit.replace("__DATA__", data), encoding="utf-8")
    print(f"Page générée → {sortie}")


if __name__ == "__main__":
    main()
