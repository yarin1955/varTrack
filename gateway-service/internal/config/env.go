package config

import (
	"bufio"
	"fmt"
	"gateway-service/internal/utils/ports"
	"log"
	"os"
	"strconv"
	"strings"
)

// Env holds the shared environment variables consumed by all VarTrack services.
// The canonical variable list lives in the project-root .env.example file.
// Default ports are defined in the ports package (Jaeger-style constants).
type Env struct {
	AppEnv           string // APP_ENV
	LogLevel         string // LOG_LEVEL
	SharedBaseURL    string // SHARED_BASE_URL
	OrchestratorPort int    // ORCHESTRATOR_PORT
	GatewayPort      int    // GATEWAY_PORT
	AgentPort        int    // AGENT_PORT
	VaultSecret      string // VAULT_SECRET
	ConfigPath       string // CONFIG_PATH — path to the CUE bundle file
	GRPCTlsCa        string // GRPC_TLS_CA — path to CA cert
	GRPCTlsCert      string // GRPC_TLS_CERT — path to client cert (mTLS)
	GRPCTlsKey       string // GRPC_TLS_KEY — path to client key (mTLS)
}

func (e *Env) OrchestratorAddr() string {
	return ports.HostPort(e.SharedBaseURL, e.OrchestratorPort)
}

func (e *Env) GatewayAddr() string {
	return ports.PortToHostPort(e.GatewayPort)
}

func (e *Env) AgentAddr() string {
	return ports.HostPort(e.SharedBaseURL, e.AgentPort)
}

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
		SharedBaseURL:    envOr("SHARED_BASE_URL", "localhost"),
		OrchestratorPort: envIntOr("ORCHESTRATOR_PORT", ports.OrchestratorGRPC),
		GatewayPort:      envIntOr("GATEWAY_PORT", ports.GatewayHTTP),
		AgentPort:        envIntOr("AGENT_PORT", ports.AgentGRPC),
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
	if e.IsProduction() && (e.SharedBaseURL == "localhost" || e.SharedBaseURL == "127.0.0.1") {
		return fmt.Errorf("SHARED_BASE_URL cannot be localhost in production")
	}
	for name, port := range map[string]int{
		"ORCHESTRATOR_PORT": e.OrchestratorPort,
		"GATEWAY_PORT":      e.GatewayPort,
		"AGENT_PORT":        e.AgentPort,
	} {
		if port < 1 || port > 65535 {
			return fmt.Errorf("%s out of range: %d", name, port)
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

func envIntOr(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}
