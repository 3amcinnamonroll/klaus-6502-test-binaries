.PHONY: build verify clean

build:
	python3 tools/artifacts.py build

verify:
	python3 tools/artifacts.py verify

clean:
	python3 tools/artifacts.py clean
