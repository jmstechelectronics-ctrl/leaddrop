const clean = (value, max) => typeof value === 'string' ? value.trim().replace(/\s+/g, ' ').slice(0, max) : '';
const json = (body, status = 200) => Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });

export async function onRequestPost({ request, env }) {
  if ((request.headers.get('Content-Type') || '').split(';')[0] !== 'application/json') {
    return json({ success: false, message: 'Please submit the form normally.' }, 415);
  }
  const origin = request.headers.get('Origin');
  if (origin && origin !== 'https://leaddrop.com.au') return new Response('Forbidden', { status: 403 });
  let body;
  try { body = await request.json(); } catch { return json({ success: false, message: 'Please check the form and try again.' }, 400); }
  if (clean(body.website, 100)) return json({ success: true, message: 'Thanks — your request has been received.' });

  const name = clean(body.name, 100);
  const business = clean(body.business, 150);
  const email = clean(body.email, 254).toLowerCase();
  const trade = clean(body.trade, 80);
  const area = clean(body.area, 120);
  if (name.length < 2 || business.length < 2 || trade.length < 2 || area.length < 2 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return json({ success: false, message: 'Please complete every field with a valid email address.' }, 400);
  }
  if (!env.ONBOARDING_DB) return json({ success: false, message: 'The beta form is not connected to storage yet.' }, 503);
  try {
    await env.ONBOARDING_DB.exec(`CREATE TABLE IF NOT EXISTS free_report_signups (id TEXT PRIMARY KEY, name TEXT NOT NULL, business_name TEXT NOT NULL, email TEXT NOT NULL, trade TEXT NOT NULL, service_area TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL)`);
    const id = `fr_${crypto.randomUUID().replaceAll('-', '')}`;
    const now = new Date().toISOString();
    await env.ONBOARDING_DB.prepare('INSERT INTO free_report_signups (id,name,business_name,email,trade,service_area,status,source,created_at) VALUES (?,?,?,?,?,?,?,?,?)').bind(id, name, business, email, trade, area, 'pending_confirmation', 'beta-free-report', now).run();
    return json({ success: true, message: 'Your request has been recorded. Confirmation email delivery is the next beta step.', id }, 201);
  } catch (_) {
    return json({ success: false, message: 'We could not save your request. Please try again.' }, 500);
  }
}
