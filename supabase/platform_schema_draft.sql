-- =====================================================================
-- 共有「うちの子」プロフィール基盤 — スキーマ叩き台（DRAFT・未適用）
-- ER / フード / 健康管理(Daily Lens) の3サービスが裏で共有する土台。
--
-- ⚠️ これはまだ本番に流していません。順序は「Pet-ER公開 → 基盤 → Daily Lens」。
--    今 live なのは旧 cats / weight_entries（体重記録MVP）。本ファイルはその発展形。
--
-- 設計原則:
--  * 基盤に置くのは「2サービス以上が共有するもの」だけ（病院マスタ=ER内, 成分DB=フード内, 動画=健康管理内 はここに置かない）
--  * health_events 1本に時系列を集約（体重・観察・通院・フード変更…）。payload(jsonb)で型ごとに拡張
--  * かかりつけ医 = Pet-ER 病院マスタの ID を緩く参照（別システムなのでSQLのFKにはしない）
--  * RLS で「自分のデータだけ」。anon公開キー前提
-- =====================================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------
-- profiles : 飼い主単位の共有情報（auth.users と 1:1）
-- ---------------------------------------------------------------------
create table if not exists public.profiles (
  id                    uuid primary key references auth.users(id) on delete cascade,  -- = auth.uid()
  display_name          text,
  postal_code           text,          -- 場所は最小限（病院検索はこれで十分。フル住所は保存しない方針）
  primary_hospital_id   text,          -- かかりつけ医 = Pet-ER 病院マスタのID（緩い参照・別DB）
  primary_hospital_name text,          -- 表示/フォールバック用にキャッシュ
  primary_hospital_tel  text,          -- 同上（受診導線で即使える）
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- pets : うちの子（旧 cats を一般化。犬猫対応）
-- ---------------------------------------------------------------------
create table if not exists public.pets (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name            text not null,
  species         text not null default 'cat' check (species in ('cat','dog')),
  birth_date      date,                 -- 年齢は誕生日から算出（固定の age は持たない）
  breed           text,
  sex             text check (sex in ('male','female','unknown')),
  conditions      text,                 -- 持病・アレルギー等の自由記述
  vet_hospital_id text,                 -- 任意: この子だけ別のかかりつけ（無ければ profiles を使う）
  target_weight   numeric,              -- 目標体重(kg)・任意（旧 cats.target）
  photo_url       text,                 -- アイコン/ベストショット（任意）
  created_at      timestamptz not null default now()
);
create index if not exists idx_pets_user on public.pets(user_id);

-- ---------------------------------------------------------------------
-- health_events : 健康タイムライン（3サービスが共通フォーマットで書き込む堀）
--   event_type 例:
--     'weight'      payload = {"kg": 4.2}
--     'observation' payload = {"note":"左目が細い","video_url":"...","ai_summary":"...","appetite":"ok"}  ← Daily Lens
--     'vet_visit'   payload = {"hospital_id":"...","reason":"...","memo":"..."}                          ← Pet-ER 連携
--     'food_change' payload = {"product":"...","maker":"...","reason":"weight"}                          ← フード連携
--     'note'        payload = {"text":"..."}
-- ---------------------------------------------------------------------
create table if not exists public.health_events (
  id          uuid primary key default gen_random_uuid(),
  pet_id      uuid not null references public.pets(id) on delete cascade,
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  event_type  text not null,
  event_date  date not null default current_date,
  payload     jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);
create index if not exists idx_events_pet_date on public.health_events(pet_id, event_date);
create index if not exists idx_events_type on public.health_events(pet_id, event_type, event_date);
-- 体重は 1日1件（上書き）。他のtypeは1日複数可なので部分ユニークにする
create unique index if not exists uq_weight_per_day
  on public.health_events(pet_id, event_date) where (event_type = 'weight');

-- ---------------------------------------------------------------------
-- Row Level Security : 自分の行だけ
-- ---------------------------------------------------------------------
alter table public.profiles      enable row level security;
alter table public.pets          enable row level security;
alter table public.health_events enable row level security;

drop policy if exists profiles_own on public.profiles;
create policy profiles_own on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists pets_own on public.pets;
create policy pets_own on public.pets
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists events_own on public.health_events;
create policy events_own on public.health_events
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------
-- サインアップ時に profiles を自動生成（任意・入れておくと楽）
-- ---------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id) values (new.id) on conflict do nothing;
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- =====================================================================
-- 旧テーブルからの移行スケッチ（参考・実行は将来）
--   cats          -> pets         （target -> target_weight, species='cat'）
--   weight_entries-> health_events（event_type='weight', payload={'kg':kg}, event_date=entry_date）
--
--   insert into public.pets (id,user_id,name,species,target_weight,created_at)
--     select id,user_id,name,'cat',target,created_at from public.cats;
--   insert into public.health_events (pet_id,user_id,event_type,event_date,payload,created_at)
--     select cat_id,user_id,'weight',entry_date,jsonb_build_object('kg',kg),created_at
--     from public.weight_entries;
-- =====================================================================
