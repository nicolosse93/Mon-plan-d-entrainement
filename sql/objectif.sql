-- Objectif de course du profil (Mon profil › Objectif de course) : date, distance en km, allure visée (« 4:55 /km »).
-- Le générateur s'en sert pour le bloc spécifique, l'affûtage et la séance du jour J. Relançable.
alter table user_profiles add column if not exists race_date date;
alter table user_profiles add column if not exists race_distance numeric;
alter table user_profiles add column if not exists race_pace text;
