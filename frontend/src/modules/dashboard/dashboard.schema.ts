import { z } from "zod";

export const serverDatabaseItemSchema = z.object({
  id: z.uuid(),
});

export const serverSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  status: z.string(),
  databases: z.array(serverDatabaseItemSchema),
});

export const databaseSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  status: z.boolean(),
});

export const schemaColumnSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  description: z.string().nullable().optional(),
  data_type: z.string(),
  is_nullable: z.boolean(),
  default_value: z.string().nullable().optional(),
  is_unique: z.boolean(),
  ordinal_position: z.number(),
  fk_table_id: z.uuid().nullable().optional(),
  fk_column_id: z.uuid().nullable().optional(),
});

export const schemaIndexSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  type: z.string(),
  definition: z.string(),
  is_unique: z.boolean(),
  is_primary: z.boolean(),
  columns: z.array(z.string()),
});

export const schemaTableSchema = z.object({
  id: z.uuid(),
  schema_name: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  columns: z.array(schemaColumnSchema),
  indexes: z.array(schemaIndexSchema),
});

export const schemaResponseSchema = z.object({
  id: z.uuid(),
  tables: z.array(schemaTableSchema),
});

export const createResourceResponseSchema = z.object({
  message: z.string(),
  id: z.uuid(),
});

export type Server = z.infer<typeof serverSchema>;
export type Database = z.infer<typeof databaseSchema>;
export type SchemaResponse = z.infer<typeof schemaResponseSchema>;
export type CreateResourceResponse = z.infer<typeof createResourceResponseSchema>;

export type CreateServerPayload = {
  name: string;
  host: string;
  port: string;
  username: string;
  password: string;
  ssl_mode?: string;
  ignore_patterns?: string[];
  ignore_tables?: string[];
  include_tables?: string[];
};

export type CreateDatabasePayload = {
  server_id: string;
  db_name: string;
};
