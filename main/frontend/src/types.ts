export interface User { id: string; email: string; full_name: string | null }
export interface TokenResponse { access_token: string; token_type: string }
export interface RegisterInput { email: string; password: string; full_name?: string }
