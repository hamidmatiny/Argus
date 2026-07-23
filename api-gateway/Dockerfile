# syntax=docker/dockerfile:1
FROM golang:1.22-bookworm AS builder
WORKDIR /src

COPY shared/gen/go/go.mod shared/gen/go/go.sum ./shared/gen/go/
COPY api-gateway/go.mod api-gateway/go.sum ./api-gateway/
WORKDIR /src/api-gateway
RUN go mod download

WORKDIR /src
COPY shared/gen/go ./shared/gen/go
COPY api-gateway ./api-gateway
WORKDIR /src/api-gateway
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/api-gateway ./cmd/api-gateway

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/api-gateway /api-gateway
COPY --from=builder /src/api-gateway/policies /etc/argus/policies
COPY --from=builder /src/api-gateway/openapi /etc/argus/openapi
ENV API_GATEWAY_ADDR=:8099 \
    API_GATEWAY_GRPC_ADDR=:9099 \
    API_GATEWAY_POLICY_DIR=/etc/argus/policies \
    API_GATEWAY_OPENAPI_PATH=/etc/argus/openapi/gateway.swagger.json
EXPOSE 8099 9099
USER nonroot:nonroot
ENTRYPOINT ["/api-gateway"]
