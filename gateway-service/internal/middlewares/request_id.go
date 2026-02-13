package middlewares

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"
)

type requestIDKey struct{}

const (
	// HeaderRequestID is the header name for the per-transaction request ID.
	// Unlike X-Correlation-ID (which is preserved across retries and
	// service hops), X-Request-ID is unique to every single HTTP
	// transaction hitting the gateway.
	//
	// This follows ArgoCD's extension header convention (Argocd-*) where
	// every incoming request gets framework-injected headers, and Jaeger's
	// AdminServer logging which attaches unique identifiers per request
	// for debugging gateway-specific issues like rate limiting or TLS
	// handshake failures.
	HeaderRequestID = "X-Request-ID"
)

// RequestID generates a unique request ID for every HTTP transaction and
// stores it in both the response header and request context.
//
// Unlike CorrelationID (which is reused across retries), the request ID
// is always freshly generated — it identifies this specific gateway
// transaction. Modeled after ArgoCD's gRPC logging interceptor
// (util-grpc/logging.go) which attaches per-call metadata, and the
// extension.go ValidateHeaders pattern which reads/injects structured
// headers on every request.
func RequestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := generateRequestID()

		ctx := context.WithValue(r.Context(), requestIDKey{}, id)
		w.Header().Set(HeaderRequestID, id)

		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// GetRequestID extracts the request ID from a context.
func GetRequestID(ctx context.Context) string {
	if v, ok := ctx.Value(requestIDKey{}).(string); ok {
		return v
	}
	return ""
}

// generateRequestID produces a 12-byte (24-char hex) random ID.
// Shorter than the correlation ID (16-byte) to visually distinguish
// the two in logs, while still providing sufficient uniqueness.
func generateRequestID() string {
	b := make([]byte, 12)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
