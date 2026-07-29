// Azure UK South deployment scaffold for the hospital reception interpreter app.
// Scaffolding only -- not deployed by this repo. See infra/README.md for manual steps.
//
// Deploy in two passes:
//   1. deployContainerApps=false (default): provisions Log Analytics, the Container Apps
//      environment, ACR, and an empty Key Vault. Then run `az keyvault secret set` for each
//      secret out-of-band -- never pass real key values as Bicep parameters.
//   2. deployContainerApps=true, after the secrets above exist: provisions the two
//      Container Apps, which reference the Key Vault secrets directly.

@allowed(['uksouth'])
param location string = 'uksouth'

param environmentName string = 'hospital-interpreter'
param acrName string = toLower('acr${uniqueString(resourceGroup().id)}')
param keyVaultName string = toLower('kv-${uniqueString(resourceGroup().id)}')

param deployContainerApps bool = false
param serverImageTag string = 'latest'
param clientImageTag string = 'latest'

var identityName = '${environmentName}-identity'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${environmentName}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${environmentName}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

// AcrPull -- lets the container apps' managed identity pull images without admin credentials.
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, 'AcrPull')
  scope: acr
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

module keyVault 'modules/keyvault.bicep' = {
  name: 'keyVaultDeploy'
  params: {
    name: keyVaultName
    location: location
    principalId: identity.properties.principalId
  }
}

module serverApp 'modules/containerapp.bicep' = if (deployContainerApps) {
  name: 'serverAppDeploy'
  params: {
    name: '${environmentName}-server'
    location: location
    environmentId: containerAppsEnvironment.id
    identityId: identity.id
    image: '${acr.properties.loginServer}/hospital-interpreter-server:${serverImageTag}'
    targetPort: 8000
    external: true
    registryServer: acr.properties.loginServer
    keyVaultSecrets: [
      { name: 'elevenlabs-api-key', keyVaultUrl: '${keyVault.outputs.vaultUri}secrets/elevenlabs-api-key' }
      { name: 'anthropic-api-key', keyVaultUrl: '${keyVault.outputs.vaultUri}secrets/anthropic-api-key' }
      { name: 'session-api-key', keyVaultUrl: '${keyVault.outputs.vaultUri}secrets/session-api-key' }
    ]
    env: [
      { name: 'ELEVENLABS_API_KEY', secretRef: 'elevenlabs-api-key' }
      { name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' }
      { name: 'SESSION_API_KEY', secretRef: 'session-api-key' }
      { name: 'CORS_ORIGINS', value: '*' }
    ]
  }
}

module clientApp 'modules/containerapp.bicep' = if (deployContainerApps) {
  name: 'clientAppDeploy'
  params: {
    name: '${environmentName}-client'
    location: location
    environmentId: containerAppsEnvironment.id
    identityId: identity.id
    image: '${acr.properties.loginServer}/hospital-interpreter-client:${clientImageTag}'
    targetPort: 80
    external: true
    registryServer: acr.properties.loginServer
    keyVaultSecrets: []
    env: []
  }
}

output acrLoginServer string = acr.properties.loginServer
output keyVaultUri string = keyVault.outputs.vaultUri
