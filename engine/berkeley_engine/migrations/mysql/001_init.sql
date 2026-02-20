CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  discord_id VARCHAR(64) UNIQUE NOT NULL,
  name TEXT,
  role TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS professors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name TEXT NOT NULL,
  dept_optional TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS courses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(32) NOT NULL UNIQUE,
  title_optional TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS course_offerings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  course_id INT NOT NULL,
  term VARCHAR(32) NOT NULL,
  section_optional VARCHAR(16),
  professor_id_optional INT,
  UNIQUE KEY uniq_course_term_section (course_id, term, section_optional)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS channel_map (
  id INT AUTO_INCREMENT PRIMARY KEY,
  guild_id VARCHAR(64) NOT NULL,
  channel_id VARCHAR(64) NOT NULL,
  course_offering_id INT NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uniq_channel (guild_id, channel_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS messages (
  message_id VARCHAR(64) PRIMARY KEY,
  guild_id VARCHAR(64) NOT NULL,
  channel_id VARCHAR(64) NOT NULL,
  author_id VARCHAR(64) NOT NULL,
  content TEXT NOT NULL,
  ts TEXT NOT NULL,
  raw_json_optional TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS cards (
  id VARCHAR(64) PRIMARY KEY,
  type VARCHAR(32) NOT NULL,
  course_offering_id INT,
  subject_type VARCHAR(32),
  subject_id VARCHAR(64),
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  tags_json TEXT,
  status VARCHAR(32) NOT NULL,
  confidence DOUBLE,
  evidence_json TEXT,
  linked_card_ids_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  approved_by TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS proposals (
  id VARCHAR(64) PRIMARY KEY,
  type VARCHAR(32) NOT NULL,
  course_offering_id INT,
  subject_type VARCHAR(32),
  subject_id VARCHAR(64),
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  tags_json TEXT,
  status VARCHAR(32) NOT NULL,
  confidence DOUBLE,
  evidence_json TEXT,
  linked_card_ids_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  created_by TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS jobs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  kind VARCHAR(64) NOT NULL,
  payload_json TEXT,
  status VARCHAR(32) NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  run_at TEXT NOT NULL,
  last_error TEXT,
  created_at TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS audit_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  event_type VARCHAR(64) NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
