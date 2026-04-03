-- マイグレーション: cancel_at_period_end カラムを users テーブルに追加
-- 実行: wrangler d1 execute deepcast-db --file=migration_add_cancel_at_period_end.sql
-- ※ ALTER TABLE ADD COLUMN は既にカラムが存在する場合エラーになるため、
--   エラーが出た場合は既に適用済みと判断してOK

ALTER TABLE users ADD COLUMN cancel_at_period_end INTEGER NOT NULL DEFAULT 0;
