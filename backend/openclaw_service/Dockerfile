FROM node:24-bookworm-slim

ARG OPENCLAW_VERSION=2026.6.6
RUN npm install --global "openclaw@${OPENCLAW_VERSION}" \
    && useradd --create-home --uid 10001 openclaw

WORKDIR /srv/placeup-openclaw
COPY server.mjs ./server.mjs
COPY workspace ./workspace
RUN chown -R openclaw:openclaw /srv/placeup-openclaw
USER openclaw

ENV PORT=8080 OPENCLAW_WORKSPACE=/srv/placeup-openclaw/workspace
CMD ["node", "server.mjs"]
