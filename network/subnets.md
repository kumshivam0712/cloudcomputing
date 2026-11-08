# Task 5 - Subnetting 10.20.0.0/16

Rules used: allocate from the largest requirement to the smallest, start at 10.20.0.0, place each
subnet immediately after the previous one, and use the smallest prefix that fits, where
usable hosts = 2^(32 - prefix) - 2. (Re-computed by `make subnets` / `python scripts/subnets.py`.)

## Working

| Subnet | Hosts needed | Smallest n with 2^n - 2 >= hosts | Prefix = 32 - n | Block size |
|---|---:|---|---|---:|
| app        | 1000 | n = 10: 2^10 - 2 = 1022 (n = 9 gives only 510) | /22 | 1024 addresses = 4 x /24 |
| public     |  250 | n = 8:  2^8 - 2 = 254 (n = 7 gives only 126)   | /24 | 256 |
| data       |  100 | n = 7:  2^7 - 2 = 126 (n = 6 gives only 62)    | /25 | 128 |
| management |   20 | n = 5:  2^5 - 2 = 30 (n = 4 gives only 14)     | /27 | 32 |

Placement (each network address = previous broadcast + 1):

1. **app** starts at 10.20.0.0. A /22 spans 1024 addresses = 10.20.0.0 - 10.20.3.255.
2. **public** starts at 10.20.3.255 + 1 = 10.20.4.0. A /24 spans 10.20.4.0 - 10.20.4.255.
3. **data** starts at 10.20.5.0. A /25 spans 128 addresses: 10.20.5.0 - 10.20.5.127.
4. **management** starts at 10.20.5.128. A /27 spans 32 addresses: 10.20.5.128 - 10.20.5.159.

Every network address is aligned to its block size (10.20.4.0 is a multiple of 256, 10.20.5.128
of 128 and of 32), so each block is a valid CIDR. Used: 10.20.0.0 - 10.20.5.159 (1,440 addresses);
10.20.5.160 - 10.20.255.255 is left free.

## Result

| Subnet | Network address | Prefix | Usable host range | Broadcast address | Usable hosts |
|---|---|---|---|---|---:|
| app        | 10.20.0.0   | /22 | 10.20.0.1 - 10.20.3.254     | 10.20.3.255 | 1022 |
| public     | 10.20.4.0   | /24 | 10.20.4.1 - 10.20.4.254     | 10.20.4.255 | 254 |
| data       | 10.20.5.0   | /25 | 10.20.5.1 - 10.20.5.126     | 10.20.5.127 | 126 |
| management | 10.20.5.128 | /27 | 10.20.5.129 - 10.20.5.158   | 10.20.5.159 | 30 |

## NACL for the public subnet (network/nacl.json)

| Dir | Rule | Proto | Ports | Address | Action | Why |
|---|---:|---|---|---|---|---|
| in  |  90 | all | all          | 198.51.100.0/24 | deny  | abusive range, blocked even on 80/443; lowest number so it is checked first |
| in  | 100 | tcp | 80           | 0.0.0.0/0       | allow | HTTP from anywhere |
| in  | 110 | tcp | 443          | 0.0.0.0/0       | allow | HTTPS from anywhere |
| in  | 120 | tcp | 22           | 10.20.5.128/27  | allow | SSH only from management |
| in  | 130 | tcp | 1024-65535   | 10.20.0.0/22    | allow | replies from app:8000 to the LB's ephemeral port |
| in  |  *  | all | all          | 0.0.0.0/0       | deny  | implicit default |
| out | 100 | tcp | 8000         | 10.20.0.0/22    | allow | LB -> app service |
| out | 110 | tcp | 1024-65535   | 0.0.0.0/0       | allow | replies to clients' ephemeral ports |
| out |  *  | all | all          | 0.0.0.0/0       | deny  | implicit default |

Check: `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check`
-> 6 / 6 correct (output in `results/task5/nacl_check.txt`).

Note (a property of every stateless NACL, not a mistake): outbound rule 110 must cover the whole
client ephemeral range 1024-65535, so it also lets out a TCP packet to port 8000 of a non-app host;
the NACL cannot tell a reply from a new connection because it keeps no connection state.
