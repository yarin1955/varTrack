package internal

import (
	"context"
	"log/slog"
	"net"
	"net/http"
	"os"
	"time"
)

// Run starts the HTTP server and blocks until ctx is cancelled.
//
// Signal handling is done in cmd/main.go (which cancels ctx). This
// mirrors ArgoCD's server.Run pattern where the select on stopCh
// triggers the shutdown sequence.
func Run(ctx context.Context, addr string, handler http.Handler) {
	// Pre-flight port check — bind+release before starting. Inspired
	// by Bytebase's checkPort() in backend/bin/server/cmd/root.go
	// which catches port conflicts with a clear error message before
	// the server is partially initialized.
	if err := checkPort(addr); err != nil {
		slog.Error("port not available", "addr", addr, "error", err)
		os.Exit(1)
	}

	srv := &http.Server{
		Addr:    addr,
		Handler: handler,

		// Timeouts prevent slowloris and resource-exhaustion attacks.
		// A production HTTP server with zero timeouts is vulnerable.
		// ArgoCD sets grpc.ConnectionTimeout(300s) on its gRPC server;
		// we use values sized for a webhook gateway with small payloads.
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       120 * time.Second,
	}

	// Graceful shutdown when context is cancelled. The 20-second drain
	// timeout matches ArgoCD's shutdownCtx:
	//   shutdownCtx, cancel := context.WithTimeout(ctx, 20*time.Second)
	go func() {
		<-ctx.Done()
		slog.Info("shutting down server")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			slog.Error("server shutdown error", "error", err)
		}
	}()

	slog.Info("server starting", "addr", addr)
	if err := srv.ListenAndServe(); err != nil {
		// Distinguish graceful shutdown from real errors — same as
		// ArgoCD's checkServeErr which only logs ErrServerClosed as info.
		if err == http.ErrServerClosed {
			slog.Info("server stopped gracefully")
		} else {
			slog.Error("server error", "error", err)
			os.Exit(1)
		}
	}
}

// checkPort verifies the address is available before starting the server.
// Inspired by Bytebase's checkPort in backend/bin/server/cmd/root.go.
func checkPort(addr string) error {
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		return err
	}
	return ln.Close()
}
