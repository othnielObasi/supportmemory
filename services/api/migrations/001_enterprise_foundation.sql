-- Continuum enterprise foundation migration.
-- The runtime uses a JSONB logical collection table for portability while
-- keeping tenant-aware indexes for enterprise separation and search.

CREATE TABLE IF NOT EXISTS trace_memory_records (
  collection TEXT NOT NULL,
  id TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (collection, id)
);

CREATE INDEX IF NOT EXISTS idx_tm_records_collection_created ON trace_memory_records (collection, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tm_records_data_gin ON trace_memory_records USING GIN (data);
CREATE INDEX IF NOT EXISTS idx_tm_records_org ON trace_memory_records (collection, (data->>'organisation_id'));
CREATE INDEX IF NOT EXISTS idx_tm_records_workspace ON trace_memory_records (collection, (data->>'workspace_id'));
CREATE INDEX IF NOT EXISTS idx_tm_records_project ON trace_memory_records (collection, (data->>'project_id'));
CREATE INDEX IF NOT EXISTS idx_tm_records_environment ON trace_memory_records (collection, (data->>'environment_id'));
CREATE INDEX IF NOT EXISTS idx_tm_records_task_id ON trace_memory_records (collection, (data->>'task_id'));
CREATE INDEX IF NOT EXISTS idx_tm_records_trace_id ON trace_memory_records (collection, (data->>'trace_id'));
CREATE INDEX IF NOT EXISTS idx_tm_records_checkpoint_id ON trace_memory_records (collection, (data->>'checkpoint_id'));
CREATE INDEX IF NOT EXISTS idx_tm_records_status ON trace_memory_records (collection, (data->>'status'));
CREATE INDEX IF NOT EXISTS idx_tm_records_idempotency ON trace_memory_records (collection, (data->>'idempotency_key'));
CREATE UNIQUE INDEX IF NOT EXISTS uq_tm_api_key_hash ON trace_memory_records ((data->>'key_hash')) WHERE collection = 'api_keys' AND data ? 'key_hash';
CREATE UNIQUE INDEX IF NOT EXISTS uq_tm_action_idempotency ON trace_memory_records ((data->>'workspace_id'), (data->>'idempotency_key')) WHERE collection = 'action_executions' AND data ? 'idempotency_key';
CREATE UNIQUE INDEX IF NOT EXISTS uq_tm_idempotency_keys ON trace_memory_records ((data->>'workspace_id'), (data->>'key')) WHERE collection = 'idempotency_keys' AND data ? 'key';
