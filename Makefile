CONFIG ?= private/desktop.toml
APP ?= build/macos/My Sign.app

export MYSIGN_CONFIG := $(value CONFIG)
export MYSIGN_APP := $(value APP)

.PHONY: app test-native check

app:
	./macos/scripts/build-app.sh

test-native:
	./macos/scripts/test.sh

check:
	uv run poe check-all
