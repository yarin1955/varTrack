package config

import (
	"bufio"
	"fmt"
	"log"
	"net"
	"os"
	"strings"
)

// Env holds the shared environment variables consumed by all VarTrack services.
//
// Service addresses follow the Jaeger convention (confignet.AddrConfig):
// every service is configured as a full host:port string so each deployment
// topology can set it independently.
type Env struct {
	AppEnv           string // APP_ENV
	LogLevel         string // LOG_LEVEL
	OrchestratorAddr string // ORCHESTRATOR_ADDR — dial address for the orchestrator gRPC service
	GatewayAddr      string // GATEWAY_ADDR — listen address for this gateway (e.g. ":5657")
	AgentAddr        string // AGENT_ADDR — dial address for the agent gRPC service
	VaultSecret      string // VAULT_SECRET
	ConfigPath       string // CONFIG_PATH — path to the CUE bundle file
	GRPCTlsCa        string // GRPC_TLS_CA — path to CA cert for outbound gRPC
	GRPCTlsCert      string // GRPC_TLS_CERT — path to client cert (mTLS)
	GRPCTlsKey       string // GRPC_TLS_KEY — path to client key (mTLS)
}

func (e *Env) GetOrchestratorAddr() string { return e.OrchestratorAddr }
func (e *Env) GetGatewayAddr() string      { return e.GatewayAddr }
func (e *Env) GetAgentAddr() string        { return e.AgentAddr }

func (e *Env) IsProduction() bool {
	return e.AppEnv == "production"
}

// LoadEnv loads an optional .env file, then reads environment variables.
//
// Resolution order (last wins):
//  1. .env file (if present — not required)
//  2. Real environment variables (always override .env file)
func LoadEnv() (*Env, error) {
	loadDotEnv()

	env := &Env{
		AppEnv:           envOr("APP_ENV", "test"),
		LogLevel:         strings.ToUpper(envOr("LOG_LEVEL", "INFO")),
		OrchestratorAddr: envOr("ORCHESTRATOR_ADDR", "localhost:50051"),
		GatewayAddr:      envOr("GATEWAY_ADDR", ":5657"),
		AgentAddr:        envOr("AGENT_ADDR", "localhost:50052"),
		VaultSecret:      os.Getenv("VAULT_SECRET"),
		ConfigPath:       envOr("CONFIG_PATH", "config.cue"),
		GRPCTlsCa:        os.Getenv("GRPC_TLS_CA"),
		GRPCTlsCert:      os.Getenv("GRPC_TLS_CERT"),
		GRPCTlsKey:       os.Getenv("GRPC_TLS_KEY"),
	}

	env.AppEnv = strings.ToLower(strings.TrimSpace(env.AppEnv))

	if err := env.validate(); err != nil {
		return nil, err
	}
	return env, nil
}

// ── .env file loader ────────────────────────────────────────────────────

func loadDotEnv() {
	candidates := []string{
		os.Getenv("ENV_FILE"),
		".env",
		"../.env",
	}
	for _, path := range candidates {
		if path == "" {
			continue
		}
		if _, err := os.Stat(path); err == nil {
			if err := parseDotEnv(path); err != nil {
				log.Printf("Warning: failed to parse %s: %v", path, err)
			} else {
				log.Printf("Loaded env from %s", path)
			}
			return
		}
	}
}

func parseDotEnv(path string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		value = strings.Trim(value, `"'`)
		if os.Getenv(key) == "" {
			os.Setenv(key, value)
		}
	}
	return scanner.Err()
}

// ── Validation ──────────────────────────────────────────────────────────
//
// validate checks all environment variables at startup, preventing
// "half-started" states. Mirrors:
//
//   - Jaeger server.go NewServer(): net.SplitHostPort on every endpoint
//     at creation time, failing immediately with "invalid host:port".
//   - Bytebase start(): checkDataDir() + checkPort() before constructing
//     the server.
//   - ArgoCD apiclient.go: "ClientCertificateData and
//     ClientCertificateKeyData must always be specified together"
func (e *Env) validate() error {
	// App environment
	switch e.AppEnv {
	case "production", "test":
	default:
		return fmt.Errorf("APP_ENV must be 'production' or 'test', got %q", e.AppEnv)
	}

	// Log level
	switch e.LogLevel {
	case "DEBUG", "INFO", "WARN", "ERROR":
	default:
		return fmt.Errorf("LOG_LEVEL must be DEBUG|INFO|WARN|ERROR, got %q", e.LogLevel)
	}

	// Service addresses — Jaeger NewServer() validates every endpoint
	// with net.SplitHostPort at creation time:
	//   _, httpPort, err := net.SplitHostPort(options.HTTP.NetAddr.Endpoint)
	//   if err != nil {
	//       return nil, fmt.Errorf("invalid HTTP server host:port: %w", err)
	//   }
	addrVars := map[string]string{
		"ORCHESTRATOR_ADDR": e.OrchestratorAddr,
		"GATEWAY_ADDR":      e.GatewayAddr,
		"AGENT_ADDR":        e.AgentAddr,
	}
	for name, addr := range addrVars {
		if addr == "" {
			return fmt.Errorf("%s must be set", name)
		}
		if _, _, err := net.SplitHostPort(addr); err != nil {
			return fmt.Errorf("%s=%q is not a valid host:port address: %w", name, addr, err)
		}
	}

	// Config path — verify file exists at startup. Mirrors Bytebase's
	// checkDataDir() which calls os.Stat before proceeding.
	if _, err := os.Stat(e.ConfigPath); err != nil {
		return fmt.Errorf("CONFIG_PATH=%q: file not accessible: %w", e.ConfigPath, err)
	}

	// Outbound gRPC TLS cert pair — ArgoCD apiclient.go enforces:
	//   "--client-crt and --client-crt-key must always be specified together"
	if err := validateTLSPair("GRPC_TLS_CERT", e.GRPCTlsCert, "GRPC_TLS_KEY", e.GRPCTlsKey); err != nil {
		return err
	}

	// Inbound gateway TLS cert pair — same "both or neither" rule.
	gwCert := os.Getenv("GATEWAY_TLS_CERT")
	gwKey := os.Getenv("GATEWAY_TLS_KEY")
	if err := validateTLSPair("GATEWAY_TLS_CERT", gwCert, "GATEWAY_TLS_KEY", gwKey); err != nil {
		return err
	}

	// CA cert path — if specified, file must exist.
	if e.GRPCTlsCa != "" {
		if _, err := os.Stat(e.GRPCTlsCa); err != nil {
			return fmt.Errorf("GRPC_TLS_CA=%q: file not accessible: %w", e.GRPCTlsCa, err)
		}
	}

	return nil
}

// validateTLSPair ensures that if either cert or key is set, both are set,
// and both files exist on disk. Mirrors ArgoCD's validation:
//
//	"ClientCertificateData and ClientCertificateKeyData must always be specified together"
func validateTLSPair(certName, certPath, keyName, keyPath string) error {
	hasCert := certPath != ""
	hasKey := keyPath != ""

	if hasCert != hasKey {
		return fmt.Errorf("%s and %s must both be set or both be empty", certName, keyName)
	}

	if hasCert {
		if _, err := os.Stat(certPath); err != nil {
			return fmt.Errorf("%s=%q: file not accessible: %w", certName, certPath, err)
		}
	}
	if hasKey {
		if _, err := os.Stat(keyPath); err != nil {
			return fmt.Errorf("%s=%q: file not accessible: %w", keyName, keyPath, err)
		}
	}
	return nil
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
