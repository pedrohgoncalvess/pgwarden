-- rollback: add n_mod_since_analyze

ALTER TABLE "metric"."table" DROP COLUMN modifications_since_last_analyze;
