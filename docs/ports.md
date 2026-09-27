# Fixed Ports

All host ports are in the `5xxxx` range by design. These are fixed for the life of
this project. Scripts under `scripts/` assume these exact values — do not change
them without updating `docker-compose.yml`, `.env.example`, and every script
together.

| Service                          | Host Port(s)         |
|-----------------------------------|-----------------------|
| Prometheus                        | 59090                |
| Grafana                           | 53300                |
| Loki                               | 53100                |
| Tempo (query API)                  | 53201                |
| OTel Collector (grpc / http)       | 54317 / 54318        |
| Langfuse web                       | 54000                |
| Langfuse worker                    | 54001                |
| Langfuse Postgres                  | 55500                |
| Langfuse ClickHouse (http/native)  | 58123 / 59100        |
| Langfuse Redis                     | 56380                |
| Langfuse MinIO (api/console)        | 59002 / 59003        |
| incident-controller                 | 58006                |
| checkout-service                    | 58001                |
| cart-service                        | 58002                |
| pricing-service                     | 58003                |
| payment-service                     | 58004                |
| load-generator                      | 58005                |
| agents-api (native, optional)        | 58010                |

Every host port maps 1:1 to a distinct 5xxxx number (e.g. Prometheus 9090 → 59090,
Grafana's original 3300 → 53300) so the scheme stays easy to reconstruct from the
service's normal default port. Two exceptions: Tempo and incident-controller don't
follow their service's usual default (3200, 8000) because those exact ports were
already held by unrelated pre-existing local processes on this machine — 53201 /
58006 keep the same "5 + last 4 digits" pattern. Langfuse Postgres uses 55500
instead of 55433 because 55340–55439 falls inside a Windows-reserved (Hyper-V/WSL)
excluded port range on this machine (`netsh interface ipv4 show excludedportrange
protocol=tcp`) — check that command if a future port unexpectedly fails to bind.

Container-internal DNS names (used inside `infra/*` configs and service env vars,
unaffected by the host-port remap above) match the compose service names:
`prometheus`, `loki`, `tempo`, `otel-collector`, `checkout-service`, `cart-service`,
`pricing-service`, `payment-service`, `incident-controller`, `load-generator`,
`langfuse-web`, `langfuse-worker`, `lf-postgres`, `lf-clickhouse`, `lf-redis`,
`lf-minio`.
