import { httpClient } from "@/lib/http-client";
import {
  authResponseSchema,
  type AuthResponse,
  type LoginPayload,
  registerResponseSchema,
  type RegisterPayload,
  type RegisterResponse,
} from "@/modules/auth/auth.schema";

export async function login(payload: LoginPayload): Promise<AuthResponse> {
  const response = await httpClient("auth", {
    method: "POST",
    body: payload,
  });

  return authResponseSchema.parse(response);
}

export async function register(payload: RegisterPayload): Promise<RegisterResponse> {
  const response = await httpClient("auth/register", {
    method: "POST",
    body: payload,
  });

  return registerResponseSchema.parse(response);
}