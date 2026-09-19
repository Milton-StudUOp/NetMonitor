from datetime import datetime, timezone


def selected_interfaces(rows: list[dict] | None, selected: list[int] | None) -> list[dict]:
    if not selected:
        return list(rows or [])
    wanted = {int(value) for value in selected}
    return [row for row in rows or [] if int(row.get("index", -1)) in wanted]


def enrich_interface_rates(rows: list[dict] | None, previous: list[dict] | None,
                           collected_at: datetime, previous_at: datetime | None) -> list[dict]:
    old = {int(row.get("index", -1)): row for row in previous or []}
    elapsed = (collected_at - previous_at).total_seconds() if previous_at else 0
    output = []
    for row in rows or []:
        value = dict(row); prior = old.get(int(row.get("index", -1)))
        if prior and elapsed > 0:
            for counter, target in (("bytes_received", "in_bps"), ("bytes_sent", "out_bps")):
                current, old_value = row.get(counter), prior.get(counter)
                if isinstance(current, (int, float)) and isinstance(old_value, (int, float)) and current >= old_value:
                    value[target] = round((current - old_value) * 8 / elapsed, 2)
            speed = row.get("speed_bps")
            if isinstance(speed, (int, float)) and speed > 0:
                total = (value.get("in_bps") or 0) + (value.get("out_bps") or 0)
                value["utilization_percent"] = round(total * 100 / speed, 2)
        output.append(value)
    return output
