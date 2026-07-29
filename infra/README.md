# Azure UK South deployment (scaffolding only)

This directory is a deployment scaffold, not a deployed environment. Nothing here has been
applied to a real Azure subscription. The steps below are manual, to be run by whoever owns the
target Azure subscription.

Region is pinned to **UK South** (`location` only accepts `uksouth`) to satisfy the NHS
UK-data-residency requirement for infrastructure hosting. See the repo root README's "Compliance
notes" for the separate, still-open questions about ElevenLabs' and Anthropic's own data
residency, which this infrastructure does not resolve on its own.

## One-time setup

```bash
az login
az group create --name hospital-interpreter-rg --location uksouth
```

## Step 1 -- provision shared infra (Log Analytics, Container Apps environment, ACR, empty Key Vault)

```bash
az deployment group create \
  --resource-group hospital-interpreter-rg \
  --template-file bicep/main.bicep \
  --parameters bicep/main.parameters.json
```

## Step 2 -- set secrets directly in Key Vault (never via Bicep parameters)

```bash
KEY_VAULT_NAME=<from the deployment output: keyVaultUri>

az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name elevenlabs-api-key --value "<your ElevenLabs key>"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name anthropic-api-key --value "<your Anthropic key>"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name session-api-key --value "<a generated secret>"
```

## Step 3 -- build and push images to ACR

```bash
ACR_LOGIN_SERVER=<from the deployment output: acrLoginServer>

az acr build --registry "$ACR_LOGIN_SERVER" --image hospital-interpreter-server:latest ../server
az acr build --registry "$ACR_LOGIN_SERVER" --image hospital-interpreter-client:latest ../client
```

## Step 4 -- deploy the container apps

```bash
az deployment group create \
  --resource-group hospital-interpreter-rg \
  --template-file bicep/main.bicep \
  --parameters bicep/main.parameters.json \
  --parameters deployContainerApps=true
```

## Notes

- Both container apps are pinned to `minReplicas`/`maxReplicas` of 1. The backend holds session
  state in memory in a single process (`server/src/session_manager.py`); scaling beyond one
  replica, or increasing the backend's `--workers`, will break session routing until a shared
  store (e.g. Redis) is introduced.
- ACR pull and Key Vault secret access both use the deployment's user-assigned managed identity --
  no admin credentials or plaintext secrets are stored in the Bicep templates.
- This scaffold does not configure a custom domain, TLS certificate, or WAF/Front Door. Add those
  before exposing this to real patients.
