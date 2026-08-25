const clean = (value, max) => typeof value === 'string' ? value.trim().replace(/\s+/g, ' ').slice(0, max) : '';
const json = (body, status = 200) => Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
const escapeHtml = (value) => value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

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
  if (!env.ONBOARDING_DB || !env.RESEND_API_KEY) return json({ success: false, message: 'The beta email service is not configured yet.' }, 503);

  const id = `fr_${crypto.randomUUID().replaceAll('-', '')}`;
  const token = crypto.randomUUID() + crypto.randomUUID();
  const tokenHash = await sha256(token);
  const unsubscribeToken = crypto.randomUUID() + crypto.randomUUID();
  const unsubscribeTokenHash = await sha256(unsubscribeToken);
  const now = new Date();
  const expires = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  const confirmUrl = `${env.PUBLIC_SITE_URL || 'https://leaddrop.com.au'}/api/confirm?token=${encodeURIComponent(token)}`;
  const unsubscribeUrl = `${env.PUBLIC_SITE_URL || 'https://leaddrop.com.au'}/api/unsubscribe?token=${encodeURIComponent(unsubscribeToken)}`;
  try {
    await ensureSchema(env.ONBOARDING_DB);
    await env.ONBOARDING_DB.prepare('INSERT INTO free_report_signups (id,name,business_name,email,trade,service_area,status,source,created_at,consent_at,token_hash,token_expires_at,unsubscribe_token_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)').bind(id, name, business, email, trade, area, 'pending_confirmation', 'beta-free-report', now.toISOString(), now.toISOString(), tokenHash, expires.toISOString(), unsubscribeTokenHash).run();

    const emailResponse = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from: env.RESEND_FROM || 'LeadDrop <reports@leaddrop.com.au>',
        to: [email],
        subject: 'Confirm your free LeadDrop weekly report',
        html: `<p>Hi ${escapeHtml(name)},</p><p>Click below to confirm your free LeadDrop weekly report:</p><p><a href="${confirmUrl}">Confirm my free report</a></p><p>This link expires in 24 hours. If you did not request this, you can ignore this email.</p><p><a href="${unsubscribeUrl}">Unsubscribe from the free weekly report</a></p>`
      })
    });
    if (!emailResponse.ok) {
      await env.ONBOARDING_DB.prepare('UPDATE free_report_signups SET status=? WHERE id=?').bind('email_failed', id).run();
      return json({ success: false, message: 'We could not send the confirmation email. Please try again.' }, 502);
    }
    return json({ success: true, message: 'Check your inbox to confirm your free weekly report.' }, 201);
  } catch (_) {
    return json({ success: false, message: 'We could not save your request. Please try again.' }, 500);
  }
}
