export async function login(email: string, password: string) {
  const response = await fetch('/api/login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const payload = await response.json();

  // Intentionally risky fixture behavior: browser-readable token storage.
  localStorage.setItem('authToken', payload.token);
  return payload.user;
}
