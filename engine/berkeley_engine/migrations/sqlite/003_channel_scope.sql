ALTER TABLE channel_map ADD COLUMN IF NOT EXISTS scope_type TEXT;
ALTER TABLE channel_map ADD COLUMN IF NOT EXISTS scope_id TEXT;
ALTER TABLE channel_map ADD COLUMN IF NOT EXISTS professor_id_optional INTEGER;
