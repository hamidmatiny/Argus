# syntax=docker/dockerfile:1
# Multi-stage Go build → distroless static (nonroot), CGO disabled.

FROM golang:1.22-bookworm AS builder
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/incident-engine ./cmd/incident-engine

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /
COPY --from=builder /out/incident-engine /incident-engine
COPY policies /etc/argus/policies
ENV INCIDENT_POLICY_DIR=/etc/argus/policies
ENV INCIDENT_ENGINE_ADDR=:8098
EXPOSE 8098
USER nonroot:nonroot
ENTRYPOINT ["/incident-engine"]
