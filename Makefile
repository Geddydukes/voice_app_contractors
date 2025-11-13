.PHONY: deploy build-images demo

REGISTRY ?= local
TAG ?= latest

build-images:
@echo "Building all service images with registry=$(REGISTRY) tag=$(TAG)"
@REGISTRY=$(REGISTRY) TAG=$(TAG) bash cva/infra/scripts/deploy.sh

deploy: build-images
@echo "Deploy step complete. Push by setting PUSH=true with the deploy script."

# Convenience target to run scripted demo scenarios
demo:
@python -m cva.infra.demo_scenarios $$TENANT
