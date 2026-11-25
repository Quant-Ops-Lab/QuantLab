-- Research bars and autopsy reports shared by the research worker and console.
-- Safe to apply more than once. Does not touch orders or enable live trading.
-- Apply to a backup or a non-production database. The application also creates
-- these tables on startup; this file is the reviewable migration.

CREATE TABLE IF NOT EXISTS quantlab_daily_bars (
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    session TEXT NOT NULL,
    close TEXT NOT NULL,
    volume TEXT NOT NULL,
    adjusted_close TEXT,
    source TEXT NOT NULL,
    PRIMARY KEY (market, symbol, session)
);

CREATE TABLE IF NOT EXISTS quantlab_research_reports (
    data_asof TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    body TEXT NOT NULL,
    markdown TEXT NOT NULL
);
