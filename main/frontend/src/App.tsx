import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell';
import { AuthProvider } from './context/AuthContext';
import DashboardPage from './pages/DashboardPage';
import HistoryPage from './pages/HistoryPage';
import InterviewRoomPage from './pages/InterviewRoomPage';
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/LoginPage';
import ModeSelectPage from './pages/ModeSelectPage';
import ProfilePage from './pages/ProfilePage';
import RandomSetupPage from './pages/RandomSetupPage';
import ReportPage from './pages/ReportPage';
import SignupPage from './pages/SignupPage';
import UploadSetupPage from './pages/UploadSetupPage';
import ProtectedRoute from './router/ProtectedRoute';

export default function App(){return <BrowserRouter><AuthProvider><Routes>
  <Route path="/" element={<LandingPage/>}/><Route path="/login" element={<LoginPage/>}/><Route path="/signup" element={<SignupPage/>}/>
  <Route element={<ProtectedRoute/>}><Route element={<AppShell/>}>
    <Route path="/dashboard" element={<DashboardPage/>}/><Route path="/interview/new" element={<ModeSelectPage/>}/><Route path="/interview/new/random" element={<RandomSetupPage/>}/><Route path="/interview/new/:mode" element={<UploadSetupPage/>}/><Route path="/interview/:sessionId/report" element={<ReportPage/>}/><Route path="/interview/:sessionId" element={<InterviewRoomPage/>}/><Route path="/history" element={<HistoryPage/>}/><Route path="/profile" element={<ProfilePage/>}/>
  </Route></Route>
  <Route path="*" element={<Navigate to="/" replace/>}/>
</Routes></AuthProvider></BrowserRouter>}
