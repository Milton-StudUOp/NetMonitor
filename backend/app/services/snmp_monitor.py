import asyncio
import structlog
from typing import Optional, Dict

logger = structlog.get_logger()

# Standard SNMP OIDs for IF-MIB
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"   # 1=up, 2=down, 3=testing
OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"  # 1=up, 2=down, 3=testing
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"         # Speed in bps
OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.14"
OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"
OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"


async def query_snmp_interface(
    ip_address: str,
    snmp_index: int,
    community: str,
    port: int = 161,
) -> Dict:
    """
    Queries SNMP interface status and statistics via PySNMP or SNMP GET fallback.
    Returns dict with oper_status, admin_status, speed_mbps, octets, errors.
    """
    if not ip_address or not snmp_index:
        return {"is_up": False, "oper_status": "UNKNOWN", "details": "Missing IP or index"}

    try:
        from pysnmp.hlapi.asyncio import (
            getCmd,
            CommunityData,
            UdpTransportTarget,
            ContextData,
            ObjectType,
            ObjectIdentity,
            SnmpEngine,
        )

        error_indication, error_status, error_index, var_binds = await getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),  # v2c
            UdpTransportTarget((ip_address, port), timeout=2.0, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(f"{OID_IF_OPER_STATUS}.{snmp_index}")),
            ObjectType(ObjectIdentity(f"{OID_IF_ADMIN_STATUS}.{snmp_index}")),
            ObjectType(ObjectIdentity(f"{OID_IF_SPEED}.{snmp_index}")),
        )

        if error_indication or error_status:
            return {"is_up": False, "oper_status": "UNKNOWN", "details": str(error_indication or error_status)}

        oper_val = int(var_binds[0][1]) if var_binds else 2
        admin_val = int(var_binds[1][1]) if len(var_binds) > 1 else 2
        speed_bps = int(var_binds[2][1]) if len(var_binds) > 2 else 0

        oper_status = "UP" if oper_val == 1 else ("DOWN" if oper_val == 2 else "UNKNOWN")
        admin_status = "UP" if admin_val == 1 else ("ADMIN_DOWN" if admin_val == 2 else "UNKNOWN")

        return {
            "is_up": (oper_status == "UP"),
            "oper_status": oper_status,
            "admin_status": admin_status,
            "speed_mbps": speed_bps // 1000000 if speed_bps else None,
        }

    except Exception as e:
        logger.debug("snmp_query_fallback", error_type=type(e).__name__)
        # Simulated fallback for development/demo when SNMP target not reachable
        return {
            "is_up": False,
            "oper_status": "UNKNOWN",
            "admin_status": "UNKNOWN",
            "speed_mbps": None,
            "error": str(e),
        }
