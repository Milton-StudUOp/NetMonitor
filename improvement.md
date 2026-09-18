# NetMonitor — Services & Metrics Discovery

Implement a professional **Services & Metrics Discovery and Monitoring module** for devices already registered in NetMonitor.

The solution must support **Windows Server 2008 R2 and newer Windows Server versions**, while keeping the NetMonitor backend running on **Linux**.

The implementation must integrate with the existing architecture without breaking current device monitoring.

## Core Workflow

For a registered device that is Online:

**Device → Discover Services & Metrics → Review → Select → Configure → Monitor → Alert → History**

The interface must be simple enough that the user does not need to understand WinRM, WMI, CIM or PowerShell.

---

# 1. Windows Monitoring Compatibility Layer

Do NOT tightly couple NetMonitor directly to one Windows management technology.

Create a backend abstraction such as:

`WindowsMonitoringProvider`

Conceptually:

```text
NetMonitor Linux
       │
       ▼
WindowsMonitoringProvider
       │
       ├── Connection / Capability Detection
       │
       ├── Modern Windows Provider
       │      └── PowerShell / CIM where supported
       │
       └── Legacy Windows Provider
              └── PowerShell / WMI-compatible commands
                       │
                       ▼
                 Windows Server
```

The rest of NetMonitor must receive normalized results regardless of which provider was used.

Example normalized service:

```json
{
  "name": "MSSQLSERVER",
  "display_name": "SQL Server (MSSQLSERVER)",
  "state": "running",
  "start_mode": "automatic",
  "monitoring_provider": "windows"
}
```

Do not expose implementation differences to the frontend unless needed for diagnostics.

---

# 2. Compatibility Requirements

Target:

**Windows Server 2008 R2 → newer supported Windows Server versions**

During the first connection/discovery, detect available capabilities where possible, including:

* Windows version
* PowerShell version
* WinRM availability
* Available management mechanism
* Authentication/connectivity status

Select the safest compatible discovery method automatically.

For modern systems, prefer appropriate PowerShell/CIM mechanisms.

For older systems such as Windows Server 2008 R2, provide a compatible fallback using available PowerShell/WMI functionality.

Do not assume modern PowerShell cmdlets exist on every target.

---

# 3. Linux Backend

NetMonitor remains Linux-based.

Do not require Windows software to run on the NetMonitor server merely to perform Windows monitoring.

Use an appropriate Python-compatible WinRM/WS-Management client or equivalent transport implementation.

Keep the transport implementation isolated from the monitoring business logic.

Conceptually:

```text
Linux NetMonitor
       │
       │ WinRM / WS-Management
       ▼
Windows Server
       │
       ├── PowerShell
       ├── CIM/WMI
       └── Windows Services
```

---

# 4. Secure Connectivity

Support WinRM connectivity using appropriate authentication mechanisms.

Prefer secure configurations suitable for production.

Where supported/configured:

**TCP 5986 — WinRM over HTTPS**

Do not weaken Windows security globally simply to make discovery work.

Avoid insecure configurations such as blindly enabling unencrypted transport or broadly configuring TrustedHosts.

Credentials must:

* Never be stored in plaintext
* Never appear in frontend responses
* Never appear in application logs
* Never appear in exception messages
* Use the existing NetMonitor secure credential mechanism

Use least-privilege monitoring accounts wherever possible.

---

# 5. Connection Test

Before discovery, provide:

**Test Connection**

Return a user-friendly result such as:

```text
SERVER-OCC-01

Connectivity       ✓
WinRM               ✓
Authentication      ✓
Windows             Server 2019
PowerShell          Available
Service Discovery   Supported

Ready for Discovery
```

For legacy systems:

```text
SERVER-LEGACY-01

Connectivity       ✓
WinRM               ✓
Authentication      ✓
Windows             Server 2008 R2
Legacy Provider     ✓
Service Discovery   Supported

Ready for Discovery
```

Do not display unnecessary protocol complexity to normal users.

Technical details may be available under **Advanced / Diagnostics**.

---

# 6. Service Discovery

Provide:

**Discover Services & Metrics**

For Windows Services retrieve, where available:

* Name
* Display Name
* State
* Start Mode
* Description
* Service account if appropriate
* Additional useful metadata when inexpensive to retrieve

For legacy Windows, use commands compatible with that environment.

Batch service discovery.

Do NOT create a separate WinRM connection/request for every Windows service.

---

# 7. Discovery vs Monitoring

Maintain a strict distinction:

**Discovered Service**

A service found on the Windows device.

**Monitored Service**

A discovered service explicitly selected for continuous monitoring.

Never monitor every discovered Windows service automatically.

A Windows server may contain hundreds of legitimate stopped/manual services.

The UI should provide:

* Search
* Running/Stopped filter
* Automatic/Manual/Disabled filter
* Multi-selection
* Bulk actions
* Rediscovery
* Monitor Selected
* Stop Monitoring

---

# 8. Monitoring Configuration

For selected services support:

**Expected State:** Running / Stopped
**Check Interval:** configurable
**Failure Threshold:** configurable
**Recovery Threshold:** configurable
**Severity:** Info / Warning / Critical
**Notifications:** Enabled / Disabled

Recommended defaults:

```text
Expected State       Running
Check Interval       60 seconds
Failure Threshold    3
Recovery Threshold   2
```

State handling:

**UP → SUSPECTED → DOWN → RECOVERING → UP**

Do not generate a DOWN event from a single temporary communication failure.

---

# 9. Intelligent Polling

Use existing NetMonitor device status before performing Windows monitoring.

```text
Device DOWN
    ↓
Skip Windows service polling

Device UP
    ↓
Windows monitoring check
    ↓
Retrieve selected services in batch
```

Avoid creating hundreds of concurrent remote sessions.

Implement:

* Controlled concurrency
* Worker limits
* Timeouts
* Retry limits
* Connection/session reuse where safe
* Backoff after repeated communication failures
* Batch retrieval

The architecture must support the existing **100+ devices** and future growth.

---

# 10. Metrics Discovery

The compatibility layer must eventually support more than Windows Services.

Design provider interfaces for:

### System

* CPU
* Memory
* Uptime

### Storage

* Disk usage
* Free space
* Disk information

### Network

* Interfaces
* Interface status
* Traffic counters where available

### Windows

* Services
* Processes
* Selected system information
* Event-related monitoring where appropriate

Capabilities may differ between Windows versions.

The provider must return only supported capabilities.

---

# 11. Capability Discovery

Maintain a device capability inventory.

Example:

```json
{
  "device": "SERVER-OCC-01",
  "platform": "windows",
  "capabilities": {
    "services": true,
    "cpu": true,
    "memory": true,
    "storage": true,
    "network_interfaces": true,
    "processes": true
  }
}
```

This architecture should later allow additional providers:

```text
MonitoringProvider
│
├── WindowsProvider
│
├── LinuxProvider
├── SNMPProvider
├── HTTPProvider
└── AgentProvider
```

Do not hard-code the overall monitoring engine specifically around Windows.

---

# 12. Error Classification

This is critical.

Differentiate between:

**DEVICE_DOWN**

Host itself is unavailable.

**WINRM_UNAVAILABLE**

Device is online but remote management cannot be reached.

**AUTHENTICATION_FAILED**

Credentials were rejected.

**PERMISSION_DENIED**

Account authenticated but lacks required permissions.

**DISCOVERY_FAILED**

Connection works but discovery operation failed.

**CHECK_TIMEOUT**

Monitoring operation exceeded timeout.

**SERVICE_DOWN**

Connection succeeded and Windows explicitly reports the monitored service is not in its expected state.

**UNKNOWN**

Status cannot currently be determined.

Never convert:

`WinRM timeout`

into:

`MSSQLSERVER DOWN`

That would create misleading operational alarms.

---

# 13. User Experience

Inside a device:

```text
SERVER-OCC-01                         ● ONLINE

Overview | Monitoring | Services | Metrics | History

Windows Monitoring
Connection                             ✓ Connected

Services
────────────────────────────────────────────────
Search...

☑ OCC Communication    Running      Automatic
☑ MSSQLSERVER          Running      Automatic
☐ Windows Update       Stopped      Manual
☐ Print Spooler        Stopped      Manual

[ Rediscover ]                 [ Monitor Selected ]
```

Normal users should interact with:

**Discover → Select → Monitor**

Advanced users may access:

**Advanced → Connection / Provider / Diagnostics**

Keep protocol-specific terminology away from the normal workflow.

---

# 14. Monitoring Profiles

Prepare support for reusable templates:

**Windows Server — Standard**

**Database Server**

**OCC Server**

**Critical Infrastructure**

Profiles should define:

* Services
* Metrics
* Thresholds
* Check intervals
* Failure thresholds
* Recovery thresholds
* Severity

This allows one monitoring policy to be applied consistently across multiple servers.

---

# 15. Device Health

Do not treat Ping as complete device health.

Model:

```text
SERVER-OCC-01
ONLINE

Availability       ✓
Windows Services   ✓
CPU                ✓
Memory              ✓
Storage             ⚠
Network             ✓
```

A device can therefore be:

**Reachable but Operationally Degraded**

Example:

```text
Ping             UP
Windows          Reachable
OCC Service      DOWN
SQL Server       UP
CPU              Normal
Memory           Normal
```

This distinction is one of the primary objectives of this feature.

---

# 16. Performance

Discovery and monitoring must be separate workloads.

Recommended model:

```text
PING
10–30 seconds

SELECTED SERVICES
30–60+ seconds depending on criticality

SYSTEM METRICS
60+ seconds

FULL DISCOVERY
Manual / scheduled infrequently
```

Do not repeatedly enumerate every Windows service every 30 seconds.

After discovery, continuous checks should focus only on selected monitored services and metrics.

---

# 17. Implementation Phases

Implement incrementally.

### Phase 1 — Compatibility & Connectivity

Implement `WindowsMonitoringProvider`, WinRM transport, capability detection, secure credential handling and **Test Connection**.

Validate against at least:

* Windows Server 2008 R2
* One modern Windows Server version available in the environment

### Phase 2 — Service Discovery

Implement service discovery, normalization, inventory and UI.

### Phase 3 — Service Monitoring

Implement selection, configuration, background polling, state transitions and history.

### Phase 4 — System Metrics

CPU, memory, uptime and storage.

### Phase 5 — Health & Alerts

Thresholds, health visualization, alert integration and historical reporting.

### Phase 6 — Profiles & Extended Providers

Monitoring templates and preparation for Linux/SNMP/Agent providers.

---

# 18. Mandatory Testing

Before considering the feature complete, test:

* Windows Server 2008 R2 compatibility
* Modern Windows Server compatibility
* Correct credentials
* Wrong credentials
* Insufficient permissions
* WinRM disabled
* Firewall blocking WinRM
* Device offline
* Service running
* Service stopped
* Service restarting
* Timeout
* Temporary network interruption
* Rediscovery
* 100+ device scalability behavior

Existing NetMonitor monitoring must continue operating normally during failures of the Windows monitoring subsystem.

---

# Final Requirement

The architecture must allow NetMonitor to evolve from:

**“Is the device reachable?”**

to:

**“Is the device reachable, are its critical services operating, are its resources healthy, and what specifically requires attention?”**

Implement this as a **modular monitoring framework**, not as a Windows-only feature bolted directly into the existing ping engine.

Preserve existing functionality, prioritize backward compatibility, security, performance and a professional user experience.
