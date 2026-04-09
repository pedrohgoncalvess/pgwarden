import { z } from "zod";

export const authResponseSchema = z.object({
  token_type: z.string(),
  access_token: z.object({
    token: z.string(),
    expires: z.string(),
  }),
  refresh_token: z.object({
    token: z.string(),
    expires: z.string(),
  }),
});

export type AuthResponse = z.infer<typeof authResponseSchema>;

export type LoginPayload = {
  email: string;
  password: string;
};

export const registerResponseSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  email: z.string().email(),
  is_admin: z.boolean(),
});

export type RegisterResponse = z.infer<typeof registerResponseSchema>;

export type RegisterPayload = {
  name: string;
  email: string;
  password: string;
};
