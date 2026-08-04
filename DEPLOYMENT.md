# LeadDrop production operations

The public site is Cloudflare Pages. `POST /api/leaddrop-onboarding` is a Pages Function using the `ONBOARDING_DB` D1 binding. It stores the record before returning a Stripe checkout URL.

## Database

Create/bind D1 database `leaddrop-onboarding` as `ONBOARDING_DB`, then apply `schema/onboarding.sql`. D1 backups and point-in-time recovery should be enabled/reviewed in Cloudflare before operational use.

## Stripe

Configure Stripe's webhook endpoint as `https://leaddrop.com.au/api/stripe-webhook` and subscribe to `checkout.session.completed`. Set `STRIPE_WEBHOOK_SECRET` as a Cloudflare Pages secret. The webhook validates Stripe's signature, uses `client_reference_id` to update the D1 onboarding record, and is idempotent by Stripe event/session ID.

Payment Links are selected only by the server: $31 core, $41 core plus SMS, $41 core plus unlimited categories, and $51 both add-ons.

## Deployment and checks

Cloudflare automatically deploys `main` from GitHub. Run `node --check functions/api/leaddrop-onboarding.js`, `node --check functions/api/stripe-webhook.js`, and `python3 -m py_compile webhook_handler.py onboarding_app.py onboarding_store.py check_signups.py` before pushing.

Use `python3 check_signups.py` for existing Stripe polling. Unmatched webhook references are logged only by their non-sensitive onboarding reference and require manual reconciliation in D1/Stripe.
