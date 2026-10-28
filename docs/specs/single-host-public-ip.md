# Single-host public IP HTTPS

- Status: implemented and verified for the approved Singapore personal trial; 41 HTTP checks plus browser and controlled reboot acceptance. Existing Beijing deployment stays private.
- Requirements: FR-009, NFR-001, NFR-005–NFR-007.
- User direction: defer domain purchase and prioritize public browser access without buying a domain.

## Approved target

One Singapore SWAS international instance, amd64 Ubuntu 24.04, 2 vCPU / 2 GiB / 40 GiB. The current one-month preview is CNY39 before an existing coupon, CNY0 cash after it, with automatic renewal disabled. The BGP route is not China-optimized. This is a separate node; retain the Beijing node and online backup as rollback. Do not turn the earlier private-host approval into permission for this new destination.

Serve authenticated DeerMate using a publicly trusted IP certificate and an HTTPS edge on TCP 443. TCP 80 is for certificate validation/HTTPS redirect, never a plaintext login endpoint. Keep the existing nginx on loopback 2027 and all Worker/runtime/admin transport ports private. Change the Go canonical origin and exact Host allowlist to the assigned new IP while retaining health-check hosts. Preserve account identity and use a consistent SQLite backup. Do not transfer host native/Codex/Worker credentials.

Let's Encrypt IP certificates require its shortlived profile (currently 160 hours). Caddy must have persistent certificate storage, automatic renewal and a loopback-only administration API. Actual trusted IP issuance, normal-chain/SAN validation, configured renewal and certificate persistence across a host reboot are verified. A real renewal has not yet been observed. Do not replace publicly trusted TLS with a browser-warning bypass.

## Acceptance

1. Recheck the selected one-month quote, zero cash ceiling, no auto-renewal and exact target before submitting; never replay an uncertain order.
2. Pin the new SSH host key through the authenticated console; separately scoped 24-hour key, no Agent/X11/PTY or remote forwarding. Verify the effective restriction.
3. Migrate consistent account/configuration state, load pinned images and preserve the original private node. Never treat a worktree or a local app fixture as cloud isolation evidence.
4. Complete public IP certificate validation with no insecure TLS client override. Confirm HTTP redirects, HTTPS Secure/HttpOnly/SameSite cookies, exact Host/Origin/CSRF handling and anonymous API rejection.
5. Verify page/login/admin and bounded reads from outside the cloud host; confirm backend/Worker ports remain private, reboot persistence and real memory/disk headroom. Do not invoke models merely to verify TLS.
6. Record certificate validity and renewal configuration separately from an observed renewal. Record rollback and operator access without committing private identifiers/keys/databases.

## References

- [Alibaba Cloud filing requirements](https://help.aliyun.com/zh/icp-filing/basic-icp-service/product-overview/icp-filing-requirements-for-a-regular-website)
- [Let's Encrypt IP/short-lived availability](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability/)
- [Caddy ACME issuer/profile](https://caddyserver.com/docs/caddyfile/directives/tls)

## Verification · 2026-10-27

The approved one-month instance was paid at CNY0 cash. Existing cloud account identity/configuration was restored before public startup. The final renderer includes an exact default SNI for IP clients and explicit 421 rejection for unknown HTTP hosts. Initial HTTPS acceptance passed 24 checks and 40 bounded reads; controlled host reboot acceptance passed 17 checks. Browser workspace/admin sessions survived; the original certificate persisted. A separate cloud node confirmed six application/admin/Worker ports closed or filtered. Host headroom and limitations are in the [receipt](../verification/single-host-public-ip-2026-10-27.json). Source checks passed 103 tests (7 skipped) and 32 actual-chart/Compose/overlay/HTTPS contract checks. No model or home Worker task was executed.
