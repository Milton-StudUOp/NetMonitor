# Deployment assets

The application itself is portable across Linux, macOS, and Windows. It finds
the repository root relative to its installed Python package and reads `.env`
from the project or backend directory.

## Linux

`systemd/` contains templates, not ready-to-copy services. Before installing,
replace `@INSTALL_DIR@`, `@SERVICE_USER@`, and `@SERVICE_GROUP@` with values
from the target host. See [Operations](../docs/OPERATIONS.md) for the command
and high-availability topology.

## macOS and Windows

Do not use the systemd templates. Start the backend from the local
`<INSTALL_DIR>/backend` using that installation's virtual environment, then
register the same command with `launchd` on macOS or the Windows Service Control
Manager/an approved service wrapper. Keep the environment file and persistent
database outside source control on every platform.
