### Network Discovery — Optional Ports + Top 100 Ports + Safe Scanning

O Network Discovery está funcionando muito bem. Preciso apenas ajustar e expandir o comportamento atual para tornar o processo mais flexível e seguro para ambientes de produção.

### 1. IP/CIDR/Range deve ser o único campo obrigatório

Atualmente parece que o Discovery exige também a especificação de portas.

O comportamento esperado é:

* `IP/CIDR/Range` → obrigatório
* `Ports` → opcional

Exemplos válidos:

`192.168.1.0/24`

`10.10.10.1-10.10.10.254`

`192.168.10.15`

Mesmo sem nenhuma porta especificada, o Discovery deve executar normalmente.

---

### 2. Port Scan Mode

Adicionar uma opção:

**Port Scan Mode**

Com três possibilidades:

**No Port Scan**

* Apenas descoberta dos equipamentos.
* ICMP/Ping.
* ARP quando aplicável.
* SNMP quando configurado.
* Hostname/DNS quando disponível.
* Não realizar TCP port scan.

**Top 100 Ports**

* Primeiro descobrir os hosts ativos.
* Depois executar scan das Top 100 TCP Ports somente nos hosts encontrados.
* O utilizador não precisa especificar portas manualmente.

**Custom Ports**

* Primeiro descobrir os hosts ativos.
* Depois realizar scan somente das portas especificadas.
* Exemplo: `22,80,443,3389`.

Quando `Custom Ports` estiver selecionado, mostrar o campo:

`Ports`

Nos outros modos, esse campo deve ficar oculto ou desabilitado.

---

### 3. Top 100 Ports

A lista das Top 100 TCP Ports deve ficar centralizada no backend/configuração do sistema e não hardcoded no frontend.

Isso permitirá atualizar a lista futuramente sem necessidade de alterar a interface.

O resultado do Discovery deve mostrar, por equipamento:

* Host
* IP
* Hostname
* Device Type, quando identificado
* SNMP availability
* Open TCP Ports
* Response time
* Status

Importante: um equipamento deve continuar sendo considerado **discovered** mesmo que nenhuma porta TCP esteja aberta.

---

### 4. Safe Discovery / Network Protection

Como o sistema será utilizado em redes de produção, o Top 100 não deve executar um scan agressivo.

O fluxo recomendado é:

`IP/CIDR/Range`
→ `ICMP/ARP/SNMP Discovery`
→ `Identify Active Hosts`
→ `TCP Port Scan`
→ `Results`

Não executar Top 100 contra todos os IPs do range quando não forem necessários.

Por exemplo, em um `/24`, primeiro identificar os hosts ativos e somente depois executar o port scan nesses hosts.

O scanner deve possuir:

* Configurable timeout
* Configurable retry
* Configurable concurrency
* Rate limiting
* Maximum hosts per scan
* Cancel Discovery
* Progress indicator

Como configuração inicial para produção, utilizar valores conservadores, por exemplo:

* Timeout: 1–2 segundos
* Concurrent hosts: 10–20
* Retry: 1
* Safe rate limiting habilitado

Esses valores devem ser configuráveis posteriormente.

---

### 5. Scan Profiles

Se possível, adicionar:

**Scan Profile**

`Safe`

* Baixa intensidade
* Recomendado para produção
* Concorrência limitada
* Rate limiting habilitado

`Normal`

* Intensidade moderada

`Aggressive`

* Maior concorrência/intensidade
* Deve exigir privilégios de administrador e apresentar aviso antes da execução

O default deve ser:

`Safe`

---

### 6. Progress / Cancellation

Durante o Discovery, apresentar progresso real.

Exemplo:

`Discovery Progress: 67%`

`Hosts Found: 38`

`Ports Scanned: 2,450`

`Elapsed Time: 00:42`

Adicionar:

`Cancel Discovery`

O cancelamento deve interromper novas tarefas de scan e permitir que as tarefas em execução sejam encerradas de forma controlada.

---

### 9. Critérios de Aceitação

O desenvolvimento será considerado correto quando:

**Teste 1 — Discovery básico**

Input:

`192.168.1.0/24`

Port Scan:

`No Port Scan`

Resultado:

Hosts ativos encontrados sem realizar port scan.

---

**Teste 2 — Top 100**

Input:

`192.168.1.0/24`

Port Scan:

`Top 100 Ports`

Resultado:

1. Descobrir hosts ativos.
2. Executar Top 100 somente nos hosts ativos.
3. Apresentar portas abertas.
4. Não gerar tráfego desnecessário contra IPs inativos.

---

**Teste 3 — Custom**

Input:

`192.168.1.0/24`

Port Scan:

`Custom`

Ports:

`22,80,443,3389`

Resultado:

Somente essas portas devem ser verificadas.

---

**Teste 4 — Sem portas**

Input:

`192.168.1.0/24`

Ports:

`Empty`

O sistema não deve apresentar erro de validação.

Deve executar o Discovery normalmente.

---

### Objetivo final

O Network Discovery deve funcionar como uma ferramenta de descoberta de infraestrutura, e não simplesmente como um port scanner.

O princípio deve ser:

**Discover first → Identify active hosts → Enrich information → Optional Port Scan**

Dessa forma, conseguimos ter uma descoberta eficiente e segura, inclusive em redes de produção, sem tornar a especificação de portas um requisito para descobrir equipamentos.