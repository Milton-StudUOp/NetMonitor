# Próxima implementação — Services e Metrics para Linux

Planeamento da próxima fase de desenvolvimento do NetMonitor. O objetivo é adicionar monitorização Linux sem duplicar a implementação Windows nem acoplar o motor principal a SSH, WinRM ou a um sistema operativo específico.

## Resultado esperado

Um dispositivo Linux registado no NetMonitor poderá ser testado, ter capacidades descobertas e disponibilizar:

- serviços `systemd` selecionados para monitorização;
- CPU, memória e uptime;
- utilização e espaço livre dos discos;
- interfaces, estado e contadores de tráfego;
- processos e informação básica do sistema quando suportados;
- histórico, métricas, alertas e topologia com a mesma experiência já usada para Windows.

O fluxo será:

`Device → Test Connection → Discover Capabilities → Discover Services/Metrics → Select → Monitor → History/Alerts`

Descobrir não significa monitorizar. Apenas serviços e métricas explicitamente selecionados serão recolhidos continuamente.

## 1. Arquitetura multiprovider

Extrair um contrato comum acima do provider Windows existente:

```text
MonitoringProvider
├── WindowsMonitoringProvider (WinRM, já existente)
└── LinuxMonitoringProvider (SSH, próxima fase)
```

O contrato deve oferecer operações normalizadas:

```python
test_connection()
discover_capabilities()
discover_services()
check_services(names)
collect_system_metrics(capabilities)
```

O scheduler, histórico, alertas, perfis e frontend devem consumir respostas normalizadas e não comandos específicos de Windows ou Linux. Cada provider devolve somente capacidades realmente suportadas pelo host.

## 2. Transporte Linux

Criar `SSHTransport`, isolado da lógica de monitorização, com:

- autenticação por chave SSH como opção recomendada;
- password como opção compatível, sempre cifrada pelo mecanismo existente;
- validação obrigatória da host key;
- porta configurável, timeout e limites de saída;
- execução sem shell interativo;
- lista fechada de comandos construídos pelo backend;
- redacção de credenciais, comandos sensíveis e detalhes internos nos logs.

Não aceitar comandos arbitrários enviados pelo frontend. Não recomendar `StrictHostKeyChecking=no`, root login ou permissões globais de `sudo`.

## 3. Test Connection e capacidades

O teste deverá classificar separadamente:

- `DEVICE_DOWN` — host não alcançável;
- `SSH_UNAVAILABLE` — host online, mas SSH indisponível;
- `HOST_KEY_MISMATCH` — identidade SSH diferente da guardada;
- `AUTHENTICATION_FAILED` — credenciais rejeitadas;
- `PERMISSION_DENIED` — login válido sem permissões de leitura;
- `DISCOVERY_FAILED` — sessão funciona, descoberta falhou;
- `CHECK_TIMEOUT` — operação excedeu o timeout;
- `SERVICE_DOWN` — serviço consultado não corresponde ao estado esperado;
- `UNKNOWN` — não foi possível confirmar o estado.

Detectar, quando disponível:

- distribuição e versão por `/etc/os-release`;
- kernel e arquitetura;
- presença de `systemctl` e estado do systemd;
- disponibilidade de `/proc`, `/sys`, `df`, `ip` e `ss`;
- permissões efetivas do utilizador de monitorização.

## 4. Serviços Linux

Primeira implementação: unidades `systemd` do tipo `service`.

Modelo normalizado:

```json
{
  "name": "nginx.service",
  "display_name": "A high performance web server",
  "state": "running",
  "start_mode": "enabled",
  "monitoring_provider": "linux"
}
```

Mapeamentos:

- `active/running` → `running`;
- `inactive`, `failed`, `deactivating` → estado normalizado apropriado;
- `enabled`, `disabled`, `static`, `masked` → `start_mode` preservado;
- falha confirmada → `DOWN` imediatamente;
- recuperação → `RECOVERING` até cumprir o limiar configurado, depois `UP`.

Descoberta será executada em lote. Checks contínuos consultarão apenas os serviços selecionados, também em lote por dispositivo.

Hosts sem systemd devem declarar `services: unsupported` na primeira versão; suporte a OpenRC/SysV será uma fase posterior, sem heurísticas silenciosas.

## 5. Métricas Linux

Coletar com interfaces estáveis do sistema, evitando instalar agente na primeira versão:

| Capacidade | Fonte preferida |
|---|---|
| CPU | `/proc/stat` com duas amostras para calcular utilização |
| Memória | `/proc/meminfo` |
| Uptime | `/proc/uptime` |
| Storage | `df -P -B1` e informação de mounts |
| Interfaces | `/sys/class/net` e `ip -j` quando disponível |
| Tráfego | RX/TX em `/sys/class/net/*/statistics` |
| Processos | `/proc` ou `ps` com formato controlado |
| Sistema | `/etc/os-release`, `uname` e hostname |

Valores serão convertidos para o mesmo schema normalizado usado pelas páginas atuais. Contadores cumulativos de rede devem ser guardados com timestamp; taxas serão calculadas entre amostras, tratando reboot e reset de contador.

## 6. Persistência e credenciais

Reutilizar as tabelas existentes sempre que o modelo já for neutro:

- `device_monitoring_credentials.provider = LINUX`;
- `device_capabilities.provider = LINUX`;
- `discovered_services.monitoring_provider = linux`;
- `service_check_history` para checks de serviços;
- `system_metric_snapshots` para métricas normalizadas.

Antes de alterar tabelas, validar se nomes Windows-específicos precisam ser generalizados. Migrações devem preservar todos os dados Windows atuais e funcionar em SQLite, PostgreSQL, MySQL, SQL Server e Oracle.

Credenciais nunca entram em backup, respostas da API, erros ou logs. A private key deverá ser cifrada em repouso e nunca escrita em ficheiro temporário sem proteção.

## 7. Scheduler e desempenho

- consultar Linux somente quando o device estiver `ONLINE`;
- uma sessão limitada por dispositivo, reutilizada apenas quando seguro;
- sem uma conexão por serviço ou métrica;
- concorrência global configurável;
- timeout, retry limitado e backoff para falhas de transporte;
- descoberta manual/infrequente separada do polling;
- services e metrics com intervalos independentes;
- nenhum erro SSH deve ser convertido em `SERVICE_DOWN`.

Meta inicial: 100+ dispositivos mistos Windows/Linux sem bloquear os ciclos ICMP, alertas ou WebSocket.

## 8. API e interface

Generalizar os fluxos existentes sem criar menus paralelos por sistema operativo:

- **Services Monitoring → Discovery**: selecionar device, testar provider, descobrir e adicionar;
- **Services Monitoring → Service Monitoring**: Windows e Linux na mesma lista, com filtro de provider/plataforma;
- **Services Monitoring → Topology**: mesmos nós, layouts e auto-save por utilizador;
- **Metrics Monitoring → Discovery**: mostrar somente métricas suportadas pelo host;
- **Metrics Monitoring**: cartões e detalhes normalizados para ambas as plataformas.

O formulário de conexão muda dinamicamente conforme o provider:

- Windows: WinRM, autenticação e certificado;
- Linux: SSH, porta, utilizador, chave/password e host key.

Protocolos e diagnósticos avançados ficam recolhidos numa área técnica. O fluxo normal continua `Test → Discover → Add → Edit`.

## 9. Fases de implementação

### Fase 1 — Contrato comum e SSH

- introduzir `MonitoringProvider` sem regressão Windows;
- implementar `SSHTransport` e armazenamento seguro;
- implementar Test Connection, host-key trust explícito e códigos de erro;
- testes unitários de parsing, timeout, autenticação e redacção.

### Fase 2 — Capabilities e serviços

- detectar Linux/systemd e capacidades;
- descobrir unidades em lote;
- adicionar seleção, configuração e polling;
- integrar estados, histórico, alertas e recovery;
- incluir provider/plataforma nos filtros.

### Fase 3 — Métricas de sistema

- CPU, memória e uptime;
- storage e mounts;
- interfaces e contadores RX/TX;
- processos e informação do sistema quando suportados;
- integrar cartões, detalhes e topologia de rede.

### Fase 4 — Robustez e escala

- backoff e limites de concorrência;
- testes com 100+ devices simulados;
- testes reais em Ubuntu LTS, Debian e uma distribuição RHEL-compatible;
- documentação operacional e de least privilege;
- revisão de segurança antes de produção.

## 10. Testes obrigatórios

- chave válida, password válida e credenciais erradas;
- host key nova, aceite e alterada;
- SSH desativado/bloqueado;
- device offline;
- systemd disponível e indisponível;
- serviço running, stopped, failed, restarting e removido;
- CPU/memória/storage com locales diferentes;
- interfaces físicas, virtuais e loopback;
- timeout, saída inválida e perda temporária de rede;
- rediscovery sem duplicados;
- Windows e Linux monitorizados simultaneamente;
- compatibilidade das migrações em todos os bancos suportados;
- permissões Viewer/Operator/Administrator;
- nenhum segredo presente em logs, API, export ou mensagens de erro.

## Critérios de conclusão

- Windows continua funcional sem regressões;
- Linux usa a mesma experiência de Services, Metrics, History, Alerts e Topology;
- somente capacidades suportadas aparecem;
- somente seleções explícitas são monitorizadas;
- falhas de transporte permanecem `UNKNOWN`, nunca falso `SERVICE_DOWN`;
- layouts, preferências e filtros continuam por utilizador;
- build frontend, suíte backend e testes reais Linux passam antes do merge.

## Fora do escopo inicial

- instalação de agente próprio;
- containers/Kubernetes;
- logs/journald completos;
- execução remota de ações corretivas;
- OpenRC/SysV;
- descoberta automática de credenciais.

Esses itens poderão ser acrescentados depois que SSH, systemd e métricas essenciais estiverem estáveis.
