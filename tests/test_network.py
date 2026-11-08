import json
from pathlib import Path

import nacl_sim
import subnets

ROOT = Path(__file__).resolve().parent.parent


def test_subnet_allocation():
    rows = {r["subnet"]: r for r in subnets.allocate()}
    assert rows["app"]["cidr"] == "10.20.0.0/22" and rows["app"]["usable_hosts"] == 1022
    assert rows["public"]["cidr"] == "10.20.4.0/24" and rows["public"]["broadcast"] == "10.20.4.255"
    assert rows["data"]["cidr"] == "10.20.5.0/25" and rows["data"]["last_usable"] == "10.20.5.126"
    assert rows["management"]["cidr"] == "10.20.5.128/27" and rows["management"]["usable_hosts"] == 30


def test_nacl_decides_every_sample_packet_correctly():
    rules = nacl_sim.load_rules(str(ROOT / "network" / "nacl.json"))
    for line in open(ROOT / "network" / "packets_sample.jsonl"):
        p = json.loads(line)
        assert nacl_sim.decide(rules, p)[0] == p["expected"], p["id"]


def test_abusive_range_is_denied_before_any_allow():
    rules = nacl_sim.load_rules(str(ROOT / "network" / "nacl.json"))
    for port in (22, 80, 443, 50000):
        pkt = {"direction": "inbound", "protocol": "tcp", "port": port, "address": "198.51.100.77"}
        assert nacl_sim.decide(rules, pkt) == ("deny", 90)
