"""
shadowsocks 报文结构

+----+-----+-------+------+----------+----------+
|VER | CMD |  RSV  | ATYP | DST.ADDR | DST.PORT |
+----+-----+-------+------+----------+----------+
| 1  |  1  |   1   |  1   | Variable |    2     |
+----+-----+-------+------+----------+----------+
"""

# CMDS
TRANSPORT_TCP = 0x01
TRANSPORT_UDP = 0x02


# ATYPS
ATYPE_IPV4 = 0x01
ATYPE_IPV6 = 0x04
ATYPE_DOMAINNAME = 0x03

ATYPE_MAP = {ATYPE_IPV4: "ipv4", ATYPE_IPV6: "ipv6", ATYPE_DOMAINNAME: "domain"}


def get_atype_for_human(atype):
    if atype in ATYPE_MAP:
        return ATYPE_MAP[atype]
    return "unknown"
