-- ================================================
-- DeepCast AI — Supabase Schema
-- ================================================

create extension if not exists "uuid-ossp";

-- ================================================
-- 1. profiles
-- ================================================
create table public.profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  display_name  text,
  avatar_url    text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "自分のプロフィールを閲覧"
  on public.profiles for select using (auth.uid() = id);

create policy "自分のプロフィールを更新"
  on public.profiles for update using (auth.uid() = id);

create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, display_name, avatar_url)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'name', 'リスナー'),
    new.raw_user_meta_data ->> 'avatar_url'
  );
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ================================================
-- 2. podcasts
-- ================================================
create table public.podcasts (
  id            uuid primary key default uuid_generate_v4(),
  title         text not null,
  description   text,
  feed_url      text not null unique,
  artwork_url   text,
  author        text,
  website_url   text,
  last_synced   timestamptz,
  created_at    timestamptz not null default now()
);

alter table public.podcasts enable row level security;

create policy "全員閲覧可"
  on public.podcasts for select using (true);

-- ================================================
-- 3. subscriptions
-- ================================================
create table public.subscriptions (
  id            uuid primary key default uuid_generate_v4(),
  user_id       uuid not null references public.profiles(id) on delete cascade,
  podcast_id    uuid not null references public.podcasts(id) on delete cascade,
  created_at    timestamptz not null default now(),
  unique (user_id, podcast_id)
);

alter table public.subscriptions enable row level security;

create policy "自分の購読を閲覧"
  on public.subscriptions for select using (auth.uid() = user_id);

create policy "自分の購読を追加"
  on public.subscriptions for insert with check (auth.uid() = user_id);

create policy "自分の購読を解除"
  on public.subscriptions for delete using (auth.uid() = user_id);

-- ================================================
-- 4. episodes
-- ================================================
create table public.episodes (
  id            uuid primary key default uuid_generate_v4(),
  podcast_id    uuid not null references public.podcasts(id) on delete cascade,
  guid          text not null,
  title         text not null,
  description   text,
  audio_url     text not null,
  duration      integer,
  published_at  timestamptz,
  image_url     text,
  created_at    timestamptz not null default now(),
  unique (podcast_id, guid)
);

create index idx_episodes_podcast_published
  on public.episodes (podcast_id, published_at desc);

alter table public.episodes enable row level security;

create policy "全員閲覧可"
  on public.episodes for select using (true);

-- ================================================
-- 5. transcripts (Whisper v3)
-- ================================================
create table public.transcripts (
  id            uuid primary key default uuid_generate_v4(),
  episode_id    uuid not null references public.episodes(id) on delete cascade unique,
  full_text     text not null,
  segments      jsonb not null default '[]',
  language      text default 'ja',
  model         text default 'whisper-v3',
  created_at    timestamptz not null default now()
);

alter table public.transcripts enable row level security;

create policy "全員閲覧可"
  on public.transcripts for select using (true);

-- ================================================
-- 6. summaries (GPT-4o)
-- ================================================
create table public.summaries (
  id            uuid primary key default uuid_generate_v4(),
  episode_id    uuid not null references public.episodes(id) on delete cascade unique,
  summary       text not null,
  chapters      jsonb not null default '[]',
  key_points    jsonb not null default '[]',
  model         text default 'gpt-4o',
  created_at    timestamptz not null default now()
);

alter table public.summaries enable row level security;

create policy "全員閲覧可"
  on public.summaries for select using (true);

-- ================================================
-- 7. playback_states
-- ================================================
create table public.playback_states (
  id            uuid primary key default uuid_generate_v4(),
  user_id       uuid not null references public.profiles(id) on delete cascade,
  episode_id    uuid not null references public.episodes(id) on delete cascade,
  position      integer not null default 0,
  playback_rate real not null default 1.0,
  completed     boolean not null default false,
  updated_at    timestamptz not null default now(),
  unique (user_id, episode_id)
);

alter table public.playback_states enable row level security;

create policy "自分の再生状態を管理"
  on public.playback_states for all using (auth.uid() = user_id);

-- ================================================
-- 8. clips (Knowledge Clipping)
-- ================================================
create table public.clips (
  id            uuid primary key default uuid_generate_v4(),
  user_id       uuid not null references public.profiles(id) on delete cascade,
  episode_id    uuid not null references public.episodes(id) on delete cascade,
  start_sec     integer not null,
  end_sec       integer not null,
  transcript    text,
  memo          text,
  created_at    timestamptz not null default now(),
  constraint valid_range check (end_sec > start_sec)
);

create index idx_clips_user on public.clips (user_id, created_at desc);

alter table public.clips enable row level security;

create policy "自分のクリップを管理"
  on public.clips for all using (auth.uid() = user_id);

-- ================================================
-- updated_at trigger
-- ================================================
create or replace function public.update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger set_updated_at
  before update on public.profiles
  for each row execute function public.update_updated_at();

create trigger set_updated_at
  before update on public.playback_states
  for each row execute function public.update_updated_at();
