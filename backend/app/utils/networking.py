from ipaddress import ip_network

from app.models.device import Device


def get_network_warning(source: Device, destination: Device) -> str | None:
    """Return a topology warning when declared endpoint networks do not overlap."""
    source_value = (source.network or "").strip()
    destination_value = (destination.network or "").strip()
    if not source_value or not destination_value:
        return None

    try:
        source_network = ip_network(source_value, strict=False)
        destination_network = ip_network(destination_value, strict=False)
    except ValueError:
        return "Sub-rede CIDR inválida em uma das pontas do enlace."

    if source_network.version != destination_network.version:
        return "As pontas usam famílias IP diferentes (IPv4/IPv6)."
    if not source_network.overlaps(destination_network):
        return (
            f"Redes distintas: {source_network} e {destination_network}. "
            "A comunicação requer roteamento configurado."
        )
    return None
