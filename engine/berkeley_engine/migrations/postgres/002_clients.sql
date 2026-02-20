CREATE TABLE IF NOT EXISTS clients (
  client_id TEXT PRIMARY KEY,
  client_token TEXT NOT NULL,
  name TEXT,
  allowed_platforms_json TEXT,
  allowed_workspaces_json TEXT,
  revoked BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
