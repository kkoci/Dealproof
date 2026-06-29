FROM oven/bun:1-slim

# oven/bun:1-slim includes Node.js — required to run the tc CLI subprocess
WORKDIR /app

COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile

COPY src/ ./src/

EXPOSE 4099
CMD ["bun", "run", "src/index.ts"]
