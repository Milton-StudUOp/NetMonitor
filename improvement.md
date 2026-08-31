# ESPECIFICAÇÃO DE DESENVOLVIMENTO

## Funcionalidades Pendentes e Melhorias do Sistema de Monitoramento de Rede

### Contexto

O sistema de monitoramento de infraestrutura de rede já se encontra desenvolvido e funcional em sua estrutura principal.

Neste momento, devem ser implementadas e concluídas as seguintes funcionalidades:

1. Network Discovery Section
2. Icon Library, alteração de ícones dos equipamentos e reflexão automática na topologia
3. Multidatabase Capabilities e Configuration/Integration Section
4. Notification Integration Section
5. Persistência completa de todas as configurações do sistema

O desenvolvimento destas funcionalidades deve preservar a arquitetura existente e garantir que todas as configurações sobrevivam a:

* Reinicialização da aplicação
* Reinicialização do servidor
* Atualização da página
* Reinicialização de containers, caso Docker seja utilizado

---

# 1. NETWORK DISCOVERY SECTION

## 1.1 Objetivo

Implementar uma secção de descoberta automática de equipamentos de rede.

O objetivo é permitir que o administrador informe uma rede ou intervalo de IPs e o sistema realize uma varredura para identificar automaticamente equipamentos ativos.

Exemplos:

```text
192.168.1.0/24
```

ou:

```text
10.10.10.1 - 10.10.10.254
```

O sistema deverá apresentar os equipamentos encontrados para que o administrador possa decidir quais deseja adicionar ao sistema de monitoramento.

---

## 1.2 Funcionalidades Obrigatórias

A Network Discovery Section deve permitir:

### Definir alvo de descoberta

O utilizador deve poder informar:

* Network/CIDR
* IP Range
* IP individual

Exemplos:

```text
192.168.1.0/24
```

```text
10.0.0.10-10.0.0.100
```

```text
192.168.100.15
```

---

### Métodos de descoberta

A descoberta deverá utilizar múltiplas técnicas configuráveis.

#### ICMP Discovery

Verificar equipamentos que respondem a Ping.

Informações:

* IP Address
* Response Time
* Status

---

#### TCP Port Discovery

Verificar portas comuns.

Exemplo:

```text
22
23
80
443
161
8080
8443
```

O sistema deve permitir configurar a lista de portas.

---

#### SNMP Discovery

Quando SNMP estiver disponível, tentar identificar automaticamente:

* Hostname
* SysName
* SysDescr
* Manufacturer, quando possível
* Modelo, quando possível
* Interfaces
* Interface Status

Versões:

```text
SNMPv2c
SNMPv3
```

---

## 1.3 Resultado da Descoberta

Cada dispositivo descoberto deverá apresentar:

| Campo        | Descrição         |
| ------------ | ----------------- |
| IP Address   | IP descoberto     |
| Hostname     | Nome identificado |
| Status       | Online/Offline    |
| Latency      | Tempo de resposta |
| Open Ports   | Portas abertas    |
| SNMP         | Disponível ou não |
| Manufacturer | Fabricante        |
| Model        | Modelo            |
| Device Type  | Tipo estimado     |

---

## 1.4 Seleção e Importação

Após a descoberta, os equipamentos não devem ser automaticamente adicionados ao ambiente produtivo.

O utilizador deverá selecionar:

```text
☐ Device 1
☐ Device 2
☐ Device 3
```

E então executar:

```text
ADD SELECTED DEVICES
```

Antes da confirmação final, deve ser possível editar:

* Nome
* Tipo
* Localização
* Grupo
* Credenciais SNMP
* Método de monitoramento

---

## 1.5 Regras de Segurança

Credenciais utilizadas durante a descoberta não devem ser armazenadas em texto simples.

Requisitos:

* Password encryption
* SNMPv3 credentials encryption
* Não expor secrets no frontend
* Não retornar passwords através da API

---

# 2. ICON LIBRARY E ALTERAÇÃO DE ÍCONES DOS EQUIPAMENTOS

## 2.1 Objetivo

Implementar uma biblioteca de ícones que permita definir visualmente o tipo de cada equipamento.

O ícone selecionado deve ser refletido automaticamente em todos os locais onde o equipamento aparece.

Principalmente:

* Dashboard
* Device List
* Device Details
* Network Topology

---

## 2.2 Biblioteca de Ícones

Criar uma Icon Library organizada por categorias.

Exemplo:

### Network

* Router
* Switch
* Firewall
* Access Point
* Load Balancer

### Server

* Physical Server
* Virtual Machine
* Database Server

### Communication

* Media Converter
* Radio
* Modem
* Satellite Equipment

### Infrastructure

* UPS
* Power Equipment
* Rack

### Custom

Permitir upload de ícones personalizados.

Formatos:

```text
SVG
PNG
```

Preferencialmente, utilizar SVG como formato principal.

---

## 2.3 Alteração de Ícone

Na configuração do equipamento deve existir:

```text
Equipment Icon
```

Com:

```text
SELECT ICON
```

Ao selecionar um novo ícone:

```text
Device
   ↓
Database Update
   ↓
Real-time Event
   ↓
Topology Update
   ↓
All Device Views Update
```

---

## 2.4 Persistência

O ícone selecionado deve ser armazenado permanentemente.

Exemplo de campo:

```text
devices.icon_id
```

ou:

```text
devices.icon_path
```

Após:

* Refresh
* Logout/Login
* Server Restart

o ícone deve permanecer associado ao equipamento.

---

## 2.5 Reflexão na Topologia

A topologia deve utilizar sempre o ícone associado ao equipamento.

Não deve existir uma configuração separada de ícones exclusivamente para a topologia.

O equipamento deve possuir uma única definição central.

Exemplo:

```text
Device
├── Name
├── Type
├── Icon
├── IP
├── Status
└── Monitoring Configuration
```

A topologia apenas consome esta configuração.

Isso evita inconsistências entre:

* Device List
* Device Details
* Topology

---

# 3. MULTIDATABASE CAPABILITIES

## 3.1 Objetivo

O sistema deve permitir utilizar múltiplas bases de dados como fontes de dados ou integrações.

A funcionalidade deve permitir configurar e gerir múltiplas conexões.

Exemplos:

```text
MySQL
PostgreSQL
Microsoft SQL Server
SQLite
Oracle
```

A arquitetura deve ser extensível para permitir adicionar outros drivers futuramente.

---

## 3.2 Database Connection Manager

Criar uma secção:

```text
DATABASE CONNECTIONS
```

Funcionalidades:

* Add Database Connection
* Edit Connection
* Delete Connection
* Enable/Disable Connection
* Test Connection

---

## 3.3 Configuração de Conexão

Campos:

```text
Connection Name
Database Type
Host
Port
Database Name
Username
Password
SSL Configuration
Status
```

---

## 3.4 Segurança

Passwords devem ser:

* Encriptadas antes de persistir
* Nunca retornadas pela API
* Nunca exibidas no frontend depois de armazenadas

A API poderá retornar:

```text
password_configured: true
```

Mas nunca:

```text
password: "..."
```

---

## 3.5 Test Connection

Deve existir um botão:

```text
TEST CONNECTION
```

Resultado:

```text
SUCCESS
```

ou:

```text
FAILED
```

Em caso de falha, apresentar uma mensagem técnica controlada.

Exemplo:

```text
Unable to connect to database host.
Connection timeout.
```

Evitar exposição de passwords ou connection strings completas.

---

## 3.6 Database Integration

Cada conexão configurada deverá poder ser utilizada por módulos do sistema.

Exemplo:

```text
DATABASE CONNECTION
    ↓
DATA SOURCE
    ↓
QUERY / MONITORING RULE
    ↓
METRIC
    ↓
ALERT / DASHBOARD
```

O sistema deve permitir que uma futura funcionalidade consulte dados de uma base externa.

Exemplo:

```sql
SELECT status
FROM communication_status
WHERE location = 'OCC'
```

O resultado poderá ser utilizado para:

* Dashboard
* Monitoring
* Alerts
* Correlation

---

# 4. NOTIFICATION INTEGRATION SECTION

## 4.1 Objetivo

Implementar uma secção centralizada de integrações de notificações.

O administrador deverá configurar diferentes canais e decidir quais eventos devem gerar notificações.

Canais iniciais:

1. Email
2. Telegram
3. WhatsApp

A arquitetura deve permitir adicionar outros canais futuramente.

---

# 4.2 Notification Providers

Criar:

```text
NOTIFICATION INTEGRATIONS
```

Exemplo:

| Provider   | Status   | Action    |
| ---------- | -------- | --------- |
| Email SMTP | Enabled  | Configure |
| Telegram   | Enabled  | Configure |
| WhatsApp   | Disabled | Configure |

---

# 4.3 Email Integration

Campos:

```text
SMTP Server
SMTP Port
Username
Password
From Address
TLS
SSL
```

Funcionalidades:

```text
TEST EMAIL
```

O sistema deve permitir definir múltiplos destinatários.

Exemplo:

```text
noc@company.com
network@company.com
administrator@company.com
```

---

# 4.4 Telegram Integration

Configuração:

```text
Bot Token
Chat ID
```

Funcionalidades:

```text
TEST TELEGRAM MESSAGE
```

Exemplo:

```text
WARNING

Primary Link Down

Location:
CCP

Redundant Link:
Operational

Status:
DEGRADED
```

---

# 4.5 WhatsApp Integration

A implementação deve ser baseada numa integração oficial ou provider configurável.

Exemplo de arquitetura:

```text
WhatsApp Provider
        ↓
Provider API Configuration
        ↓
API Token
        ↓
Sender
        ↓
Recipient
```

A arquitetura não deve depender de automação não oficial do WhatsApp Web.

A configuração deve permitir:

```text
Provider
API URL
API Token
Sender ID
Recipient
```

Deve existir:

```text
TEST WHATSAPP MESSAGE
```

---

# 4.6 Notification Rules

Criar uma secção:

```text
NOTIFICATION RULES
```

Cada regra deve possuir:

```text
Rule Name
Event Type
Severity
Source
Notification Channel
Recipients
Enabled/Disabled
```

Exemplo:

```text
Rule:
Critical Network Failure

Event:
LINK DOWN

Severity:
CRITICAL

Channel:
Email + Telegram

Recipients:
Network Team
```

---

# 4.7 Evitar Alertas Duplicados

O sistema deve possuir deduplicação.

Exemplo:

Evento:

```text
LINK_PRIMARY DOWN
```

O sistema envia:

```text
1 ALERT
```

Enquanto o estado não mudar, não deve enviar notificações repetidas continuamente.

Enviar novamente apenas quando:

* Ocorre mudança de estado
* O alerta é escalado
* É atingido um intervalo de lembrete configurado

---

# 4.8 Recuperação

Quando o equipamento ou link recuperar:

```text
LINK_PRIMARY UP
```

Enviar:

```text
RECOVERY ALERT

Primary Link Restored

Downtime:
12 minutes
```

---

# 5. PERSISTÊNCIA COMPLETA DE CONFIGURAÇÕES

## 5.1 Objetivo

Todas as configurações criadas pelo utilizador devem ser persistentes.

Nenhuma configuração deve depender exclusivamente de:

* Estado do browser
* LocalStorage como fonte principal
* Variáveis temporárias em memória
* Estado do container

---

## 5.2 Configurações que Devem Ser Persistidas

O sistema deve persistir obrigatoriamente:

### Devices

* Nome
* IP
* Tipo
* Localização
* Grupo
* Ícone
* Configuração de monitoramento

### Network Topology

* Posição dos equipamentos
* Ligações
* Labels
* Configuração visual

### Monitoring

* Intervalos
* Thresholds
* Métodos
* Targets

### Redundancy

* Primary Links
* Secondary Links
* Redundancy Groups
* Regras

### Database Integrations

* Connection Configurations
* Encrypted Credentials
* Connection Status

### Notifications

* Providers
* Credentials
* Recipients
* Notification Rules

### System Settings

* Timezone
* Retention Period
* Default Monitoring Settings

---

# 6. REGRA FUNDAMENTAL DE PERSISTÊNCIA

A arquitetura deve seguir o princípio:

```text
USER CONFIGURATION
        ↓
API
        ↓
BACKEND VALIDATION
        ↓
DATABASE
        ↓
SUCCESS RESPONSE
```

O frontend não deve considerar uma alteração como permanentemente salva antes da confirmação do backend.

---

# 7. AUTOLOAD

Ao iniciar o sistema:

```text
APPLICATION START
        ↓
DATABASE LOAD
        ↓
LOAD CONFIGURATIONS
        ↓
INITIALIZE SERVICES
        ↓
START MONITORING
        ↓
LOAD DASHBOARD
```

Após reiniciar a aplicação, o sistema deve recuperar automaticamente:

* Equipamentos
* Topologia
* Ícones
* Regras
* Integrações
* Bases de dados
* Configurações de monitoramento
* Configurações de alertas

---

# 8. BACKUP E RESTORE DE CONFIGURAÇÃO

Deve ser implementada uma funcionalidade adicional de:

```text
EXPORT CONFIGURATION
```

e:

```text
IMPORT CONFIGURATION
```

A exportação deve permitir backup de:

* Devices
* Topology
* Monitoring Rules
* Notification Rules
* General Settings

Credenciais e passwords devem ser tratadas separadamente e nunca exportadas em texto simples.

---

# 9. REQUISITOS TÉCNICOS GERAIS

## Backend

Todas as novas funcionalidades devem possuir:

* API REST
* Validação de dados
* Tratamento de erros
* Logging
* Persistência

---

## Frontend

Deve possuir:

* Loading States
* Success Messages
* Error Messages
* Test Connection Actions
* Confirmation antes de Delete
* Auto Refresh onde necessário

---

## Segurança

Obrigatório:

* Encryption de passwords e tokens
* Secrets fora do frontend
* Não expor credenciais através da API
* Validação de inputs
* Proteção contra SQL Injection
* Audit Log para alterações importantes

---

# 10. PRIORIDADE DE IMPLEMENTAÇÃO

## PRIORIDADE 1 — CRÍTICA

### Persistência completa

Antes de adicionar novas funcionalidades, garantir que todas as configurações existentes já possuem persistência real.

Nenhuma funcionalidade crítica deve depender apenas de estado temporário.

---

## PRIORIDADE 2 — NETWORK DISCOVERY

Permite acelerar significativamente o cadastro de equipamentos.

---

## PRIORIDADE 3 — ICON LIBRARY E TOPOLOGY REFLECTION

Melhora a precisão visual e operacional da topologia.

---

## PRIORIDADE 4 — NOTIFICATION INTEGRATION

Permite transformar o sistema de visualização em um sistema operacional de monitoramento ativo.

---

## PRIORIDADE 5 — MULTIDATABASE CAPABILITIES

Implementar com uma arquitetura extensível, evitando acoplamento excessivo entre o sistema e um tipo específico de base de dados.

---

# 11. CRITÉRIO FINAL DE ACEITAÇÃO

As funcionalidades serão consideradas concluídas quando for possível:

1. Descobrir automaticamente equipamentos numa rede.
2. Selecionar equipamentos descobertos e adicioná-los ao sistema.
3. Alterar o ícone de qualquer equipamento.
4. Ver automaticamente o novo ícone refletido na topologia.
5. Configurar múltiplas conexões de bases de dados.
6. Testar cada conexão.
7. Utilizar uma conexão configurada como fonte de integração.
8. Configurar Email.
9. Configurar Telegram.
10. Configurar WhatsApp através de integração baseada em API.
11. Testar individualmente cada canal.
12. Criar regras de notificação.
13. Reiniciar completamente o sistema.
14. Confirmar que todas as configurações continuam disponíveis.
15. Confirmar que o monitoramento reinicia automaticamente utilizando as configurações persistidas.

---

# RESULTADO ESPERADO

Após esta fase, o sistema deverá evoluir de um monitoramento funcional para uma plataforma completa de Network Infrastructure Monitoring, com capacidade de:

* Descoberta automática
* Visualização de topologia
* Monitoramento de múltiplas redes
* Identificação de perda de redundância
* Monitoramento em tempo real
* Integração com múltiplas bases de dados
* Alertas multicanal
* Configuração persistente
* Recuperação automática após reinicialização

O princípio central da plataforma deve continuar sendo:

DETECTAR NÃO APENAS QUANDO A COMUNICAÇÃO PAROU, MAS TAMBÉM QUANDO A INFRAESTRUTURA PERDEU REDUNDÂNCIA E AINDA ESTÁ FUNCIONANDO EM ESTADO DEGRADADO.
