from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, DeviceStatus, DeviceType
from app.models.interface import Interface, InterfaceStatus
from app.models.link import Link, LinkStatus


async def analyze_probable_root_cause(
    failed_link: Link,
    db: AsyncSession
) -> Dict[str, str]:
    """
    Implements section §13 (Detecção de Possível Causa da Falha) of Technical Specification.
    Analyzes physical/logical chain between source device, interfaces, and destination device.
    Returns:
    {
      "root_cause": "POSSÍVEL FALHA ENTRE SWITCH_A E SWITCH_B",
      "suspect_components": ["Cabo Ethernet", "Media Converter", "Fibra Óptica", "Alimentação"],
      "details": "..."
    }
    """
    source_device = await db.get(Device, failed_link.source_device_id)
    dest_device = await db.get(Device, failed_link.destination_device_id)

    src_name = source_device.name if source_device else "Origem"
    dst_name = dest_device.name if dest_device else "Destino"

    # Case 1: Source device itself is OFFLINE
    if source_device and source_device.status == DeviceStatus.OFFLINE:
        return {
            "root_cause": f"Falha no equipamento de origem: {src_name}",
            "suspect_components": [src_name, "Fonte de Alimentação", "Cabo Elétrico"],
            "details": f"O equipamento de origem {src_name} ({source_device.ip_address}) não responde a ICMP/SNMP.",
        }

    # Case 2: Destination device itself is OFFLINE
    if dest_device and dest_device.status == DeviceStatus.OFFLINE:
        return {
            "root_cause": f"Falha no equipamento de destino: {dst_name}",
            "suspect_components": [dst_name, "Fonte de Alimentação", "Cabo Elétrico"],
            "details": f"O equipamento de destino {dst_name} ({dest_device.ip_address}) não responde a ICMP/SNMP.",
        }

    # Case 3: Check interface statuses if connected
    src_if = await db.get(Interface, failed_link.source_interface_id) if failed_link.source_interface_id else None
    dst_if = await db.get(Interface, failed_link.destination_interface_id) if failed_link.destination_interface_id else None

    if src_if and src_if.status == InterfaceStatus.DOWN:
        return {
            "root_cause": f"Interface física DOWN no equipamento {src_name} (Porta: {src_if.interface_name})",
            "suspect_components": [f"{src_name}:{src_if.interface_name}", "Cabo de Patch", "SFP / Transceiver"],
            "details": f"A porta {src_if.interface_name} em {src_name} reporta estado operacional DOWN via SNMP.",
        }

    if dst_if and dst_if.status == InterfaceStatus.DOWN:
        return {
            "root_cause": f"Interface física DOWN no equipamento {dst_name} (Porta: {dst_if.interface_name})",
            "suspect_components": [f"{dst_name}:{dst_if.interface_name}", "Cabo de Patch", "SFP / Transceiver"],
            "details": f"A porta {dst_if.interface_name} em {dst_name} reporta estado operacional DOWN via SNMP.",
        }

    # Case 4: Devices & Interfaces are UP, but Link physical communication is DOWN
    if source_device and source_device.device_type == DeviceType.MEDIA_CONVERTER:
        return {
            "root_cause": f"Possível falha no Media Converter {src_name} ou enlace de fibra",
            "suspect_components": [src_name, "Fibra Óptica", "Conversor de Mídia", "Alimentação AC/DC"],
            "details": f"Link {failed_link.name} interrompido no trecho do conversor de mídia {src_name}.",
        }

    return {
        "root_cause": f"POSSÍVEL FALHA DE COMUNICAÇÃO ENTRE {src_name} E {dst_name}",
        "suspect_components": ["Cabo Ethernet", "Media Converter", "Enlace de Fibra/Rádio", "Porta de Rede"],
        "details": f"Ambos equipamentos de ponta respondem, mas o canal {failed_link.name} ({failed_link.link_type}) encontra-se inoperante.",
    }
