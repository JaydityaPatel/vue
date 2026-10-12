import { api } from './client';
import type { RegisterInput, TokenResponse, User } from '../types';

export async function registerUser(payload: RegisterInput): Promise<User> {
  const { data } = await api.post<User>('/auth/register', payload);
  return data;
}

export async function loginUser(email: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/auth/login', { email, password });
  return data;
}

export async function fetchCurrentUser(): Promise<User> {
  const { data } = await api.get<User>('/auth/me');
  return data;
}
