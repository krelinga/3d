# Toolchain image for building this repo's OpenSCAD models.
#
# There is no current OpenSCAD stable release with the features this repo
# relies on (--backend=manifold, headless EGL preview rendering), so the base
# is a pinned dev snapshot rather than a stable release. See
# docs/design/initial-design.md, "There is no current stable OpenSCAD".
FROM openscad/openscad:dev.2026-01-12

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-trimesh \
        python3-yaml \
        imagemagick \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
