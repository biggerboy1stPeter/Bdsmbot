-- ============================================================
-- KinkBot Database Schema (PostgreSQL)
-- Run this file against your database:
--   psql -U username -d kinkbot -f schema.sql
-- ============================================================

-- Profiles: stores user BDSM profiles (role and bio)
CREATE TABLE IF NOT EXISTS profiles (
    user_id BIGINT PRIMARY KEY,
    role TEXT CHECK (role IN ('Dom', 'Sub', 'Switch')),
    about TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Kink lists: per‑user arrays of kinks
CREATE TABLE IF NOT EXISTS kinklists (
    user_id BIGINT PRIMARY KEY,
    kinks TEXT[] NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Collar relationships: who owns whose collar
CREATE TABLE IF NOT EXISTS collars (
    sub_id BIGINT PRIMARY KEY,
    dom_id BIGINT NOT NULL,
    since TIMESTAMP DEFAULT NOW()
);

-- Warnings: moderation warnings
CREATE TABLE IF NOT EXISTS warnings (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    moderator_id BIGINT NOT NULL,
    reason TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Moderation action logs
CREATE TABLE IF NOT EXISTS mod_logs (
    id SERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    user_id BIGINT,
    moderator_id BIGINT,
    details TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Scheduled posts (future use, if you want DB‑driven scheduling)
CREATE TABLE IF NOT EXISTS scheduled_posts (
    id SERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE
);

-- Bot configuration key‑value store (per guild)
CREATE TABLE IF NOT EXISTS configs (
    guild_id BIGINT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (guild_id, key)
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_warnings_user ON warnings (user_id);
CREATE INDEX IF NOT EXISTS idx_modlogs_user ON mod_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_configs_guild ON configs (guild_id);
