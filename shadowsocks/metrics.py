import socket

from prometheus_client import Counter, Gauge, Histogram, Info

# METRICS
NODE_HOST_NAME = socket.gethostname()

SS_NODE_INFO = Info("ss_node", "ss node info")
SS_NODE_INFO.info({"ss_node_name": NODE_HOST_NAME})

CONNECTION_MADE_COUNT = Counter(
    "connection_made_count",
    "shadowsocks connection made number",
    labelnames=[
        "ss_node",
    ],
)
CONNECTION_MADE_COUNT = CONNECTION_MADE_COUNT.labels(ss_node=NODE_HOST_NAME)


ACTIVE_CONNECTION_COUNT = Gauge(
    "active_connection_count",
    "shadowsocks active connection count",
    labelnames=[
        "ss_node",
    ],
)
ACTIVE_CONNECTION_COUNT = ACTIVE_CONNECTION_COUNT.labels(ss_node=NODE_HOST_NAME)


NETWORK_TRANSMIT_BYTES = Counter(
    "network_transmit_bytes",
    "shadowsocks network transmit bytes",
    labelnames=[
        "ss_node",
    ],
)
NETWORK_TRANSMIT_BYTES = NETWORK_TRANSMIT_BYTES.labels(ss_node=NODE_HOST_NAME)


ENCRYPT_DATA_TIME = Histogram(
    "encrypt_data_time_seconds",
    "shadowsocks encrypt data time seconds",
    labelnames=[
        "ss_node",
    ],
)
ENCRYPT_DATA_TIME = ENCRYPT_DATA_TIME.labels(ss_node=NODE_HOST_NAME)


DECRYPT_DATA_TIME = Histogram(
    "decrypt_data_time_seconds",
    "shadowsocks decrypt data time seconds",
    labelnames=[
        "ss_node",
    ],
)
DECRYPT_DATA_TIME = DECRYPT_DATA_TIME.labels(ss_node=NODE_HOST_NAME)


FIND_ACCESS_USER_TIME = Histogram(
    "find_access_user_time_seconds",
    "time to find access user",
    labelnames=[
        "ss_node",
    ],
)
FIND_ACCESS_USER_TIME = FIND_ACCESS_USER_TIME.labels(ss_node=NODE_HOST_NAME)
