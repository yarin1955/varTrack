package config

import (
	"bufio"
	"fmt"
	"log"
	"os"
	"strings"
)

// Env holds the shared environment variables consumed by all VarTrack services.
// The canonical variable list lives in the project-root .env.example file.
//
// Service addresses follow the Jaeger convention: every service is configured
// as a full address string so each deployment topology (Kubernetes, Docker
// Compose, bare Linux) can set it independently.
//
//	K8s:
//	  ORCHESTRATOR_ADDR=orchestrator.vartrack.svc.cluster.local:50051
//	  AGENT_ADDR=agent.vartrack.svc.cluster.local:50052
//	  GATEWAY_ADDR=:5657
//
//	Compose:
//	  ORCHESTRATOR_ADDR=orchestrator:50051
//	  AGENT_ADDR=agent:50052
//	  GATEWAY_ADDR=:5657
//
//	Bare Linux:
//	  ORCHESTRATOR_ADDR=10.0.1.5:50051
//	  AGENT_ADDR=10.0.1.6:50052
//	  GATEWAY_ADDR=0.0.0.0:5657
type Env struct {
	AppEnv           string // APP_ENV
	LogLevel         string // LOG_LEVEL
	OrchestratorAddr string // ORCHESTRATOR_ADDR — dial address for the orchestrator gRPC service
	GatewayAddr      string // GATEWAY_ADDR — listen address for this gateway (e.g. ":5657", "0.0.0.0:5657")
	AgentAddr        string // AGENT_ADDR — dial address for the agent gRPC service
	VaultSecret      string // VAULT_SECRET
	ConfigPath       string // CONFIG_PATH — path to the CUE bundle file
	GRPCTlsCa        string // GRPC_TLS_CA — path to CA cert
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
//
// The .env file is searched in this order:
//  1. ENV_FILE env var (explicit path)
//  2. .env in the current working directory
//  3. ../.env (project root when running from gateway-service/)
func LoadEnv() (*Env, error) {
	// Load .env file if found — does NOT override existing env vars
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
// Lightweight loader — no external dependencies. Sets env vars only if
// they are not already set (real env always wins).

func loadDotEnv() {
	// Explicit path takes priority
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
	// No .env found — fine, rely on real environment
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

		// Skip blanks and comments
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		key, value, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}

		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)

		// Strip surrounding quotes
		value = strings.Trim(value, `"'`)

		// Only set if not already defined — real env always wins
		if os.Getenv(key) == "" {
			os.Setenv(key, value)
		}
	}

	return scanner.Err()
}

func (e *Env) validate() error {
	switch e.AppEnv {
	case "production", "test":
	default:
		return fmt.Errorf("APP_ENV must be 'production' or 'test', got %q", e.AppEnv)
	}
	switch e.LogLevel {
	case "DEBUG", "INFO", "WARN", "ERROR":
	default:
		return fmt.Errorf("LOG_LEVEL must be DEBUG|INFO|WARN|ERROR, got %q", e.LogLevel)
	}
	for name, addr := range map[string]string{
		"ORCHESTRATOR_ADDR": e.OrchestratorAddr,
		"GATEWAY_ADDR":      e.GatewayAddr,
		"AGENT_ADDR":        e.AgentAddr,
	} {
		if addr == "" {
			return fmt.Errorf("%s must be set", name)
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
