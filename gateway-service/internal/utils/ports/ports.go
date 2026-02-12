package ports

import "strconv"

const (
	// GatewayHTTP is the default port for the gateway HTTP server (webhook ingestion, health checks).
	GatewayHTTP = 5657

	// OrchestratorGRPC is the default port for the orchestrator gRPC service.
	OrchestratorGRPC = 50051

	// AgentGRPC is the default port for agent gRPC services.
	AgentGRPC = 50052

	// HealthChecks is the default port for health check extensions.
	HealthChecks = 13133

	// MetricsHTTP is the default port for Prometheus metrics scraping.
	MetricsHTTP = 9090
)

// PortToHostPort converts a port into a ":port" listen address.
func PortToHostPort(port int) string {
	return ":" + strconv.Itoa(port)
}

// HostPort combines a host and port into a "host:port" dial address.
func HostPort(host string, port int) string {
	return host + ":" + strconv.Itoa(port)
}
