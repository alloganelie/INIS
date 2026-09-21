import apiClient from './client';
import { TokenResponse, UserSession } from '../types';

export async function login(username: string, password: string): Promise<TokenResponse> {
  const res = await apiClient.post<TokenResponse>('/auth/login', {
    username,
    password,
  });
  if (res.data.access_token) {
    localStorage.setItem('inis_token', res.data.access_token);
  }
  if (res.data.refresh_token) {
    localStorage.setItem('inis_refresh_token', res.data.refresh_token);
  }
  return res.data;
}

export async function refresh(refreshToken: string): Promise<TokenResponse> {
  const res = await apiClient.post<TokenResponse>('/auth/refresh', {
    refresh_token: refreshToken,
  });
  if (res.data.access_token) {
    localStorage.setItem('inis_token', res.data.access_token);
  }
  return res.data;
}

export async function getMe(): Promise<UserSession> {
  const res = await apiClient.get<UserSession>('/auth/me');
  return res.data;
}

export function logout(): void {
  localStorage.removeItem('inis_token');
  localStorage.removeItem('inis_refresh_token');
}
