# --- Stage 1: build ---
FROM golang:1.23-alpine AS builder

WORKDIR /app

# Copy everything first — go mod tidy needs to see the actual imports
# in .go files to resolve which packages are required and generate go.sum.
# Once go.sum is committed to the repo, this can be split into two COPY
# steps for better layer caching (copy go.mod+go.sum, download, copy source).
COPY . .

# go mod tidy downloads all dependencies and writes go.sum.
# Requires network access during build, which Docker allows by default.
RUN go mod tidy

# Build a statically linked binary (no C runtime required).
# -ldflags="-s -w" strips debug symbols to reduce binary size.
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o situationroom-api .


# --- Stage 2: run ---
# Alpine is ~5 MB. ca-certificates is needed for any outbound HTTPS calls.
FROM alpine:3.20

RUN apk add --no-cache ca-certificates

WORKDIR /app
COPY --from=builder /app/situationroom-api .

EXPOSE 8080
CMD ["./situationroom-api"]
