# Windows monitoring

NetMonitor connects from Linux to Windows through WS-Management using the modular
`MonitoringProvider` interface. Phase 1 provides encrypted connection settings,
capability detection, safe error classification, and a connection test. Service
inventory and continuous polling are added in later phases.

## Windows preparation

- Prefer WinRM over HTTPS on TCP 5986 with a certificate trusted by the NetMonitor host.
- Use a dedicated least-privilege monitoring account.
- Do not enable unencrypted transport or broad `TrustedHosts` entries for NetMonitor.
- Windows Server 2008 R2 must have WinRM and PowerShell available. PowerShell 2 uses
  the legacy WMI-compatible provider automatically; PowerShell 3 and newer use the
  modern provider path.

The device screen presents protocol-neutral readiness information. Transport and
capability details are available under **Advanced diagnostics**.

## Security

Passwords are encrypted using the existing `SECRET_KEY`-derived credential mechanism.
They are never returned by the API or included in diagnostics. Transport exceptions
are converted into stable error codes such as `WINRM_UNAVAILABLE`,
`AUTHENTICATION_FAILED`, `PERMISSION_DENIED`, and `CHECK_TIMEOUT` so remote exception
text cannot expose credentials or infrastructure details.

Keep `SECRET_KEY` stable and back it up. Certificate validation is enabled by default.
