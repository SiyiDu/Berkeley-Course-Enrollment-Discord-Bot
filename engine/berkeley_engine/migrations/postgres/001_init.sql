CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  discord_id TEXT UNIQUE NOT NULL,
  name TEXT,
  role TEXT
);
CREATE TABLE IF NOT EXISTS professors (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  dept_optional TEXT
);
CREATE TABLE IF NOT EXISTS courses (
  id SERIAL PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  title_optional TEXT
);
CREATE TABLE IF NOT EXISTS course_offerings (
  id SERIAL PRIMARY KEY,
  course_id INTEGER NOT NULL,
  term TEXT NOT NULL,
  section_optional TEXT,
  professor_id_optional INTEGER,
  UNIQUE(course_id, term, section_optional)
);
CREATE TABLE IF NOT EXISTS channel_map (
  id SERIAL PRIMARY KEY,
  guild_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  course_offering_id INTEGER NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE(guild_id, channel_id)
);
CREATE TABLE IF NOT EXISTS messages (
  message_id TEXT PRIMARY KEY,
  guild_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  author_id TEXT NOT NULL,
  content TEXT NOT NULL,
  ts TEXT NOT NULL,
  raw_json_optional TEXT
);
CREATE TABLE IF NOT EXISTS cards (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  course_offering_id INTEGER,
  subject_type TEXT,
  subject_id TEXT,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  tags_json TEXT,
  status TEXT NOT NULL,
  confidence DOUBLE PRECISION,
  evidence_json TEXT,
  linked_card_ids_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  approved_by TEXT
);
CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  course_offering_id INTEGER,
  subject_type TEXT,
  subject_id TEXT,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  tags_json TEXT,
  status TEXT NOT NULL,
  confidence DOUBLE PRECISION,
  evidence_json TEXT,
  linked_card_ids_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  created_by TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
  id SERIAL PRIMARY KEY,
  kind TEXT NOT NULL,
  payload_json TEXT,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  run_at TEXT NOT NULL,
  last_error TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id SERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL
);
