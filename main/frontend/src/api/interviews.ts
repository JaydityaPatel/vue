import { api } from './client';

export interface InterviewConfig {
  role: string;
  experience: string;
  skills: string[];
  difficulty: 'Gentle' | 'Balanced' | 'Challenging';
  interview_type: 'Mixed' | 'Technical' | 'Behavioral' | 'System design';
  duration: number;
}
export interface TurnResult {
  session_id: string;
  turn_id: string | null;
  next_question: string | null;
  is_complete: boolean;
  completion_reason: string | null;
  report_generation?: { method: 'POST'; url: string };
}
export interface InterviewCreated extends TurnResult { first_question: string }
export type InterviewMode = 'random' | 'resume' | 'job';
export interface TurnScore {
  technical_correctness: number;
  completeness: number;
  communication: number;
  problem_solving: number;
  expected_concepts: string[];
  missing_concepts: string[];
  skill_tags: string[];
  feedback: string;
  rubric_version: string;
  scored_by_model: string;
  provisional: boolean;
}
export interface InterviewTurn {
  id: string;
  turn_index: number;
  question_text: string;
  answer_text: string | null;
  action_taken: string | null;
  topic: string;
  generated_by_model: string | null;
  provisional: boolean;
  score: TurnScore | null;
}
export interface InterviewSession {
  session_id: string;
  mode: InterviewMode;
  status: 'in_progress' | 'completed' | 'abandoned';
  config: InterviewConfig;
  started_at: string;
  completed_at: string | null;
  time_remaining: number;
  current_topic: string | null;
  turns_on_current_topic: number;
  topic_coverage: Record<string, 'not_started' | 'in_progress' | 'covered'>;
  turns: InterviewTurn[];
  completion_reason: string | null;
  report_generation: { method: 'POST'; url: string } | null;
  preparation_status: 'preparing' | 'ready' | 'failed';
}
export interface InterviewReport {
  id: string;
  session_id: string;
  summary: string;
  overall_score: number;
  improvement_suggestions: string[];
  generated_by_model: string;
  provisional: boolean;
}
export async function createInterview(config: InterviewConfig): Promise<InterviewCreated> {
  return (await api.post<InterviewCreated>('/interviews', { mode: 'random', config })).data;
}
export async function createDocumentInterview(data: FormData): Promise<InterviewCreated> {
  return (await api.post<InterviewCreated>('/interviews', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180_000,
  })).data;
}
export async function getInterview(id: string): Promise<InterviewSession> {
  return (await api.get<InterviewSession>(`/interviews/${encodeURIComponent(id)}`)).data;
}
export async function submitAnswer(id: string, answer: string, turnId: string): Promise<TurnResult> {
  return (await api.post<TurnResult>(`/interviews/${encodeURIComponent(id)}/answer`, {
    answer_text: answer, turn_id: turnId,
  })).data;
}
export async function generateReport(id: string): Promise<InterviewReport> {
  return (await api.post<InterviewReport>(`/interviews/${encodeURIComponent(id)}/report`)).data;
}
