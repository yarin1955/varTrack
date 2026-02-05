package handlers

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"gateway-service/internal/models"
	"io"
	"net/http"
	"strings"
	"time"
)

type WebhookHandler struct {
	bundleService *models.Bundle
	client        pb.OrchestratorClient
}

func NewWebhookHandler(bundleService *models.Bundle, client pb.OrchestratorClient) *WebhookHandler {
	return &WebhookHandler{
		bundleService: bundleService,
		client:        client,
	}
}

func (h *WebhookHandler) Handle(w http.ResponseWriter, r *http.Request) {
	// 1. Get parameters from the URL path
	ctx := r.Context()

	// Get platform name from query parameter or path
	platformName := r.PathValue("platform")
	datasourceName := r.PathValue("datasource")

	if platformName == "" {
		http.Error(w, "platform name is required", http.StatusBadRequest)
		return
	}

	// Get platform instance
	platform, err := h.bundleService.GetPlatform(ctx, platformName)
	if err != nil {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}

	// Get the signature
	signature := platform.GetGitScmSignature()
	secret := platform.GetSecret()

	// 4. Read the body for verification
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read request body", http.StatusInternalServerError)
		return
	}

	if !verifySignature(body, secret, signature) {
		http.Error(w, "Invalid signature", http.StatusUnauthorized)
		return
	}

	// 3. Prepare headers for the gRPC request
	headers := make(map[string]string)
	for k, v := range r.Header {
		if len(v) > 0 {
			headers[k] = v[0]
		}
	}

	// 4. Call the Python Orchestrator service via gRPC
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	resp, err := h.client.ProcessWebhook(ctx, &pb.ProcessWebhookRequest{
		Platform:   platformName,
		Datasource: datasourceName,
		RawPayload: string(body),
		Headers:    headers,
	})

	if err != nil {
		http.Error(w, "Failed to forward to orchestrator", http.StatusInternalServerError)
		return
	}

	// 5. Respond with the task ID from the backend
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	io.WriteString(w, `{"task_id":"`+resp.GetTaskId()+`","message":"`+resp.GetMessage()+`"}`)
}

func verifySignature(payload []byte, signatureHeader string, secret string) bool {
	// 1. The header comes in the format "sha256=..."
	if !strings.HasPrefix(signatureHeader, "sha256=") {
		return false
	}

	// 2. Get the actual hex string (strip the prefix)
	actualSignature := signatureHeader[7:]

	// 3. Compute the HMAC-SHA256 of the body
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	expectedSignature := hex.EncodeToString(mac.Sum(nil))

	// 4. Constant-time comparison to prevent timing attacks
	return hmac.Equal([]byte(actualSignature), []byte(expectedSignature))
}
