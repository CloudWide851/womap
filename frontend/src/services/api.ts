const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export async function getHealth() {
  const response = await fetch(`${apiBaseUrl}/health`);
  if (!response.ok) {
    throw new Error('服务状态检查失败');
  }
  return response.json() as Promise<{
    status: string;
    environment: string;
    database: string;
    redis_configured: boolean;
  }>;
}
