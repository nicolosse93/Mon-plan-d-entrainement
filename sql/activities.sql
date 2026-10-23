-- Activités importées depuis les fichiers .FIT de la montre : à coller une fois dans le SQL Editor de Supabase
-- (relançable sans risque). Chacun ne voit et ne modifie que ses propres activités.

create table if not exists activities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  workout_id text,                 -- séance du calendrier rattachée (texte : compatible uuid ou nombre)
  sport text,                      -- type de séance de l'app (Course, Vélo…), null si sport non géré
  fit_sport integer,
  fit_sub_sport integer,
  start_time timestamptz not null,
  start_date_local date not null,
  elapsed_time integer,            -- secondes
  timer_time integer,              -- secondes en mouvement (chrono)
  distance real,                   -- mètres
  total_ascent real,               -- mètres
  avg_heart_rate smallint,
  max_heart_rate smallint,
  avg_speed real,                  -- m/s
  avg_power smallint,              -- watts
  laps jsonb,                      -- tours : durée, distance, vitesse, FC, puissance
  created_at timestamptz not null default now(),
  unique (user_id, start_time)     -- un même fichier importé deux fois n'est enregistré qu'une fois
);
create index if not exists activities_workout on activities (workout_id);

-- Données détaillées (ajoutées ensuite : relancer ce fichier les crée si la table existait déjà)
alter table activities add column if not exists max_speed real;               -- m/s
alter table activities add column if not exists avg_cadence smallint;
alter table activities add column if not exists calories smallint;
alter table activities add column if not exists training_effect real;         -- Training Effect aérobie Garmin (0-5)
alter table activities add column if not exists anaerobic_effect real;        -- Training Effect anaérobie (0-5)
alter table activities add column if not exists time_in_zones jsonb;          -- secondes dans les zones de FC 1 à 5
alter table activities add column if not exists zone_basis jsonb;             -- base des zones : {type: threshold|max, hr}
alter table activities add column if not exists load real;                    -- charge (TRIMP d'Edwards)
alter table activities add column if not exists load_estimated boolean not null default false;
alter table activities add column if not exists streams jsonb;                -- courbes réduites : t, hr, speed, pwr, alt, cad
alter table activities add column if not exists track jsonb;                  -- tracé GPS simplifié [[lat, lon], …]

alter table activities enable row level security;

drop policy if exists "Users can view own activities" on activities;
create policy "Users can view own activities" on activities
  for select using (auth.uid() = user_id);

drop policy if exists "Users can insert own activities" on activities;
create policy "Users can insert own activities" on activities
  for insert with check (auth.uid() = user_id);

drop policy if exists "Users can update own activities" on activities;
create policy "Users can update own activities" on activities
  for update using (auth.uid() = user_id);

drop policy if exists "Users can delete own activities" on activities;
create policy "Users can delete own activities" on activities
  for delete using (auth.uid() = user_id);
