# syntax=docker/dockerfile:1
FROM golang:1.22-bookworm AS builder
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/api-gateway ./cmd/api-gateway

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/api-gateway /api-gateway
ENV API_GATEWAY_ADDR=:8099
EXPOSE 8099
USER nonroot:nonroot
ENTRYPOINT ["/api-gateway"]
