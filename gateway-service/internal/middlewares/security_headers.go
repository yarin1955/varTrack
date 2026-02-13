package middlewares

import (
	"net/http"
	"time"
)

// SecurityHeaders adds baseline HTTP security headers to every response.
//
// Inspired by Bytebase's securityHeadersMiddleware (CSP, X-Frame-Options,
// nosniff, HSTS) and ArgoCD's noCacheHeaders map (Expires, Cache-Control,
// Pragma, X-Accel-Expires). We apply the subset relevant to a webhook
// ingestion API gateway with no browser UI.
func SecurityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Prevent MIME-type sniffing (same as Bytebase).
		w.Header().Set("X-Content-Type-Options", "nosniff")

		// This service is an API — it should never be framed.
		w.Header().Set("X-Frame-Options", "DENY")

		// No-cache headers — mirrors ArgoCD's noCacheHeaders which sets
		// multiple headers for broad proxy/CDN compatibility.
		w.Header().Set("Cache-Control", "no-cache, private, max-age=0")
		w.Header().Set("Expires", time.Unix(0, 0).Format(time.RFC1123))
		w.Header().Set("Pragma", "no-cache")

		next.ServeHTTP(w, r)
	})
}
