# M4.4 memory diagrams

All six diagrams describe the **Proposed** design in the
[technical spec](../../specs/m4-memory-technical-design.md). They are not deployment
or runtime evidence.

The `.mmd` files are the editable Mermaid sources; same-name `.svg` files are
rendered exports for Markdown viewers. Change the source first, then regenerate
the export. The JSON file keeps the exports legible with a neutral palette and
CJK font fallbacks. No application dependencies were added for these diagrams.

Render from the repository root with an externally installed
`@mermaid-js/mermaid-cli@11.4.2` and a local browser:

```bash
mmdc -i docs/diagrams/personal-memory/01-capture.mmd \
  -o docs/diagrams/personal-memory/01-capture.svg \
  -c docs/diagrams/personal-memory/mermaid-config.json -w 1600
```

Repeat for each `.mmd` file. A custom browser executable may be supplied through
Mermaid CLI's `-p` Puppeteer configuration; keep machine-specific paths outside the
repository. Rendering uses only synthetic design labels, without conversations,
credentials or runtime databases. Review all exports after regeneration.
