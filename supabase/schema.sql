-- ねこごはんファクト：体重記録のクラウド保存スキーマ
-- Supabase ダッシュボード > SQL Editor に貼り付けて Run してください。
-- 認証ユーザーごとに「自分の行だけ」読み書きできるよう Row Level Security を有効化します。

create extension if not exists "pgcrypto";

-- 猫プロフィール
create table if not exists public.cats (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name       text not null,
  target     numeric,                       -- 目標体重(kg)・任意
  created_at timestamptz not null default now()
);

-- 体重の記録（1日1件）
create table if not exists public.weight_entries (
  id         uuid primary key default gen_random_uuid(),
  cat_id     uuid not null references public.cats(id) on delete cascade,
  user_id    uuid not null default auth.uid() references auth.users(id) on delete cascade,
  entry_date date not null,
  kg         numeric not null check (kg > 0),
  created_at timestamptz not null default now(),
  unique (cat_id, entry_date)              -- 同じ日は上書き
);

create index if not exists idx_cats_user on public.cats(user_id);
create index if not exists idx_entries_cat on public.weight_entries(cat_id, entry_date);

-- ===== Row Level Security（自分のデータだけ） =====
alter table public.cats           enable row level security;
alter table public.weight_entries enable row level security;

drop policy if exists cats_own on public.cats;
create policy cats_own on public.cats
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists entries_own on public.weight_entries;
create policy entries_own on public.weight_entries
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
