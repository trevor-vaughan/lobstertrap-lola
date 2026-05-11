SHELL := /bin/bash

.PHONY: help
help: ## - print the help and usage
	@printf "Project Usage:\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		sed 's/^[^:]*://' | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## - build the package
	uv build

.PHONY: test
test: ## - run tests, linting, and type checking
	uv run ruff check src tests
	uv run mypy src
	uv run pytest

.PHONY: install
install: ## - install the local package in editable mode
	uv tool install --force --editable .

.PHONY: uninstall
uninstall: ## - uninstall lola-ai
	uv tool uninstall lola-ai

include mk/mkdocs.mk
include mk/adr.mk
