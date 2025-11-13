# Cascade Flow Plumbing

*Tenant ID*: `cascade-plumbing`
*Primary Contact*: Ana Martínez (ana@cascadeflowplumbing.com, +12065551234)

## Getting Started

1. Export the environment file:
   ```bash
   export $(grep -v '^#' /workspace/voice_app_contractors/cva/infra/tenants/cascade-plumbing/.env | xargs)
   ```
2. Start the platform with docker compose.
3. Run the onboarding helper to refresh credentials and seed demo data:
   ```bash
   python -m cva admin:onboard cascade-plumbing \
     --owner-email ana@cascadeflowplumbing.com \
     --owner-password TempPass123 \
     --seed-demo
   ```
