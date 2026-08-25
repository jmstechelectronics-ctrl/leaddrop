async function sha256(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

const page = (title, message) => new Response(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title} | LeadDrop</title><style>body{margin:0;background:#0b0c0e;color:#f0f0ec;font:18px/1.5 system-ui;padding:12vh 24px}main{max-width:620px;margin:auto}a{color:#facc15}</style><main><p style="color:#facc15">LeadDrop</p><h1>${title}</h1><p>${message}</p><p><a href="/beta/">Back to LeadDrop</a></p></main>`, { headers: { 'Content-Type': 'text/html; charset=UTF-8', 'Cache-Control': 'no-store' } });

export async function onRequestGet({ request, env }) {
  const token = new URL(request.url).searchParams.get('token') || '';
  if (!token || !env.ONBOARDING_DB) return page('Unsubscribe unavailable', 'This unsubscribe link is incomplete.');
  try {
    const hash = await sha256(token);
    const row = await env.ONBOARDING_DB.prepare('SELECT id,status FROM free_report_signups WHERE unsubscribe_token_hash=?').bind(hash).first();
    if (!row) return page('Link not found', 'This unsubscribe link is invalid.');
    if (row.status === 'unsubscribed') return page('Already unsubscribed', 'You will not receive further free weekly LeadDrop reports.');
    await env.ONBOARDING_DB.prepare('UPDATE free_report_signups SET status=?,unsubscribed_at=? WHERE id=?').bind('unsubscribed', new Date().toISOString(), row.id).run();
    return page('You’re unsubscribed', 'You will not receive further free weekly LeadDrop reports.');
  } catch (_) {
    return page('Unsubscribe error', 'We could not complete your request. Please try again later.');
  }
}
