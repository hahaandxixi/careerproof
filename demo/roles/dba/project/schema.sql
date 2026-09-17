CREATE TABLE tasks (id bigint PRIMARY KEY, owner_id bigint NOT NULL, state text NOT NULL);
CREATE INDEX tasks_owner_state ON tasks(owner_id, state);
EXPLAIN SELECT id FROM tasks WHERE owner_id = 7 AND state = 'open';
