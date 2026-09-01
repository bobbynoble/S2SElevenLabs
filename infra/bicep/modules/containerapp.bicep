param name string
param location string
param environmentId string
param identityId string
param image string
param targetPort int
param external bool
param registryServer string
param env array = []
param keyVaultSecrets array = [] // [{ name: 'elevenlabs-api-key', keyVaultUrl: '<vaultUri>secrets/elevenlabs-api-key' }]

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      ingress: {
        external: external
        targetPort: targetPort
        transport: 'auto'
      }
      registries: [
        {
          server: registryServer
          identity: identityId
        }
      ]
      secrets: [for s in keyVaultSecrets: {
        name: s.name
        keyVaultUrl: s.keyVaultUrl
        identity: identityId
      }]
    }
    template: {
      containers: [
        {
          name: name
          image: image
          env: env
        }
      ]
      scale: {
        // Kept at 1/1: server session state is in-memory and single-process
        // (see server/src/session_manager.py). Do not scale beyond one replica
        // without adding a shared session store.
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output fqdn string = containerApp.properties.configuration.ingress.fqdn
