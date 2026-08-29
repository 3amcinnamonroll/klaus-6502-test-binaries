.PHONY: all build update verify clean

all: build

build:
	python3 tools/artifacts.py build

update:
	python3 tools/artifacts.py update

verify:
	python3 tools/artifacts.py verify

clean:
	python3 tools/artifacts.py clean
