import apiClient from './client';
import { Agent } from '../types';

export async function listAgents(): Promise<Agent[]> {
  const res = await apiClient.get<Agent[] | { agents: Agent[] }>('/agents');
  if (Array.isArray(res.data)) {
    return res.data;
  }
  return res.data.agents || [];
}

export async function getAgent(id: string): Promise<Agent> {
  const res = await apiClient.get<Agent>(`/agents/${id}`);
  return res.data;
}

export async function registerAgent(agent: Partial<Agent>): Promise<Agent> {
  const res = await apiClient.post<Agent>('/agents/register', agent);
  return res.data;
}
