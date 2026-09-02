const clean = (value, max) => typeof value === 'string' ? value.trim().replace(/\s+/g, ' ').slice(0, max) : '';
const json = (body, status = 200) => Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
async function sha256(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function ensureSchema(db) {
  await db.exec(`CREATE TABLE IF NOT EXISTS free_report_signups (id TEXT PRIMARY KEY, name TEXT NOT NULL, business_name TEXT NOT NULL, email TEXT NOT NULL, trade TEXT NOT NULL, service_area TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL, consent_at TEXT, token_hash TEXT, token_expires_at TEXT, unsubscribe_token_hash TEXT, confirmed_at TEXT, unsubscribed_at TEXT)`);
  for (const sql of [
    'ALTER TABLE free_report_signups ADD COLUMN token_hash TEXT',
    'ALTER TABLE free_report_signups ADD COLUMN token_expires_at TEXT',
    'ALTER TABLE free_report_signups ADD COLUMN confirmed_at TEXT',
    'ALTER TABLE free_report_signups ADD COLUMN consent_at TEXT',
    'ALTER TABLE free_report_signups ADD COLUMN unsubscribe_token_hash TEXT',
    'ALTER TABLE free_report_signups ADD COLUMN unsubscribed_at TEXT'
  ]) { try { await db.exec(sql); } catch (_) {} }
}

export async function onRequestPost({ request, env }) {
  if ((request.headers.get('Content-Type') || '').split(';')[0] !== 'application/json') return json({ success: false, message: 'Please submit the form normally.' }, 415);
  const origin = request.headers.get('Origin');
  if (origin && origin !== 'https://leaddrop.com.au') return new Response('Forbidden', { status: 403 });
  let body;
  try { body = await request.json(); } catch { return json({ success: false, message: 'Please check the form and try again.' }, 400); }
  if (clean(body.website, 100)) return json({ success: true, message: 'Thanks — your request has been received.' });

  const name = clean(body.name, 100), business = clean(body.business, 150), email = clean(body.email, 254).toLowerCase(), trade = clean(body.trade, 80), area = clean(body.area, 120);
  if (name.length < 2 || business.length < 2 || trade.length < 2 || area.length < 2 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ success: false, message: 'Please complete every field with a valid email address.' }, 400);
  if (body.consent !== true) return json({ success: false, message: 'Please confirm you want to receive the free weekly report.' }, 400);
  if (!env.ONBOARDING_DB) return json({ success: false, message: 'The signup service is not configured yet.' }, 503);

  const id = `fr_${crypto.randomUUID().replaceAll('-', '')}`;
  const unsubscribeToken = crypto.randomUUID() + crypto.randomUUID();
  const unsubscribeTokenHash = await sha256(unsubscribeToken);
  const now = new Date();
  try {
    await ensureSchema(env.ONBOARDING_DB);
    await env.ONBOARDING_DB.prepare('INSERT INTO free_report_signups (id,name,business_name,email,trade,service_area,status,source,created_at,consent_at,unsubscribe_token_hash,confirmed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)').bind(id, name, business, email, trade, area, 'confirmed', 'beta-free-report', now.toISOString(), now.toISOString(), unsubscribeTokenHash, now.toISOString()).run();
    return json({ success: true, message: 'You’re on the free weekly report list. We’ll email you when reports begin.' }, 201);
  } catch (_) {
    return json({ success: false, message: 'We could not save your request. Please try again.' }, 500);
  }
}
