CREATE TABLE IF NOT EXISTS clients (
  client_id VARCHAR(64) PRIMARY KEY,
  client_token TEXT NOT NULL,
  name TEXT,
  allowed_platforms_json TEXT,
  allowed_workspaces_json TEXT,
  revoked TINYINT(1) NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
