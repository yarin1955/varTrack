package handlers

import (
	"encoding/json"
	"log/slog"
	"net/http"
)

// errorResponse is the standard JSON error body returned for all error
// conditions. This replaces http.Error (which returns text/plain) so
// automated webhook clients always receive consistent JSON.
//
// Modeled after:
//   - ArgoCD's grpc-gateway JSONMarshaler (util-grpc/json.go) which
//     ensures all API responses, including errors, are JSON-encoded.
//   - Jaeger's httperr.HandleError (hotrod/pkg/httperr/httperr.go)
//     which centralizes error-to-HTTP-response conversion.
//   - ArgoCD's webhook Handler() which uses http.Error for failures —
//     we improve on this by always returning JSON.
type errorResponse struct {
	Error  string `json:"error"`
	Status int    `json:"status"`
}

// writeErrorJSON writes a JSON error response with the given HTTP status
// code. It replaces every call to http.Error in the webhook handlers so
// that clients always receive application/json responses.
//
// ArgoCD's webhook handler uses http.Error for failures like:
//
//	http.Error(w, "Unknown webhook event", http.StatusBadRequest)
//	http.Error(w, msg, http.StatusBadRequest)
//
// This normalizes them all to JSON.
func writeErrorJSON(w http.ResponseWriter, statusCode int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	if err := json.NewEncoder(w).Encode(errorResponse{
		Error:  message,
		Status: statusCode,
	}); err != nil {
		// If JSON encoding fails, there's nothing left to do — headers
		// are already written. Log it for debugging.
		slog.Error("failed to encode error response", "error", err)
	}
}
