# NetMonitor Implementation Roadmap

This document records the current implementation baseline and the next improvements. It intentionally reflects the product decisions already adopted in the application.

## Implemented baseline

- Unified monitoring-provider model for WinRM, SSH, and SNMP.
- One active provider per device, with explicit unlinking before replacement.
- Windows services through WinRM and Linux systemd services through SSH.
- Capability-driven Windows, Linux, and SNMP metrics.
- Individual service policy, immediate confirmed DOWN state, recovery handling, history, alerts, and notifications.
- Separate Network and Service React Flow topologies with private saved views, autosave, layout restore, zoom, minimap, and fullscreen support.
- Device metric summaries automatically displayed in Network Topology after collection.
- SNMP v1/v2c/v3 configuration, selected-interface monitoring, counter persistence, calculated inbound/outbound traffic, and utilization when interface speed is exposed.
- SMTP, Telegram, and WhatsApp notifications with testing, rules, reminders, recovery messages, and protected secrets.
- Primary database promotion with migration validation, protected credentials, and preservation of accounts and valid sessions.
- Monitoring Profiles for reusable service-policy defaults and bulk application.

## Product rules

- Discovery never means automatic continuous monitoring; users explicitly select services, metrics, and SNMP interfaces.
- Providers expose only capabilities that the selected target supports.
- A communication error is not presented as a stopped service.
- Service state does not use a `SUSPECTED` transition; it follows the configured failure threshold and then becomes DOWN.
- Links and redundancy groups are the supported model for network relationships. Manual device dependencies are not a product feature.

## Next operational improvements

### Linux hardening

- Extend validation across Ubuntu LTS, Debian, and RHEL-compatible distributions.
- Improve SSH diagnostics for host-key, authentication, permission, timeout, and systemd capability failures.
- Add controlled Linux journal/event collection only where safely supported.

### SNMP operations

- Add reusable SNMP credential profiles.
- Add interface state, error, traffic, and utilization alert policies.
- Add optional vendor-specific enrichments without presenting them as generic SNMP capabilities.

### Service profiles and reporting

- Extend profiles with richer metric-policy templates where the provider supports them.
- Add configurable contractual SLA targets while retaining the current calculated availability reports.

## Quality gates

- Validate database schema evolution on SQLite, PostgreSQL, MySQL/MariaDB, SQL Server, and Oracle.
- Keep secrets out of API responses, logs, exports, and error messages.
- Run backend tests, frontend production build, and real provider checks before release.
- Verify Viewer, Operator, and Administrator permissions for every new operational action.
