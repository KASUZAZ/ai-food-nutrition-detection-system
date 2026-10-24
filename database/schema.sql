-- Vercel Marketplace Postgres (Neon). Image contents live in private Vercel Blob.
CREATE TABLE IF NOT EXISTS nt_credentials (
  id integer PRIMARY KEY CHECK (id=1), salt text NOT NULL, password_hash text NOT NULL
);
CREATE TABLE IF NOT EXISTS nt_foods (
  id serial PRIMARY KEY, food text NOT NULL CHECK(length(food) BETWEEN 1 AND 100),
  calorie_per_gram double precision NOT NULL CHECK(calorie_per_gram BETWEEN 0 AND 100),
  note text NOT NULL DEFAULT '' CHECK(length(note)<=500)
);
CREATE UNIQUE INDEX IF NOT EXISTS nt_foods_name ON nt_foods(lower(food));
CREATE TABLE IF NOT EXISTS nt_meals (
  id serial PRIMARY KEY, food text NOT NULL CHECK(length(food) BETWEEN 1 AND 100),
  weight_g double precision NOT NULL CHECK(weight_g>0 AND weight_g<=100000),
  calories double precision NOT NULL CHECK(calories BETWEEN 0 AND 1000000),
  eaten_at timestamptz NOT NULL, image_url text,
  source text NOT NULL CHECK(source IN ('manual','sensor')), event_key text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS nt_meals_date ON nt_meals(eaten_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS nt_sessions (
  token_hash text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS nt_attempts (
  id text PRIMARY KEY, attempts integer NOT NULL DEFAULT 1, started_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS nt_live (
  id integer PRIMARY KEY CHECK(id=1), payload jsonb NOT NULL,
  latest_image text, received_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS nt_commands (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  action text NOT NULL CHECK(action IN ('tare','capture')),
  status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','leased','succeeded','failed','expired')),
  message text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now(),
  leased_at timestamptz, completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS nt_commands_pending ON nt_commands(created_at) WHERE status IN ('pending','leased');
