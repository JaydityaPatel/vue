import { api } from './client';

export interface InterviewConfig {
  role: string;
  experience: string;
  skills: string[];
  difficulty: 'Gentle' | 'Balanced' | 'Challenging';
  interview_type: 'Mixed' | 'Technical' | 'Behavioral' | 'System design' | 'Coding';
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
  tests_passed?: number | null;
  tests_total?: number | null;
  complexity_correct?: boolean | null;
  edge_cases_identified?: string[] | null;
}
export interface InterviewTurn {
  id: string;
  turn_index: number;
  question_text: string;
  answer_text: string | null;
  action_taken: string | null;
  topic: string;
  topic_type?: 'discussion' | 'coding';
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
  current_topic_type?: 'discussion' | 'coding' | null;
  coding_status?: string | null;
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
  dimension_breakdown: Record<string, number>;
  turns: ReportTurn[];
  coding_breakdown?: {
    problems_solved: number; problems_total: number; tests_passed: number;
    tests_total: number; complexity_correct: number; complexity_total: number;
  } | null;
}
export interface ReportTurn {
  id: string; turn_index: number; question: string; answer: string | null; topic: string;
  topic_type: 'discussion' | 'coding'; expected_concepts: string[]; missing_concepts: string[];
  skill_tags: string[]; scores: Record<string, number> | null; feedback: string | null;
  tests_passed: number | null; tests_total: number | null;
}
export interface InterviewHistoryItem {
  session_id: string; mode: string; started_at: string; completed_at: string | null;
  status: string; overall_score: number | null;
}
export interface WeaknessItem {
  skill_tag: string; occurrence_count: number; session_count: number;
  average_scores: Record<string, number>; weak_dimensions: string[];
  trend: 'improving' | 'declining' | 'flat'; trend_delta: number;
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
  return (await api.get<InterviewReport>(`/interviews/${encodeURIComponent(id)}/report`)).data;
}
export async function getInterviewHistory(page = 1, pageSize = 20) {
  return (await api.get<{ items: InterviewHistoryItem[]; page: number; page_size: number; total: number }>(
    '/interviews', { params: { page, page_size: pageSize } },
  )).data;
}
export async function getRecurringWeaknesses() {
  return (await api.get<{ items: WeaknessItem[] }>('/users/me/weaknesses')).data.items;
}
