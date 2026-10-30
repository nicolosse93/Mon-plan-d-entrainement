// Mise à jour des données Garmin (bouton « Mettre à jour » de la page Mes données Garmin).
// Appelée par l'app avec la session de l'utilisateur : toutes les écritures passent par ses règles d'accès (RLS).
// Garmin limite à ~100 requêtes / minute : la synchro est incrémentale (derniers jours + nouvelles activités).
import { createClient } from 'npm:@supabase/supabase-js@2.117.0';

const GARMIN = 'https://personal.connectapi.garmin.com';
const TOKEN_PATH = '/personalapitoken-service/personal-api/personal-api-key/token';
const BUDGET_MS = 110_000; // au-delà, on s'arrête proprement (limite des fonctions : 150 s)

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

// Type Garmin -> types de séance de l'app, par ordre de préférence (comme outils/garmin-supabase.py)
const TYPES_APP: Record<string, string[]> = {
  running: ['Course'], treadmill_running: ['Course'], trail_running: ['Course'], track_running: ['Course'], indoor_running: ['Course'],
  cycling: ['Vélo'], road_biking: ['Vélo'], mountain_biking: ['Vélo'], gravel_cycling: ['Vélo'], virtual_ride: ['Vélo'],
  indoor_cycling: ['Vélo'], e_bike_mountain: ['Vélo'], e_bike_fitness: ['Vélo'],
  strength_training: ['Renfo'],
  cross_country_skiing_ws: ['Ski de fond classique', 'Ski de fond skate'],
  skate_skiing_ws: ['Ski de fond skate', 'Ski de fond classique'],
  paddling_v2: ['Kayak'], kayaking_v2: ['Kayak'],
  rowing_v2: ['Aviron'], indoor_rowing: ['Aviron'],
  walking: ['Marche'], casual_walking: ['Marche'], speed_walking: ['Marche'],
  hiking: ['Randonnée'],
};
const typesApp = (key: string) => TYPES_APP[key] || ['Autre'];
const SPORT_FIT: Record<string, number> = {
  'Course': 1, 'Vélo': 2, 'Renfo': 10, 'Ski de fond classique': 12, 'Ski de fond skate': 12, 'Kayak': 19,
  'Aviron': 15, 'Marche': 11, 'Randonnée': 17,
};
const SPORT_LABELS: Record<string, string> = { 'Renfo': 'Muscu' };

// deno-lint-ignore no-explicit-any
type Json = any;

class LimiteGarmin extends Error {}

const json = (body: Json, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, 'Content-Type': 'application/json' } });
const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setUTCDate(x.getUTCDate() + n); return x; };
const positif = (v: unknown) => typeof v === 'number' && v >= 0 ? v : null;
const entier = (v: unknown) => typeof v === 'number' ? Math.round(v) : null;
// Titre comparable : sans accents, casse, espaces ni ponctuation
const cleTitre = (t: unknown) => String(t || '').normalize('NFD').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
// Séance de l'app suivie sur la montre : la sortie en garde le nom « 10-29 Jeu - Titre » (tronqué à 47 caractères)
const seanceSuivie = (nom: unknown) => {
  const m = String(nom || '').match(/^(?:\d{2}-)?\d{2}-\d{2} \S+ - (.+)$/);
  const cle = m ? cleTitre(m[1]) : '';
  return cle ? { cle, tronque: String(nom).length >= 47 } : null;
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
  const debutSynchro = Date.now();

  const sb = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_ANON_KEY')!, {
    global: { headers: { Authorization: req.headers.get('Authorization') ?? '' } },
  });
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return json({ error: 'Session expirée : reconnecte-toi.' }, 401);

  const { data: cred } = await sb.from('garmin_credentials').select('*').eq('user_id', user.id).maybeSingle();
  if (!cred?.api_key) return json({ error: 'Clé Garmin absente : ajoute-la dans « Clé Personal API ».' }, 400);

  // Jeton d'accès Garmin (24 h) : celui en cache s'il reste plus d'une heure, sinon échange de la clé
  let token: string = cred.access_token;
  if (!token || !cred.token_expires_at || new Date(cred.token_expires_at).getTime() - Date.now() < 3_600_000) {
    const r = await fetch(GARMIN + TOKEN_PATH, { method: 'POST', headers: { Accept: '*/*', Authorization: `ApiKey ${cred.api_key}` } });
    if (!r.ok) {
      return json({ error: r.status === 401 || r.status === 403
        ? 'Clé Garmin refusée (expirée ?) : crée-en une nouvelle dans Garmin Connect › Paramètres › Personal API Key.'
        : `Garmin indisponible (HTTP ${r.status}).` }, 502);
    }
    token = (await r.text()).trim();
    const exp = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).exp;
    await sb.from('garmin_credentials').update({ access_token: token, token_expires_at: new Date(exp * 1000).toISOString() }).eq('user_id', user.id);
  }

  let appels = 0;
  async function garmin(path: string, params: Record<string, string | number> = {}): Promise<Json> {
    const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
    for (;;) {
      if (Date.now() - debutSynchro > BUDGET_MS) throw new LimiteGarmin('temps');
      appels++;
      const r = await fetch(`${GARMIN}${path}${qs ? '?' + qs : ''}`, { headers: { Accept: 'application/json', Authorization: `Bearer ${token}` } });
      if (r.status === 429) {
        // Limite de Garmin : on patiente si l'attente tient dans le temps restant, sinon on s'arrête là
        const attente = ((await r.json().catch(() => ({}))).retryInSeconds ?? 60) + 2;
        if (Date.now() - debutSynchro + attente * 1000 > BUDGET_MS) throw new LimiteGarmin('limite');
        await new Promise(res => setTimeout(res, attente * 1000));
        continue;
      }
      if (r.status === 404 || r.status === 204) return null;
      if (!r.ok) throw new Error(`Garmin ${path} : HTTP ${r.status}`);
      const texte = await r.text();
      return texte ? JSON.parse(texte) : null;
    }
  }

  const rapport: Json = { jours: 0, courbes: 0, activites: [], partiel: false };
  const maintenant = new Date().toISOString();
  const today = new Date(Date.now() - 4 * 3_600_000); // jour local approximatif (Québec), pour ne pas demander demain
  try {
    // 1) Profil
    const [settings, zones, fitnessAge] = [
      await garmin('/userprofile-service/userprofile/settings'),
      await garmin('/biometric-service/heartRateZones/v2'),
      await garmin(`/fitnessage-service/fitnessage/v2/${iso(today)}`),
    ];
    await sb.from('garmin_profile').upsert({ user_id: user.id, settings, hr_zones: zones, fitness_age: fitnessAge, updated_at: maintenant });

    // 2) Santé au quotidien : depuis le dernier jour en base (moins 2, pour compléter la nuit), 28 jours au plus
    const { data: dernier } = await sb.from('garmin_daily').select('date').order('date', { ascending: false }).limit(1);
    const plancher = addDays(today, -27);
    let debut = dernier?.[0] ? addDays(new Date(dernier[0].date + 'T00:00:00Z'), -2) : plancher;
    if (debut < plancher) debut = plancher;
    const plage = { startDate: iso(debut), endDate: iso(today) };

    const brut: Record<string, Json> = {};
    const ranger = (date: string | undefined, cle: string, valeur: Json) => { if (date) (brut[date] ??= {})[cle] = valeur; };
    ((await garmin('/usersummary-service/v2/dailysummaries', plage))?.data || []).forEach((s: Json) => ranger(s.calendarDate, 'summary', s));
    (await garmin('/sleep-service/sleep/dailySleepSummariesByDate', plage) || []).forEach((s: Json) => ranger(s.calendarDate, 'sleep', s));
    ((await garmin(`/hrv-service/hrv/daily/${plage.startDate}/${plage.endDate}`))?.hrvSummaries || []).forEach((s: Json) => ranger(s.calendarDate, 'hrv', s));
    (await garmin('/wellness-service/wellness/bodyBattery/reports/daily', plage) || []).forEach((s: Json) => ranger(s.date, 'body_battery', s));
    // Stress et pas : 7 jours au plus par appel
    for (let d = new Date(debut); d <= today; d = addDays(d, 7)) {
      const f = addDays(d, 6) < today ? addDays(d, 6) : today;
      (await garmin(`/usersummary-service/stats/stress/daily/${iso(d)}/${iso(f)}`) || []).forEach((s: Json) => ranger(s.calendarDate, 'stress', s));
      (await garmin(`/usersummary-service/stats/steps/daily/${iso(d)}/${iso(f)}`) || []).forEach((s: Json) => ranger(s.calendarDate, 'steps', s));
    }

    const jours = Object.entries(brut).map(([date, r]) => {
      const s = r.summary || {}, sl = r.sleep || {}, hv = r.hrv || {}, st = r.steps || {};
      const hr = s.heartRate || {}, bb = s.bodyBattery || {}, stress = s.stress || {}, mv = s.movement || {};
      const cal = s.calories || {}, im = s.intensityMinutes || {}, base = hv.baseline || {};
      return {
        user_id: user.id, date,
        resting_hr: positif(hr.restingValue), min_hr: positif(hr.minValue), max_hr: positif(hr.maxValue),
        hrv_last_night: hv.lastNightAvg ?? null, hrv_weekly_avg: hv.weeklyAvg ?? null,
        hrv_baseline_low: base.balancedLow ?? null, hrv_baseline_high: base.balancedUpper ?? null, hrv_status: hv.status ?? null,
        sleep_seconds: sl.sleepTimeSeconds ?? null, sleep_deep_seconds: sl.deepSleepSeconds ?? null,
        sleep_light_seconds: sl.lightSleepSeconds ?? null, sleep_rem_seconds: sl.remSleepSeconds ?? null,
        sleep_awake_seconds: sl.awakeSleepSeconds ?? null, sleep_avg_hr: sl.avgHeartRate ?? null,
        sleep_avg_stress: sl.avgSleepStress ?? null, sleep_avg_respiration: sl.averageRespirationValue ?? null,
        body_battery_min: positif(bb.minValue), body_battery_max: positif(bb.maxValue),
        body_battery_charged: positif(bb.chargedValue), body_battery_drained: positif(bb.drainedValue),
        stress_avg: positif(stress.avgLevel), stress_max: positif(stress.maxLevel),
        steps: positif(r.steps ? st.totalSteps : mv.steps), step_goal: st.stepGoal ?? null,
        distance_m: positif(st.totalDistance), floors_ascended: positif(mv.floorsAscended),
        calories_total: entier(positif(cal.burnedTotal)), calories_active: entier(positif(cal.burnedActive)),
        intensity_minutes_moderate: positif(im.moderate), intensity_minutes_vigorous: positif(im.vigorous),
        respiration_avg: positif((s.respiration || {}).avgValue),
        raw: r, updated_at: maintenant,
      };
    });
    if (jours.length) {
      const { error } = await sb.from('garmin_daily').upsert(jours, { onConflict: 'user_id,date' });
      if (error) throw new Error(`garmin_daily : ${error.message}`);
    }
    rapport.jours = jours.length;

    // 3) Activités : pages de 30 jusqu'à retrouver des activités déjà en base (5 pages au plus)
    const garminActs: Json[] = [];
    for (let page = 0; page < 5; page++) {
      const liste = await garmin('/activitylist-service/activities/search/activities', { start: page * 30, limit: 30 }) || [];
      garminActs.push(...liste);
      if (liste.length < 30) break;
      const ids = liste.map((a: Json) => a.activityId);
      const { count } = await sb.from('activities').select('id', { count: 'exact', head: true }).in('garmin_activity_id', ids);
      if (count) break;
    }
    if (garminActs.length) {
      const plusAncien = garminActs.map(a => a.startTimeGMT).sort()[0].replace(' ', 'T') + 'Z';
      const { data: enBase } = await sb.from('activities').select('id, start_time, garmin_activity_id, workout_id')
        .gte('start_time', new Date(new Date(plusAncien).getTime() - 86_400_000).toISOString());
      const parId = new Set((enBase || []).map(a => String(a.garmin_activity_id)));
      const parHeure = new Map((enBase || []).map(a => [new Date(a.start_time).getTime(), a]));
      // 14 jours plus tôt : séance suivie sur la montre mais faite après la date prévue
      const { data: seances } = await sb.from('workouts').select('id, date, type, completed, title')
        .gte('date', iso(addDays(new Date(plusAncien), -14)));
      const prises = new Set((enBase || []).filter(a => a.workout_id).map(a => String(a.workout_id)));
      const { data: prof } = await sb.from('garmin_profile').select('hr_zones').eq('user_id', user.id).maybeSingle();
      const z = (prof?.hr_zones || [])[0] || {};
      const baseZones = z.maxHeartRateUsed ? { type: 'max', hr: z.maxHeartRateUsed } : null;
      const vues = new Set<number>();

      for (const a of garminActs.sort((x, y) => x.startTimeGMT.localeCompare(y.startTimeGMT))) {
        const debutAct = new Date(a.startTimeGMT.replace(' ', 'T') + 'Z');
        if (parId.has(String(a.activityId)) || vues.has(debutAct.getTime())) continue;
        vues.add(debutAct.getTime());
        const detail = await garmin(`/activity-service/activity/${a.activityId}`);
        const dateLocale = a.startTimeLocal.slice(0, 10);
        const garminCols = {
          garmin_activity_id: a.activityId, name: a.activityName, garmin_type: a.activityType.typeKey,
          garmin_summary: a, garmin_detail: detail,
        };
        const types = typesApp(a.activityType.typeKey);
        const label = `${SPORT_LABELS[types[0]] || types[0]} du ${new Date(dateLocale + 'T12:00:00Z').toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' })}`;

        const deja = parHeure.get(debutAct.getTime());
        if (deja) {
          // Déjà importée depuis la montre : infos Garmin ajoutées, courbes et séance liée intactes
          await sb.from('activities').update(garminCols).eq('id', deja.id);
          rapport.activites.push({ label, issue: 'déjà importée, complétée' });
          continue;
        }

        const tiz = [1, 2, 3, 4, 5].map(i => entier(a[`hrTimeInZone_${i}`]) || 0);
        const avecZones = tiz.some(Boolean);
        const timer = entier(a.duration);
        const charge = avecZones ? Math.round(tiz.reduce((s, sec, i) => s + sec / 60 * (i + 1), 0)) : null;
        const cadence = a.averageBikingCadenceInRevPerMinute ||
          (a.averageRunningCadenceInStepsPerMinute ? a.averageRunningCadenceInStepsPerMinute / 2 : null);

        // Même rattachement que l'import FIT (findPlannedWorkout de l'app) : séance suivie sur la montre, retrouvée
        // par son titre à 14 jours au plus ; sinon séance libre du jour et du sport (non réalisée d'abord) ;
        // sinon séance « libre » réalisée ajoutée au calendrier
        const libres = (seances || []).filter(w => types.includes(w.type) && !prises.has(String(w.id)));
        const suivie = seanceSuivie(a.activityName);
        const ecart = (w: Json) => Math.abs(Date.parse(w.date) - Date.parse(dateLocale)) / 86_400_000;
        const seance = (suivie && libres
          .filter(w => ecart(w) <= 14 && (suivie.tronque ? cleTitre(w.title).startsWith(suivie.cle) : cleTitre(w.title) === suivie.cle))
          .sort((p, q) => ecart(p) - ecart(q) || Number(p.completed) - Number(q.completed))[0])
          || libres.filter(w => w.date === dateLocale)
            .sort((p, q) => Number(p.completed) - Number(q.completed) || types.indexOf(p.type) - types.indexOf(q.type))[0];
        let workoutId: string | null = null;
        let issue: string;
        if (seance) {
          workoutId = String(seance.id);
          if (!seance.completed) await sb.from('workouts').update({ completed: true }).eq('id', seance.id);
          issue = 'séance prévue cochée';
        } else {
          const km = a.distance > 0 ? ` ${(a.distance / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} km` : '';
          const { data: creee } = await sb.from('workouts').insert([{
            title: `${SPORT_LABELS[types[0]] || types[0]} libre${km}`, date: dateLocale, type: types[0],
            warmup: '', main_block: a.activityName || '', cooldown: '', completed: true, user_id: user.id,
          }]).select();
          workoutId = creee?.[0] ? String(creee[0].id) : null;
          issue = workoutId ? 'ajoutée au calendrier (non prévue)' : "enregistrée, mais l'ajout au calendrier a échoué";
        }
        if (workoutId) prises.add(workoutId);

        const { error } = await sb.from('activities').insert([{
          user_id: user.id, workout_id: workoutId, ...garminCols,
          sport: types[0], fit_sport: SPORT_FIT[types[0]] ?? null, fit_sub_sport: null,
          start_time: debutAct.toISOString(), start_date_local: dateLocale,
          elapsed_time: entier(a.elapsedDuration), timer_time: timer, distance: a.distance || null,
          total_ascent: a.elevationGain ?? null, avg_heart_rate: entier(a.averageHR), max_heart_rate: entier(a.maxHR),
          avg_speed: a.averageSpeed ?? null, max_speed: a.maxSpeed ?? null, avg_cadence: entier(cadence),
          avg_power: entier(a.avgPower), calories: entier(a.calories),
          training_effect: a.aerobicTrainingEffect ?? null, anaerobic_effect: a.anaerobicTrainingEffect ?? null,
          time_in_zones: avecZones ? tiz : null, zone_basis: avecZones ? baseZones : null,
          // Sans FC : même estimation que l'app (2 points par minute)
          load: charge ?? Math.round((timer || 0) / 60 * 2), load_estimated: charge === null,
        }]);
        rapport.activites.push({ label, issue: error ? `erreur d'enregistrement (${error.message})` : issue });
      }
    }

    // 4) Détail intra-journée d'hier et d'aujourd'hui (sommeil, VFC, FC, SpO2)
    const courbes = [];
    for (const d of [iso(addDays(today, -1)), iso(today)]) {
      const sources: [string, string, Record<string, string>?][] = [
        ['sleep', '/sleep-service/sleep/dailySleep', { date: d }],
        ['hrv', `/hrv-service/hrv/${d}`],
        ['heart_rate', '/wellness-service/wellness/dailyHeartRate', { date: d }],
        ['spo2', `/wellness-service/wellness/daily/spo2acclimation/${d}`],
      ];
      for (const [kind, path, params] of sources) {
        const data = await garmin(path, params);
        if (data !== null) courbes.push({ user_id: user.id, date: d, kind, data, updated_at: maintenant });
      }
    }
    if (courbes.length) await sb.from('garmin_daily_detail').upsert(courbes, { onConflict: 'user_id,date,kind' });
    rapport.courbes = courbes.length;
  } catch (e) {
    if (!(e instanceof LimiteGarmin)) {
      rapport.erreur = (e as Error).message;
    }
    rapport.partiel = true;
  }

  rapport.appels = appels;
  await sb.from('garmin_credentials').update({ last_sync_at: new Date().toISOString(), last_sync_report: rapport }).eq('user_id', user.id);
  return json(rapport);
});
