# NetMonitor Improvement Roadmap

This document tracks approved improvements and proposals. Implemented items are marked explicitly.

## Guiding principles

- Remain compatible with SQLite, PostgreSQL, MySQL, SQL Server, and Oracle.
- Prefer portable SQLAlchemy queries over database-specific SQL.
- Keep discovery and monitoring traffic safe for production networks.
- Make operational state understandable without requiring specialist knowledge.
- Protect credentials, personal data, audit records, and administrative operations.
- Design high-volume metric storage with retention and aggregation from the beginning.

## Priority 1 — Production foundation

### 1. Authentication and role-based access control

Add local authentication initially, with a design that can later support LDAP, Active Directory, or OIDC.

Suggested roles:

- **Viewer:** read dashboards, topology, metrics, alerts, and reports.
- **Operator:** acknowledge incidents, run approved discovery profiles, and manage maintenance windows.
- **Administrator:** manage users, integrations, databases, retention, templates, and aggressive discovery.

Acceptance criteria:

- Every non-public API requires authentication.
- Permissions are enforced by the backend, not only hidden in the frontend.
- Login, logout, failed authentication, and administrative actions are audited.
- Passwords use a modern adaptive hash and tokens have controlled expiration.
- A first-administrator bootstrap procedure is documented.

### 2. Metric retention and aggregation

The `monitoring_results` table will grow rapidly and should not remain an unlimited raw-event table.

Add:

- Configurable raw-data retention.
- Hourly and daily aggregates.
- Background cleanup with visible job status.
- Compound indexes for target, status, and timestamp.
- Server-side pagination for all historical views.
- Streaming exports for large reports.
- Database-aware batch sizes without changing business behavior between engines.

Acceptance criteria:

- Retention runs safely on every supported database.
- Aggregated reports remain available after raw samples expire.
- Cleanup never blocks the monitoring loop.
- Administrators can preview affected record counts before deletion.

### 3. NetMonitor self-monitoring

Expose the health of the monitoring platform itself:

- Database connectivity and query latency.
- Monitoring-cycle duration and last successful cycle.
- Number of delayed or failed checks.
- Notification queue and delivery failures.
- Discovery jobs and poller load.
- Database size and metric growth rate.
- Backend CPU, memory, file descriptors, and disk usage.

Provide a dedicated **System Health** page and include critical failures in notifications.

## Priority 2 — Monitoring depth

### 4. SNMP performance metrics

Expand monitoring beyond reachability:

- Device uptime.
- CPU and memory utilization.
- Temperature, fan, and power-supply state when supported.
- Interface administrative and operational state.
- Interface speed and utilization percentage.
- Incoming and outgoing traffic.
- Errors, discards, and packet drops.
- 95th-percentile bandwidth utilization.

Metric names, units, and labels should be centralized and consistent. Counter rollover, device reboot, and 32-bit/64-bit interface counters must be handled correctly.

Acceptance criteria:

- Missing OIDs do not make the entire device check fail.
- Counter resets do not generate false traffic spikes.
- Charts clearly identify units and collection gaps.
- Metric support is visible before a template is assigned.

### 5. Monitoring templates

Introduce reusable templates similar to mature monitoring platforms.

Initial templates:

- Generic ICMP device.
- Generic SNMP device.
- Cisco switch/router.
- MikroTik RouterOS.
- FortiGate firewall.
- Ubiquiti access point/radio.
- Linux server.
- Windows server.

A template should define checks, intervals, retry policy, thresholds, supported metrics, default icon, and notification recommendations. Devices may override individual values without modifying the template.

### 6. Service and port monitoring

Add explicit service checks independent of discovery:

- TCP connection.
- HTTP/HTTPS response, status code, latency, and certificate expiry.
- DNS resolution.
- SMTP, IMAP, and database port reachability.
- Optional content matching.
- Custom command/plugin interface with strict execution controls.

Service failures should appear in device analytics, topology context, alerts, and reports.

## Priority 3 — Incident operations

### 7. Complete incident lifecycle

Extend alerts into operational incidents with:

- Acknowledgement and assigned operator.
- Comments and activity history.
- Active, acknowledged, resolved, suppressed, and reopened states.
- Manual and automatic resolution reason.
- Escalation after configurable durations.
- Reminder limits and notification cooldown.
- Related-alert grouping.
- Root-cause incident linked to affected downstream devices.

All transitions must record actor, timestamp, previous state, new state, and reason.

### 8. Maintenance windows and silencing

Add maintenance schedules for devices, links, groups, services, or locations.

Required behavior:

- One-time and recurring windows.
- Timezone-aware scheduling.
- Optional monitoring continuation while notifications are suppressed.
- Visible maintenance state in topology and device lists.
- SLA reports can include or exclude planned maintenance.
- Emergency silence requires a reason and expiration time.

### 9. Notification reliability

Improve the delivery pipeline with:

- Persistent notification queue.
- Retry with exponential backoff.
- Dead-letter state for exhausted deliveries.
- Per-provider rate limiting.
- Delivery history linked to each incident.
- Message templates with preview and test data.
- Provider health and last successful delivery.
- Clear distinction between incident, reminder, escalation, and recovery messages.

## Priority 4 — User experience and reporting

### 10. Custom dashboards

Allow users to create and save dashboards containing:

- Availability and SLA widgets.
- Critical devices and active incidents.
- Highest latency and packet loss.
- Top interfaces by utilization.
- Devices with the most downtime.
- Redundancy state.
- Compact topology.
- Group, location, tag, and period filters.

Dashboard layouts and filters should be stored per user in the active database.

### 11. Advanced device analytics

Enhance the existing device metric view with:

- Compare current period with previous period.
- Zoomable graphs and selectable metrics.
- Annotations for outages, maintenance, and configuration changes.
- Interface-level drill-down.
- Baselines and anomaly indication.
- Export graph as PNG and data as CSV.
- Shareable, permission-checked URLs.

### 12. SLA and executive reporting

Add:

- SLA targets per device, service, group, or customer.
- Business-hour calendars.
- Planned-maintenance exclusions.
- Error budgets and burn rate.
- MTTR, MTBF, incident count, and availability trends.
- Scheduled PDF/CSV delivery.
- Report branding and reusable report definitions.
- Comparison by location, group, provider, or device type.

Calculations must have documented formulas and produce equivalent results on every supported database.

### 13. Inventory and configuration history

Track operational inventory changes:

- Device and interface attributes over time.
- Discovery reconciliation: new, changed, missing, or unmanaged assets.
- Configuration change audit.
- Tags, owners, service importance, warranty, and asset identifiers.
- Duplicate detection by IP, hostname, serial number, or SNMP engine ID.

Discovery should propose changes for approval instead of silently overwriting managed data.

## Priority 5 — Scale and integration

### 14. Distributed pollers

Support remote sites and segmented networks through pollers:

- Secure registration and mutual authentication.
- Assignment of devices or network ranges.
- Local buffering during central-server outages.
- Controlled concurrency and resource limits.
- Version and health visibility.
- No database credentials stored on pollers.

The central server remains the source of truth for configuration and reporting.

### 15. Public API, webhooks, and integrations

Provide a documented, versioned API and outbound webhooks for:

- Device and topology changes.
- Incident creation, acknowledgement, and recovery.
- SLA violations.
- Discovery completion.
- Notification delivery failures.

Add scoped API tokens, expiration, rotation, revocation, rate limits, and audit logging. Candidate integrations include ticketing systems, SIEM platforms, Grafana, and automation tools.

### 16. High availability and disaster recovery

Plan for:

- Multiple backend instances.
- Distributed job and notification queues.
- Leader election for scheduled monitoring.
- Health-aware load balancing.
- Scheduled encrypted backups.
- Automated restore verification.
- Documented recovery point and recovery time objectives.

In-memory discovery jobs and process-local state must move to a shared store before horizontal scaling.

## Cross-cutting quality improvements

These should accompany every approved feature:

- API pagination and stable response schemas.
- Structured error codes for frontend messages.
- Accessibility and keyboard navigation.
- Responsive layouts and consistent empty/loading/error states.
- Unit, integration, migration, and browser-level tests.
- Performance budgets for API queries and frontend bundles.
- Secrets excluded from logs, exports, backups, and API responses.
- Migration tests for all supported database engines.
- Operational documentation and rollback procedures.

## Recommended delivery sequence

### Phase A — Secure and stabilize

Status: **implemented**. Production activation requires setting unique secrets and completing the first-administrator bootstrap described in `README.md`.

1. Authentication and RBAC.
2. Metric retention, aggregation, indexes, and pagination.
3. NetMonitor self-monitoring.

### Phase B — Improve monitoring value

1. SNMP performance metrics.
2. Monitoring templates.
3. Service checks.

### Phase C — Professional incident management

1. Acknowledgement, ownership, and incident timeline.
2. Maintenance windows and silencing.
3. Persistent notification queue and escalation.

### Phase D — Reporting and scale

1. Custom dashboards and enhanced analytics.
2. SLA definitions and scheduled reports.
3. Distributed pollers, public API, and high availability.

## Evaluation checklist

For each proposal, decide:

- [ ] Approved, rejected, or postponed.
- [ ] Expected users and operational problem solved.
- [ ] Priority and target release.
- [ ] Required database migrations.
- [ ] Security and permission requirements.
- [ ] Expected metric/event volume.
- [ ] Multidatabase test coverage.
- [ ] Upgrade and rollback strategy.
- [ ] Documentation and training requirements.

## Suggested next decision

The recommended next package is **Phase A — Secure and stabilize**. Authentication should come first because future administrative features, distributed pollers, API tokens, scheduled exports, and incident ownership all depend on a reliable user and permission model.
