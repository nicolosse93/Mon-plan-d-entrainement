-- Données Garmin Connect (Personal API) : à coller une fois dans le SQL Editor de Supabase
-- (relançable sans risque). Remplies par outils/garmin-supabase.py. Chacun ne voit que ses propres données.

-- Activités : colonnes Garmin ajoutées à la table des activités (sql/activities.sql doit avoir été exécuté)
alter table activities add column if not exists garmin_activity_id bigint;
alter table activities add column if not exists name text;                    -- nom de l'activité dans Garmin Connect
alter table activities add column if not exists garmin_type text;             -- type Garmin (running, cycling, skate_skiing_ws…)
alter table activities add column if not exists garmin_summary jsonb;         -- résumé complet renvoyé par Garmin
alter table activities add column if not exists garmin_detail jsonb;          -- fiche détaillée (summaryDTO, lieu…)
create unique index if not exists activities_garmin_id on activities (user_id, garmin_activity_id);

-- Profil : réglages, zones de FC, âge physique (une ligne par utilisateur)
create table if not exists garmin_profile (
  user_id uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  settings jsonb,
  hr_zones jsonb,
  fitness_age jsonb,
  updated_at timestamptz not null default now()
);

-- Santé au quotidien : une ligne par jour, colonnes utiles + données brutes Garmin
create table if not exists garmin_daily (
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  date date not null,
  resting_hr smallint,
  min_hr smallint,
  max_hr smallint,
  hrv_last_night smallint,         -- ms
  hrv_weekly_avg smallint,
  hrv_baseline_low smallint,
  hrv_baseline_high smallint,
  hrv_status text,                 -- BALANCED, UNBALANCED, LOW, POOR
  sleep_seconds integer,
  sleep_deep_seconds integer,
  sleep_light_seconds integer,
  sleep_rem_seconds integer,
  sleep_awake_seconds integer,
  sleep_avg_hr real,
  sleep_avg_stress real,
  sleep_avg_respiration real,
  body_battery_min smallint,
  body_battery_max smallint,
  body_battery_charged smallint,
  body_battery_drained smallint,
  stress_avg smallint,
  stress_max smallint,
  steps integer,
  step_goal integer,
  distance_m real,
  floors_ascended real,
  calories_total integer,
  calories_active integer,
  intensity_minutes_moderate smallint,
  intensity_minutes_vigorous smallint,
  respiration_avg real,
  raw jsonb,                       -- {summary, sleep, hrv, body_battery, stress, steps} tels que renvoyés par Garmin
  updated_at timestamptz not null default now(),
  primary key (user_id, date)
);

-- Détail intra-journée : courbes du sommeil, de la VFC, de la FC et de la SpO2
create table if not exists garmin_daily_detail (
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  date date not null,
  kind text not null,              -- sleep, hrv, heart_rate, spo2
  data jsonb,
  updated_at timestamptz not null default now(),
  primary key (user_id, date, kind)
);

-- Clé Personal API de Garmin Connect (saisie dans l'app) et jeton d'accès en cache (24 h), lus par la fonction
-- garmin-sync (bouton « Mettre à jour » de la page Mes données Garmin)
create table if not exists garmin_credentials (
  user_id uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  api_key text,
  access_token text,
  token_expires_at timestamptz,
  last_sync_at timestamptz,
  last_sync_report jsonb
);

alter table garmin_credentials enable row level security;
drop policy if exists "Users manage own garmin credentials" on garmin_credentials;
create policy "Users manage own garmin credentials" on garmin_credentials
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

alter table garmin_profile enable row level security;
alter table garmin_daily enable row level security;
alter table garmin_daily_detail enable row level security;

drop policy if exists "Users manage own garmin profile" on garmin_profile;
create policy "Users manage own garmin profile" on garmin_profile
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "Users manage own garmin daily" on garmin_daily;
create policy "Users manage own garmin daily" on garmin_daily
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "Users manage own garmin detail" on garmin_daily_detail;
create policy "Users manage own garmin detail" on garmin_daily_detail
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
