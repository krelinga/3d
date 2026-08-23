# Toolchain image for building this repo's OpenSCAD models.
#
# There is no current OpenSCAD stable release with the features this repo
# relies on (--backend=manifold, headless EGL PNG rendering), so the base
# is a pinned dev snapshot rather than a stable release. See
# docs/design/initial-design.md, "There is no current stable OpenSCAD".
FROM openscad/openscad:dev.2026-01-12

# networkx and lxml are not optional: trimesh's 3MF *loader* imports both at
# module scope, so without them `trimesh.load(...3mf)` raises ModuleNotFoundError
# and the whole metrics path fails. python3-trimesh does not pull them in.
# scipy backs several trimesh geometry operations.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-trimesh \
        python3-yaml \
        python3-networkx \
        python3-lxml \
        python3-scipy \
        imagemagick \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
