package handlers

import (
	"net/http"
)

type HealthHandler struct{}

func NewHealthHandler() *HealthHandler {
	return &HealthHandler{}
}

func (h *HealthHandler) Liveness(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

func (h *HealthHandler) Readiness(w http.ResponseWriter, r *http.Request) {
	// Add DB/Cache checks here
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("READY"))
}
