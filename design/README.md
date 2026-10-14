# Tactus design

The shared home for Tactus visual style, tokens, interactive specimens and brand
assets. Start here when building a widget or exploring a Studio surface.

The listening and review interface is no longer built here: it is the separate
`audition-ui` package, which owns its components and its own copy of these tokens
(taken 2026-10-14, not synchronized). The tokens below serve the Tactus brand assets
and this specimen.

| File | Responsibility |
| --- | --- |
| [tokens.css](tokens.css) | Shared color, typography, spacing, density and state values |
| [index.html](index.html) | Interactive reference: audio widgets, Studio composition and token inspection |
| [assets/](assets/index.html) | Canonical logo, favicon, banner, editable banner source and downloads |

## Adopted direction and open choices

Accepted on September 30, 2026: the T and beat-dot identity, banner and copy, dark
palette, restrained panels, and the refined waveform treatment from the v02 study.
The specimen preserves that visual baseline. Compact density with fine borders is
its starting configuration; comfortable density and layered/flat boundaries remain
comparison variants. Their availability does not prescribe a layout for every widget.

The specimen is maintained reference material, not a shipped component library or
Studio application. It uses synthetic audio and page-local feedback. Runtime
integration, returning feedback to an agent, component packaging, and the Studio
interaction model remain open. UI typography uses local system fonts; the final
choice and distribution of UI fonts have not been settled.

## Visual principles

- Give audio, measurements and the current selection the most visual weight.
  Dark neutral surfaces, fine separators and limited decoration keep dense work legible.
- Use yellow for the brand, primary actions, focus and selection; teal for audio;
  periwinkle for MIDI. Warning and error colors have separate meanings. Always pair
  a state color with text or a recognizable control state.
- Keep the rounded T and detached dot recognizable at small sizes. Resonance arcs
  belong to banners and welcome surfaces; working views prioritize data.
- Use monospaced, tabular figures for times and measurements. Show units, scope and
  provenance beside values. An observation does not imply an aesthetic verdict.
- Compose a larger workspace from the same controls, plots and state treatments
  used by small widgets. Code remains the source of creative decisions; a visual
  preview does not establish another editable work model.
- Preserve visible keyboard focus, labeled controls, disabled states and readable
  narrow layouts. The specimen demonstrates these conventions; it is not a full
  accessibility certification.

## Tokens and reuse

Import [tokens.css](tokens.css) and consume semantic variables:

```html
<link rel="stylesheet" href="path/to/design/tokens.css">
<style>
  .audio-panel {
    background: var(--surface-panel);
    color: var(--text-primary);
    border: 1px solid var(--border-panel);
    border-radius: var(--radius);
    padding: var(--panel-pad);
  }
</style>
```

| Token family | Meaning |
| --- | --- |
| `--color-*` | Base palette; prefer semantic tokens in components |
| `--surface-*`, `--border-panel`, `--text-*` | Surface and text hierarchy |
| `--accent-primary`, `--focus-ring`, `--selection-fill` | Actions, focus and selected controls |
| `--audio-*`, `--midi-*`, `--status-*` | Content and state meanings |
| `--font-*`, `--space-*`, `--panel-pad`, `--control-height`, `--row-height`, `--radius`, `--font-size` | Shared UI typography and dimensions |
| `--wave-*` | Waveform rulers, grid, selection and hover treatments |
| `--brand-*` | Banner typography and decorative treatments |

Values are owned by the CSS file, rather than duplicated in this guide or a second
JSON registry. Component geometry and the specimen's layout stay in `index.html`.
Canvas drawing reads the same computed color tokens. Translucent selection, audio
and MIDI states derive from their semantic colors with CSS color-mix; changing a
semantic color updates both the foreground and its related fills. Shared spacing
steps are consumed by component padding, margins and gaps; plot geometry keeps
its own dimensions. The token tab displays the
current computed values and links to the complete source stylesheet.

The default is compact density with line boundaries. To preview alternatives, set
`data-density="comfortable"` and/or `data-boundary="layer"` or `"flat"` on `<html>`.
These attributes affect presentation only. A specimen selector never modifies the
stylesheet or saves a product preference.

Brand typography uses Outfit for the wordmark and IBM Plex Mono for timing labels.
The UI specimen deliberately uses system UI and monospace stacks so it works offline;
these roles are separate tokens. Importing tokens does not download a font.

## Waveform and interaction reference

The waveform treatment was informed by Solfege's WaveViz and Timeline. This specimen
implements its own canvas renderer without a Solfege or React dependency.

- Each visible bucket scans all covered samples for maximum absolute amplitude.
  The filled, mirrored peak envelope is an overview, not a signed sample waveform.
- Both candidates use the same explicitly labeled display gain. Display gain does
  not change playback or the reported whole-clip sample peak and RMS.
- Seconds and bar rulers provide separate context. The example's 108 BPM grid comes
  from its synthesis settings, not a beat detector. Real views must identify their
  grid source and accommodate audio without a chosen beat grid.
- Click to seek; drag to select; drag range edges or edit start/end values to refine
  a selection. Selection playback stops at its end. Zoom and pan change the viewport.
- Arrow keys seek, Shift increases the step, Home/End seek to clip edges and Escape
  clears the selection. Playback begins only after a user action.
- A/B switching preserves position. The two eight-second candidates, waveform and
  measurements share the same generated sample buffers. Output names in the Studio
  scene are illustrative; selecting them does not load separate stems.
- Form submission displays a result on the page. It does not contact an agent or
  save a work. The short Python snippet is illustrative and is not executed.

## Brand assets

The master is the original T and detached beat dot. Keep the dot separate, preserve
proportions, and use the dark tile on light surfaces. The logo and favicon have no
resonance arcs; the banner uses cropped arcs, beat points and quiet timing guides.

**Produce music with code. Built for agents.**

**Arrange, render, analyze, and refine.**

“Produce” emphasizes making and refining a finished work. The implementation
language belongs in technical documentation. The outcome-oriented copy was informed
by [Remotion](https://www.remotion.dev/) and
[HyperFrames](https://github.com/heygen-com/hyperframes).

| Asset | Use |
| --- | --- |
| [tactus-logo.svg](assets/tactus-logo.svg) | Canonical scalable mark, transparent background |
| [tactus-logo.png](assets/tactus-logo.png) | Transparent 512 × 512 export |
| [favicon.svg](assets/favicon.svg) | Same mark on a dark tile |
| [favicon.ico](assets/favicon.ico) | Dark tile at 16, 32 and 48 pixels |
| [16 px](assets/favicon-16.png), [32 px](assets/favicon-32.png), [48 px](assets/favicon-48.png) | Individual favicon exports |
| [apple-touch-icon.png](assets/apple-touch-icon.png) | Opaque 180 × 180 tile |
| [tactus-icon-512.png](assets/tactus-icon-512.png) | Opaque 512 × 512 tile; plugin logo |
| [tactus-banner.png](assets/tactus-banner.png) | 1200 × 400 repository banner |
| [banner.html](assets/banner.html) | Editable banner layout, consuming shared tokens |

SVG geometry is the master; standalone SVG, PNG and ICO exports embed fixed colors.
After a brand-color change in tokens, update the standalone SVG fills and regenerate
the derived exports. The favicon SVG uses the same geometry with a dark background.
Preserve alpha for the transparent logo and an opaque background for icon tiles.

To regenerate the banner, serve this directory, open `assets/banner.html`, wait for
`document.fonts.ready` and logo decoding, and capture a 1200 × 400 viewport. Its Google
Fonts stylesheet needs network access; exported PNGs and the main specimen do not.
Codex manifest icon paths are relative to the plugin root, following the
[plugin asset convention](https://developers.openai.com/plugins/build/plugins).

## Preview and maintenance

From the repository root:

```bash
uv run python -m http.server 4186 --bind 127.0.0.1 --directory design
```

Open `http://localhost:4186/`. When working remotely, forward the port with
`ssh -L 4186:localhost:4186 USER@HOST`. Reuse an existing preview server when possible.

Update this guide when a visual rule changes, tokens when a shared value changes,
and the specimen when an interaction needs a reference. Check widget and Studio
layouts at desktop and narrow widths, keyboard navigation, A/B playback, selection
and asset loading. Keep historical candidates in the local ignored exploration
area. Accepted reference material belongs here and is included in source archives;
the Python wheel continues to contain only the runtime package.
