# Tactus branding

The selected identity is the original **E: T and beat dot** direction, accepted on
2026-09-30. The rounded T represents the name and the action; the detached dot
marks the contact and beat. The master keeps this silhouette without resonance arcs.
The favicon is this same **T and detached dot**, with no rings, letters or wordmark
added. Its dark tile preserves contrast in both light and dark browser chrome.

The banner pairs the unchanged mark with a separate resonance motif: cropped arcs,
beat points and quiet timing guides on its right side. The public-facing headline is
**Produce music with code. Built for agents.** The supporting line is
**Arrange, render, analyze, and refine.** The tagline and banner direction were accepted
on 2026-09-30. "Produce" emphasizes the workflow of making and refining a finished
work, while analysis describes objective observations rather than aesthetic judgment.
It emphasizes programmable creation, code and agent use, following
the outcome-led approach of [Remotion](https://www.remotion.dev/) and
[HyperFrames](https://github.com/heygen-com/hyperframes). The implementation language
belongs in the technical documentation rather than the banner tagline.

## Assets

| File | Use |
| --- | --- |
| `tactus-logo.svg` | Canonical, scalable mark with a transparent background |
| `tactus-logo.png` | 512 × 512 transparent raster export |
| `favicon.svg` | Mark on a dark tile, suitable for light and dark browser chrome |
| `favicon.ico` | Dark tile at 16, 32 and 48 pixels |
| `favicon-16.png`, `favicon-32.png`, `favicon-48.png` | Individual dark tile exports |
| `apple-touch-icon.png` | 180 × 180 opaque dark tile |
| `tactus-icon-512.png` | 512 × 512 opaque dark tile |
| `tactus-banner.png` | 1200 × 400 dark banner used by the repository README |
| `banner.html` | Editable banner layout; render at 1200 × 400 |
| `index.html` | Asset overview, downloads and favicon previews at actual pixel sizes |

## Visual conventions

- Signal yellow: `#FFD700`.
- Dark background: `#121212`; panel surface: `#1E1E1E`.
- Main text: `#E0E0E0`.
- Wordmark: Outfit, weight 500; timing labels: IBM Plex Mono, weight 400.

The dark palette and typography continue the archived agent-daw web identity.
Use the transparent mark on a dark background; use the dark tile on light surfaces.
Keep the dot separate from the stem and preserve the mark's proportions.

The SVG is a clean geometric reconstruction of the selected imagegen draft.
Other candidates remain local, Git-ignored exploration material. The favicon SVG
is a standalone derivative of the master with a dark background; keep its mark in
sync with `tactus-logo.svg`. PNG and ICO files are derived exports.

The Codex plugin's `interface.composerIcon` and `interface.logo` use the same dark
T icon via paths relative to the repository/plugin root, following the
[plugin asset path convention](https://developers.openai.com/plugins/build/plugins).
Package metadata, CLI help and both host manifests share the headline above.

To reproduce the banner, serve this directory, open `banner.html`, wait for
`document.fonts.ready` and the logo to load, then capture the 1200 × 400 viewport.
Its Google Fonts stylesheet requires network access when regenerating the banner;
the exported PNG has no external dependencies. SVG rasterization must preserve
alpha for the logo and use an opaque dark background for the icon tiles.
