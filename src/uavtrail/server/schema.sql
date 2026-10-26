-- The traceability server's record. The trail is append-only: rows are inserted once per (unit, seq) and a trigger
-- refuses any update or delete. Everything else (units, steps, claims) is derived from it or is a claim registry.

create table if not exists stations (
  station text primary key,
  public_key text not null,
  registered_at timestamptz not null default now()
);

create table if not exists trail (
  unit text not null,
  seq integer not null,
  hash text not null unique,
  prev text not null,
  station text not null references stations,
  kind text not null,
  at timestamptz not null,
  data jsonb not null,
  sig text not null,
  raw text not null,                 -- the event exactly as the station signed it, for re-verification
  received_at timestamptz not null default now(),
  primary key (unit, seq)
);
create index if not exists trail_kind_at on trail (kind, at);

create or replace function trail_append_only() returns trigger language plpgsql as $$
begin
  raise exception 'the trail is append-only: % on (%, %) refused', tg_op, old.unit, old.seq;
end $$;
drop trigger if exists trail_no_change on trail;
create trigger trail_no_change before update or delete on trail for each row execute function trail_append_only();

create table if not exists claims (
  kind text not null,
  value text not null,
  unit text not null,
  at timestamptz not null default now(),
  primary key (kind, value)
);

-- one row per airframe, kept current by ingest
create table if not exists units (
  unit text primary key,
  status text not null,              -- in_progress | released | held
  release text,
  station text,
  slot text,
  step text,
  hold_code text,
  hold_owner text,
  runs integer not null default 0,
  hold_seconds double precision not null default 0,
  first_pass boolean,
  operator text,
  dims jsonb not null default '{}',  -- what the unit is made of: board revisions, lots, module SKU and batch
  started_at timestamptz,
  updated_at timestamptz,
  certificate jsonb
);

-- one row per step attempt, with the dimensions the analysis groups by
create table if not exists attempts (
  unit text not null,
  seq integer not null,
  run integer not null,
  step text not null,
  attempt integer not null,
  ok boolean not null,
  code text,
  seconds double precision not null,
  at timestamptz not null,
  station text not null,
  fixture text not null,
  slot text not null,
  release text,
  operator text,
  dims jsonb not null default '{}',
  evidence jsonb not null default '{}',
  primary key (unit, seq)
);
create index if not exists attempts_at on attempts (at);

create table if not exists recoveries (
  unit text not null,
  seq integer not null,
  step text not null,
  code text not null,
  action text not null,
  seconds double precision not null,
  at timestamptz not null,
  slot text not null,
  primary key (unit, seq)
);

create table if not exists issue_actions (
  id bigserial primary key,
  issue text not null,
  action text not null,               -- acknowledge | fixed | not_a_problem | note
  owner text,
  note text not null,
  actor text not null,
  effective_at timestamptz not null,
  at timestamptz not null default now()
);
