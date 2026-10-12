import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import LandingPage from './LandingPage';
import LoginPage from './LoginPage';
import SignupPage from './SignupPage';
import ProtectedRoute from '../router/ProtectedRoute';

const { fetchCurrentUser, loginUser, registerUser } = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(), loginUser: vi.fn(), registerUser: vi.fn(),
}));
vi.mock('../api/auth', () => ({ fetchCurrentUser, loginUser, registerUser }));

function renderPage(element: React.ReactNode, initialEntry = '/') {
  return render(<MemoryRouter initialEntries={[initialEntry]}><AuthProvider>{element}</AuthProvider></MemoryRouter>);
}

describe('public core pages', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    fetchCurrentUser.mockResolvedValue({ id: 'user-1', email: 'ada@example.com', full_name: 'Ada' });
    loginUser.mockResolvedValue({ access_token: 'test-token', token_type: 'bearer' });
    registerUser.mockResolvedValue({ id: 'user-1', email: 'ada@example.com', full_name: 'Ada' });
  });

  it('renders the landing hero and account links', () => {
    renderPage(<LandingPage/>);
    expect(screen.getByRole('heading', { name: /make room for your best answer/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /get started/i })).toHaveAttribute('href', '/signup');
    expect(screen.getAllByRole('link', { name: /i have an account/i }).some(link => link.getAttribute('href') === '/login')).toBe(true);
  });

  it('renders the login form and signup link', () => {
    renderPage(<LoginPage/>);
    expect(screen.getByRole('heading', { name: 'Welcome back.' })).toBeInTheDocument();
    expect(screen.getByLabelText('Email address')).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /create an account/i })).toHaveAttribute('href', '/signup');
  });

  it('renders the signup form and login link', () => {
    renderPage(<SignupPage/>);
    expect(screen.getByRole('heading', { name: 'Let’s get to know you.' })).toBeInTheDocument();
    expect(screen.getByLabelText(/your name/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Email address')).toHaveAttribute('type', 'email');
    expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^sign in/i })).toHaveAttribute('href', '/login');
  });

  it('blocks short passwords on the client before registration', async () => {
    renderPage(<SignupPage/>);
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'ada@example.com' } });
    fireEvent.change(screen.getByLabelText('Create a password'), { target: { value: 'short' } });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Use at least 8 characters');
    expect(registerUser).not.toHaveBeenCalled();
  });

  it('redirects protected pages to login without an auth token', async () => {
    renderPage(<Routes>
      <Route path="/login" element={<div>Login destination</div>}/>
      <Route element={<ProtectedRoute/>}><Route path="/dashboard" element={<div>Private dashboard</div>}/></Route>
    </Routes>, '/dashboard');
    expect(await screen.findByText('Login destination')).toBeInTheDocument();
    expect(screen.queryByText('Private dashboard')).not.toBeInTheDocument();
  });
});
