# Tenant Setup Checklist

This checklist keeps the onboarding flow for new contractors under fifteen minutes.

## Pre-Call Preparation (3 minutes)
- [ ] Confirm the contractor's legal business name and DBA.
- [ ] Gather the owner or dispatcher email that will manage the dashboard.
- [ ] Collect a forwarding phone number for SMS notifications.
- [ ] Verify service categories, home base address, and service radius.
- [ ] Ensure OAuth credentials for the contractor's calendar are accessible.

## Environment Bootstrap (4 minutes)
1. Generate a tenant scaffold:
   ```bash
   python -m cva admin:new-tenant <tenant-id> --template plumber
   ```
2. Review the generated `.env` file and inject provider secrets.
3. Share the resulting `/cva/infra/tenants/<tenant-id>/README.md` with the contractor.

## Dashboard + Lead Store Onboarding (4 minutes)
1. Initialize the dashboard owner:
   ```bash
   python -m cva admin:onboard <tenant-id> \
     --owner-email owner@example.com \
     --owner-password <TemporaryPass123> \
     --seed-demo
   ```
2. Log in to the dashboard and personalize services, service radius, and branding.
3. Connect the contractor's calendar (Google/Outlook) using OAuth or service account token.

## Voice & Notification Validation (3 minutes)
- [ ] Run `python cva/telephony-service/harness.py --tenant <tenant-id>` and place a WAV test call.
- [ ] Confirm the booking confirmation SMS and contractor alert were recorded in the lead store.
- [ ] Open the dashboard leads page to verify the transcript and summary are visible.

## Launch Sign-off (1 minute)
- [ ] Capture trace IDs from the telephony logs and archive them with the tenant folder.
- [ ] Email the contractor the dashboard link, credentials, and support contacts.
