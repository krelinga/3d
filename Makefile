# Build every part in the catalog. See docs/design/initial-design.md.
#
# Both tools resolve through bin/, which runs them inside the pinned toolchain
# image (docs/design/openscad-image.md). They are named explicitly rather than
# relied on via PATH so that `make` behaves identically in the devcontainer and
# in CI, and so shimming python3 cannot shadow an unrelated python3 elsewhere.
OPENSCAD ?= ./bin/openscad
PYTHON   ?= ./bin/python3

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

# $(wildcard) has no ** -- find is the only way to reach nested parts.
PARTS := $(shell find parts -name entry.yaml 2>/dev/null)

# The directories matter as well as the files. Renaming a part with `git mv`
# preserves entry.yaml's mtime, so parts.mk would still look up to date and
# make would reuse rules naming paths that no longer exist. A directory's
# mtime does change when a child is added, removed or renamed, so depending on
# the directories catches exactly the cases the file list cannot.
PART_DIRS := $(shell find parts -type d 2>/dev/null)

.PHONY: all check index index-check thumbnails clean help
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

# Regenerates the README index block from the catalog. The generated-artifact
# counterpart to `make thumbnails`: both produce something committed that CI
# then verifies you did not forget.
index:
	$(PYTHON) tools/render_index.py

# Same check `make check` runs, exposed separately so a CI step can fail with
# a name that says what is wrong rather than "check".
index-check:
	$(PYTHON) tools/render_index.py --check

# Everything CI can check without building. The index check is included
# deliberately: without it `make check` passes on a stale index and the first
# sign of trouble is a failed PR, which is the loop this target exists to close.
check:
	$(PYTHON) tools/catalog.py --validate
	$(PYTHON) tools/render_index.py --check

clean:
	rm -rf $(OUT) $(BUILD)

help:
	@echo "make            build every part and variant (3mf + stl + metrics)"
	@echo "make check      validate the catalog and the README index"
	@echo "make index      regenerate the README index block"
	@echo "make thumbnails render the committed PNGs for PR review"
	@echo "make clean      remove out/ and build/"
	@echo ""
	@echo "Run with -j\$$(nproc): parts are independent and OpenSCAD is"
	@echo "single-threaded per invocation."
