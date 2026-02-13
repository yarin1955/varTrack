package internal

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"fmt"
	"log/slog"
	"math/big"
	"net"
	"net/http"
	"os"
	"time"
)

// TLSConfig holds inbound TLS settings for the HTTP server.
//
// This is modeled after Jaeger's tlscfg.options struct which carries
// Enabled/CAPath/CertPath/KeyPath/MinVersion/MaxVersion/CipherSuites
// as a single config object, and ArgoCD's CreateServerTLSConfig which
// generates self-signed certs when no cert/key files are provided.
type TLSConfig struct {
	CertFile string // GATEWAY_TLS_CERT — path to PEM-encoded certificate
	KeyFile  string // GATEWAY_TLS_KEY  — path to PEM-encoded private key

	// MinVersion and MaxVersion follow ArgoCD's tls util pattern which
	// maps string versions ("1.2", "1.3") to crypto/tls constants and
	// validates MinVersion <= MaxVersion. We use constants directly.
	MinVersion uint16 // default: tls.VersionTLS12

	// SelfSignedIfMissing mirrors ArgoCD's CreateServerTLSConfig():
	// when true and cert/key files don't exist, the server generates
	// a self-signed cert for the session. This is useful for local dev
	// but should never be set in production.
	SelfSignedIfMissing bool
}

// Enabled returns true when TLS should be used. Mirrors ArgoCD's
//
//	func (server *ArgoCDServer) useTLS() bool {
//	    if server.Insecure || server.settings.Certificate == nil {
//	        return false
//	    }
//	    return true
//	}
func (t *TLSConfig) Enabled() bool {
	if t == nil {
		return false
	}
	return (t.CertFile != "" && t.KeyFile != "") || t.SelfSignedIfMissing
}

// Run starts the HTTP server and blocks until ctx is cancelled.
//
// If tlsCfg is non-nil and enabled, the server terminates TLS itself.
// Otherwise it serves plaintext, expecting TLS termination upstream
// (Ingress, ALB, sidecar proxy).
func Run(ctx context.Context, addr string, handler http.Handler, tlsCfg *TLSConfig) {
	// Pre-flight port check — Bytebase's checkPort() pattern.
	if err := checkPort(addr); err != nil {
		slog.Error("port not available", "addr", addr, "error", err)
		os.Exit(1)
	}

	srv := &http.Server{
		Addr:              addr,
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       120 * time.Second,
	}

	useTLS := tlsCfg != nil && tlsCfg.Enabled()

	if useTLS {
		tlsServerConfig, err := buildServerTLSConfig(tlsCfg)
		if err != nil {
			slog.Error("failed to build TLS config", "error", err)
			os.Exit(1)
		}
		srv.TLSConfig = tlsServerConfig
	}

	// Graceful shutdown — ArgoCD's shutdownCtx with 20s timeout.
	go func() {
		<-ctx.Done()
		slog.Info("shutting down server")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			slog.Error("server shutdown error", "error", err)
		}
	}()

	slog.Info("server starting", "addr", addr, "tls", useTLS)

	var err error
	if useTLS {
		// When TLSConfig is set on the server, ListenAndServeTLS with
		// empty strings uses the config's Certificates / GetCertificate.
		// When files are provided, they're loaded into the config.
		err = srv.ListenAndServeTLS(tlsCfg.CertFile, tlsCfg.KeyFile)
	} else {
		err = srv.ListenAndServe()
	}

	// ArgoCD's checkServeErr: only log ErrServerClosed as info.
	if err != nil {
		if err == http.ErrServerClosed {
			slog.Info("server stopped gracefully")
		} else {
			slog.Error("server error", "error", err)
			os.Exit(1)
		}
	}
}

// buildServerTLSConfig constructs a *tls.Config for the HTTP server.
//
// Pattern sources:
//   - ArgoCD's CreateServerTLSConfig: loads cert/key from files, falls back
//     to self-signed when files are missing and the option is set.
//   - ArgoCD's tls util: MinVersion default TLS 1.2, cipher suite parsing.
//   - Jaeger's tlscfg.options: structured config with MinVersion/MaxVersion.
func buildServerTLSConfig(cfg *TLSConfig) (*tls.Config, error) {
	tc := &tls.Config{
		MinVersion: cfg.MinVersion,
	}
	if tc.MinVersion == 0 {
		tc.MinVersion = tls.VersionTLS12 // ArgoCD's DefaultTLSMinVersion
	}

	hasCert := cfg.CertFile != ""
	hasKey := cfg.KeyFile != ""

	switch {
	case hasCert && hasKey:
		// Load from files — matches ArgoCD's CreateServerTLSConfig
		// "Loading TLS configuration from cert=%s and key=%s" path.
		cert, err := tls.LoadX509KeyPair(cfg.CertFile, cfg.KeyFile)
		if err != nil {
			return nil, fmt.Errorf("failed to load TLS keypair (cert=%s, key=%s): %w",
				cfg.CertFile, cfg.KeyFile, err)
		}
		tc.Certificates = []tls.Certificate{cert}
		slog.Info("loaded TLS certificate from files",
			"cert", cfg.CertFile, "key", cfg.KeyFile)

	case cfg.SelfSignedIfMissing:
		// Generate self-signed cert for the session — mirrors ArgoCD's
		// CreateServerTLSConfig which calls GenerateX509KeyPair when
		// cert files are not found, logging:
		//   "Generating self-signed TLS certificate for this session"
		cert, err := generateSelfSignedCert()
		if err != nil {
			return nil, fmt.Errorf("failed to generate self-signed cert: %w", err)
		}
		tc.Certificates = []tls.Certificate{cert}
		slog.Warn("using auto-generated self-signed TLS certificate (not for production)")

	default:
		return nil, fmt.Errorf("TLS enabled but no cert/key provided and self-signed fallback is disabled")
	}

	return tc, nil
}

// generateSelfSignedCert creates a self-signed ECDSA P-256 certificate
// valid for localhost and 127.0.0.1, lasting 24 hours. Inspired by
// ArgoCD's GenerateX509KeyPair in util/tls/tls.go which generates
// self-signed certs with configurable hosts, organization, and validity.
func generateSelfSignedCert() (tls.Certificate, error) {
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return tls.Certificate{}, err
	}

	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		return tls.Certificate{}, err
	}

	template := x509.Certificate{
		SerialNumber: serial,
		Subject:      pkix.Name{Organization: []string{"gateway-service (self-signed)"}},
		NotBefore:    time.Now(),
		NotAfter:     time.Now().Add(24 * time.Hour),
		KeyUsage:     x509.KeyUsageKeyEncipherment | x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		DNSNames:     []string{"localhost"},
		IPAddresses:  []net.IP{net.IPv4(127, 0, 0, 1), net.IPv6loopback},
	}

	certDER, err := x509.CreateCertificate(rand.Reader, &template, &template, &key.PublicKey, key)
	if err != nil {
		return tls.Certificate{}, err
	}

	return tls.Certificate{
		Certificate: [][]byte{certDER},
		PrivateKey:  key,
	}, nil
}

// checkPort verifies the address is available — Bytebase's checkPort pattern.
func checkPort(addr string) error {
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		return err
	}
	return ln.Close()
}
