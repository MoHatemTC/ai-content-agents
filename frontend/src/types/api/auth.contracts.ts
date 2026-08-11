import type { UserRole } from "@/types/database.types";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  initials: string;
  role: UserRole;
}

export interface Session {
  access_token: string;
  refresh_token: string;
  expires_at: number;
  user: AuthUser;
}

export interface LoginResponse {
  session: Session;
}

export interface RefreshSessionRequest {
  refresh_token: string;
}

export interface RefreshSessionResponse {
  session: Session;
}

export interface GetCurrentUserResponse {
  user: AuthUser | null;
}
