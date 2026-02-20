CREATE TABLE IF NOT EXISTS bot_users (
  user_id TEXT PRIMARY KEY,
  student_id TEXT NOT NULL,
  email TEXT NOT NULL,
  name TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bot_enrollments (
  user_id TEXT NOT NULL,
  slug TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, slug)
);
CREATE TABLE IF NOT EXISTS bot_course_index (
  slug TEXT PRIMARY KEY,
  container_id TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
