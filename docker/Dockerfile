# Overlay image: a stock OmegaClaw-Core image with the omegaclaw-deontic stack
# installed into its baked-in clone. The installer runs at build time, so the
# runtime security posture (drops to nobody, tmpfs, scrubbed env) is untouched.
#
# Build from the bundle root (the directory holding payload/ and installer/):
#   docker build -f docker/Dockerfile -t omegaclaw-deontic:latest .
#
# Enable optional layers at build time:
#   docker build -f docker/Dockerfile -t omegaclaw-deontic:latest \
#     --build-arg FLAGS="--enable-guardrail" .
#
# Run it through the normal launcher, pointing -d at this image:
#   scripts/omegaclaw -d omegaclaw-deontic:latest start -t telegram ...

ARG BASE=singularitynet/omegaclaw:latest
FROM ${BASE}

# The image bakes the clone here (see scripts/omegaclaw: volume + securityPolicyPath).
ARG CLONE=/PeTTa/repos/OmegaClaw-Core
ARG FLAGS=""

# Build steps need write access to the baked-in clone; the entrypoint drops
# privileges again at runtime.
USER root

COPY payload  /opt/omegaclaw-deontic/payload
COPY installer /opt/omegaclaw-deontic/installer
COPY VERSION  /opt/omegaclaw-deontic/VERSION

# --minimal skips tests/ and docs/ to keep the image lean.
RUN python3 /opt/omegaclaw-deontic/installer/install.py "${CLONE}" --minimal ${FLAGS}
