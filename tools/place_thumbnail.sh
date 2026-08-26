#!/bin/sh
# Move a freshly rendered thumbnail into place -- unless it differs from the
# committed one by so little that the difference is rendering noise rather than
# geometry.
#
# WHY THIS EXISTS. OpenSCAD's headless PNG output is deterministic on one host
# and not across hosts: a face-vs-face depth tie at a silhouette pixel gets
# broken differently by different CPUs. Measured, on this repo, at one pixel of
# 480,000. Without this, `make pr` on a machine whose CPU disagrees with
# whoever last committed rewrites the PNG, the developer commits the flip, and
# the next machine flips it back -- churn that says nothing about the model.
#
# Putting the tolerance HERE rather than in CI is what keeps it declared once.
# The committed PNG is only replaced when it is genuinely out of date, so CI
# needs nothing more than its ordinary `git diff --quiet -- thumbnails/`: a
# clean tree already means every thumbnail is current. See
# docs/design/initial-design.md, "Why not a pixel tolerance".
#
# Run from the repo root by the generated rules in build/parts.mk, because
# bin/magick bind-mounts $PWD at /work and cannot resolve a path outside it.
set -e

tmp=$1
target=$2
tol=${THUMB_TOLERANCE_PX:-50}

# Nothing committed yet -- there is no baseline to be noise against.
if [ ! -f "$target" ]; then
    mv "$tmp" "$target"
    exit 0
fi

# The ordinary case, and the reason this is not slow: identical bytes need no
# image comparison, so a no-op `make thumbnails` starts no containers at all.
if cmp -s "$tmp" "$target"; then
    rm -f "$tmp"
    exit 0
fi

# compare writes the metric to stderr and exits non-zero whenever the images
# differ at all, which at this point they are known to.
ae=$(./bin/magick compare -metric AE "$target" "$tmp" null: 2>&1 >/dev/null || true)
ae=${ae%% *}

case "$ae" in
    ''|*[!0-9]*)
        # Differing dimensions make compare error rather than count. That is a
        # real change by definition, so take the new render.
        echo "place_thumbnail: $target: cannot compare ('$ae'), taking the new render" >&2
        mv "$tmp" "$target"
        ;;
    *)
        if [ "$ae" -le "$tol" ]; then
            echo "place_thumbnail: $target: $ae px differ, within tolerance $tol -- keeping the committed render"
            rm -f "$tmp"
        else
            mv "$tmp" "$target"
        fi
        ;;
esac
