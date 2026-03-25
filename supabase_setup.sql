create table sw_users (
  id uuid default gen_random_uuid() primary key,
  phone text unique not null,
  name text default 'Friend',
  streak integer default 0,
  wins_today integer default 0,
  wins_total integer default 0,
  current_task text default '',
  last_win_date text default '',
  context text default '',
  created_at timestamp default now()
);
