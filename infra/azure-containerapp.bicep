// Headless deploy — Azure Container Apps (zero VM, auto-sleep optional, runs 24/7 without laptop)
// Deploy: az deployment group create -g rg-inbox-guardian -f infra/azure-containerapp.bicep -p containerImage=ghcr.io/you/inbox-guardian:latest
param location string = resourceGroup().location
param containerAppName string = 'inbox-guardian'
param environmentName string = 'cae-inbox-guardian'
param containerImage string // e.g. ghcr.io/<user>/email-agent:latest or <acr>.azurecr.io/email-agent:latest
param mailboxUpn string
param azureClientId string
@secure()
param azureClientSecret string
param azureTenantId string
@secure()
param openAiKey string = ''
@secure()
param apiKey string
param allowWrite bool = false

resource env 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: environmentName
  location: location
  properties: { }
}

resource app 'Microsoft.App/containerApps@2023-05-01' = {
  name: containerAppName
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      secrets: [
        { name: 'azure-client-secret', value: azureClientSecret }
        { name: 'openai-key', value: openAiKey }
        { name: 'api-key', value: apiKey }
      ]
    }
    template: {
      containers: [
        {
          name: containerAppName
          image: containerImage
          env: [
            { name: 'AZURE_CLIENT_ID', value: azureClientId }
            { name: 'AZURE_TENANT_ID', value: azureTenantId }
            { name: 'AZURE_CLIENT_SECRET', secretRef: 'azure-client-secret' }
            { name: 'MAILBOX_UPN', value: mailboxUpn }
            { name: 'AUTH_MODE', value: 'client_credentials' }
            { name: 'ALLOW_WRITE', value: string(allowWrite) }
            { name: 'OPENAI_API_KEY', secretRef: 'openai-key' }
            { name: 'API_KEY', secretRef: 'api-key' }
            { name: 'PORT', value: '8000' }
          ]
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
      scale: {
        minReplicas: 1  // headless = always 1 replica so scheduler never sleeps; set 0 for cost-save but cron will miss
        maxReplicas: 1
      }
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
output url string = 'https://${app.properties.configuration.ingress.fqdn}'
