# Agent tools and connection diagnostics

- Status: Deployed; offline, pinned runtime/public-provider, cloud model and browser connection checks passed
- Updated: 2026-10-29
- Requirements: FR-001, FR-011, FR-018, FR-021; NFR-001, NFR-003, NFR-005

## Problem and behavior

The minimal deployment only configured remote Codex. The upstream capability
catalog's search/read cards were installation guides, not evidence of tools loaded
into the Agent. Generic MCP connections could be saved without proving that the
server could initialize and advertise tools.

Enable DeerFlow's bundled, keyless public search and Jina Reader in the shared
ACK/local/single-host configuration. Read URLs are screened for HTTP(S), public
addresses, ports 80/443 and absent embedded credentials before delegating to Jina.
Search queries and read URLs go to external providers; no privacy or availability
guarantee follows. Fetched content is untrusted reference material. Host shell,
filesystem, browser login and private data connectors are not enabled by this fix.

Use the pinned runtime's supported PluginContribution/BrowserAssets contract for
a Tools & connections page. Its internal diagnostics actions remain behind Go
authentication and the existing admin runtime gate. They additionally reject
non-admin and internal principals. Native `loaded` proves provider resolution,
not successful execution. Saved MCP definitions display configured/disabled.

A deliberate connection test snapshots one saved platform or current user's
personal definition and reuses DeerFlow's selected-server discovery, credential,
personal authorization, lifecycle and session machinery. The client cannot supply
another owner, URL, command or headers. Only initialize/list_tools runs; no business
tool is called. Bound the test to 20 seconds and one in-flight check per admin.
Report discovery success (including zero tools), missing, disabled, unavailable,
busy and timeout separately. Return bounded tool names, not raw configs or errors.

Existing Capability center still owns MCP creation/editing and secrets. Installing
GitHub/Notion/SQL requires an appropriate MCP endpoint and explicit authorization.
The catalog alone never supplies those permissions or a working connector. Tools
are assembled on the next chat run; an already-running message is not mutated.

## Acceptance

- Fresh deployments load public search/read with and without a home Worker.
- Provider assembly, plugin assets and default runtime schema pass on the pinned
  upstream; actual public search/read have independent bounded smoke checks.
- Private/metadata/local/credential-bearing URLs are rejected before delegation.
- A real MCP metadata fixture advertises a tool without executing it.
- Unknown/disabled servers and non-admin callers never initiate discovery; personal
  discovery binds the authenticated owner. Exceptions never expose credential text.
- The deployed browser page shows actual loaded/configured states and a real test
  result. One bounded real chat proves model selection and tool responses; discovery
  alone does not establish chat execution or private data permissions.

## Evidence

The admitted cloud chat actually selected `web_search` and `web_fetch`, received
nonempty search results and the requested public page, and completed successfully.
The browser page showed three loaded native tools and discovered three exposed
Codex MCP tools without submitting native work. See the sanitized
[receipt](../verification/tools-and-connections-2026-10-29.json). A preceding probe
using an obsolete model profile name was rejected before admission (HTTP 400,
empty run list); its attempted intent remains preserved and was not replayed.
