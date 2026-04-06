# --- Stage 1: build ---
# Build the React app into a static dist/ folder.
FROM node:22-alpine AS builder

WORKDIR /app

# Install dependencies first (separate layer — only re-runs if package.json changes).
# Using npm install rather than npm ci because package-lock.json is generated
# on first local `npm install` and may not yet exist in the repo.
# Once package-lock.json is committed, switch back to `npm ci` for reproducible builds.
COPY package.json package-lock.json* ./
RUN npm install

# Copy source and build.
COPY . .
RUN npm run build


# --- Stage 2: serve ---
# Copy only the built static files into a minimal nginx image.
# nginx:alpine is ~25 MB. No Node.js runtime needed to serve static files.
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Return index.html for any path that doesn't match a file.
# This enables client-side routing (if React Router is added later).
RUN printf 'server {\n\
  listen 80;\n\
  root /usr/share/nginx/html;\n\
  index index.html;\n\
  location / {\n\
    try_files $uri $uri/ /index.html;\n\
  }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
