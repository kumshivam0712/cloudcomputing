"""Variable-length subnetting of 10.20.0.0/16 (Task 5): largest requirement first, each subnet
placed right after the previous one, smallest prefix with 2^(32-prefix) - 2 >= hosts.

    python scripts/subnets.py            prints the table (Markdown)
"""
import ipaddress
import json
import sys

BLOCK = ipaddress.ip_network("10.20.0.0/16")
NEEDS = {"app": 1000, "public": 250, "data": 100, "management": 20}


def smallest_prefix(hosts):
    for prefix in range(30, 0, -1):
        if 2 ** (32 - prefix) - 2 >= hosts:
            return prefix
    raise ValueError(hosts)


def allocate(block=BLOCK, needs=NEEDS):
    rows, cursor = [], int(block.network_address)
    for name, hosts in sorted(needs.items(), key=lambda kv: -kv[1]):
        prefix = smallest_prefix(hosts)
        net = ipaddress.ip_network((cursor, prefix))
        assert net.subnet_of(block), f"{name} does not fit in {block}"
        rows.append({
            "subnet": name, "hosts_needed": hosts, "network": str(net.network_address), "prefix": f"/{prefix}",
            "cidr": str(net), "first_usable": str(net.network_address + 1),
            "last_usable": str(net.broadcast_address - 1),
            "broadcast": str(net.broadcast_address), "usable_hosts": 2 ** (32 - prefix) - 2,
        })
        cursor = int(net.broadcast_address) + 1
    return rows


def main():
    rows = allocate()
    if "--json" in sys.argv:
        print(json.dumps(rows, indent=2))
        return
    print("| Subnet | Hosts needed | Network address | Prefix | Usable host range | Broadcast | Usable hosts |")
    print("|---|---:|---|---|---|---|---:|")
    for r in rows:
        print(f"| {r['subnet']} | {r['hosts_needed']} | {r['network']} | {r['prefix']} | "
              f"{r['first_usable']} - {r['last_usable']} | {r['broadcast']} | {r['usable_hosts']} |")


if __name__ == "__main__":
    main()
