ALTER TABLE collector.server DROP COLUMN ingestion_project_id;
DROP TABLE ingestion.event;
DROP TABLE ingestion.entity;
DROP TABLE ingestion.api_key;
DROP TABLE ingestion.project;
DROP SCHEMA ingestion;
