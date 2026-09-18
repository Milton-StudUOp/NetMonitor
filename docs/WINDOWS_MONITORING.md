# Windows monitoring

NetMonitor connects from Linux to Windows through WS-Management using the modular
`MonitoringProvider` interface. It provides encrypted connection settings,
capability detection, safe error classification, service inventory, selected-service
polling, system metrics, health, history, alerts, and reusable monitoring profiles.

## Windows preparation

- Prefer WinRM over HTTPS on TCP 5986 with a certificate trusted by the NetMonitor host.
- Use a dedicated least-privilege monitoring account.
- Do not enable unencrypted transport or broad `TrustedHosts` entries for NetMonitor.
- Windows Server 2008 R2 must have WinRM and PowerShell available. PowerShell 2 uses
  the legacy WMI-compatible provider automatically; PowerShell 3 and newer use the
  modern provider path.

The device screen presents protocol-neutral readiness information. Transport and
capability details are available under **Advanced diagnostics**.

Service operations are a dedicated module in the main navigation:

- **Service Monitoring** is the operational dashboard for health, coverage, failures,
  and recent checks.
- **Discover Services** is a four-step assistant: choose device, test connection,
  discover, then select and configure monitoring.
- **Service Topology** is a separate full-screen-capable device-to-service map.

These workflows are deliberately kept out of the device metrics/analytics page.

The assistant does not assume that only devices registered as `SERVER` can expose
Windows services. Any online registered device with an IP address can be selected;
the non-persistent connection test determines the actual platform and capabilities.
Credentials and connection settings are saved only after that test returns `READY`.

## Security

Passwords are encrypted using the existing `SECRET_KEY`-derived credential mechanism.
They are never returned by the API or included in diagnostics. Transport exceptions
are converted into stable error codes such as `WINRM_UNAVAILABLE`,
`AUTHENTICATION_FAILED`, `PERMISSION_DENIED`, and `CHECK_TIMEOUT` so remote exception
text cannot expose credentials or infrastructure details.

Keep `SECRET_KEY` stable and back it up. Certificate validation is enabled by default.

## Discovery and polling

Discovery retrieves all services in one remote operation but does not monitor them
automatically. Operators explicitly select services or apply a profile. Selected
services are fetched in one batch per device. The background worker:

- skips Windows checks while the device is offline;
- limits concurrent device sessions;
- honors per-service intervals and thresholds;
- backs off after communication errors;
- records communication failures as `UNKNOWN`, never as `SERVICE_DOWN`;
- transitions through `SUSPECTED`, `DOWN`, `RECOVERING`, and `UP`;
- opens and resolves service-specific alerts.

CPU, memory, uptime, and fixed-disk capacity are collected in a separate system metric
snapshot. The operational-health endpoint combines reachability, selected services,
and the latest system snapshot without redefining ping as complete health.

## Validation boundary

Automated tests cover modern/legacy selection, normalized discovery, batched checks,
metrics parsing, state thresholds, recovery, malformed responses, and a 100-service
batch. Release acceptance still requires integration tests against an actual Windows
Server 2008 R2 host and a modern Windows Server host with the security configuration
used in production.
