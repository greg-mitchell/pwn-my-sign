# Display calibration

The first generated image was a 1280 × 720 calibration image with grayscale and text elements testing visible margin.
I took a photograph of the displayed image after uploading from my laptop.

## Measurement

The 4080 × 3072 photograph was aligned to the source using SIFT features and a RANSAC perspective estimate.
373 of 471 candidate matches were inliers. The median interior alignment residual was about **0.24 display pixels**
(approximately 0.56 camera pixels); the 95th-percentile camera residual was about 1.50 pixels.

After rectification, the strongest intensity transition was measured in blank edge strips:

| Edge | Median inset, display px | 10th–90th percentile |
| --- | --- | --- |
| Top | 23.5 | 18.5–25.5 |
| Left | 6.5 | 6.5–7.5 |
| Right | 18 | 18–18 |
| Bottom | 7 | 7–9 |

These are **frame/shadow transition estimates**, not precise physical crop boundaries. Bevel, shadow, glare, lens
distortion, and extrapolation outside the matched interior affect the estimates. The small interior residual does not give
equally precise edge measurements or establish a firmware offset.

## Device guidance

For this sign, keep text at least **32 pixels inside every edge** where practical. The recommended text area is:

```text
x ∈ [32, 1248), y ∈ [32, 688)
width 1216, height 656
```

This is device-specific visibility advice, not a constraint on artwork or layout templates.
Artwork and backgrounds may use the full 1280 × 720 canvas. Text outside the recommended area is allowed and may be
partially obscured by the frame; the renderer currently emits no automatic visibility warning.
Keep the proven encoder geometry. The diagnostic's corner labels intentionally probe the physical edges.

The grayscale ramp looked broadly correct to the owner. This photo cannot establish absolute brightness, gamma, or
16 distinct physical shades: the darkest patches measured similarly, and a glare bump near level 6 interrupted
local monotonicity. The wire format supports 16 values; photometric calibration remains unclaimed.

## Reproduce

```sh
uv sync --locked --extra investigation
uv run --no-sync python scripts/investigation/analyze_photo.py private/photos/<your-photo-of-a-test-image>.jpg
```

The tool writes `measurements.json`, `rectified-photo.png`, and a source/photo comparison with the proposed inset to
`private/photo-analysis/`. The original image is never modified. These are investigation artifacts, outside the production
test suite; normal tests use synthetic pixels and sanitized captured payloads.
