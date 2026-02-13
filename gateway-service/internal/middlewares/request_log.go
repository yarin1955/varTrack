package middlewares

import (
	"log/slog"
	"net/http"
	"time"
)

// RequestLog logs completed HTTP requests with method, path, status, and
// duration. Errors (status >= 500) are logged at Error level; client
// errors (4xx) at Warn; successes are silent to avoid noise.
func RequestLog(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		sw := &statusWriter{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(sw, r)

		duration := time.Since(start)
		cid := GetCorrelationID(r.Context())

		switch {
		case sw.status >= 500:
			slog.Error("request",
				"method", r.Method,
				"path", r.URL.Path,
				"status", sw.status,
				"duration", duration,
				"correlation_id", cid,
			)
		case sw.status >= 400:
			slog.Warn("request",
				"method", r.Method,
				"path", r.URL.Path,
				"status", sw.status,
				"duration", duration,
				"correlation_id", cid,
			)
			// 2xx/3xx: silent by default to avoid log noise on health probes.
		}
	})
}

// statusWriter captures the HTTP status code written by downstream handlers.
type statusWriter struct {
	http.ResponseWriter
	status      int
	wroteHeader bool
}

func (w *statusWriter) WriteHeader(code int) {
	if !w.wroteHeader {
		w.status = code
		w.wroteHeader = true
	}
	w.ResponseWriter.WriteHeader(code)
}

func (w *statusWriter) Write(b []byte) (int, error) {
	if !w.wroteHeader {
		w.wroteHeader = true
	}
	return w.ResponseWriter.Write(b)
}
