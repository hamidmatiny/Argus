package argus.gateway

import future.keywords.if
import future.keywords.in

default allow := false

# Public / infra paths are handled before OPA; still allow if evaluated.
allow if {
	input.path in {"/health", "/healthz", "/readyz", "/metrics", "/openapi.json", "/v1/ping"}
}

# Viewer+: read endpoints
allow if {
	input.role in {"viewer", "operator", "admin"}
	input.method == "GET"
	startswith(input.path, "/v1/")
}

# Viewer may also POST read-style telemetry queries
allow if {
	input.role in {"viewer", "operator", "admin"}
	input.method == "POST"
	input.path == "/v1/telemetry/query"
}

# Operator/admin: acknowledge incidents
allow if {
	input.role in {"operator", "admin"}
	input.method == "POST"
	endswith(input.path, "/acknowledge")
	startswith(input.path, "/v1/incidents/")
}

# Operator/admin: resolve incidents
allow if {
	input.role in {"operator", "admin"}
	input.method == "POST"
	endswith(input.path, "/resolve")
	startswith(input.path, "/v1/incidents/")
}

# Operator/admin: trigger retraining
allow if {
	input.role in {"operator", "admin"}
	input.method == "POST"
	input.path == "/v1/retraining:trigger"
}

# Admin: everything under /v1
allow if {
	input.role == "admin"
	startswith(input.path, "/v1/")
}
