# Build every part in the catalog. See docs/design/initial-design.md.
#
# Both tools resolve through bin/, which runs them inside the pinned toolchain
# image (docs/design/openscad-image.md). They are named explicitly rather than
# relied on via PATH so that `make` behaves identically in the devcontainer and
# in CI, and so shimming python3 cannot shadow an unrelated python3 elsewhere.
OPENSCAD ?= ./bin/openscad
PYTHON   ?= ./bin/python3

JOBS   ?= $(shell nproc 2>/dev/null || echo 4)

OUT    := out
BUILD  := build
THUMBS := thumbnails

# --hardwarnings is not optional: OpenSCAD otherwise warns about non-manifold
# output and still exits 0, so CI would report success on a mesh that fails in
# a slicer. --backend=manifold is dramatically faster on boolean-heavy models
# and is still not the default.
OPENSCAD_FLAGS    ?= --backend=manifold --hardwarnings --check-parameter-ranges=true
THUMB_SIZE        ?= 800,600
THUMB_COLORSCHEME ?= Tomorrow

# How many pixels a re-render may differ from the committed PNG before it
# counts as a real change. Not zero: the same mesh rasterizes one pixel
# differently on a different CPU, so zero would make every machine rewrite the
# other's thumbnails forever. Calibrated to that measured noise and kept far
# below the smallest real geometry change -- docs/design/initial-design.md,
# "Why not a pixel tolerance", has the numbers.
THUMB_TOLERANCE_PX ?= 50
export THUMB_TOLERANCE_PX

# Decides whether a fresh render replaces the committed one.
PLACE_THUMB := tools/place_thumbnail.sh

# $(wildcard) has no ** -- find is the only way to reach nested parts.
PARTS := $(shell find parts -name entry.yaml 2>/dev/null)

# The directories matter as well as the files. Renaming a part with `git mv`
# preserves entry.yaml's mtime, so parts.mk would still look up to date and
# make would reuse rules naming paths that no longer exist. A directory's
# mtime does change when a child is added, removed or renamed, so depending on
# the directories catches exactly the cases the file list cannot.
PART_DIRS := $(shell find parts -type d 2>/dev/null)

.PHONY: all pr check catalog-check index index-check fonts-check thumbnails clean help
.DEFAULT_GOAL := all

$(BUILD)/parts.mk: $(PARTS) $(PART_DIRS) tools/gen_rules.py tools/catalog.py
	@mkdir -p $(BUILD)
	$(PYTHON) tools/gen_rules.py > $@

# Auto-remade by make before the include is resolved, so editing an entry.yaml
# regenerates the rules on the next make with no extra step.
-include $(BUILD)/parts.mk

# These come after the include so ARTIFACTS and THUMBNAILS are already defined.
all: $(ARTIFACTS)

thumbnails: $(THUMBNAILS)

# Run this before opening a PR. Does everything CI does, in CI's order, and
# *regenerates* the committed artifacts rather than only reporting them stale
# -- there is rarely a reason to run the pieces separately, and forgetting one
# is how a PR fails on something mechanical.
#
# Recursive rather than prerequisites because the order matters and would not
# survive -j. Thumbnails are forced: mtimes decide nothing here, so this cannot
# disagree with CI, which forces them for the same reason.
pr:
	@$(MAKE) --no-print-directory catalog-check
	@$(MAKE) --no-print-directory fonts-check
	@$(MAKE) --no-print-directory -j$(JOBS) all
	@$(MAKE) --no-print-directory -B thumbnails
	@$(MAKE) --no-print-directory index
	@echo ""
	@if git diff --quiet -- README.md $(THUMBS)/ 2>/dev/null; then \
	  echo "Ready to push: nothing regenerated, tree unchanged."; \
	else \
	  echo "Ready to push, once you commit these:"; \
	  git diff --name-only -- README.md $(THUMBS)/ | sed 's/^/    /'; \
	fi

catalog-check:
	$(PYTHON) tools/catalog.py --validate

# Regenerates the README index block from the catalog. The generated-artifact
# counterpart to `make thumbnails`: both produce something committed that CI
# then verifies you did not forget.
index:
	$(PYTHON) tools/render_index.py

# Same check `make check` runs, exposed separately so a CI step can fail with
# a name that says what is wrong rather than "check".
index-check:
	$(PYTHON) tools/render_index.py --check

# Verifies every string a part draws actually renders in the font it names.
# Unlike the other checks this one renders, but only a few tiny probes, and
# `make check` already needs the toolchain image to run $(PYTHON) at all -- so
# the dependency is unchanged and only the runtime grows. See
# docs/design/fonts.md.
fonts-check:
	$(PYTHON) tools/check_fonts.py

# Everything CI can check without building. The index check is included
# deliberately: without it `make check` passes on a stale index and the first
# sign of trouble is a failed PR, which is the loop this target exists to close.
check: catalog-check index-check fonts-check

clean:
	rm -rf $(OUT) $(BUILD)

help:
	@echo "make pr         everything to do before opening a PR (start here)"
	@echo ""
	@echo "make            build every part and variant (3mf + stl + metrics)"
	@echo "make check      validate the catalog, README index and fonts"
	@echo "make index      regenerate the README index block"
	@echo "make thumbnails render the committed PNGs for PR review"
	@echo "make clean      remove out/ and build/"
	@echo ""
	@echo "Run with -j\$$(nproc): parts are independent and OpenSCAD is"
	@echo "single-threaded per invocation."
