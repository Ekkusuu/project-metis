const env = (import.meta as any).env;
const rawApiUrl = env?.VITE_API_URL?.trim() || (env?.DEV ? 'http://localhost:8000' : '');

export const API_URL = rawApiUrl.replace(/\/$/, '');
