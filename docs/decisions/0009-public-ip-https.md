# ADR 0009: Optional public IPv4 HTTPS edge

- Date: 2026-10-27
- Status: Accepted; actual deployment evidence is tracked separately in STATUS.

## Context

The owner deferred buying a domain and approved a separate minimum Singapore instance, migration of the existing cloud-created account/configuration, and authenticated public IP HTTPS. The Beijing deployment remains private for rollback. Mainland public IP websites have filing requirements; an extra port is not a filing alternative. Keep ADR 0008's private default and the local Mac profile unchanged.

## Decision

Add an explicit file-only opt-in renderer, `scripts/single_host_https.py`, for the existing single-host bundle. Preserve nginx on loopback 2027 and Go as the authentication/API boundary. Configure the exact assigned public IPv4 as Go's HTTPS origin and host, retaining internal health-check hosts. Restore the existing owner before public startup; never copy native host/Worker credentials.

Use the digest-pinned official Caddy 2.11.7 image with an explicit Let's Encrypt ACME issuer and `shortlived` profile. Keep certificate/account storage in separate persistent volumes. TCP 80 supports ACME validation and redirects; TCP 443 serves the app. Set the exact IP as `default_sni` for IP clients that omit SNI, and return 421 for unexpected HTTP hosts. Disable HTTP/3 and bind administration to host loopback. Publicly trusted certificate verification remains mandatory.

The edge uses host networking to reach the existing loopback listener without publishing another app port. Its root process has only `NET_BIND_SERVICE`, a read-only root filesystem, no Docker socket, bounded logs and a 128 MiB memory ceiling. This is an explicit edge exception to the four normal non-root application containers. It does not grant the runtime access to host Docker or the certificate volume. Host administrators remain trusted.

Write the new service into the bundle's existing Compose file, with an original-file backup and replay refusal. The bundle's start script explicitly selects that file; an automatically discovered override would otherwise be lost. The renderer does not purchase, migrate data, start services or request certificates.

## Alternatives and consequences

A domain would add registration and DNS lifecycle work the owner deferred. A self-signed certificate would introduce a browser trust exception. A native host Caddy service is feasible, but a fifth Compose service keeps the installation and restart path together. Bridge networking would require a different upstream route; host networking preserves the already verified loopback path, with the edge's host-network access stated explicitly.

IP certificates currently last about 160 hours. Configured automatic renewal and first issuance are distinct from observing a real renewal. Persistent storage, running Docker/Caddy and reachable validation ports are operational dependencies. This remains one small host with SQLite and no HA; bounded page checks do not prove model/Worker capacity. Cloud auto-renewal stays off under the selected one-month purchase; later pricing is not guaranteed.

See the [specification](../specs/single-host-public-ip.md), [operator guide](../single-host.md), [filing requirements](https://help.aliyun.com/zh/icp-filing/basic-icp-service/product-overview/icp-filing-requirements-for-a-regular-website), [IP certificate announcement](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability/) and [Caddy issuer configuration](https://caddyserver.com/docs/caddyfile/directives/tls).

## Retirement follow-up · 2026-10-27

The owner subsequently requested retiring the Beijing rollback host. Its final application home/configuration and consistent database are backed up and verified locally, and the node is now permanently unsubscribed and released. Singapore public access was rechecked afterward. The owner confirmed permanent unsubscription, accepted its rules and completed vendor identity verification. The cloud console confirms the resource is gone and the refund detail reports success; this changes the operational rollback arrangement, not the HTTPS architecture. See the [retirement receipt](../verification/beijing-retirement-2026-10-27.json).
