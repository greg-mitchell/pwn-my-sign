import argparse
import json
from pathlib import Path

import cv2
import numpy as np

parser = argparse.ArgumentParser(
    description="Compare a Dory photo with its source image"
)
parser.add_argument("photo", type=Path)
parser.add_argument("--source", type=Path, default=Path("private/mac-test.png"))
parser.add_argument("--output", type=Path, default=Path("private/photo-analysis"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
source = cv2.imread(str(args.source), cv2.IMREAD_GRAYSCALE)
photo = cv2.imread(str(args.photo))
if source is None or photo is None:
    raise ValueError("Source image or photograph could not be loaded")
if source.shape != (720, 1280):
    raise ValueError("This diagnostic expects the 1280x720 MAC test card")
cv2.setRNGSeed(0)
sift = cv2.SIFT_create(nfeatures=4000)
source_keys, source_descriptors = sift.detectAndCompute(source, None)
photo_keys, photo_descriptors = sift.detectAndCompute(
    cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY), None
)
pairs = cv2.BFMatcher().knnMatch(source_descriptors, photo_descriptors, k=2)
matches = [first for first, second in pairs if first.distance < 0.7 * second.distance]
source_points = np.float32([source_keys[match.queryIdx].pt for match in matches])
photo_points = np.float32([photo_keys[match.trainIdx].pt for match in matches])
homography, mask = cv2.findHomography(source_points, photo_points, cv2.RANSAC, 2)
if homography is None or mask is None:
    raise ValueError("Source and photograph could not be registered")
inliers = mask.ravel().astype(bool)
projected = cv2.perspectiveTransform(
    source_points.reshape(-1, 1, 2), homography
).reshape(-1, 2)
residual = np.linalg.norm(projected[inliers] - photo_points[inliers], axis=1)
rectified = cv2.warpPerspective(photo, np.linalg.inv(homography), (1280, 720))
gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY).astype(float)
blur = cv2.GaussianBlur(gray, (5, 5), 0.8)
# Blank edge strips avoid text; the top samples also exclude the central glare.
columns = np.r_[80:450, 800:1200]
rows = np.r_[230:450, 590:650]
edge_positions = {
    "top": np.argmax(np.diff(blur[2:35, columns], axis=0), axis=0) + 2.5,
    "left": np.argmax(np.diff(blur[rows, 0:25], axis=1), axis=1) + 0.5,
    "right": 1279.5
    - (np.argmin(np.diff(blur[rows, 1250:1280], axis=1), axis=1) + 1250.5),
    "bottom": 719.5
    - (np.argmin(np.diff(blur[698:720, columns], axis=0), axis=0) + 698.5),
}
edges = {
    edge: {
        "median": float(np.median(values)),
        "p10": float(np.percentile(values, 10)),
        "p90": float(np.percentile(values, 90)),
    }
    for edge, values in edge_positions.items()
}
grays = []
for level in range(16):
    x = 40 + level * 75
    patch = float(np.median(gray[493:537, x + 12 : x + 63]))
    reference = float(
        np.median(
            np.r_[
                gray[445:460, x + 12 : x + 63].ravel(),
                gray[602:614, x + 12 : x + 63].ravel(),
            ]
        )
    )
    grays.append(
        {
            "level": level,
            "camera_gray_median": patch,
            "nearby_white_median": reference,
            "ratio": patch / reference,
        }
    )
scale_points = np.float32([[640, 360], [641, 360], [640, 361]])
scale_projected = cv2.perspectiveTransform(
    scale_points.reshape(-1, 1, 2), homography
).reshape(-1, 2)
photo_pixels_per_display_pixel = float(
    np.mean(np.linalg.norm(scale_projected[1:] - scale_projected[0], axis=1))
)
report = {
    "photo": args.photo.name,
    "source": str(args.source),
    "source_size": [1280, 720],
    "photo_size": [photo.shape[1], photo.shape[0]],
    "matches": len(matches),
    "inliers": int(inliers.sum()),
    "median_reprojection_error_photo_px": float(np.median(residual)),
    "p95_reprojection_error_photo_px": float(np.percentile(residual, 95)),
    "photo_pixels_per_display_pixel_at_center": photo_pixels_per_display_pixel,
    "median_reprojection_error_display_px_approx": float(np.median(residual))
    / photo_pixels_per_display_pixel,
    "source_inlier_bounds": [
        source_points[inliers].min(axis=0).tolist(),
        source_points[inliers].max(axis=0).tolist(),
    ],
    "homography_source_to_photo": homography.tolist(),
    "bezel_or_shadow_transition_insets_display_px": edges,
    "edge_method": "Strongest blurred intensity transition in blank edge strips after perspective rectification. Top excludes central glare.",
    "edge_limitations": "Estimates include shadow and bevel; they do not locate exact physical occlusion or firmware cropping. Edge extrapolation and lens distortion are not represented by the interior match residual.",
    "recommended_content_inset_display_px": 32,
    "recommended_content_box_xyxy_exclusive": [32, 32, 1248, 688],
    "grayscale_camera_measurements": grays,
    "grayscale_limitations": "Nonuniform lighting, reflections and camera tone processing prevent absolute gray calibration. Darkest patches are similar and a glare bump near level 6 reverses local monotonicity.",
}
(args.output / "measurements.json").write_text(json.dumps(report, indent=2) + "\n")
cv2.imwrite(str(args.output / "rectified-photo.png"), rectified)
comparison = np.full((800, 2560, 3), 255, dtype=np.uint8)
comparison[80:, :1280] = cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
comparison[80:, 1280:] = rectified
cv2.putText(
    comparison, "Source image", (24, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 0, 0), 2
)
cv2.putText(
    comparison,
    "Photo aligned to source coordinates",
    (1304, 34),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.85,
    (0, 0, 0),
    2,
)
for origin in (0, 1280):
    cv2.putText(
        comparison,
        "Green: recommended 32px content inset",
        (origin + 24, 64),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 100, 0),
        1,
    )
    cv2.rectangle(comparison, (origin + 32, 112), (origin + 1247, 767), (0, 170, 0), 2)
cv2.imwrite(str(args.output / "comparison.png"), comparison)
print(
    json.dumps(
        {
            "inliers": report["inliers"],
            "median_error_display_px": report[
                "median_reprojection_error_display_px_approx"
            ],
            "edge_transition_insets_display_px": edges,
            "output": str(args.output),
        },
        indent=2,
    )
)
