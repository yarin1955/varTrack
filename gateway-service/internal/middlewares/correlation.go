package middlewares

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"
)

type contextKey string

const correlationIDKey contextKey = "correlation-id"

const (
	// HeaderCorrelationID is the canonical header name for request tracing.
	HeaderCorrelationID = "X-Correlation-ID"
)

// CorrelationID ensures every request carries a unique correlation ID.
// If the incoming request already has the header, it is reused; otherwise
// a new random ID is generated. The ID is stored in the request context
// and echoed back in the response header.
func CorrelationID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get(HeaderCorrelationID)
		if id == "" {
			id = generateID()
		}

		// Store in context for downstream handlers and gRPC metadata.
		ctx := context.WithValue(r.Context(), correlationIDKey, id)

		// Echo back to the caller.
		w.Header().Set(HeaderCorrelationID, id)

		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// GetCorrelationID extracts the correlation ID from a context. Returns ""
// if none is present.
func GetCorrelationID(ctx context.Context) string {
	if v, ok := ctx.Value(correlationIDKey).(string); ok {
		return v
	}
	return ""
}

func generateID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
