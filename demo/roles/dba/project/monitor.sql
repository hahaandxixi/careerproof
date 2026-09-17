SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
SELECT datname, numbackends FROM pg_stat_database;
