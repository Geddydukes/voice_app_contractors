# Infrastructure & Enablement

This directory now bundles tooling for rapid pilot launches, tenant automation, and sales collateral.

## Command Line Utilities
Use the Python entrypoint to access administrative commands:

```bash
python -m cva admin:new-tenant cascade-plumbing
python -m cva admin:onboard cascade-plumbing --owner-email ana@cascadeflowplumbing.com --owner-password TempPass123 --seed-demo
```

- `admin:new-tenant` scaffolds a tenant directory under `cva/infra/tenants/`, generates a branded `.env`, and stores metadata for future automation.
- `admin:onboard` provisions dashboard credentials, updates service radius, connects the calendar, and optionally seeds demo leads.

## Demo & QA Assets
- `demo_scenarios.py` – scripted journeys for English and Spanish booking demos with optional lead-store seeding.
- `tests/synthetic_calls.py` – regression harness for latency and fallback guarantees.

## Deployment Helpers
- `../Makefile` exposes a `deploy` target that shells out to `infra/scripts/deploy.sh` for Docker builds and pushes.
- `scripts/deploy.sh` (see below) tags images per service using the `REGISTRY` and `TAG` environment variables.

## Sales Enablement
- `sales/landing_page.html` – drop-in responsive landing page.
- `sales/pricing_sheet.(md|html)` – pricing overview in Markdown and HTML formats.
- `sales/demo_video_script.md` – narration script for the 60-second overview clip.
- `checklists/tenant_setup.md` – step-by-step operator checklist to keep deployment under 15 minutes.

## Deploy Script
```
bash cva/infra/scripts/deploy.sh
```
Set `REGISTRY` (e.g. `ghcr.io/your-org`) and `TAG` (default `latest`) before running. The script builds each service image and performs a `docker compose build` for parity with local environments.
