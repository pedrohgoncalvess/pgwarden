import { z } from "zod";
import { httpClient } from "@/lib/http-client";
import {
  createResourceResponseSchema,
  databaseSchema,
  schemaResponseSchema,
  serverSchema,
  type CreateDatabasePayload,
  type CreateResourceResponse,
  type CreateServerPayload,
  type Database,
  type SchemaResponse,
  type Server,
} from "@/modules/dashboard/dashboard.schema";

const serversSchema = z.array(serverSchema);
const databasesSchema = z.array(databaseSchema);

export async function listServers(token?: string): Promise<Server[]> {
  const response = await httpClient("server", {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  return serversSchema.parse(response);
}

export async function listDatabases(token?: string): Promise<Database[]> {
  const response = await httpClient("database", {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  return databasesSchema.parse(response);
}

export async function createServer(
  payload: CreateServerPayload,
  token?: string
): Promise<CreateResourceResponse> {
  const response = await httpClient("server/", {
    method: "POST",
    body: payload,
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });

  return createResourceResponseSchema.parse(response);
}

export async function createDatabase(
  payload: CreateDatabasePayload,
  token?: string
): Promise<CreateResourceResponse> {
  const response = await httpClient("database/", {
    method: "POST",
    body: payload,
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });

  return createResourceResponseSchema.parse(response);
}

export async function getDatabaseSchema(databaseId: string, token?: string): Promise<SchemaResponse> {
  const response = await httpClient(`schema/${databaseId}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  return schemaResponseSchema.parse(response);
}
