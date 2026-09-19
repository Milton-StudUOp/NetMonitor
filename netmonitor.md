# NetMonitor Functional Guide

NetMonitor is an infrastructure monitoring platform for network devices, Windows and Linux hosts, services, metrics, redundancy, incidents, notifications, history, and reporting. It combines inventory, background collection, real-time updates, and interactive topologies in one web application.

## Access control and user accounts

NetMonitor provides authenticated local accounts and role-based access control.

- **Viewer** users have read-only access to operational information.
- **Operator** users can perform authorized operational tasks, including discovery and monitoring configuration.
- **Administrator** users manage users, integrations, databases, notifications, backups, and system administration.

The application supports initial administrator bootstrap, sign in/sign out, expiring sessions, first-login password changes, password recovery, and user administration. Passwords are stored as hashes; session tokens are stored as digests. Administrative activity is recorded for audit purposes.

## Application navigation and interface

The sidebar groups the operational modules as follows:

- **Network Monitoring**: Topology, Redundancy, Devices, Links, and Discovery.
- **Services Monitoring**: Topology, Service Monitoring, and Discovery.
- **Metrics Monitoring**: Metrics Monitoring and Discovery.
- **General modules**: Dashboard, Alerts, History, Reports, Settings, and System Health.

The header title follows the current page. Light, dark, and system theme modes are available. Long pages, filters, tables, dialogs, and topology canvases are designed to remain scrollable and usable on smaller screens or when browser zoom is enabled.

## Dashboard

The Dashboard is the central operational view. It provides:

- monitored-device, communication-link, redundancy-group, and active-alert summary cards;
- active incidents with severity, target, cause, time, and resolution action;
- real-time redundancy status;
- embedded **Network Topology**;
- embedded **Service Topology**.

Dashboard data is updated as backend events arrive. Configuration remains in the dedicated Network, Services, Metrics, and Settings modules.

## Network Monitoring

### Devices

Devices can be registered, edited, and removed. A device includes a name, IP address or hostname, type, icon, and monitoring details. NetMonitor records reachability, latency, packet loss, and availability history for supported probe types.

### Links

Links define communication paths between registered devices. They are displayed in the network topology and are used by link monitoring and redundancy evaluation.

### Network Discovery

Discovery accepts individual IP addresses, ranges, and CIDR ranges. Supported network discovery and probing methods include ICMP, TCP, HTTP/HTTPS, and SNMP where applicable. Results can be reviewed before selected devices are imported. Discovery can identify available hostname, SNMP description, manufacturer, model, and interface information when exposed by the target.

### Network Topology

Network Topology is an interactive React Flow canvas that shows devices, primary links, and redundancy paths. It includes:

- pan, zoom, minimap, controls, and fullscreen mode;
- automatic layout, free layout, and manual reorganization;
- saved views, restore, create/delete view actions, and viewport persistence;
- automatic layout saving;
- private saved views and layouts per user;
- live device health on each node;
- configured metric summaries on nodes after metric data is collected;
- dedicated visual paths for redundancy.

Saving or rearranging a view changes only that user’s visual arrangement; it does not modify the inventory, monitored links, or other users’ layouts.

### Redundancy

Redundancy groups protect availability through alternative devices or link paths. The module displays normal, degraded, and critical conditions and raises incidents when a required path or redundant capability is lost. Diagnosis uses registered links, gateways, and monitoring state.

There is no separate manual dependency model. Operational relationships are represented through links and redundancy groups, preventing conflicting dependency and topology definitions.

## Services Monitoring

### Integration model

Each device has one active monitoring integration at a time. This avoids mixing service and metric data from different providers. To change from WinRM to SSH or SNMP, the active integration must first be unlinked, then the new integration can be configured.

Credentials are protected at rest, and the interface displays the active provider for each device.

### Supported integrations

- **WinRM**: Windows service discovery, Windows service monitoring, and Windows telemetry.
- **SSH**: Linux systemd service discovery, Linux service monitoring, and Linux telemetry.
- **SNMP v1/v2c/v3**: network-device inventory and SNMP metrics for switches, routers, appliances, and compatible devices.

The discovery workflow includes protocol guidance for WinRM over HTTP (5985) and HTTPS (5986), SSH, and SNMP (UDP 161). Connection testing is recommended but a known-good configuration may be saved when a test cannot be completed at that moment.

### Service discovery and configuration

Service Discovery starts with a searchable registered-device combobox; devices are not displayed before the user searches. After selecting a device, the user configures or confirms its provider, discovers available services, selects the required services, and adds them with defaults. Each monitored service can then be edited independently.

Service policies include expected state, check interval, failure threshold, recovery threshold, severity, and notifications. A service that violates its expected state becomes **DOWN** after its configured failure rule; NetMonitor does not use a “suspected” service state. Communication failures are classified separately so a transport outage is not incorrectly shown as a stopped service.

### Service Monitoring

The Service Monitoring page supports search and filters for service, device, observed state, expected state, health, severity, and notification state. Every monitored service has an individual configuration dialog, current observed state, expected state, last check, and notification policy.

### Service Topology

Service Topology is a separate React Flow view. It provides the same user-specific saved views, layout persistence, autosave, pan, zoom, minimap, fullscreen, restore, automatic layout, and free layout functions as Network Topology. It shows service state separately from host reachability, so an online host with a stopped expected service is clearly represented.

### Device and service analytics

Dedicated analysis pages provide availability, latency, packet loss, outages, checks, and service-related operational history. They support investigation without leaving the relevant device or service context.

## Metrics Monitoring

### Metrics workflow

Metrics Discovery uses the device’s active service integration; it does not create a duplicate WinRM, SSH, or SNMP configuration. The workflow is:

1. Search for and select a registered device.
2. Confirm the active provider.
3. Discover only provider-supported capabilities.
4. Select metrics, thresholds, and notifications.
5. Save the configuration and collect a sample.

The UI shows **Not monitored** or **Awaiting data** instead of displaying a misleading zero for unconfigured or not-yet-collected metrics. Once data is available, enabled metrics appear automatically on the corresponding Network Topology node.

### Windows metrics through WinRM

Depending on host capabilities, Windows monitoring can collect CPU, memory, uptime, disk usage and free space, network interfaces and state, processes, selected system information, and event-related data.

### Linux metrics through SSH

Depending on host capabilities, Linux monitoring can collect CPU, memory, uptime, storage and free space, interfaces, processes, system information, and systemd services.

### SNMP metrics

SNMP is configured in Services Monitoring and consumed by Metrics Discovery. Depending on the MIBs exposed by the device, it can collect:

- system description and uptime;
- storage information exposed by HOST-RESOURCES-MIB;
- IF-MIB interface index, name, type, MTU, speed, administrative and operational state;
- interface byte, packet, and error counters.

The SNMP discovery screen lets the operator choose the interfaces to monitor. The first successful collection stores counters. From the second valid collection, NetMonitor calculates inbound and outbound traffic in bits per second from counter deltas over time. If interface speed is available, it also calculates utilization percentage. This is intended for production switch, router, and appliance monitoring without automatically enabling every port.

CPU and memory are not reported as generic SNMP capabilities because they are vendor-specific and cannot be reliably normalized across all equipment.

### Thresholds and metric notifications

Monitored metrics are editable per device. CPU, memory, and storage thresholds can generate normal NetMonitor alerts and notifications when exceeded. Metric cards and device details show current collected values only for configured metrics.

## Alerts, incidents, and notifications

### Alert management

NetMonitor consolidates device, link, redundancy, service, and metric-threshold events into alerts. An alert contains its state, severity, target, description, probable cause when available, time, acknowledgement information, and resolution state.

The Alerts page provides search, filtering, paging, acknowledgement, and resolution. Acknowledgements store the acting user, timestamp, and note.

### Notification channels

Settings → Notifications supports independent configuration, save, test, and enablement of the following channels:

- **SMTP email**: SMTP server, port, account, encrypted password, sender, recipients, STARTTLS, or implicit TLS.
- **Telegram**: encrypted bot token and one or more chat IDs, including groups and channels.
- **WhatsApp**: persisted WhatsApp Web linked-device session using a QR code, or an official/provider HTTP API with encrypted token and recipients.

Stored passwords, tokens, and secrets are never returned by the API. The UI indicates that a secret exists without revealing it. Every channel stores its last test result and error details for operational diagnosis.

### Notification rules

Rules decide which incidents produce notifications and where they are delivered. A rule can define its name, enabled state, event type, severity, optional source, one or more channels, specific recipients, reminder interval, and whether recovery notifications are sent.

The notification engine deduplicates events for an incident, sends reminders according to the applicable rule, and can deliver a recovery message after the monitored condition normalizes. Delivery and failure indicators are available in System Health.

## History and reports

### History

History stores probe results and alert history. It provides target, type, state, and date-range filters with server-side pagination. Probe history includes availability, latency, and packet loss when applicable.

Raw samples are retained for the configured period, then processed into hourly and daily aggregates for efficient long-term reporting.

### Reports

Reports provide calculated availability, incident counts, MTTR, MTBF, redundancy-loss information, and inventory reporting using retained raw and aggregate data.

## Settings and platform administration

### Databases and primary database migration

SQLite is the default local database. Administrators can register SQLite, PostgreSQL, MySQL/MariaDB, Microsoft SQL Server, and Oracle connections and test them before use.

Promoting a database to primary requires an empty compatible destination. NetMonitor creates the schema, migrates data, validates record counts, and only then activates the new database. User accounts, password hashes, roles, and valid sessions are included, so users retain their credentials. Changes are disabled during migration, and the prior database is never deleted by a failed promotion.

### External data sources

Read-only external SQL data sources can be registered with named, parameterized queries and tested from Settings. They are intended for safe data lookup and do not modify the external source.

### Monitoring profiles

Monitoring Profiles reuse service-monitoring policies. A profile can define service patterns, interval, recovery behavior, severity, and notification defaults, then be applied in bulk to selected devices. Services remain individually editable afterwards.

### Backup, icons, and system preferences

The platform supports backup and restore of persistent data and configuration. The icon library supports device-type icons and sanitized SVG/PNG uploads to improve inventory and topology presentation.

### System Health

System Health displays platform runtime and operational data, including engine state, last successful cycle, WebSocket clients, discovery jobs, database latency, stored metric samples and aggregates, active alerts, notification deliveries, sessions, and disk information.

## Real-time operation and data persistence

Background monitoring workers collect network, service, and metric data. Relevant updates are sent to authenticated clients through WebSocket. Inventory, settings, samples, alerts, layouts, and saved views are persisted in the active database.

WebSocket authentication occurs through the private protocol after connection rather than through a URL credential. Retention and aggregation work is separated from probe cycles so historical processing does not block routine monitoring.

## Security model

- WinRM, SSH, SNMP, database, and notification secrets are encrypted at rest.
- Role permissions are enforced by the backend as well as hidden in the UI where appropriate.
- Provider capabilities are validated before they are offered for metric configuration.
- One active integration per device prevents contradictory collection sources.
- Database migration validates compatibility and disables mutable settings while running.
- Initial administration requires a one-time bootstrap token.

## Current boundaries

- SNMP currently focuses on metrics and interface monitoring, not operating-system service discovery.
- Generic SNMP CPU and memory are deliberately excluded because vendors expose them differently.
- SNMP interface traffic and utilization require two valid counter samples.
- Linux event collection and vendor-specific SNMP enrichment depend on target capabilities and provider evolution.
- Manual device-dependency configuration is not part of the product; use links and redundancy groups.
- Reports provide calculated availability, but contractual SLA targets per monitored service are not yet configurable.

## Suggested demonstration flow

1. Register devices, links, and a redundancy group.
2. Organize Network Topology and save a personal view.
3. Configure WinRM for Windows or SSH for Linux, discover services, and add a monitored service.
4. Demonstrate a controlled service state change, alert, notification, acknowledgement, and recovery.
5. Discover and enable metrics, then show their values on the device card and topology node.
6. Configure an SNMP device, select interfaces, and show calculated traffic after the second collection.
7. Show Alerts, History, Reports, Settings, and System Health to complete the operational narrative.
