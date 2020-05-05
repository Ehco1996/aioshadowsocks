from prometheus_client import Counter, Gauge, Histogram

# METRICS
CONNECTION_MADE_COUNT = Counter(
    "connection_made_count", "shadowsocks connection made number"
)
ACTIVE_CONNECTION_COUNT = Gauge(
    "active_connection_count", "shadowsocks active connection count"
)
NETWORK_TRANSMIT_BYTES = Counter(
    "network_transmit_bytes", "shadowsocks network transmit bytes"
)
ENCRYPT_DATA_TIME = Histogram(
    "encrypt_data_time_seconds", "shadowsocks encrypt data time seconds"
)
DECRYPT_DATA_TIME = Histogram(
    "decrypt_data_time_seconds", "shadowsocks decrypt data time seconds"
)

FIND_ACCESS_USER_TIME = Histogram(
    "find_access_user_time_seconds", "time to find access user"
)
