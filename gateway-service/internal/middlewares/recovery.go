package middlewares

import (
	"fmt"
	"log/slog"
	"net/http"
	"runtime/debug"
)

// RecoveryOption configures the recovery middleware.
type RecoveryOption func(*recoveryConfig)

type recoveryConfig struct {
	printStack bool
	logger     *slog.Logger
}

// WithPrintStack controls whether the full goroutine stack trace is included
// in the log entry. Enabled by default.
func WithPrintStack(v bool) RecoveryOption {
	return func(c *recoveryConfig) { c.printStack = v }
}

// WithLogger overrides the default slog logger used for panic reports.
// Inspired by Jaeger's RecoveryHandler(logger, printStack) pattern —
// structured logging lets panic data flow into the same observability
// pipeline as normal request logs.
func WithLogger(l *slog.Logger) RecoveryOption {
	return func(c *recoveryConfig) { c.logger = l }
}

// Recovery returns middleware that catches panics in downstream handlers,
// logs the event with structured fields (method, path, correlation ID,
// and optionally the stack trace), and returns a 500 to the caller.
//
// It uses a responseWriter wrapper to track whether headers were already
// flushed. If headers were committed, we can only log — the client
// connection is likely broken anyway. This is the same guard as Bytebase's
// resp.Committed check in their Echo recovery middleware.
func Recovery(opts ...RecoveryOption) func(http.Handler) http.Handler {
	cfg := &recoveryConfig{
		printStack: true,
		logger:     slog.Default(),
	}
	for _, o := range opts {
		o(cfg)
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			rw := &recoverResponseWriter{ResponseWriter: w}

			defer func() {
				if rec := recover(); rec != nil {
					attrs := []slog.Attr{
						slog.String("method", r.Method),
						slog.String("path", r.URL.Path),
						slog.String("panic", fmt.Sprint(rec)),
					}

					if cid := GetCorrelationID(r.Context()); cid != "" {
						attrs = append(attrs, slog.String("correlation_id", cid))
					}

					if cfg.printStack {
						attrs = append(attrs, slog.String("stack", string(debug.Stack())))
					}

					cfg.logger.LogAttrs(r.Context(), slog.LevelError, "recovered from panic", attrs...)

					// Only write the error response if headers haven't been
					// flushed yet — same guard as Bytebase's resp.Committed
					// check. Writing after commit causes superfluous
					// WriteHeader warnings and possibly broken responses.
					if !rw.committed {
						http.Error(w, "Internal Server Error", http.StatusInternalServerError)
					}
				}
			}()
			next.ServeHTTP(rw, r)
		})
	}
}

// recoverResponseWriter tracks whether WriteHeader has been called.
type recoverResponseWriter struct {
	http.ResponseWriter
	committed bool
}

func (rw *recoverResponseWriter) WriteHeader(code int) {
	rw.committed = true
	rw.ResponseWriter.WriteHeader(code)
}

func (rw *recoverResponseWriter) Write(b []byte) (int, error) {
	rw.committed = true
	return rw.ResponseWriter.Write(b)
}
