import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HistoryPage from './HistoryPage';

const { getInterviewHistory, getRecurringWeaknesses } = vi.hoisted(() => ({
  getInterviewHistory: vi.fn(), getRecurringWeaknesses: vi.fn(),
}));
vi.mock('../api/interviews', () => ({ getInterviewHistory, getRecurringWeaknesses }));

beforeEach(() => {
  vi.clearAllMocks();
  getInterviewHistory.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 });
  getRecurringWeaknesses.mockResolvedValue([]);
});

function renderPage() { render(<MemoryRouter><HistoryPage/></MemoryRouter>); }

describe('History page', () => {
  it('renders an empty state and an empty weakness section', async () => {
    renderPage();
    expect(await screen.findByText('Nothing to look back on just yet.')).toBeInTheDocument();
    expect(screen.getByText('No recurring weaknesses yet.')).toBeInTheDocument();
  });

  it('renders past sessions with their real score and report link', async () => {
    getInterviewHistory.mockResolvedValue({ items: [{ session_id: 'session-42', mode: 'random',
      started_at: '2026-10-10T12:00:00Z', completed_at: '2026-10-10T12:20:00Z', status: 'completed', overall_score: 3.75 }], page: 1, page_size: 20, total: 1 });
    getRecurringWeaknesses.mockResolvedValue([{ skill_tag: 'API reliability', occurrence_count: 3, session_count: 2,
      average_scores: { technical_correctness: 2, completeness: 2.25 }, weak_dimensions: ['technical_correctness'], trend: 'improving', trend_delta: .5 }]);
    renderPage();
    expect(await screen.findByRole('link', { name: /3\.75 \/ 5/i })).toHaveAttribute('href', '/interview/session-42/report');
    expect(screen.getByText('API reliability')).toBeInTheDocument();
    expect(screen.getByText('improving')).toBeInTheDocument();
  });
});
