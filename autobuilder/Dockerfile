FROM node:20-bookworm

# System deps: Python 3, git, and Playwright browser dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    git \
    curl \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /autobuilder

# Copy package files first for better layer caching
COPY package.json package-lock.json ./
RUN npm ci

COPY app/package.json app/package-lock.json ./app/
RUN cd app && npm ci

# Install Playwright chromium
RUN npx playwright install chromium

# Copy the rest of the project
COPY . .

# Build the app once to verify everything works and warm caches
RUN cd app && npm run build

# Init git repo so agents can commit
RUN git init && git add -A && git commit -m "initial scaffold"

# Output directory for built apps
VOLUME /output

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
